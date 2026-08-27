"""R16 Campus Sample 01 地图输出"""
import warnings; warnings.filterwarnings("ignore")
import json, os, html as _html
from collections import Counter

data = json.load(open("outputs/campus_sample_01/campus_data.json"))
results = data["poi_membership_results"]
# 从原始数据补回 lng,lat
all_pois = {p["name"]:p for p in data["pois_campus_internal"]+data["pois_external_negative"]}
for r in results:
    orig = all_pois.get(r["name"],{})
    r["lat"]=orig.get("lat");r["lng"]=orig.get("lng")

mc = Counter(r["membership"] for r in results)
ok_count = sum(1 for r in results if r["match"]=="✓")
warn_count = sum(1 for r in results if r["match"]=="⚠")
bad_count = sum(1 for r in results if r["match"]=="✗")

markers = ""
MC = {"IN_CAMPUS":"#3498db","OUT_OF_CAMPUS":"#e74c3c","AMBIGUOUS":"#f39c12"}
for r in results:
    color = MC.get(r["membership"], "#888")
    n = _html.escape(str(r["name"]))
    m = r["membership"]
    t = _html.escape(str(r.get("type","")))
    reason = _html.escape(str(r.get("reason","")))
    popup = f"<b>{n}</b><br>{m} · {t}<br>{reason}"
    markers += (f"L.circleMarker([{r['lat']},{r['lng']}],"
                f"{{radius:8,color:'{color}',fillColor:'{color}',fillOpacity:0.85}})"
                f".addTo(map).bindPopup('{popup}');\n")

poly_js = ("L.polygon([[39.9093,116.7329],[39.9093,116.748],[39.9016,116.748],[39.9016,116.7329]],"
           "{color:'#2ecc71',weight:3,fillOpacity:0.08})"
           ".addTo(map).bindPopup('<b>人大通州校区</b><br>官方1652亩');\n")

html_out = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Campus Sample 01: 人大通州校区</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{width:100vw;height:100vh}}
.lg{{position:absolute;bottom:16px;right:16px;z-index:1000;background:white;padding:12px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.8}}</style></head>
<body><div id="map"></div>
<div class="lg"><b>人大通州校区 Campus Sample 01</b><br>
<span style="color:#3498db">●</span> IN_CAMPUS ({mc["IN_CAMPUS"]})<br>
<span style="color:#e74c3c">●</span> OUT_OF_CAMPUS ({mc["OUT_OF_CAMPUS"]})<br>
<span style="color:#f39c12">●</span> AMBIGUOUS ({mc["AMBIGUOUS"]})<br>
<small style="color:#888">正判 {ok_count}/14 · KNOWN_ISSUE 标注保留<br>面积 ~144 ha (~2161 亩, 官方 1652)</small></div>
<script>
var map=L.map('map',{{center:[39.9055,116.74],zoom:16,maxZoom:19}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
{poly_js}
{markers}
</script></body></html>"""

out = os.path.abspath("outputs/campus_sample_01/campus_map.html")
open(out,"w",encoding="utf-8").write(html_out)
print("MAP:", out)
import webbrowser
webbrowser.open("file://" + out)
