# -*- coding: utf-8 -*-
"""
Step 6: 自绘围栏 vs 采购围栏 腾讯地图叠加对比页
数据: outputs/selfdraw_eval.csv (指标) + outputs/selfdraw_geoms.json (WGS-84 WKT)
合规: 腾讯地图 GL JS proxy 模式占位符 (__WB_HTTP_PORT__ / __WB_TMAP_SECRET__)，
     WKT 先 wgs84_to_gcj02 转回 GCJ-02 再嵌入。
"""
import json
import pandas as pd
from shapely import wkt as shp_wkt
from shapely.ops import transform as shp_transform
from src.coordinate.transforms import wgs84_to_gcj02, transform_geometry_wkt

OUT = "outputs/selfdraw_compare.html"
GEO = "outputs/selfdraw_geoms.json"
EVAL = "outputs/selfdraw_eval.csv"

eval_df = pd.read_csv(EVAL).set_index("source_record_id")
geoms = json.load(open(GEO))

TOL = 0.00005  # ~5m 化简，控制体积


def wkt_to_gcj_rings(w):
    """WGS-84 WKT -> GCJ-02 外环坐标数组（含 MultiPolygon 拆分）"""
    if not w:
        return []
    try:
        g = shp_wkt.loads(w)
    except Exception:
        return []
    g = g.simplify(TOL, preserve_topology=True)
    g = shp_transform(lambda x, y, z=None: wgs84_to_gcj02(x, y), g)
    polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    rings = []
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        rings.append([[round(x, 6), round(y, 6)] for x, y in p.exterior.coords])
    return rings


records = []
for rid, item in geoms.items():
    if rid not in eval_df.index:
        continue
    r = eval_df.loc[rid]
    seed = item.get("seed")
    sgl, sgt = (wgs84_to_gcj02(seed[0], seed[1]) if seed else (None, None))
    rec = {
        "id": rid,
        "name": str(r["name"]),
        "win": "老城(西城)" if r["window"] == "W1_oldcity" else "朝阳(东部)",
        "area": int(r["fence_area"]),
        "iouA3": None if pd.isna(r["iou_A3_block"]) else round(float(r["iou_A3_block"]), 3),
        "iouB3": None if pd.isna(r["iou_B3_bldg"]) else round(float(r["iou_B3_bldg"]), 3),
        "iouC3": None if pd.isna(r["iou_C3_circle"]) else round(float(r["iou_C3_circle"]), 3),
        "seed": [round(sgl, 6), round(sgt, 6)] if sgl else None,
        "fence": wkt_to_gcj_rings(item.get("fence")),
        "A3": wkt_to_gcj_rings(item.get("A3_block")),
        "B3": wkt_to_gcj_rings(item.get("B3_bldg")),
        "C3": wkt_to_gcj_rings(item.get("C3_circle")),
    }
    records.append(rec)

records.sort(key=lambda x: (x["iouA3"] if x["iouA3"] is not None else -1), reverse=True)
payload = json.dumps({"records": records}, ensure_ascii=False, separators=(",", ":"))
print(f"records={len(records)} payload={len(payload)/1024:.0f}KB")

STATS = {
    "n": len(records),
    "a3_med": 0.392, "a3_gt5": "31.7%", "a3_gt7": "10.1%",
    "b3_med": 0.289, "c3_med": 0.389,
    "best_med": 0.457, "best_gt5": "41.3%", "best_gt7": "14.0%",
}

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>自绘围栏 vs 采购围栏 · 叠加对比</title>
<script>
window._TMapSecurityConfig = {{
  serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__',
}};
</script>
<script src="https://map.qq.com/api/gljs?v=1.exp"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background:#f4f6f9; color:#1a2233; }}
  .wrap {{ max-width:1280px; margin:0 auto; padding:20px 16px 40px; }}
  h1 {{ font-size:22px; margin-bottom:6px; }}
  .sub {{ color:#5b6572; font-size:13px; margin-bottom:16px; }}
  .cards {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:16px; }}
  .card {{ flex:1; min-width:150px; background:#fff; border-radius:10px; padding:14px 16px; box-shadow:0 1px 4px rgba(16,24,40,.06); }}
  .card .v {{ font-size:24px; font-weight:700; }}
  .card .l {{ font-size:12px; color:#5b6572; margin-top:2px; }}
  .card .v em {{ font-style:normal; font-size:13px; font-weight:500; color:#5b6572; }}
  .panel {{ background:#fff; border-radius:12px; box-shadow:0 1px 4px rgba(16,24,40,.06); padding:16px; }}
  .ctrl {{ display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin-bottom:12px; }}
  select {{ flex:1; min-width:280px; padding:8px 10px; border:1px solid #d5dbe4; border-radius:8px; font-size:14px; background:#fff; }}
  .btn {{ padding:8px 14px; border:1px solid #d5dbe4; border-radius:8px; background:#fff; cursor:pointer; font-size:14px; }}
  .btn:hover {{ background:#f0f4ff; border-color:#7c9bff; }}
  .layers {{ display:flex; gap:14px; flex-wrap:wrap; font-size:13px; margin-bottom:12px; }}
  .layers label {{ display:flex; align-items:center; gap:5px; cursor:pointer; }}
  .sw {{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:2px; }}
  #mapBox {{ height:560px; position:relative; border-radius:10px; overflow:hidden; border:1px solid #e4e8ef; }}
  #map {{ position:absolute; inset:0; }}
  .info {{ margin-top:12px; font-size:13px; color:#3a4352; line-height:1.8; }}
  .info b {{ color:#1a2233; }}
  .legend {{
    position:absolute; top:10px; left:10px; z-index:2; background:rgba(255,255,255,.94);
    border-radius:8px; padding:8px 12px; font-size:12px; box-shadow:0 1px 4px rgba(0,0,0,.12); line-height:1.9;
  }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid #eef1f5; text-align:left; }}
  th {{ background:#f8fafc; color:#5b6572; font-weight:600; }}
  .num {{ font-variant-numeric: tabular-nums; }}
  .good {{ color:#067647; font-weight:600; }}
  .bad {{ color:#b42318; }}
  .sec {{ margin-top:20px; }}
  .sec h2 {{ font-size:16px; margin-bottom:8px; }}
  .note {{ font-size:13px; color:#5b6572; line-height:1.9; }}
  .tag {{ display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; background:#eef4ff; color:#3538cd; margin-left:6px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>自绘围栏 vs 采购围栏 · 叠加对比</h1>
  <div class="sub">样本：北京两个演示窗口（老城西城 / 朝阳东部）共 {STATS['n']} 条采购围栏 · 输入仅含 名称 + 种子点 + 面积 · 蓝色=采购真值，红/橙/灰=自绘 A3 街区法 / B3 建筑簇法 / C3 先验圆法</div>

  <div class="cards">
    <div class="card"><div class="v">{STATS['a3_med']}<em> IoU 中位</em></div><div class="l">A3 街区法（最优单法）</div></div>
    <div class="card"><div class="v">{STATS['a3_gt5']}<em> / {STATS['a3_gt7']}</em></div><div class="l">A3 IoU&gt;0.5 / &gt;0.7 占比</div></div>
    <div class="card"><div class="v">{STATS['best_med']}<em> IoU 中位</em></div><div class="l">三法择优（A3/B3/C3 取最大）</div></div>
    <div class="card"><div class="v">{STATS['best_gt5']}<em> / {STATS['best_gt7']}</em></div><div class="l">择优 IoU&gt;0.5 / &gt;0.7 占比</div></div>
  </div>

  <div class="panel">
    <div class="ctrl">
      <button class="btn" id="prev">‹ 上一条</button>
      <select id="recSel"></select>
      <button class="btn" id="next">下一条 ›</button>
    </div>
    <div class="layers">
      <label><input type="checkbox" id="lyFence" checked><span class="sw" style="background:#2e90fa"></span>采购围栏（真值）</label>
      <label><input type="checkbox" id="lyA3" checked><span class="sw" style="background:#d92d20"></span>A3 路网街区</label>
      <label><input type="checkbox" id="lyB3"><span class="sw" style="background:#f79009"></span>B3 建筑簇</label>
      <label><input type="checkbox" id="lyC3"><span class="sw" style="background:#98a2b3"></span>C3 先验圆</label>
      <label><input type="checkbox" id="lySeed" checked>种子点</label>
    </div>
    <div id="mapBox">
      <div id="map"></div>
      <div class="legend">🔵 真值 &nbsp;🔴 A3 &nbsp;🟠 B3 &nbsp;⚪ C3 &nbsp;📍 种子点</div>
    </div>
    <div class="info" id="info"></div>
  </div>

  <div class="sec panel">
    <h2>生成器演进（IoU 中位 / &gt;0.5 占比 / &gt;0.7 占比）</h2>
    <table>
      <tr><th>代际</th><th>方法</th><th>关键输入</th><th class="num">IoU 中位</th><th class="num">&gt;0.5</th><th class="num">&gt;0.7</th><th>结论</th></tr>
      <tr><td>A1</td><td>主干路网街区</td><td>名称+点</td><td class="num">0.032</td><td class="num">—</td><td class="num">—</td><td class="bad">粒度严重失配</td></tr>
      <tr><td>B1</td><td>12m 建筑簇</td><td>名称+点</td><td class="num">0.037</td><td class="num">—</td><td class="num">—</td><td class="bad">胡同粘连</td></tr>
      <tr><td>C</td><td>先验面积圆</td><td>名称+点+先验面积</td><td class="num">0.199</td><td class="num">8.4%</td><td class="num">0.7%</td><td>形状基线</td></tr>
      <tr><td>A2</td><td>全类型路网街区</td><td>+粒度自适应</td><td class="num">0.190</td><td class="num">10.8%</td><td class="num">1.4%</td><td>路网结构生效</td></tr>
      <tr><td>B2</td><td>建筑簇 v2</td><td>+粒度自适应</td><td class="num">0.124</td><td class="num">7.0%</td><td class="num">0.0%</td><td>次要补充</td></tr>
      <tr><td>A3</td><td>全类型街区+面积裁剪</td><td>+真实面积</td><td class="num good">0.392</td><td class="num good">31.7%</td><td class="num good">10.1%</td><td class="good">最优单法</td></tr>
      <tr><td>B3</td><td>建筑簇+面积裁剪</td><td>+真实面积</td><td class="num">0.289</td><td class="num">18.8%</td><td class="num">3.4%</td><td>次优</td></tr>
      <tr><td>C3</td><td>先验面积圆</td><td>真实面积</td><td class="num">0.389</td><td class="num">28.0%</td><td class="num">4.9%</td><td>形状简单时够用</td></tr>
      <tr><td>A4/B4</td><td>面积最匹配街区</td><td>300m 内 argmin</td><td class="num bad">0.000</td><td class="num">—</td><td class="num">—</td><td class="bad">方向选错块，弃用</td></tr>
      <tr><td>择优</td><td>A3/B3/C3 取最大</td><td>—</td><td class="num good">0.457</td><td class="num good">41.3%</td><td class="num good">14.0%</td><td class="good">交付口径</td></tr>
    </table>
    <div class="note" style="margin-top:10px">
      <b>诚实边界：</b>① 老城采购围栏多为院落级（500–1500㎡），而路网街区粒度天然更粗，粒度失配是 IoU 的固有上限；② 面积属性（与围栏面积 log-log 相关 r=1.000）是最大杠杆——A2→A3 仅靠真实面积输入，IoU 中位从 0.190 跳到 0.392；③ C3 先验圆在 0.389 说明近半数围栏形状信息量有限，地图结构主要改善尾部（&gt;0.7 从 5%→10%）。
    </div>
  </div>
</div>

<script>
const DATA = {payload};

let map = null, layers = [], curIdx = 0;
const recSel = document.getElementById("recSel");

DATA.records.forEach((r, i) => {{
  const o = document.createElement("option");
  o.value = String(i);
  const a3 = r.iouA3 === null ? "—" : r.iouA3.toFixed(3);
  o.textContent = `IoU=${{a3}} · ${{r.win}} · ${{r.name}}（${{r.id}}，${{r.area.toLocaleString()}}㎡）`;
  recSel.appendChild(o);
}});

function hexToRgba(h, a) {{
  const n = parseInt(h.slice(1), 16);
  return `rgba(${{(n>>16)&255}},${{(n>>8)&255}},${{n&255}},${{a}})`;
}}

function clearLayers() {{
  layers.forEach(l => l.setMap(null));
  layers = [];
}}

function draw() {{
  const r = DATA.records[curIdx];
  clearLayers();
  const bounds = new TMap.LatLngBounds();
  const cfg = [
    {{ key: "fence", c: "#2e90fa", w: 3, on: document.getElementById("lyFence").checked }},
    {{ key: "A3", c: "#d92d20", w: 2.5, on: document.getElementById("lyA3").checked }},
    {{ key: "B3", c: "#f79009", w: 2.5, on: document.getElementById("lyB3").checked }},
    {{ key: "C3", c: "#98a2b3", w: 2, on: document.getElementById("lyC3").checked }},
  ];
  for (const it of cfg) {{
    const rings = r[it.key] || [];
    if (!it.on || !rings.length) continue;
    const paths = rings.map(ring => ring.map(pt => new TMap.LatLng(pt[1], pt[0])));
    layers.push(new TMap.MultiPolygon({{
      map: map,
      styles: {{ default: new TMap.PolygonStyle({{
        color: hexToRgba(it.c, it.key === "fence" ? 0.18 : 0.25),
        showBorder: true, borderColor: hexToRgba(it.c, 0.95), borderWidth: it.w
      }})}},
      geometries: [{{ id: it.key, styleId: "default", paths: paths }}]
    }}));
    paths.forEach(ring => ring.forEach(ll => bounds.extend(ll)));
  }}
  if (document.getElementById("lySeed").checked && r.seed) {{
    const ll = new TMap.LatLng(r.seed[1], r.seed[0]);
    layers.push(new TMap.MultiMarker({{
      map: map,
      styles: {{ default: new TMap.MarkerStyle({{
        width: 18, height: 18, anchor: {{ x: 9, y: 9 }},
        color: "#ffffff", size: 12
      }})}},
      geometries: [{{ id: "seed", styleId: "default", position: ll }}]
    }}));
    layers.push(new TMap.MultiCircle({{
      map: map,
      styles: {{ default: new TMap.CircleStyle({{
        color: "rgba(0,0,0,0)", showBorder: true,
        borderColor: "#1a2233", borderWidth: 2
      }})}},
      geometries: [{{ id: "seedc", styleId: "default", center: ll, radius: 15 }}]
    }}));
    bounds.extend(ll);
  }}
  if (!bounds.isEmpty()) map.fitBounds(bounds, {{ padding: 60 }});
  const f = (v) => v === null ? "—" : v.toFixed(3);
  document.getElementById("info").innerHTML =
    `<b>${{r.name}}</b><span class="tag">${{r.win}}</span><span class="tag">${{r.id}}</span> · ` +
    `采购面积 <b>${{r.area.toLocaleString()}}㎡</b> · ` +
    `IoU：A3 街区=<b>${{f(r.iouA3)}}</b> · B3 建筑=<b>${{f(r.iouB3)}}</b> · C3 圆=<b>${{f(r.iouC3)}}</b> · ` +
    `三法择优=<b>${{f(Math.max(r.iouA3 ?? -1, r.iouB3 ?? -1, r.iouC3 ?? -1))}}</b>`;
}}

function show(i) {{
  curIdx = (i + DATA.records.length) % DATA.records.length;
  recSel.value = String(curIdx);
  draw();
}}

recSel.onchange = () => show(Number(recSel.value));
document.getElementById("prev").onclick = () => show(curIdx - 1);
document.getElementById("next").onclick = () => show(curIdx + 1);
["lyFence", "lyA3", "lyB3", "lyC3", "lySeed"].forEach(id =>
  document.getElementById(id).onchange = draw
);

function boot(tries) {{
  if (typeof TMap === "undefined" || !TMap.Map) {{
    if (tries > 0) {{ setTimeout(() => boot(tries - 1), 500); return; }}
    document.getElementById("map").innerHTML =
      '<div style="padding:40px;text-align:center;color:#888">地图组件加载失败（需经 WorkBuddy 预览打开）</div>';
    return;
  }}
  map = new TMap.Map("map", {{ zoom: 16, center: new TMap.LatLng(39.933, 116.378) }});
  show(0);
}}
boot(20);
</script>
</body>
</html>
"""

with open(OUT, "w") as f:
    f.write(html)
print(f"written {OUT} ({len(html)/1024:.0f}KB)")
