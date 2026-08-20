"""
Interactive visual case inspector — FULL DATA version.
- All Beijing cases (no head limits)
- GeoJSON separated to geodata.js (simplified, loaded on-demand)
- Case metadata in cases_data.js
- Search + pagination in UI
"""

import json
import math
import os
import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence
from src.coordinate.transforms import wgs84_to_gcj02, transform_geometry_wkt
from src.geometry.validation import GeometryQAEngine

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
EXCEL_PATH = "data/client_a_sites.xlsx"

# --- Data loading ---
records = ExcelIngestionParser.parse_file(EXCEL_PATH)
rec_map = {r.source_record_id: r for r in records}

df_rel = pd.read_csv(os.path.join(OUTPUT_DIR, "entity_relations.csv"))
df_qa = pd.read_csv(os.path.join(OUTPUT_DIR, "qa_issues_report.csv"))

# --- Coordinate normalization + GCJ-02 conversion ---
norm_wkts, norm_coords, qa_scores = {}, {}, {}
for r in records:
    c_eval, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
    qa_res, clean_wkt, _ = GeometryQAEngine.validate_and_extract_features(r.source_record_id, n_wkt)
    gcj_lng, gcj_lat = wgs84_to_gcj02(n_lng, n_lat)
    norm_coords[r.source_record_id] = (gcj_lng, gcj_lat)
    norm_wkts[r.source_record_id] = transform_geometry_wkt(clean_wkt, wgs84_to_gcj02)
    qa_scores[r.source_record_id] = qa_res.score


def _clean_nan(obj):
    """Recursively convert NaN/inf to None for valid JSON."""
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def is_beijing(city_str):
    return city_str and '北京' in str(city_str)


def build_pair(row, color_a="#2563eb", color_b="#10b981"):
    """Build a case dict WITHOUT embedded GeoJSON (looked up from geodata.js at render time)."""
    s_id, o_id = row["subject_record_id"], row["object_record_id"]
    ra, rb = rec_map[s_id], rec_map[o_id]
    return {
        "title": f"{row['subject_name']} vs {row['object_name']}",
        "city": row["subject_city"],
        "relation_type": row["relation_type"],
        "confidence": row["relation_confidence"],
        "explain": row["explain"],
        "cross_encoder_score": float(row.get("cross_encoder_score", 0.0) or 0.0),
        "distance": row["distance_m"],
        "iou": row["iou"],
        "entities": [
            {"id": s_id, "name": ra.name_raw, "address": ra.address_raw,
             "coords": norm_coords[s_id], "qa_score": qa_scores[s_id], "color": color_a},
            {"id": o_id, "name": rb.name_raw, "address": rb.address_raw,
             "coords": norm_coords[o_id], "qa_score": qa_scores[o_id], "color": color_b},
        ],
    }


# =====================================================================
# Build ALL Beijing cases (no head limits)
# =====================================================================
cases = {k: [] for k in [
    "REVIEW_QUEUE", "SIBLING", "COMPONENT_GATE", "MERGE_ERROR",
    "ZERO_POINTS", "TOPOLOGY_HEALED", "RERANK_DOWN", "RERANK_ALIAS",
    "EXTREME_LONG",
]}

bj_rel = df_rel[df_rel["subject_city"].str.contains("北京", na=False)]

# 1. RELATED_ENTITY → 存疑待确认
for _, row in bj_rel[bj_rel["relation_type"] == "RELATED_ENTITY"].sort_values("distance_m").iterrows():
    cases["REVIEW_QUEUE"].append(build_pair(row, "#2563eb", "#10b981"))

# 2. SIBLING → 同名不同店
for _, row in bj_rel[bj_rel["relation_type"].str.startswith("SIBLING")].sort_values(
        "bge_sim", ascending=False).iterrows():
    cases["SIBLING"].append(build_pair(row, "#3b82f6", "#8b5cf6"))

# 3. COMPONENT_GATE → 关键词不匹配
gate = bj_rel[bj_rel["explain"].str.contains("结构化组件冲突", na=False) & (bj_rel["bge_sim"] >= 0.85)]
for _, row in gate.sort_values("bge_sim", ascending=False).iterrows():
    cases["COMPONENT_GATE"].append(build_pair(row, "#ef4444", "#f97316"))

# 4. MERGE_ERROR → 围栏互相覆盖
for _, row in bj_rel[bj_rel["relation_type"] == "POSSIBLE_MERGE_ERROR"].iterrows():
    cases["MERGE_ERROR"].append(build_pair(row, "#ef4444", "#f97316"))

# 5. ZERO_POINTS → 坐标缺失为零 (from df_qa, filter Beijing via rec_map)
bj_qa_ids = {r.source_record_id for r in records if is_beijing(r.city_raw)}
bj_qa = df_qa[df_qa["source_record_id"].isin(bj_qa_ids)]
for _, row in bj_qa[bj_qa["coord_status"] == "SYSTEMATIC_OFFSET"].iterrows():
    s_id = row["source_record_id"]
    r = rec_map[s_id]
    cases["ZERO_POINTS"].append({
        "title": f"坐标缺失为零: {r.name_raw}", "city": r.city_raw,
        "relation_type": "POINT_RECONSTRUCTED", "confidence": 0.98,
        "explain": f"原坐标点为(0,0)，系统依据围栏面质心重构标准点 ({norm_coords[s_id][0]:.6f}, {norm_coords[s_id][1]:.6f})",
        "distance": 0, "iou": 1.0,
        "entities": [{"id": s_id, "name": r.name_raw, "address": r.address_raw,
                      "coords": norm_coords[s_id], "qa_score": qa_scores[s_id], "color": "#0ea5e9"}],
    })

# 6. TOPOLOGY_HEALED → 边界打结已修复
for _, row in bj_qa[bj_qa["qa_issues"].str.contains("TOPOLOGY_AUTO_HEALED", na=False)].iterrows():
    s_id = row["source_record_id"]
    r = rec_map[s_id]
    cases["TOPOLOGY_HEALED"].append({
        "title": f"边界打结已修复: {r.name_raw}", "city": r.city_raw,
        "relation_type": "TOPOLOGY_AUTO_HEALED", "confidence": 0.85,
        "explain": f"原始多边形自相交/环反转，经自动闭合修复，面积: {row['area_m2']:.1f} m²",
        "distance": 0, "iou": 1.0,
        "entities": [{"id": s_id, "name": r.name_raw, "address": r.address_raw,
                      "coords": norm_coords[s_id], "qa_score": qa_scores[s_id], "color": "#eab308"}],
    })

# 7. RERANK_DOWN → 名字差异较大
for _, row in bj_rel[bj_rel["explain"].str.contains("CROSS_ENCODER_UNRELATED", na=False)].sort_values(
        "cross_encoder_score").iterrows():
    cases["RERANK_DOWN"].append(build_pair(row, "#ef4444", "#64748b"))

# 8. RERANK_ALIAS → 可能是同一店
for _, row in bj_rel[bj_rel["explain"].str.contains("CROSS_ENCODER_ALIAS_CONFIRMED", na=False)].sort_values(
        "cross_encoder_score", ascending=False).iterrows():
    cases["RERANK_ALIAS"].append(build_pair(row, "#16a34a", "#22c55e"))

# 9. NARROW_STRIP → 窄条退化围栏 (最大内切圆直径 < 50m, JTS/PostGIS 工业标准)
extreme_ids = set()
for _, row in bj_qa[bj_qa["qa_issues"].str.contains("NARROW_STRIP", na=False)].sort_values(
        "max_width_m", ascending=True).iterrows():
    s_id = row["source_record_id"]
    r = rec_map[s_id]
    extreme_ids.add(s_id)
    other = row["qa_issues"].replace("NARROW_STRIP", "").replace(";", "").replace(" ", "")
    extra = f"；同时伴有: {other}" if other else ""
    cases["EXTREME_LONG"].append({
        "title": f"窄条退化(最宽{row['max_width_m']:.0f}m): {r.name_raw}", "city": r.city_raw,
        "relation_type": "窄条退化", "confidence": row["max_width_m"],
        "explain": f"围栏最宽处仅 {row['max_width_m']:.0f} 米(阈值<50m，按最大内切圆测算)，"
                   f"平均宽度 {row['mean_width_m']:.1f} 米，整条围栏任何位置都不足一个标准小区的宽度；"
                   f"总长约 {row['rect_length_m']:.0f}m，面积 {row['area_m2']:.0f} ㎡。"
                   f"多为沿街/胡同带状描绘过窄所致{extra}",
        "distance": 0, "iou": 1.0,
        "entities": [{"id": s_id, "name": r.name_raw, "address": r.address_raw,
                      "coords": norm_coords[s_id], "qa_score": qa_scores[s_id], "color": "#d946ef"}],
    })


# =====================================================================
# Generate geodata.js (simplified GeoJSON for all entity IDs in cases)
# =====================================================================
all_entity_ids = set()
for cat_cases in cases.values():
    for case_data in cat_cases:
        for ent in case_data["entities"]:
            all_entity_ids.add(ent["id"])

geodata = {}
for eid in all_entity_ids:
    wkt_str = norm_wkts.get(eid)
    if not wkt_str:
        continue
    try:
        geom = wkt.loads(wkt_str)
        # 狭长围栏用更细的容差(约5m)，避免窄多边形被简化退化成线
        tol = 0.00005 if eid in extreme_ids else 0.0005
        simplified = geom.simplify(tol, preserve_topology=True)
        geodata[eid] = mapping(simplified)
    except Exception:
        pass

geodata = _clean_nan(geodata)
geodata_json = json.dumps(geodata, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUTPUT_DIR, "geodata.js"), "w", encoding="utf-8") as f:
    f.write("window.GEOJSON_DATA=" + geodata_json + ";")
del geodata, geodata_json  # free memory
print(f"geodata.js: {len(all_entity_ids)} entities")

# =====================================================================
# Generate cases_data.js
# =====================================================================
counts = {k: len(v) for k, v in cases.items()}
cases_clean = _clean_nan(cases)
cases_json = json.dumps(cases_clean, ensure_ascii=False, separators=(',', ':'))
with open(os.path.join(OUTPUT_DIR, "cases_data.js"), "w", encoding="utf-8") as f:
    f.write("window.CASES_DATA=" + cases_json + ";")
del cases_clean, cases_json
total_cases = sum(counts.values())
print(f"cases_data.js: {total_cases} cases total")
for k, v in counts.items():
    print(f"  {k}: {v}")

# =====================================================================
# Generate HTML (lightweight template, loads data files)
# =====================================================================
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>围栏治理抽检器 (全量数据·北京)</title>
<script type="text/javascript">
  window._TMapSecurityConfig = {{
    serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__',
  }};
</script>
<script src="https://map.qq.com/api/gljs?v=1.exp" async></script>
<style>
:root {{ --bg:#f8fafc; --sidebar:#fff; --text:#0f172a; --sub:#64748b; --primary:#2563eb; --border:#e2e8f0; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; overflow:hidden; }}
header {{ background:#fff; border-bottom:1px solid var(--border); padding:10px 20px; z-index:10; flex-wrap:wrap; gap:6px; }}
header h1 {{ font-size:16px; font-weight:700; margin-bottom:6px; }}
.tab-bar {{ display:flex; gap:4px; flex-wrap:wrap; }}
.tab-btn {{ padding:5px 10px; border-radius:6px; font-size:12px; font-weight:600; border:1px solid var(--border); background:#f1f5f9; color:#475569; cursor:pointer; white-space:nowrap; }}
.tab-btn.active {{ background:var(--primary); color:#fff; border-color:var(--primary); }}
.tab-btn .count {{ font-size:10px; opacity:.7; }}
.main-container {{ flex:1; display:flex; overflow:hidden; }}
.sidebar {{ width:380px; background:var(--sidebar); border-right:1px solid var(--border); display:flex; flex-direction:column; overflow:hidden; }}
.sidebar-top {{ border-bottom:1px solid var(--border); background:#f8fafc; }}
.search-box {{ padding:8px 12px; }}
.search-box input {{ width:100%; padding:7px 10px; border:1px solid var(--border); border-radius:6px; font-size:13px; outline:none; }}
.search-box input:focus {{ border-color:var(--primary); box-shadow:0 0 0 2px rgba(37,99,235,.1); }}
.case-count-bar {{ padding:4px 12px; font-size:11px; color:var(--sub); border-bottom:1px solid var(--border); background:#fff; display:flex; justify-content:space-between; align-items:center; }}
.hint {{ padding:8px 12px; font-size:11px; color:var(--sub); border-bottom:1px solid var(--border); background:#f8fafc; }}
.case-list {{ flex:1; overflow-y:auto; padding:8px; }}
.case-card {{ background:#fff; border:1px solid var(--border); border-radius:8px; padding:10px; margin-bottom:8px; cursor:pointer; transition:border-color .12s; }}
.case-card:hover {{ border-color:var(--primary); }}
.case-card.active {{ border-color:var(--primary); background:#eff6ff; box-shadow:0 0 0 2px rgba(37,99,235,.12); }}
.case-card h3 {{ font-size:12px; font-weight:600; margin-bottom:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.case-card .meta {{ font-size:11px; color:var(--sub); display:flex; gap:6px; margin-bottom:4px; flex-wrap:wrap; }}
.badge-type {{ display:inline-block; font-size:10px; padding:1px 5px; border-radius:3px; font-weight:600; background:#dbeafe; color:#1d4ed8; }}
.load-more-btn {{ display:block; width:100%; padding:8px; border:1px dashed var(--border); border-radius:6px; background:transparent; color:var(--sub); font-size:12px; cursor:pointer; margin-top:4px; }}
.load-more-btn:hover {{ background:#f1f5f9; border-color:var(--primary); color:var(--primary); }}
.map-container {{ flex:1; position:relative; min-height:0; }}
#map {{ width:100%; height:100%; position:absolute; top:0; left:0; }}
.detail-panel {{ position:absolute; bottom:16px; right:16px; width:340px; max-height:40%; overflow-y:auto; background:rgba(255,255,255,.95); backdrop-filter:blur(8px); border:1px solid var(--border); border-radius:10px; padding:14px; box-shadow:0 4px 12px rgba(0,0,0,.1); z-index:1000; font-size:12px; }}
.detail-panel h4 {{ font-size:13px; font-weight:600; margin-bottom:6px; }}
.legend-item {{ display:flex; align-items:center; margin-bottom:4px; font-size:11px; }}
.color-dot {{ width:10px; height:10px; border-radius:3px; margin-right:6px; display:inline-block; flex-shrink:0; }}
</style>
</head>
<body>
<header>
  <h1>围栏治理抽检器 · 全量数据 · 🏛️ 北京城区</h1>
  <div class="tab-bar">
    <button class="tab-btn active" onclick="switchCategory('REVIEW_QUEUE', this)">1.存疑待确认 <span class="count">({counts["REVIEW_QUEUE"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('SIBLING', this)">2.同名不同店 <span class="count">({counts["SIBLING"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('COMPONENT_GATE', this)">3.关键词不匹配 <span class="count">({counts["COMPONENT_GATE"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('MERGE_ERROR', this)">4.围栏互相覆盖 <span class="count">({counts["MERGE_ERROR"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('ZERO_POINTS', this)">5.坐标缺失为零 <span class="count">({counts["ZERO_POINTS"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('TOPOLOGY_HEALED', this)">6.边界打结已修复 <span class="count">({counts["TOPOLOGY_HEALED"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('RERANK_DOWN', this)">7.名字差异较大 <span class="count">({counts["RERANK_DOWN"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('RERANK_ALIAS', this)">8.可能是同一店 <span class="count">({counts["RERANK_ALIAS"]})</span></button>
    <button class="tab-btn" onclick="switchCategory('EXTREME_LONG', this)">9.窄条退化围栏 <span class="count">({counts["EXTREME_LONG"]})</span></button>
  </div>
</header>
<div class="main-container">
  <div class="sidebar">
    <div class="sidebar-top">
      <div class="search-box"><input type="text" id="caseSearch" placeholder="🔍 搜索名称..." oninput="onSearchInput()"></div>
      <div class="case-count-bar">
        <span id="caseCount">共 0 条</span>
        <span style="font-size:10px;color:#94a3b8;">每次显示 50 条，滚动到底部加载更多</span>
      </div>
    </div>
    <div class="case-list" id="caseList"></div>
  </div>
  <div class="map-container">
    <div id="map"></div>
    <div id="mapLoadHint" style="position:absolute;top:60px;left:50%;transform:translateX(-50%);background:rgba(255,255,255,.95);border:1px solid var(--border);border-radius:8px;padding:8px 14px;font-size:12px;color:#b25e09;z-index:998;display:none;box-shadow:0 2px 8px rgba(0,0,0,.1);">⚠️ 腾讯地图 SDK 加载中或失败(需联网)，案例列表不受影响</div>
    <div class="detail-panel" id="detailPanel">
      <h4>判定依据</h4>
      <p id="explainText" style="color:#475569; margin-bottom:8px; line-height:1.4;">请从左侧选择一个案例。</p>
      <div id="legendContainer"></div>
    </div>
  </div>
</div>
<script src="geodata.js"></script>
<script src="cases_data.js"></script>
<script>
const CASES_DATA = window.CASES_DATA || {{}};
const GEOJSON_DATA = window.GEOJSON_DATA || {{}};
let currentCategory = 'REVIEW_QUEUE';
let map = null;
let searchQuery = '';
let visibleCount = 50;
const PAGE_SIZE = 50;
window._layers = [];

function hexToRgba(hex, a) {{
  if (!hex) return 'rgba(46,144,250,' + a + ')';
  hex = hex.replace('#','');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  const r = parseInt(hex.substring(0,2),16)||0;
  const g = parseInt(hex.substring(2,4),16)||0;
  const b = parseInt(hex.substring(4,6),16)||0;
  return 'rgba(' + r + ',' + g + ',' + b + ',' + a + ')';
}}
function clearLayers() {{
  (window._layers||[]).forEach(l => {{ try {{ l.setMap(null); }} catch(e){{}} }});
  window._layers = [];
}}
function initMap() {{
  if (typeof TMap === 'undefined' || !TMap.Map) throw new Error('TMap not ready');
  map = new TMap.Map('map', {{ zoom: 12, center: new TMap.LatLng(39.9042, 116.4074) }});
}}
function bootMap(tries) {{
  try {{
    initMap();
    if (getFilteredCases().length > 0) selectCase(0, true);
  }} catch(e) {{
    if (tries > 0) {{ setTimeout(() => bootMap(tries-1), 500); return; }}
    const hint = document.getElementById('mapLoadHint');
    if (hint) hint.style.display = 'block';
  }}
}}
function getFilteredCases() {{
  let items = CASES_DATA[currentCategory] || [];
  if (searchQuery) {{
    const q = searchQuery.toLowerCase();
    items = items.filter(c =>
      (c.title && c.title.toLowerCase().includes(q)) ||
      (c.explain && c.explain.toLowerCase().includes(q)) ||
      (c.entities && c.entities.some(e => e.name && e.name.toLowerCase().includes(q)))
    );
  }}
  return items;
}}
function switchCategory(cat, btn) {{
  currentCategory = cat;
  searchQuery = '';
  visibleCount = PAGE_SIZE;
  const searchInput = document.getElementById('caseSearch');
  if (searchInput) searchInput.value = '';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderCaseList();
  const items = getFilteredCases();
  if (items.length > 0) selectCase(0);
  else {{
    clearLayers();
    document.getElementById('explainText').innerText = '该类别暂无案例。';
    document.getElementById('legendContainer').innerHTML = '';
  }}
}}
function onSearchInput() {{
  searchQuery = document.getElementById('caseSearch').value.trim();
  visibleCount = PAGE_SIZE;
  renderCaseList();
  const items = getFilteredCases();
  if (items.length > 0) selectCase(0);
  else {{
    clearLayers();
    document.getElementById('explainText').innerText = '无匹配案例。';
    document.getElementById('legendContainer').innerHTML = '';
  }}
}}
function loadMore() {{
  visibleCount += PAGE_SIZE;
  renderCaseList();
}}
function renderCaseList() {{
  const listEl = document.getElementById('caseList');
  const items = getFilteredCases();
  const shown = items.slice(0, visibleCount);
  document.getElementById('caseCount').textContent = '共 ' + items.length + ' 条' + (searchQuery ? ' (搜索结果)' : '');
  if (!items.length) {{
    listEl.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">无匹配案例</div>';
    return;
  }}
  let html = '';
  for (let i = 0; i < shown.length; i++) {{
    const c = shown[i];
    const distStr = (c.distance !== null && c.distance !== undefined && c.distance > 0) ? '<span>距离:' + c.distance.toFixed(0) + 'm</span>' : '';
    const iouStr = (c.iou !== null && c.iou !== undefined && c.iou > 0) ? '<span>IoU:' + c.iou.toFixed(2) + '</span>' : '';
    const ceStr = (c.cross_encoder_score && c.cross_encoder_score > 0) ? '<span>CE:<b>' + c.cross_encoder_score.toFixed(3) + '</b></span>' : '';
    const confStr = (c.confidence !== null && c.confidence !== undefined) ? c.confidence : '—';
    const confLabel = currentCategory === 'EXTREME_LONG' ? '最宽处:<b>' + confStr + '</b>m' : '置信度:<b>' + confStr + '</b>';
    html += '<div class="case-card' + (i === 0 ? ' active' : '') + '" onclick="selectCase(' + i + ')">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">';
    html += '<span class="badge-type">' + (c.relation_type||'') + '</span>';
    html += '<span style="font-size:10px;color:#94a3b8;">' + (c.city||'') + '</span>';
    html += '</div>';
    html += '<h3>' + (c.title||'') + '</h3>';
    html += '<div class="meta"><span>' + confLabel + '</span>' + distStr + iouStr + ceStr + '</div>';
    html += '<div style="font-size:10px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + (c.explain||'') + '</div>';
    html += '</div>';
  }}
  if (items.length > visibleCount) {{
    html += '<button class="load-more-btn" onclick="loadMore()">加载更多 (剩余 ' + (items.length - visibleCount) + ' 条)</button>';
  }}
  listEl.innerHTML = html;
}}
function selectCase(idx, skipMapIfDown) {{
  document.querySelectorAll('.case-card').forEach((el,i) => el.classList.toggle('active', i === idx));
  const items = getFilteredCases();
  const c = items[idx];
  if (!c) return;
  document.getElementById('explainText').innerText = c.explain || '';
  const legendEl = document.getElementById('legendContainer');
  legendEl.innerHTML = '<b>图层要素：</b><br>';
  const mapReady = map && typeof TMap !== 'undefined' && TMap.LatLng;
  if (!mapReady) {{
    if (!skipMapIfDown) {{
      const hint = document.getElementById('mapLoadHint');
      if (hint) hint.style.display = 'block';
    }}
    (c.entities||[]).forEach(ent => {{
      legendEl.innerHTML += '<div class="legend-item"><span class="color-dot" style="background:' + ent.color + '"></span><span><b>' + ent.id + '</b>: ' + (ent.name||'') + ' (QA:' + (ent.qa_score||'—') + ')</span></div>';
    }});
    return;
  }}
  clearLayers();
  try {{
    const bounds = new TMap.LatLngBounds();
    (c.entities||[]).forEach(ent => {{
      const gj = GEOJSON_DATA[ent.id];
      if (gj && (gj.type === 'Polygon' || gj.type === 'MultiPolygon')) {{
        let paths = [];
        if (gj.type === 'Polygon') {{
          paths = gj.coordinates.map(ring => ring.map(pt => new TMap.LatLng(pt[1], pt[0])));
        }} else {{
          gj.coordinates.forEach(poly => poly.forEach(ring => paths.push(ring.map(pt => new TMap.LatLng(pt[1], pt[0])))));
        }}
        const poly = new TMap.MultiPolygon({{
          map: map,
          styles: {{ default: new TMap.PolygonStyle({{
            color: hexToRgba(ent.color, 0.22),
            showBorder: true,
            borderColor: hexToRgba(ent.color, 0.95),
            borderWidth: 2
          }}) }},
          geometries: [{{ id: String(ent.id), styleId: 'default', paths: paths }}]
        }});
        paths.forEach(ring => ring.forEach(ll => bounds.extend(ll)));
        window._layers.push(poly);
      }}
      if (ent.coords && ent.coords[0] !== 0) {{
        const ll = new TMap.LatLng(ent.coords[1], ent.coords[0]);
        const circle = new TMap.MultiCircle({{
          map: map,
          styles: {{ default: new TMap.CircleStyle({{
            color: hexToRgba(ent.color, 0.25),
            showBorder: true,
            borderColor: hexToRgba(ent.color, 0.95),
            borderWidth: 2
          }}) }},
          geometries: [{{ id: String(ent.id)+'_c', center: ll, radius: 30 }}]
        }});
        bounds.extend(ll);
        window._layers.push(circle);
      }}
      legendEl.innerHTML += '<div class="legend-item"><span class="color-dot" style="background:' + ent.color + '"></span><span><b>' + ent.id + '</b>: ' + (ent.name||'') + ' (QA:' + (ent.qa_score||'—') + ')</span></div>';
    }});
    if (!bounds.isEmpty()) {{
      map.fitBounds(bounds, 60);
      if (map.getZoom() > 16) map.setZoom(16);
    }}
  }} catch(e) {{}}
}}
window.onload = () => {{
  renderCaseList();
  bootMap(10);
  if (getFilteredCases().length > 0) {{
    const items = getFilteredCases();
    document.getElementById('explainText').innerText = items[0].explain || '';
    const legendEl = document.getElementById('legendContainer');
    legendEl.innerHTML = '<b>图层要素：</b><br>';
    (items[0].entities||[]).forEach(ent => {{
      legendEl.innerHTML += '<div class="legend-item"><span class="color-dot" style="background:' + ent.color + '"></span><span><b>' + ent.id + '</b>: ' + (ent.name||'') + ' (QA:' + (ent.qa_score||'—') + ')</span></div>';
    }});
  }}
}};
</script>
</body>
</html>"""

with open(os.path.join(OUTPUT_DIR, "interactive_inspector.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("interactive_inspector.html generated successfully.")
