"""R15 最终地图: GB50137 分类 + 户数/房价/医院等级 popup + OSM/Amap 双底图"""
import warnings; warnings.filterwarnings("ignore")
import json, html, os
import geopandas as gpd
from src.classification.gb50137 import GB_CLASSES

EN2CODE = {v.name_en: k for k, v in GB_CLASSES.items()}
gdf = gpd.read_file("outputs/huilongguan_demo/huilongguan_landuse_gb50137_enriched.geojson")
gdf["_area"] = gdf.geometry.area
gdf = gdf.sort_values("_area", ascending=False)

polys_js = ""
for _, r in gdf.iterrows():
    cls = GB_CLASSES.get(EN2CODE.get(r["Class"], "U"), GB_CLASSES["U"])
    geom = r.geometry
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    name = html.escape(str(r["Name"] or r["osm_fclass"]))
    rows = [f"<b>[{cls.code}] {cls.name_cn}</b>", name]
    if r.get("households") is not None and str(r["households"]) != "nan":
        rows.append(f"户数: {int(float(r['households'])):,}")
    elif r.get("households_est") is not None and str(r["households_est"]) != "nan" and str(r["Name"] or ""):
        rows.append(f"户数(估): {int(float(r['households_est'])):,} *")
    grade = getattr(r, "grade", "") or (r["grade"] if "grade" in gdf.columns else "")
    if grade and str(grade) != "nan":
        note = r["scale_note"] if "scale_note" in gdf.columns else ""
        rows.append(f"等级: {grade} {'' if note=='nan' else note}")
    if r.get("price") is not None and str(r["price"]) != "nan":
        rows.append(f"挂牌均价: {int(float(r['price'])):,} 元/m²")
    if "built" in gdf.columns and r.get("built") is not None and str(r["built"]) != "nan":
        rows.append(f"建成: {int(float(r['built']))}")
    popup = "<br>".join(rows).replace("'", "\\'")
    for poly in polys:
        latlngs = json.dumps([[c[1], c[0]] for c in poly.exterior.coords])
        polys_js += (
            f"L.polygon({latlngs},{{color:'{cls.color}',weight:1,fillOpacity:0.55}})"
            f".addTo(map).bindPopup('{popup}');\n"
        )

from collections import Counter
counts = Counter(EN2CODE.get(c, "U") for c in gdf["Class"])
legend_rows = "".join(
    f"<div><span style='background:{GB_CLASSES[c].color};display:inline-block;width:12px;"
    f"height:12px;margin-right:5px;border-radius:2px'></span>"
    f"{GB_CLASSES[c].code} {GB_CLASSES[c].name_cn}: {n}</div>"
    for c, n in sorted(counts.items()))

html_content = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>回龙观 · 城市建设用地分类与小区画像</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{width:100vw;height:100vh}}
.legend{{position:absolute;bottom:16px;left:16px;z-index:1000;background:white;padding:12px 14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.8;max-height:55vh;overflow:auto}}
.hdr{{position:absolute;top:16px;left:16px;z-index:1000;background:white;padding:10px 16px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.2);font-size:15px;font-weight:bold}}
.basemap{{position:absolute;top:64px;left:16px;z-index:1000;background:white;padding:8px 12px;
border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.18);font-size:13px}}</style></head><body>
<div id="map"></div>
<div class="hdr">回龙观 · 城市建设用地 + 小区画像 <small style="color:#888;font-weight:normal">({len(gdf)} 地块)</small></div>
<div class="basemap">
<label><input type="radio" name="bm" checked onclick="useOSM()">OSM 底图</label>
<label><input type="radio" name="bm" onclick="useAmap()">高德底图<small style="color:#c00">(GCJ02 偏移~500m)</small></label>
</div>
<div class="legend"><b>R 类小区 {int((gdf.Class == 'RESIDENTIAL').sum())} 个</b><br>{legend_rows}
<br><small style="color:#666">户数* 为面积回归估算(0.0139户/m²)<br>房价 94/185 命中 · 高德 biz_ext<br>数据 Geofabrik OSM · R15 管线</small></div>
<script>
var map=L.map('map',{{center:[40.074,116.34],zoom:14,maxZoom:18}});
var osm=L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'©OSM'}}).addTo(map);
var amap=null;
function useOSM(){{if(amap&&map.hasLayer(amap))map.removeLayer(amap);if(!map.hasLayer(osm))osm.addTo(map);}}
function useAmap(){{if(!amap)amap=L.tileLayer('https://webrd0{{s}}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={{x}}&y={{y}}&z={{z}}',{{subdomains:['1','2','3','4'],attribution:'©Amap'}});
if(map.hasLayer(osm))map.removeLayer(osm);amap.addTo(map);}}
{polys_js}
</script></body></html>"""

out = os.path.abspath("outputs/huilongguan_demo/huilongguan_final.html")
open(out, "w", encoding="utf-8").write(html_content)
print("FINAL MAP:", out)
import webbrowser
webbrowser.open("file://" + out)
