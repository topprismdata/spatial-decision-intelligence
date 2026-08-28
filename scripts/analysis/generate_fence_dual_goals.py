"""
生成「围栏双目标诊断报告」——以用户两条主线为目标:
  目标1: 找有问题的围栏  (几何质量 + 坐标质量)
  目标2: 找可能重合的围栏 (多边形几何重叠 IoU>0)
并额外给出交叉优先级: 既是问题围栏、又卷入重叠对的, 优先级最高。
支持两座城市（北京城区、石家庄市）及全量数据的全局无缝切换！

数据来源(均为既有产出, 不重跑大模型):
  outputs/qa_issues_report.csv   —— 逐围栏几何/坐标诊断
  outputs/entity_relations.csv   —— 候选对的空间/语义关系(含 iou / intersection_over_min)
  outputs/dataset_health_report.json / pipeline_summary.json —— 汇总
"""
import pandas as pd
import numpy as np
import json
import os
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(PROJECT_ROOT)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
OUT = "outputs/fence_dual_goals.html"
qa = pd.read_csv("outputs/qa_issues_report.csv")
rel = pd.read_csv("outputs/entity_relations.csv")
try:
    summary = json.load(open("outputs/pipeline_summary.json"))
except Exception:
    summary = {}

TOTAL = int(summary.get("total_source_records", 9039))

# ---------- 中文通俗（人话）映射字典 ----------
ISSUE_ZH = {
    "SELF_INTERSECTION_OR_INVALID_TOPOLOGY": "自相交(边界打结)",
    "TOPOLOGY_AUTO_HEALED": "拓扑已自愈修复",
    "LOW_COMPACTNESS_IRREGULAR": "形状畸形(毛刺触角多)",
    "POSSIBLE_SLIVER_TOO_SMALL": "碎片面积过小(<500㎡)",
    "EXTREME_ASPECT_RATIO": "极端细长(长宽比>10)",
    "NARROW_STRIP": "窄条退化(最宽处<50m)",
    "JAGGED_BOUNDARY": "锯齿边界(周长虚高)",
    "ELONGATED_BLOCK": "长条地块(仅提示)",
    "MIXED_CRS_坐标真坏": "坐标真坏(点面脱节)",
    "POSSIBLE_OVERSIZED": "围栏过大(>1.5km²)",
}

COORD_ZH = {
    "POINT_POLYGON_CRS_CONFLICT": "坐标系偏差(已自动对齐)",
    "SYSTEMATIC_OFFSET": "点缺失(已从围栏重建)",
    "CONFIRMED_WGS84": "标准正常",
    "MIXED_CRS": "坐标真坏(无法自动对齐)",
}

DECISION_ZH = {
    "PASS": "正常通过",
    "WARN": "警告",
    "REVIEW": "需复核",
}

RELATION_ZH = {
    "POSSIBLE_MERGE_ERROR": "空间碰撞告警",
    "WHOLE_TO_PHASE": "整体包含分期",
    "PHASE_TO_WHOLE": "分期反向重叠",
    "SIBLING_SUBAREA": "兄弟子区相交",
    "SIBLING_COURTYARD": "兄弟院落相交",
    "SIBLING_PHASE": "兄弟分期相交",
    "RELATED_ENTITY": "邻近同名关联",
}

PRIORITY_ZH = {
    "HARD": "🚨 严重硬伤",
    "FLAGGED": "⚠️ 标记待查",
    "COLLISION": "💥 空间碰撞",
    "HIGH": "🔴 高重叠",
    "MED": "🟡 中重叠",
    "LOW": "🟢 低重叠",
}

# ---------- 目标1: 有问题的围栏 ----------
def _issues_list(v):
    if pd.isna(v):
        return []
    res = []
    for p in str(v).split(";"):
        p = p.strip()
        if p:
            res.append(ISSUE_ZH.get(p, p))
    return res

qa["_issues"] = qa["qa_issues"].apply(_issues_list)
qa["_coord_issues"] = qa["coord_status"].apply(
    lambda s: [ISSUE_ZH["MIXED_CRS_坐标真坏"]] if str(s) == "MIXED_CRS" else []
)
qa["_all_issues"] = qa.apply(lambda r: r["_issues"] + r["_coord_issues"], axis=1)

# 纳入口径: 几何标记(非空) 或 坐标真坏 或 决策 WARN/REVIEW
def _is_problem(r):
    return (len(r["_issues"]) > 0) or (r["coord_status"] == "MIXED_CRS") or (r["geom_decision"] in ("WARN", "REVIEW"))

prob = qa[qa.apply(_is_problem, axis=1)].copy()

def _priority(r):
    if (r["geom_decision"] in ("WARN", "REVIEW")) or (r["coord_status"] == "MIXED_CRS"):
        return "HARD"
    return "FLAGGED"

prob["_priority"] = prob.apply(_priority, axis=1)
area = pd.to_numeric(prob["area_m2"], errors="coerce")

g1_table = []
for _, r in prob.iterrows():
    g1_table.append({
        "id": r["source_record_id"],
        "name": r["name"],
        "city": str(r["city"]) if not pd.isna(r["city"]) else "未知",
        "district": str(r["district"]) if not pd.isna(r["district"]) else "",
        "type": r["entity_type"],
        "coord": COORD_ZH.get(str(r["coord_status"]), str(r["coord_status"])),
        "decision": DECISION_ZH.get(str(r["geom_decision"]), str(r["geom_decision"])),
        "area_m2": float(area.loc[r.name]) if not pd.isna(area.loc[r.name]) else 0.0,
        "issues": r["_all_issues"],
        "priority": r["_priority"],
        "priority_label": PRIORITY_ZH.get(r["_priority"], r["_priority"]),
    })

# ---------- 目标2: 可能重合的围栏 (仅几何重叠 IoU>0) ----------
iou = pd.to_numeric(rel["iou"], errors="coerce").fillna(0)
inter = pd.to_numeric(rel["intersection_over_min"], errors="coerce").fillna(0)
dist = pd.to_numeric(rel["distance_m"], errors="coerce").fillna(0)
bge = pd.to_numeric(rel["bge_sim"], errors="coerce").fillna(0)

overlaps = rel[iou > 0].copy()
overlaps["_iou"] = iou[iou > 0]
overlaps["_inter"] = inter[iou > 0]
overlaps["_dist"] = dist[iou > 0]
overlaps["_bge"] = bge[iou > 0]

def _ov_priority(row):
    if row["relation_type"] == "POSSIBLE_MERGE_ERROR":
        return "COLLISION"
    if row["_iou"] >= 0.35:
        return "HIGH"
    if row["_iou"] >= 0.05:
        return "MED"
    return "LOW"

overlaps["_priority"] = overlaps.apply(_ov_priority, axis=1)
overlaps = overlaps.sort_values("_iou", ascending=False).reset_index(drop=True)

g2_table = []
for _, r in overlaps.iterrows():
    g2_table.append({
        "subject": r["subject_name"],
        "object": r["object_name"],
        "city": str(r["subject_city"]) if not pd.isna(r["subject_city"]) else "未知",
        "type": RELATION_ZH.get(str(r["relation_type"]), str(r["relation_type"])),
        "raw_type": r["relation_type"],
        "iou": round(float(r["_iou"]), 4),
        "inter_min": round(float(r["_inter"]), 4),
        "dist_m": round(float(r["_dist"]), 1),
        "bge": round(float(r["_bge"]), 3),
        "explain": str(r["explain"]),
        "priority": r["_priority"],
        "priority_label": PRIORITY_ZH.get(r["_priority"], r["_priority"]),
    })

# ---------- 交叉优先级: 既是问题围栏、又卷入重叠对 ----------
prob_ids = set(prob["source_record_id"])
sub_ids = set(rel.loc[iou > 0, "subject_record_id"])
obj_ids = set(rel.loc[iou > 0, "object_record_id"])
overlap_ids = sub_ids | obj_ids
cross_ids = sorted(prob_ids & overlap_ids)
id_to_name = dict(zip(prob["source_record_id"], prob["name"]))
id_to_city = dict(zip(prob["source_record_id"], prob["city"]))

cross_rows = []
seen = set()
for _, r in overlaps.iterrows():
    for fid, oname in ((r["subject_record_id"], r["object_name"]),
                       (r["object_record_id"], r["subject_name"])):
        if fid in cross_ids:
            key = (fid, oname)
            if key in seen:
                continue
            seen.add(key)
            cross_rows.append({
                "id": fid,
                "name": id_to_name.get(fid, fid),
                "city": str(id_to_city.get(fid, "未知")),
                "overlap_with": oname,
                "iou": round(float(r["_iou"]), 4),
                "type": RELATION_ZH.get(str(r["relation_type"]), str(r["relation_type"])),
                "priority": r["_priority"],
                "priority_label": PRIORITY_ZH.get(r["_priority"], r["_priority"]),
            })

# ---------- 为目标2地图解析重合围栏坐标 (GCJ-02) ----------
from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence
from src.coordinate.transforms import wgs84_to_gcj02, transform_geometry_wkt
from src.geometry.validation import GeometryQAEngine
from shapely import wkt as _shp_wkt
from shapely.geometry import mapping as _shp_mapping

_EXCEL = "data/client_a_sites.xlsx"
_all_recs = ExcelIngestionParser.parse_file(_EXCEL)
_rm = {r.source_record_id: r for r in _all_recs}
_need = set(overlaps["subject_record_id"]) | set(overlaps["object_record_id"])
_gc, _gj = {}, {}
for rid in _need:
    if rid not in _rm:
        continue
    rr = _rm[rid]
    _ce, _lng, _lat, _w = CoordinateIntelligence.assess_and_normalize(rr)
    _qr, _cw, _ = GeometryQAEngine.validate_and_extract_features(rid, _w)
    _glng, _glat = wgs84_to_gcj02(_lng, _lat)
    _gc[rid] = [_glng, _glat]
    _gw = transform_geometry_wkt(_cw, wgs84_to_gcj02)
    try:
        _gj[rid] = _shp_mapping(_shp_wkt.loads(_gw)) if _gw else None
    except Exception:
        _gj[rid] = None

def _round_gj(g):
    """递归压缩 GeoJSON 坐标精度到 6 位小数, 控制 HTML 体积"""
    if g is None:
        return None
    if isinstance(g, (list, tuple)):
        if len(g) == 2 and all(isinstance(x, (int, float)) for x in g):
            return [round(float(g[0]), 6), round(float(g[1]), 6)]
        return [_round_gj(x) for x in g]
    if isinstance(g, dict):
        return {k: _round_gj(v) for k, v in g.items()}
    return g

map_pairs = []
for _, r in overlaps.iterrows():
    s_id, o_id = r["subject_record_id"], r["object_record_id"]
    map_pairs.append({
        "s_name": r["subject_name"], "o_name": r["object_name"],
        "city": str(r["subject_city"]) if not pd.isna(r["subject_city"]) else "未知",
        "iou": round(float(r["_iou"]), 4), "dist": round(float(r["_dist"]), 1),
        "type": RELATION_ZH.get(str(r["relation_type"]), str(r["relation_type"])),
        "priority": r["_priority"],
        "s_coord": _round_gj(_gc.get(s_id)), "s_geojson": _round_gj(_gj.get(s_id)),
        "o_coord": _round_gj(_gc.get(o_id)), "o_geojson": _round_gj(_gj.get(o_id)),
    })

# ---------- 按城市预先计算统计快照 ----------
raw_cities = pd.Series([r.city_raw for r in _all_recs])
raw_city_totals = raw_cities.value_counts().to_dict()

city_stats = {}
iou_bins = [(0.0, 0.01), (0.01, 0.05), (0.05, 0.15), (0.15, 0.35), (0.35, 1.01)]
iou_bin_labels = ["0–1%", "1–5%", "5–15%", "15–35%", ">35%"]

for cname in ["全部", "北京城区", "石家庄市"]:
    sub_qa = qa if cname == "全部" else qa[qa["city"] == cname]
    sub_prob = prob if cname == "全部" else prob[prob["city"] == cname]
    sub_ov = overlaps if cname == "全部" else overlaps[overlaps["subject_city"] == cname]
    sub_cross = cross_rows if cname == "全部" else [x for x in cross_rows if x["city"] == cname]
    
    # 统计 issue
    ic = Counter()
    for lst in sub_prob["_all_issues"]:
        for t in lst:
            ic[t] += 1
            
    sub_area = pd.to_numeric(sub_prob["area_m2"], errors="coerce")
    sub_iou = sub_ov["_iou"]
    
    iou_counts = []
    for lo, hi in iou_bins:
        iou_counts.append(int(((sub_iou > lo) & (sub_iou <= hi)).sum()))
        
    c_tot = TOTAL if cname == "全部" else int(raw_city_totals.get(cname, len(sub_qa)))
    
    city_stats[cname] = {
        "total": c_tot,
        "qa_count": len(sub_qa),
        "missing_clean": c_tot - len(sub_qa),
        "g1": {
            "problem_count": len(sub_prob),
            "hard_count": int((sub_prob["_priority"] == "HARD").sum()),
            "flagged_count": int((sub_prob["_priority"] == "FLAGGED").sum()),
            "topology_healed": int(ic.get(ISSUE_ZH["TOPOLOGY_AUTO_HEALED"], 0)),
            "sliver": int((sub_area < 500).sum()),
            "oversized": int((sub_area > 1_500_000).sum()),
            "issue_types": dict(ic.most_common()),
        },
        "g2": {
            "overlap_count": len(sub_ov),
            "collision_count": int((sub_ov["_priority"] == "COLLISION").sum()),
            "high_count": int((sub_iou >= 0.35).sum()),
            "med_count": int(((sub_iou >= 0.05) & (sub_iou < 0.35)).sum()),
            "low_count": int((sub_iou < 0.05).sum()),
            "iou_bins": iou_bin_labels,
            "iou_bin_counts": iou_counts,
        },
        "cross_count": len(sub_cross),
        "center": [39.9042, 116.4074] if cname == "北京城区" else ([38.0428, 114.5149] if cname == "石家庄市" else [39.5, 115.8]),
        "zoom": 12 if cname != "全部" else 9
    }

# ---------- 组装数据给前端 ----------
payload = {
    "city_stats": city_stats,
    "tables": {
        "g1": g1_table,
        "g2": g2_table,
        "cross": cross_rows,
        "map_pairs": map_pairs
    }
}

def _clean_nan(o):
    """递归把 NaN 转 None, 保证 payload 是严格合法 JSON"""
    if isinstance(o, dict):
        return {k: _clean_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean_nan(x) for x in o]
    if isinstance(o, float) and o != o:
        return None
    return o

payload = _clean_nan(payload)

# ---------- HTML 模板 ----------
def fmt_area(a):
    if a >= 1_000_000:
        return f"{a/1e6:.3f} km²"
    if a >= 1000:
        return f"{a/1000:.1f} 千㎡"
    return f"{a:.0f} ㎡"

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>围栏双目标诊断报告 - 城市分级多维看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script type="text/javascript">
window._TMapSecurityConfig = {
  serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__',
};
</script>
<script src="https://map.qq.com/api/gljs?v=1.exp"></script>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1f2329;--muted:#6b7280;--line:#e5e7eb;
--red:#d92d20;--amber:#f79009;--green:#12b76a;--blue:#2e90fa;--purple:#7a5af8;--brand:#101828;}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
background:var(--bg);color:var(--ink);font-size:14px;line-height:1.6;}
header{background:linear-gradient(120deg,#1f2937,#374151);color:#fff;padding:24px 32px;}
header h1{margin:0 0 6px;font-size:22px;font-weight:700;}
header p{margin:0;color:#cbd5e1;font-size:13px;}
.wrap{max-width:1180px;margin:0 auto;padding:20px 20px 60px;}

/* 城市选择器 */
.city-card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 20px;margin-bottom:20px;
display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.03);}
.city-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.city-title{font-weight:700;font-size:14px;color:var(--ink);}
.city-pills{display:flex;gap:8px;flex-wrap:wrap;}
.city-btn{padding:7px 16px;border-radius:20px;border:1px solid var(--line);background:#f9fafb;color:#475569;
font-size:13px;font-weight:600;cursor:pointer;transition:all .18s ease;outline:none;}
.city-btn:hover{background:#f1f5f9;border-color:#cbd5e1;}
.city-btn.active{background:var(--brand);color:#fff;border-color:var(--brand);box-shadow:0 2px 6px rgba(16,24,40,.2);}
.city-badge-info{font-size:12.5px;color:var(--muted);}

.section{background:var(--card);border:1px solid var(--line);border-radius:14px;
margin:22px 0;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04);}
.sec-head{padding:16px 22px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--line);}
.sec-head .tag{font-size:12px;font-weight:700;color:#fff;background:var(--blue);padding:3px 10px;border-radius:20px;}
.sec-head.g1 .tag{background:var(--red);}
.sec-head.g2 .tag{background:var(--green);}
.sec-head h2{margin:0;font-size:17px;}
.sec-head .sub{color:var(--muted);font-size:12.5px;margin-left:auto;}
.cards{display:flex;flex-wrap:wrap;gap:12px;padding:18px 22px 4px;}
.stat{flex:1;min-width:130px;background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:14px 16px;transition:all .2s ease;}
.stat .n{font-size:24px;font-weight:800;line-height:1.1;}
.stat .l{color:var(--muted);font-size:12px;margin-top:4px;}
.stat.red .n{color:var(--red)} .stat.amber .n{color:var(--amber)}
.stat.green .n{color:var(--green)} .stat.blue .n{color:var(--blue)}
.chart-box{padding:10px 22px 20px;max-width:720px;}
.toolbar{padding:10px 22px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;}
.toolbar input,.toolbar select{padding:7px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff;}
.toolbar input{flex:1;min-width:180px;}
table{width:100%;border-collapse:collapse;font-size:12.5px;}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;}
th{background:#f3f4f6;position:sticky;top:0;cursor:pointer;user-select:none;white-space:nowrap;}
th:hover{background:#e9ebef;}
.tbl-wrap{max-height:460px;overflow:auto;border-top:1px solid var(--line);}
.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:600;}
.b-HARD{background:#fde4e1;color:#d92d20;} .b-FLAGGED{background:#fef3e6;color:#b25e09;}
.b-COLLISION{background:#fde4e1;color:#d92d20;} .b-HIGH{background:#fef3e6;color:#b25e09;}
.b-MED{background:#eef2ff;color:#3538cd;} .b-LOW{background:#ecfdf3;color:#067647;}
.note{padding:14px 22px;color:var(--muted);font-size:12.5px;border-top:1px dashed var(--line);}
.pill{display:inline-block;background:#eef2ff;color:#3538cd;border-radius:6px;padding:2px 7px;margin:1px 2px;font-size:11.5px;}
.city-tag{display:inline-block;background:#f1f5f9;color:#475569;border-radius:4px;padding:1px 6px;font-size:11px;font-weight:600;margin-right:4px;}
.cross-row{background:#fff7ed;}
.map-city-btn{padding:4px 10px;border-radius:6px;border:1px solid var(--line);background:#f8fafc;color:#475569;
font-size:11.5px;font-weight:600;cursor:pointer;transition:all .15s ease;}
.map-city-btn:hover{background:#edf2f7;color:var(--ink);}
.map-city-btn.active{background:var(--brand);color:#fff;border-color:var(--brand);}

footer{color:var(--muted);font-size:12px;text-align:center;padding:20px;}
</style></head><body>
<header>
  <h1>围栏双目标诊断报告</h1>
  <p>目标1 · 找有问题的围栏　|　目标2 · 找可能重合(几何重叠)的围栏　|　支持城市级分层下钻</p>
</header>
<div class="wrap">

<!-- 城市选择栏 -->
<div class="city-card">
  <div class="city-left">
    <span class="city-title">📍 切换城市区域：</span>
    <div class="city-pills">
      <button class="city-btn active" onclick="switchCity('全部')">🌐 全部城市 (9,039)</button>
      <button class="city-btn" onclick="switchCity('北京城区')">🏛️ 北京城区 (7,431)</button>
      <button class="city-btn" onclick="switchCity('石家庄市')">🏢 石家庄市 (1,608)</button>
    </div>
  </div>
  <div class="city-badge-info" id="cityDesc">当前查看：全部城市 (9,039 条围栏)</div>
</div>

<!-- 目标1 -->
<div class="section">
  <div class="sec-head g1"><span class="tag">目标 1</span><h2>有问题的围栏</h2>
    <span class="sub" id="g1Sub">几何质量 + 坐标质量 · 纳入口径: 几何标记 / 坐标真坏 / 决策 WARN·REVIEW</span></div>
  <div class="cards">
    <div class="stat red"><div class="n" id="c_g1_prob">0</div><div class="l">有问题围栏(合计)</div></div>
    <div class="stat red"><div class="n" id="c_g1_hard">0</div><div class="l">🚨 严重硬伤(最高优先级)</div></div>
    <div class="stat amber"><div class="n" id="c_g1_flag">0</div><div class="l">⚠️ 标记待核查</div></div>
    <div class="stat blue"><div class="n" id="c_g1_topo">0</div><div class="l">拓扑已自愈</div></div>
    <div class="stat amber"><div class="n" id="c_g1_sliver">0</div><div class="l">碎片(&lt;500㎡)</div></div>
    <div class="stat red"><div class="n" id="c_g1_over">0</div><div class="l">过大超标(&gt;1.5km²)</div></div>
  </div>
  <div class="chart-box"><canvas id="issueChart" height="150"></canvas></div>
  <div class="toolbar">
    <input id="g1search" placeholder="搜索名称 / 城市 / 区 / 问题类型…">
    <select id="g1pri"><option value="">全部优先级</option><option value="HARD">🚨 严重硬伤</option><option value="FLAGGED">⚠️ 标记待查</option></select>
    <span id="g1count" style="color:var(--muted);font-size:12px"></span>
  </div>
  <div class="tbl-wrap"><table id="g1table"><thead><tr>
    <th data-k="city">城市</th><th data-k="district">所属区</th><th data-k="name">围栏名称</th><th data-k="type">实体类型</th>
    <th data-k="coord">坐标状态</th><th data-k="decision">几何判定</th><th data-k="area_m2">围栏面积</th>
    <th data-k="issues">诊断问题清单</th><th data-k="priority">优先级</th></tr></thead><tbody></tbody></table></div>
  <div class="note" id="g1Note">说明: 报告仅纳入"带任何标记"的围栏, 另有完全干净围栏(坐标已确认、无几何问题、分数1.0)被正确排除, 非漏报。
  拓扑自愈指自交/无效拓扑已被 make_valid 自动修复(仍可正常渲染, 但建议复核)。坐标真坏为点面偏移极端、无法自动对齐。</div>
</div>

<!-- 目标2 -->
<div class="section">
  <div class="sec-head g2"><span class="tag">目标 2</span><h2>可能重合的围栏</h2>
    <span class="sub">多边形几何重叠 IoU&gt;0 · STRtree 300m 缓冲保证不漏</span></div>
  <div class="cards">
    <div class="stat green"><div class="n" id="c_g2_ov">0</div><div class="l">几何重叠对(IoU&gt;0)</div></div>
    <div class="stat red"><div class="n" id="c_g2_col">0</div><div class="l">💥 空间碰撞告警</div></div>
    <div class="stat blue"><div class="n" id="c_g2_hi">0</div><div class="l">🔴 高重叠(IoU≥35%)</div></div>
    <div class="stat amber"><div class="n" id="c_g2_med">0</div><div class="l">🟡 中重叠(5–35%)</div></div>
  </div>
  <div class="chart-box"><canvas id="iouChart" height="150"></canvas></div>
  <div class="toolbar">
    <input id="g2search" placeholder="搜索围栏A / 围栏B / 城市…">
    <select id="g2pri"><option value="">全部优先级</option><option value="COLLISION">💥 空间碰撞告警</option><option value="HIGH">🔴 高重叠 (IoU≥35%)</option><option value="MED">🟡 中重叠 (5–35%)</option><option value="LOW">🟢 低重叠 (&lt;5%)</option></select>
    <span id="g2count" style="color:var(--muted);font-size:12px"></span>
  </div>
  <div class="tbl-wrap"><table id="g2table"><thead><tr>
    <th data-k="city">城市</th><th data-k="subject">围栏 A</th><th data-k="object">围栏 B</th><th data-k="type">空间关系</th>
    <th data-k="iou">重叠比(IoU)</th><th data-k="inter_min">重叠率(较小者)</th><th data-k="dist_m">中心距(m)</th>
    <th data-k="bge">语义相似度</th><th data-k="priority">优先级</th></tr></thead><tbody></tbody></table></div>
  <div class="note">说明: "重叠率"=交集面积/较小者面积。空间碰撞告警中, 有若干对是<b>超大异常围栏(见目标1)包住小围栏</b>造成的"假碰撞", 需结合面积判断是否为真实重合。</div>
  <div style="padding:14px 22px 20px;border-top:1px dashed var(--line);">
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
      <b style="font-size:13.5px;">🗺️ 空间叠加图:</b>
      <span style="font-size:12.5px;color:#475569;font-weight:600;">地图城市:</span>
      <select id="mapCitySelect" onchange="onMapCitySelect(this.value)" style="padding:6px 12px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;background:#f8fafc;font-weight:700;color:var(--brand);">
        <option value="全部">🌐 全部城市 (248对)</option>
        <option value="北京城区">🏛️ 北京城区 (231对)</option>
        <option value="石家庄市">🏢 石家庄市 (17对)</option>
      </select>
      <span style="font-size:12.5px;color:#475569;font-weight:600;margin-left:4px;">围栏对:</span>
      <select id="pairSelect" style="flex:1;min-width:240px;max-width:460px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;background:#fff;"></select>
      <span id="pairInfo" style="color:var(--muted);font-size:12px;"></span>
      <span style="font-size:12px;margin-left:auto;"><span class="color-dot" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#2e90fa;vertical-align:middle;"></span> 围栏A　<span class="color-dot" style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#d92d20;vertical-align:middle;"></span> 围栏B</span>
    </div>
    <div style="position:relative;height:480px;border:1px solid var(--line);border-radius:10px;overflow:hidden;">
      <div id="pairMap" style="position:absolute;inset:0;"></div>
      <!-- 地图右上角快捷城市选择按钮 -->
      <div style="position:absolute;top:12px;right:12px;background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.12);border-radius:8px;padding:4px 6px;display:flex;gap:4px;z-index:999;box-shadow:0 2px 8px rgba(0,0,0,.1);">
        <button id="mapBtnAll" class="map-city-btn active" onclick="onMapCitySelect('全部')">全部城市</button>
        <button id="mapBtnBj" class="map-city-btn" onclick="onMapCitySelect('北京城区')">🏛️ 北京 (231)</button>
        <button id="mapBtnSjz" class="map-city-btn" onclick="onMapCitySelect('石家庄市')">🏢 石家庄 (17)</button>
      </div>
      <div id="pairMapHint" style="position:absolute;top:12px;left:12px;background:rgba(255,255,255,.92);border:1px solid var(--line);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--muted);z-index:2;">地图加载中…(腾讯地图)</div>
    </div>
  </div>
</div>

<!-- 交叉优先级 -->
<div class="section">
  <div class="sec-head"><span class="tag" style="background:var(--purple)">交叉</span><h2>最高优先级:既是问题围栏、又卷入重叠对</h2>
    <span class="sub" id="crossSub">__CROSS_N__ 条围栏同时满足两条主线</span></div>
  <div class="tbl-wrap"><table id="crosstable"><thead><tr>
    <th>城市</th><th>围栏</th><th>卷入重叠对象</th><th>IoU</th><th>关系</th><th>优先级</th></tr></thead><tbody></tbody></table></div>
  <div class="note">这些围栏既自身有质量缺陷、又与他人几何重叠, 修复或核查时应优先处理。</div>
</div>

<footer>由既有产出 (qa_issues_report.csv / entity_relations.csv) + 源表坐标直接生成 · 地图: 腾讯地图 GL JS (GCJ-02, 经本地代理转发) · 不重跑大模型</footer>
</div>

<script>
const DATA = __PAYLOAD__;
let currentCity = '全部';
let issueChart = null, iouChart = null;
let pmap = null, pLayers = [];

function fmtArea(a){ if(a>=1e6) return (a/1e6).toFixed(3)+" km²"; if(a>=1000) return (a/1000).toFixed(1)+" 千㎡"; return Math.round(a)+" ㎡"; }
function badge(p, customLabel){
  const labelMap = {
    'HARD': '🚨 严重硬伤',
    'FLAGGED': '⚠️ 标记待查',
    'COLLISION': '💥 空间碰撞',
    'HIGH': '🔴 高重叠',
    'MED': '🟡 中重叠',
    'LOW': '🟢 低重叠'
  };
  const text = customLabel || labelMap[p] || p;
  return '<span class="badge b-'+p+'">'+text+'</span>';
}

function hexToRgba(hex, a) {
  if (!hex) return `rgba(46,144,250,${a})`;
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  const r = parseInt(hex.substring(0, 2), 16) || 0;
  const g = parseInt(hex.substring(2, 4), 16) || 0;
  const b = parseInt(hex.substring(4, 6), 16) || 0;
  return `rgba(${r},${g},${b},${a})`;
}

function geojsonToPaths(gj){
  if(!gj) return [];
  if(gj.type==='Polygon') return gj.coordinates.map(ring=>ring.map(pt=>new TMap.LatLng(pt[1],pt[0])));
  if(gj.type==='MultiPolygon'){
    const paths=[];
    gj.coordinates.forEach(poly=>poly.forEach(ring=>paths.push(ring.map(pt=>new TMap.LatLng(pt[1],pt[0])))));
    return paths;
  }
  return [];
}

// ---- 城市切换核心函数 ----
function switchCity(cityName) {
  currentCity = cityName;
  document.querySelectorAll('.city-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.includes(cityName));
  });

  const st = DATA.city_stats[cityName] || DATA.city_stats['全部'];
  
  // 更新描述与卡片
  document.getElementById('cityDesc').textContent = `当前查看：${cityName} (总计 ${st.total.toLocaleString()} 条围栏)`;
  document.getElementById('c_g1_prob').textContent = st.g1.problem_count;
  document.getElementById('c_g1_hard').textContent = st.g1.hard_count;
  document.getElementById('c_g1_flag').textContent = st.g1.flagged_count;
  document.getElementById('c_g1_topo').textContent = st.g1.topology_healed;
  document.getElementById('c_g1_sliver').textContent = st.g1.sliver;
  document.getElementById('c_g1_over').textContent = st.g1.oversized;

  document.getElementById('c_g2_ov').textContent = st.g2.overlap_count;
  document.getElementById('c_g2_col').textContent = st.g2.collision_count;
  document.getElementById('c_g2_hi').textContent = st.g2.high_count;
  document.getElementById('c_g2_med').textContent = st.g2.med_count;

  document.getElementById('crossSub').textContent = `${st.cross_count} 条围栏同时满足两条主线 (${cityName})`;
  document.getElementById('g1Note').innerHTML = `说明: 报告仅纳入"带任何标记"的围栏, 该城市另有 <b>${st.missing_clean}</b> 条为完全干净围栏(坐标已确认、无几何问题、分数1.0)被正确排除, 非漏报。`;

  // 更新图表
  updateCharts(st);

  // 渲染三张表
  renderG1();
  renderG2();
  renderCross();

  // 更新地图城市选择器状态
  mapSelectedCity = cityName;
  const mSel = document.getElementById("mapCitySelect");
  if (mSel) mSel.value = cityName;
  const btnAll = document.getElementById("mapBtnAll");
  const btnBj = document.getElementById("mapBtnBj");
  const btnSjz = document.getElementById("mapBtnSjz");
  if (btnAll) btnAll.classList.toggle("active", cityName === '全部');
  if (btnBj) btnBj.classList.toggle("active", cityName === '北京城区');
  if (btnSjz) btnSjz.classList.toggle("active", cityName === '石家庄市');

  // 更新地图
  updateMapForCity(st, cityName);
}

function updateCharts(st) {
  const it = st.g1.issue_types;
  const ik = Object.keys(it);
  const iv = ik.map(k => it[k]);

  if (!issueChart) {
    issueChart = new Chart(document.getElementById("issueChart"), {
      type: "bar",
      data: { labels: ik, datasets: [{ label: "围栏数", data: iv, backgroundColor: "#f79009" }] },
      options: {
        plugins: { title: { display: true, text: "目标1 · 围栏质量问题分类统计（人话分类）" }, legend: { display: false } },
        scales: { x: { ticks: { maxRotation: 35, minRotation: 20, font: { size: 11 } } }, y: { beginAtZero: true } }
      }
    });
  } else {
    issueChart.data.labels = ik;
    issueChart.data.datasets[0].data = iv;
    issueChart.update();
  }

  const gb = st.g2.iou_bins;
  const gbc = st.g2.iou_bin_counts;
  if (!iouChart) {
    iouChart = new Chart(document.getElementById("iouChart"), {
      type: "bar",
      data: { labels: gb, datasets: [{ label: "重叠对数量", data: gbc, backgroundColor: "#12b76a" }] },
      options: {
        plugins: { title: { display: true, text: "目标2 · IoU(重叠度)分布" }, legend: { display: false } },
        scales: { x: { title: { display: true, text: "IoU 区间" } }, y: { beginAtZero: true } }
      }
    });
  } else {
    iouChart.data.labels = gb;
    iouChart.data.datasets[0].data = gbc;
    iouChart.update();
  }
}

// ---- 目标1 表 ----
let g1Sort = { k: "priority", dir: 1 };
function renderG1() {
  const q = document.getElementById("g1search").value.trim().toLowerCase();
  const pri = document.getElementById("g1pri").value;
  let rows = DATA.tables.g1.filter(r => {
    if (currentCity !== '全部' && r.city !== currentCity) return false;
    if (pri && r.priority !== pri) return false;
    if (!q) return true;
    const hay = (r.name + " " + r.city + " " + r.district + " " + r.issues.join(" ") + " " + r.type).toLowerCase();
    return hay.includes(q);
  });

  rows.sort((a, b) => {
    let x = a[g1Sort.k], y = b[g1Sort.k];
    if (x < y) return -1 * g1Sort.dir;
    if (x > y) return 1 * g1Sort.dir;
    return 0;
  });

  const tb = document.querySelector("#g1table tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><span class="city-tag">${r.city}</span></td><td>${r.district || ""}</td><td><b>${r.name}</b></td><td>${r.type}</td>
      <td>${r.coord}</td><td>${r.decision}</td><td>${fmtArea(r.area_m2)}</td>
      <td>${r.issues.map(i => '<span class="pill">' + i + '</span>').join("")}</td><td>${badge(r.priority, r.priority_label)}</td>`;
    tb.appendChild(tr);
  }
  document.getElementById("g1count").textContent = "共 " + rows.length + " 条 (" + currentCity + ")";
}
document.getElementById("g1search").oninput = renderG1;
document.getElementById("g1pri").onchange = renderG1;
document.querySelectorAll("#g1table th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if (g1Sort.k === k) g1Sort.dir *= -1;
  else { g1Sort.k = k; g1Sort.dir = 1; }
  renderG1();
});

// ---- 目标2 表 ----
let g2Sort = { k: "iou", dir: -1 };
function renderG2() {
  const q = document.getElementById("g2search").value.trim().toLowerCase();
  const pri = document.getElementById("g2pri").value;
  let rows = DATA.tables.g2.filter(r => {
    if (currentCity !== '全部' && r.city !== currentCity) return false;
    if (pri && r.priority !== pri) return false;
    if (!q) return true;
    return (r.subject + " " + r.object + " " + r.city).toLowerCase().includes(q);
  });

  rows.sort((a, b) => {
    let x = a[g2Sort.k], y = b[g2Sort.k];
    if (x < y) return -1 * g2Sort.dir;
    if (x > y) return 1 * g2Sort.dir;
    return 0;
  });

  const tb = document.querySelector("#g2table tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><span class="city-tag">${r.city}</span></td><td><b>${r.subject}</b></td><td><b>${r.object}</b></td><td>${r.type}</td>
      <td>${r.iou.toFixed(3)}</td><td>${r.inter_min.toFixed(3)}</td><td>${r.dist_m}</td>
      <td>${r.bge.toFixed(3)}</td><td>${badge(r.priority, r.priority_label)}</td>`;
    tb.appendChild(tr);
  }
  document.getElementById("g2count").textContent = "共 " + rows.length + " 对 (" + currentCity + ")";
}
document.getElementById("g2search").oninput = renderG2;
document.getElementById("g2pri").onchange = renderG2;
document.querySelectorAll("#g2table th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if (g2Sort.k === k) g2Sort.dir *= -1;
  else { g2Sort.k = k; g2Sort.dir = 1; }
  renderG2();
});

// ---- 交叉表 ----
function renderCross() {
  const tb = document.querySelector("#crosstable tbody");
  tb.innerHTML = "";
  const rows = DATA.tables.cross.filter(r => currentCity === '全部' || r.city === currentCity);
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.className = "cross-row";
    tr.innerHTML = `<td><span class="city-tag">${r.city}</span></td><td><b>${r.name}</b></td><td>${r.overlap_with}</td><td>${r.iou.toFixed(3)}</td><td>${r.type}</td><td>${badge(r.priority, r.priority_label)}</td>`;
    tb.appendChild(tr);
  }
}

// ---- 目标2 空间叠加图 (腾讯地图, GCJ-02) ----
const pairSel = document.getElementById("pairSelect");
const pairHint = document.getElementById("pairMapHint");
let currentCityPairs = [];
let mapSelectedCity = '全部';

function onMapCitySelect(cname) {
  mapSelectedCity = cname;
  
  // 同步地图控制栏下拉框
  const mSel = document.getElementById("mapCitySelect");
  if (mSel) mSel.value = cname;
  
  // 同步地图右上角浮动按钮状态
  const btnAll = document.getElementById("mapBtnAll");
  const btnBj = document.getElementById("mapBtnBj");
  const btnSjz = document.getElementById("mapBtnSjz");
  if (btnAll) btnAll.classList.toggle("active", cname === '全部');
  if (btnBj) btnBj.classList.toggle("active", cname === '北京城区');
  if (btnSjz) btnSjz.classList.toggle("active", cname === '石家庄市');

  const st = DATA.city_stats[cname] || DATA.city_stats['全部'];
  updateMapForCity(st, cname);
}

function showPair(i) {
  const p = currentCityPairs[i];
  if (!p) return;
  pairSel.value = String(i);
  document.getElementById("pairInfo").textContent = `[${p.city}] IoU=${p.iou.toFixed(3)} · 距离=${p.dist}m · ${p.type}`;
  if (!pmap) pmap = new TMap.Map('pairMap', { zoom: 13, center: new TMap.LatLng(39.9042, 116.4074) });
  pLayers.forEach(l => l.setMap(null));
  pLayers = [];
  const bounds = new TMap.LatLngBounds();
  const items = [
    { gj: p.s_geojson, co: p.s_coord, c: '#2e90fa', n: p.s_name },
    { gj: p.o_geojson, co: p.o_coord, c: '#d92d20', n: p.o_name }
  ];
  for (const it of items) {
    const paths = geojsonToPaths(it.gj);
    if (paths.length) {
      pLayers.push(new TMap.MultiPolygon({
        map: pmap,
        styles: {
          default: new TMap.PolygonStyle({
            color: hexToRgba(it.c, 0.22),
            showBorder: true,
            borderColor: hexToRgba(it.c, 0.95),
            borderWidth: 2
          })
        },
        geometries: [{ id: it.n, styleId: 'default', paths: paths }]
      }));
      paths.forEach(ring => ring.forEach(ll => bounds.extend(ll)));
    } else if (it.co && it.co[0] !== 0) {
      const ll = new TMap.LatLng(it.co[1], it.co[0]);
      pLayers.push(new TMap.MultiCircle({
        map: pmap,
        styles: {
          default: new TMap.CircleStyle({
            color: hexToRgba(it.c, 0.25),
            showBorder: true,
            borderColor: hexToRgba(it.c, 0.95),
            borderWidth: 2
          })
        },
        geometries: [{ id: it.n + "_c", center: ll, radius: 30 }]
      }));
      bounds.extend(ll);
    }
  }
  if (!bounds.isEmpty()) pmap.fitBounds(bounds, { padding: 60 });
  if (pairHint) pairHint.style.display = 'none';
}

function updateMapForCity(st, targetCity) {
  const cityFilter = targetCity || mapSelectedCity || currentCity;
  currentCityPairs = DATA.tables.map_pairs.filter(p => cityFilter === '全部' || p.city === cityFilter);
  pairSel.innerHTML = "";
  if (!currentCityPairs.length) {
    pairSel.innerHTML = "<option>该城市暂无几何重叠对</option>";
    if (pmap) {
      pmap.setCenter(new TMap.LatLng(st.center[0], st.center[1]));
      pmap.setZoom(st.zoom);
    }
    pLayers.forEach(l => l.setMap(null));
    pLayers = [];
    document.getElementById("pairInfo").textContent = "";
    return;
  }

  currentCityPairs.forEach((p, i) => {
    const o = document.createElement('option');
    o.value = String(i);
    o.textContent = `[${p.city}] ${p.s_name} ↔ ${p.o_name} (IoU=${p.iou.toFixed(3)})`;
    pairSel.appendChild(o);
  });
  pairSel.onchange = () => showPair(Number(pairSel.value));
  showPair(0);
}

function bootPairMap(tries) {
  if (typeof TMap === 'undefined' || !TMap.Map) {
    if (tries > 0) { setTimeout(() => bootPairMap(tries - 1), 500); return; }
    if (pairHint) pairHint.textContent = '腾讯地图 SDK 加载失败(需联网), 表格与图表不受影响';
    return;
  }
  switchCity('全部');
}

window.onload = () => {
  bootPairMap(10);
};
</script>
</body></html>"""

html = (html
    .replace("__CROSS_N__", str(city_stats["全部"]["cross_count"]))
    .replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print("已成功生成城市选择版:", OUT)
