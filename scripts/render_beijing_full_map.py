"""Render outputs/beijing_full/beijing_gb50137_all.geojson as a Leaflet map HTML.

Previously the map html had no in-repo generator (it was produced ad-hoc);
this script closes that gap and keeps the html in sync with the geojson.
Round-trip verifiable with scripts/extract_html_geojson.py.

Usage: python3 scripts/render_beijing_full_map.py [in.geojson] [out.html]
"""
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    _REPO, "outputs", "beijing_full", "beijing_gb50137_all.geojson")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    _REPO, "outputs", "beijing_full", "beijing_gb50137_map.html")

GB_CN = {"R": "居住用地", "B1": "商业服务用地", "B2": "商务办公用地", "M": "工业用地",
         "S": "交通枢纽用地", "A3": "教育科研用地", "A4": "体育文化用地", "A5": "医疗卫生用地",
         "G": "公园与绿地", "MIL": "军事用地", "AGR": "农林业用地", "U": "未分类"}
GB_COLOR = {"R": "#e6550d", "B1": "#fdae6b", "B2": "#fd8d3c", "M": "#756bb1",
            "S": "#41b6c4", "A3": "#a1d99b", "A4": "#74c476", "A5": "#fec44f",
            "G": "#31a354", "MIL": "#969696", "AGR": "#c7e9b4", "U": "#d9d9d9"}

fc = json.load(open(IN, encoding="utf-8"))
feats = fc["features"]
from collections import Counter
dist = Counter(f["properties"]["gb_code"] for f in feats)

parts = []
for f in feats:
    g = f["geometry"]
    if g["type"] == "Polygon":
        rings = list(g.get("coordinates") or [])      # already a list of rings
    elif g["type"] == "MultiPolygon":
        rings = [r for poly in (g.get("coordinates") or []) for r in (poly or [])]
    else:
        continue
    p = f["properties"]
    gb = str(p.get("gb_code", "U"))
    color = GB_COLOR.get(gb, "#d9d9d9")
    name = str(p.get("name") or "").replace("\\", "").replace("'", "’")
    tip = (f"{name} | {GB_CN.get(gb, gb)} ({gb}) | {p.get('osm_fclass','')} | "
           f"{p.get('source','')}").replace("\n", " ")
    for ring in rings:
        pts = [pt for pt in (ring or [])
               if isinstance(pt, (list, tuple)) and len(pt) >= 2
               and isinstance(pt[0], (int, float)) and isinstance(pt[1], (int, float))]
        if len(pts) < 3:
            continue
        closed = pts[0] == pts[-1]
        pts = pts[:400]
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        coords = ", ".join(f"[{lat:.6f}, {lng:.6f}]" for lng, lat, *_ in pts)
        parts.append(
            f"L.polygon([{coords}],{{color:'{color}',weight:1,fillOpacity:0.55}})"
            f".addTo(map).bindPopup('{tip}');")

legend = "".join(
    f"<div><span style='display:inline-block;width:12px;height:12px;"
    f"background:{GB_COLOR[c]};margin-right:6px'></span>{GB_CN[c]} {c} — {dist.get(c,0)} 面</div>"
    for c in ["R", "B1", "B2", "M", "S", "A3", "A4", "A5", "G", "MIL", "AGR", "U"])
html = ("""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>北京 · GB50137 全量分类 (%d 地块)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{margin:0}#map{width:100vw;height:100vh}
.lg{position:absolute;bottom:16px;left:16px;z-index:1000;background:white;padding:14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.9;max-height:80vh;overflow:auto}
.hdr{position:absolute;top:16px;left:16px;z-index:1000;background:white;padding:10px 14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:14px;font-weight:600}
</style></head><body>
<div id="map"></div>
<div class="hdr">北京 · GB50137 全量分类（%d 地块）· © OpenStreetMap contributors (ODbL)</div>
<div class="lg">%s</div>
<script>
var map=L.map('map',{preferCanvas:true}).setView([39.92,116.40],10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,
attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
%s
</script></body></html>""" % (len(feats), len(feats), legend, "\n".join(parts)))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(html)
print(f"saved {len(feats)} polygons -> {OUT} ({os.path.getsize(OUT)/1048576:.1f} MB)")
