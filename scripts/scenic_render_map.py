"""R16 渲染: 北京 A 级景区地图 (5色等级 + disposition 虚实边框)"""
import warnings; warnings.filterwarnings("ignore")
import json, os, html
import geopandas as gpd

gdf = gpd.read_file("outputs/scenic_spots/beijing_alevel_scenic.geojson")
gdf = gdf[gdf.geometry.notna() & (gdf.geometry.geom_type.isin(["Polygon","MultiPolygon"]))]
GRADE_COLOR = {"5A":"#c0392b","4A":"#e67e22","3A":"#f1c40f","2A":"#27ae60","1A":"#3498db"}
DISP_STYLE = {"OSM_MATCH":(0.45,"solid"),"CONSTRUCTED":(0.30,"dashed")}

feats=[]
for _,r in gdf.iterrows():
    geom=r.geometry
    rings=[]
    polys=[geom] if geom.geom_type=="Polygon" else list(geom.geoms)
    for poly in polys:
        rings.append([[round(c[1],6),round(c[0],6)] for c in poly.exterior.coords])
    feats.append({"rings":rings,
                  "props":{"name":str(r["name"]),"grade":r["grade"],
                           "disp":r["disposition"],
                           "src":str(r.get("source","")),
                           "area_ha": round(r.geometry.area*111320**2/10000)}})

from collections import Counter
gd = Counter(f["props"]["grade"] for f in feats if f["props"]["grade"] in GRADE_COLOR)
legend_rows="".join(
  f"<div><span style='background:{GRADE_COLOR[g]};display:inline-block;width:12px;height:12px;margin-right:5px;border-radius:2px'></span>{g} 级: {n}</div>"
  for g,n in sorted(gd.items(),reverse=True))

html=f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>北京 A 级景区围栏 ({len(feats)} 个)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{width:100vw;height:100vh}}
.legend{{position:absolute;bottom:16px;left:16px;z-index:1000;background:white;padding:12px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.8}}</style>
</head><body><div id="map"></div>
<div class="legend"><b>北京 A 级景区 {len(feats)} / 204</b><br>{legend_rows}
<br><small>实线=OSM面(可信) 虚线=构造圆(待核)</small></div>
<script>
var map=L.map('map',{{center:[40.25,116.35],zoom:10,maxZoom:17}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'©OSM'}}).addTo(map);
var G={json.dumps(GRADE_COLOR)};
var D={json.dumps({k:v[1] for k,v in DISP_STYLE.items()})};
var F={json.dumps(feats, ensure_ascii=False)};
F.forEach(function(f){{
 f.rings.forEach(function(ring){{
   L.polygon(ring,{{color:G[f.props.grade]||'#888',weight:2,
     dashArray:D[f.props.disp]==='dashed'?'6,4':null,
     fillOpacity:D[f.props.disp]==='dashed'?0.18:0.35}})
    .addTo(map).bindPopup('<b>'+f.props.name+'</b><br>'+f.props.grade+' 级 · '+(f.props.area_ha||'')+' 公顷<br>'+f.props.disp+' · '+f.props.src);
 }});
}});
</script></body></html>"""

out=os.path.abspath("outputs/scenic_spots/beijing_alevel_map.html")
open(out,"w",encoding="utf-8").write(html)
print("MAP:", out)
print("等级分布:", dict(gd))
import webbrowser; webbrowser.open("file://"+out)
