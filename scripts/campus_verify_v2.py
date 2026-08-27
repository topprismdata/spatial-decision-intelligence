"""Campus Sample 01: 三级证据优先级归属判定 + 地图输出"""
import warnings; warnings.filterwarnings("ignore")
import json, os, re
import html as H
from shapely.geometry import Point, shape
from collections import Counter

def main():
    cp_geo = json.load(open("outputs/campus_sample_01/campus_polygon.geojson"))
    campus = shape(cp_geo["features"][0]["geometry"])
    data = json.load(open("outputs/campus_sample_01/campus_data.json"))
    all_pois = data["pois_campus_internal"] + data["pois_external_negative"]
    
    KEYWORDS = ["通州校区", "人大通州", "人大", "人民大学"]
    
    results = []
    for poi in all_pois:
        pt = Point(poi["lng"], poi["lat"])
        inside = campus.contains(pt) or campus.touches(pt)
        
        if inside:
            d_deg = campus.exterior.distance(pt)
        else:
            d_deg = campus.distance(pt)
        dist_m = round(d_deg * 111320)
        
        name = str(poi.get("name", ""))
        evidence_parts = []
        
        # E1: Name semantic (highest priority)
        has_kw = False
        kw_hit = ""
        for kw in KEYWORDS:
            if kw in name:
                has_kw = True
                kw_hit = kw
                break
        
        if has_kw:
            membership = "IN_CAMPUS"
            confidence = "HIGH"
            evidence_parts.append(f"E1:name[{kw_hit}]")
        elif inside:
            membership = "IN_CAMPUS"
            confidence = "MEDIUM"
            evidence_parts.append("E2:contain")
        elif dist_m < 150:
            membership = "AMBIGUOUS"
            confidence = "LOW"
            evidence_parts.append(f"E3:near({dist_m}m)")
        else:
            membership = "OUT_OF_CAMPUS"
            confidence = "HIGH"
            evidence_parts.append(f"E3:far({dist_m}m)")
        
        expected = str(poi.get("expected_membership", ""))
        if membership == expected:
            tag = "✓"
        elif membership == "AMBIGUOUS":
            tag = "⚠"
        else:
            tag = "✗"
        
        results.append({
            "name": name,
            "type": poi.get("type", ""),
            "lng": poi["lng"],
            "lat": poi["lat"],
            "membership": membership,
            "expected": expected,
            "match": tag,
            "confidence": confidence,
            "reason": "; ".join(evidence_parts),
            "dist_to_boundary_m": dist_m
        })
    
    mc = Counter(r["membership"] for r in results)
    ok_n = sum(1 for r in results if r["match"] == "✓")
    warn_n = sum(1 for r in results if r["match"] == "⚠")
    bad_n = sum(1 for r in results if r["match"] == "✗")
    
    print("=== Campus Sample 01 — 三级证据优先级 ===\n")
    for r in results:
        print(f"{r['match']} [{r['membership']:14s}] {r['confidence']:5s} | {r['name'][:26]:28s} | {r['reason']}")
    print(f"\nIN={mc['IN_CAMPUS']} OUT={mc['OUT_OF_CAMPUS']} AMB={mc['AMBIGUOUS']}")
    print(f"✓ {ok_n}/14  ⚠ {warn_n}  ✗ {bad_n}")
    
    data["poi_membership_results"] = results
    json.dump(data, open("outputs/campus_sample_01/campus_data.json", "w"),
              ensure_ascii=False, indent=2)
    
    render_map(results, campus, mc, ok_n, warn_n, bad_n)

def render_map(results, campus, mc, ok_n, warn_n, bad_n):
    MC = {"IN_CAMPUS": "#3498db", "OUT_OF_CAMPUS": "#e74c3c", "AMBIGUOUS": "#f39c12"}
    
    markers_lines = []
    for r in results:
        c = MC.get(r["membership"], "#888")
        n = H.escape(r["name"])
        m = r["membership"]
        conf = r["confidence"]
        evi = H.escape(r["reason"])
        lat = r["lat"]
        lng = r["lng"]
        popup = f"<b>{n}</b><br>{m}<br>conf:{conf}<br>{evi}"
        circle = (
            f"L.circleMarker([{lat},{lng}],"
            f"{{radius:9,color:'{c}',fillColor:'{c}',fillOpacity:.85}})"
            f".addTo(map).bindPopup('{popup}');"
        )
        markers_lines.append(circle)
    
    coords_json = json.dumps([[c[1], c[0]] for c in list(campus.exterior.coords)])
    area_ha = round(campus.area * 111320 ** 2 / 10000)
    
    html_out = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Campus Sample 01</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{{margin:0}}
#map{{width:100vw;height:100vh}}
.lg{{position:absolute;top:16px;left:16px;z-index:1000;background:white;padding:14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.8}}
</style></head><body><div id="map"></div>
<div class="lg"><b>📍 Campus Sample 01 · 中国人民大学通州校区</b><br>
🟢 OSM way:645644236<br>
🔵 IN ({mc["IN_CAMPUS"]}) 🔴 OUT ({mc["OUT_OF_CAMPUS"]}) 🟡 AMB ({mc["AMBIGUOUS"]})<br>
✅ {ok_n}/14 · ⚠ {warn_n} · ❌ {bad_n}<br>
<small style="color:#888">{area_ha} ha / 1817 mu</small></div>
<script>
var map=L.map('map',{{center:[39.9055,116.74],zoom:16,maxZoom:19}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
var cp=L.polygon({coords_json},{{color:'#2ecc71',weight:3,fillOpacity:0.08}}).addTo(map);
{chr(10).join(markers_lines)}
</script></body></html>"""
    
    p = os.path.abspath("outputs/campus_sample_01/campus_map.html")
    open(p, "w", encoding="utf-8").write(html_out)
    print(f"\nMAP: {p}")
    import webbrowser
    webbrowser.open("file://" + p)

if __name__ == "__main__":
    main()
