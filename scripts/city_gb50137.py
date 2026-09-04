"""Generic GB50137 land-use classification for ANY Geofabrik city/province extract.

Generalizes scripts/beijing_full_gb50137.py:
  landuse_a + POI 面 + transport_a  ->  12-class GeoJSON + Shapefile + Leaflet map

Inputs (downloaded by scripts/fetch_city_data.py or manually):
  <data-dir>/gis_osm_landuse_a_free_1.shp    (required)
  <data-dir>/gis_osm_pois_a_free_1.shp       (required, may be empty)
  <data-dir>/gis_osm_transport_a_free_1.shp  (required, may be empty)

Three traps this script handles (each bit a real run; see docs/new-city-guide.md):
  1. Province extracts (e.g. shaanxi) contain many cities -> pass --bbox to cut
     the target city extent (centroid test), otherwise you silently classify the
     whole province.
  2. Exporting ESRI Shapefile to a name whose directory already exists raises a
     misleading EPERM/GDAL error -> the stale shapefile dir is removed first.
  3. Malformed rings (NaN / <3 points) poison a whole Leaflet page -> every ring
     is validated and vertex-capped at 400 before embedding; canvas renderer.

Usage:
  python3 scripts/city_gb50137.py --city xian \
      --data-dir data/xian_shp --bbox 34.10,108.50,34.55,109.30
  python3 scripts/city_gb50137.py --city beijing --data-dir data/beijing_shp
"""

import argparse
import json
import math
import os
import shutil
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_REPO = Path(os.environ.get("SDI_ROOT") or Path(__file__).resolve().parents[1])

LANDUSE_GB = {
    "residential": "R", "retail": "B1", "commercial": "B2", "industrial": "M",
    "park": "G", "forest": "G", "grass": "G", "meadow": "G", "scrub": "G",
    "orchard": "G", "recreation_ground": "G", "village_green": "G",
    "heath": "G",  # shrub heathland; Shaanxi-specific, grouped with scrub/grass
    "military": "MIL", "farmland": "AGR", "farmyard": "AGR", "quarry": "M",
    "cemetery": "U", "landfill": "U", "vineyard": "AGR", "allotments": "AGR",
    "railway": "S", "education": "A3", "hospital": "A5",
}
POI_GB = {
    "school": "A3", "university": "A3", "college": "A3", "kindergarten": "A3",
    "hospital": "A5", "clinic": "A5", "dentist": "A5", "doctors": "A5",
    "stadium": "A4", "pitch": "A4", "track": "A4", "sports_centre": "A4",
    "library": "A4", "museum": "A4", "theatre": "A4", "community_centre": "A4",
    "bus_station": "S", "railway_station": "S", "airport": "S", "ferry_terminal": "S",
}
GB_CN = {
    "R": "居住用地", "B1": "商业服务用地", "B2": "商务办公用地", "M": "工业用地",
    "S": "交通枢纽用地", "A3": "教育科研用地", "A4": "体育文化用地",
    "A5": "医疗卫生用地", "G": "公园与绿地", "MIL": "军事用地",
    "AGR": "农林业用地", "U": "未分类",
}
GB_COLOR = {
    "R": "#e6b8a2", "B1": "#d94f4f", "B2": "#f0a03c", "M": "#8c6bb1",
    "S": "#3b3b6d", "A3": "#4c9ce6", "A4": "#7ec8e3", "A5": "#e66a8a",
    "G": "#6cc04a", "MIL": "#556b2f", "AGR": "#c9d94a", "U": "#d9d9d9",
}
TRANSPORT_KEEP = {"bus_station", "railway_station", "airport"}
CLASS_ORDER = ["R", "B1", "B2", "M", "S", "A3", "A4", "A5", "G", "MIL", "AGR", "U"]


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--city", required=True, help="city slug, used for dir names")
    ap.add_argument("--data-dir", default=None,
                    help="dir with gis_osm_*.shp (default: data/<city>_shp under repo root)")
    ap.add_argument("--out-root", default="outputs", help="output root (default outputs/)")
    ap.add_argument("--bbox", default=None,
                    help="min_lat,min_lng,max_lat,max_lng WGS84 to cut province extracts; "
                         "a feature's representative point must fall inside")
    ap.add_argument("--title", default=None, help="display name (default=city slug)")
    return ap.parse_args()


def load_layer(data_dir: Path, name: str) -> gpd.GeoDataFrame:
    path = data_dir / f"gis_osm_{name}_free_1.shp"
    if not path.exists():
        print(f"FATAL: missing layer {path} — run scripts/fetch_city_data.py first")
        sys.exit(2)
    gdf = gpd.read_file(path)
    # Geofabrik ships EPSG:4326; enforce, never trust silently.
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
    return gdf.set_crs(epsg=4326, allow_override=True)


def in_bbox(gdf: gpd.GeoDataFrame, bbox):
    if bbox is None or gdf.empty:
        return gdf
    min_lat, min_lng, max_lat, max_lng = bbox
    # representative-point test: whole-feature attribution stays stable
    # (no clipped slivers), mirroring how Geofabrik city extracts behave.
    c = gdf.geometry.representative_point()
    mask = (c.y >= min_lat) & (c.y <= max_lat) & (c.x >= min_lng) & (c.x <= max_lng)
    return gdf[mask]


def main():
    args = parse_args()
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    data_dir = Path(args.data_dir) if args.data_dir else _REPO / "data" / f"{args.city}_shp"
    if not data_dir.is_absolute():
        data_dir = _REPO / data_dir
    out_dir = _REPO / args.out_root / f"{args.city}_full"
    title = args.title or args.city
    t0 = time.time()

    lu = load_layer(data_dir, "landuse_a")
    lu["gb_code"] = lu.fclass.map(LANDUSE_GB).fillna("U")
    lu["src_layer"] = "landuse"
    n_raw = len(lu)
    lu = in_bbox(lu, bbox)
    print(f"landuse: {len(lu)} (extract had {n_raw}{', bbox-filtered' if bbox else ''})")
    if lu.empty:
        print("FATAL: landuse empty after bbox — check --bbox order "
              "min_lat,min_lng,max_lat,max_lng")
        sys.exit(2)

    pois_a = load_layer(data_dir, "pois_a")
    pois_a["gb_code"] = pois_a.fclass.map(POI_GB).fillna("")
    pa_sub = in_bbox(pois_a[pois_a.gb_code != ""].copy(), bbox)
    pa_sub["src_layer"] = "poi_area"
    print(f"POI 补充: {len(pa_sub)}")

    tr = load_layer(data_dir, "transport_a")
    tr_sub = in_bbox(tr[tr.fclass.isin(TRANSPORT_KEEP)].copy(), bbox)
    tr_sub["gb_code"] = "S"
    tr_sub["src_layer"] = "transport"
    print(f"Transport: {len(tr_sub)}")

    keep = ["name", "fclass", "gb_code", "src_layer", "geometry"]
    gdf = pd.concat([lu[keep], pa_sub[keep], tr_sub[keep]], ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")
    dist = Counter(gdf.gb_code)
    total = len(gdf)

    print(f"\n=== {title} 全量 GB50137 === ({time.time()-t0:.0f}s)")
    for code in CLASS_ORDER:
        print(f"  {code:3s} {GB_CN[code]:10s}: {dist.get(code, 0):6d} 面")
    print(f"  总计: {total}")
    u_pct = 100.0 * dist.get("U", 0) / max(total, 1)
    if u_pct > 15:
        print(f"  WARN: 未分类占比 {u_pct:.1f}% — 检查新 fclass "
              "(scripts/check_city_data.py --stage output)")

    out_dir.mkdir(parents=True, exist_ok=True)

    # GeoJSON
    out_geo = out_dir / f"{args.city}_gb50137_all.geojson"
    features = []
    for r in gdf.itertuples():
        props = {
            "gb_code": str(r.gb_code), "ClassCn": GB_CN.get(str(r.gb_code), ""),
            "osm_fclass": str(r.fclass), "source": str(r.src_layer),
            "name": str(getattr(r, "name", "") or ""),
        }
        features.append({
            "type": "Feature",
            "geometry": json.loads(json.dumps(r.geometry.__geo_interface__)),
            "properties": props,
        })
    with open(out_geo, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)
    print(f"\nsaved {len(features)} features -> {out_geo} "
          f"({out_geo.stat().st_size/1048576:.1f} MB)")

    # Shapefile (trap #2: clear stale name-dir, else misleading EPERM)
    shp_stem = out_dir / f"{args.city}_gb50137_all"
    if shp_stem.is_dir():
        shutil.rmtree(shp_stem)
    export = gdf[["gb_code", "name", "fclass", "src_layer", "geometry"]].copy()
    export["ClassCn"] = export.gb_code.map(GB_CN)
    export.to_file(shp_stem, encoding="utf-8", driver="ESRI Shapefile")
    print(f"SHP saved: {shp_stem}/")

    # Leaflet map (canvas renderer; 48k+ SVG paths freeze browsers)
    out_html = out_dir / f"{args.city}_gb50137_map.html"
    parts = []
    for f in features:
        g = f["geometry"]
        if not g or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        gb = f["properties"]["gb_code"]
        color = GB_COLOR.get(gb, "#d9d9d9")
        p = f["properties"]
        tip = (f"{p['name']} | {GB_CN.get(gb, gb)} ({gb}) | {p['osm_fclass']} | "
               f"{p['source']}").replace("\n", " ").replace("'", "’")
        rings = g["coordinates"] if g["type"] == "Polygon" else \
            [r for poly in g["coordinates"] for r in poly]
        for ring in rings:
            pts = [pt for pt in (ring or [])
                   if isinstance(pt, (list, tuple)) and len(pt) >= 2
                   and isinstance(pt[0], (int, float)) and isinstance(pt[1], (int, float))
                   and not (math.isnan(pt[0]) or math.isnan(pt[1]))]
            if len(pts) < 3:
                continue
            closed = pts[0] == pts[-1]
            pts = pts[:400]
            if closed and pts[0] != pts[-1]:
                pts.append(pts[0])
            coords = ", ".join(f"[{lat:.6f}, {lng:.6f}]" for lng, lat, *_ in pts)
            parts.append(f"L.polygon([{coords}],{{color:'{color}',weight:1,"
                         f"fillOpacity:0.55}}).addTo(map).bindPopup('{tip}');")

    # map view = centroid of the classified landuse (JS array literal, not tuple)
    vc = lu.geometry.representative_point()
    view = f"[{float(vc.y.mean()):.4f}, {float(vc.x.mean()):.4f}]"

    legend = "".join(
        f"<div><span style='display:inline-block;width:12px;height:12px;"
        f"background:{GB_COLOR[c]};margin-right:6px'></span>{GB_CN[c]} {c} — "
        f"{dist.get(c, 0)} 面</div>" for c in CLASS_ORDER)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{title} · GB50137 全量分类 ({total} 地块)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{{margin:0}}#map{{width:100vw;height:100vh}}
.lg{{position:absolute;bottom:16px;left:16px;z-index:1000;background:white;padding:14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:13px;line-height:1.9;max-height:80vh;overflow:auto}}
.hdr{{position:absolute;top:16px;left:16px;z-index:1000;background:white;padding:10px 14px;
border-radius:6px;box-shadow:0 2px 14px rgba(0,0,0,.25);font-size:14px;font-weight:600}}
</style></head><body>
<div id="map"></div>
<div class="hdr">{title} · GB50137 全量分类（{total} 地块）· © OpenStreetMap contributors (ODbL)</div>
<div class="lg">{legend}</div>
<script>
var map=L.map('map',{{preferCanvas:true}}).setView({view},10);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{maxZoom:19,
attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);
{chr(10).join(parts)}
</script></body></html>"""
    out_html.write_text(html, encoding="utf-8")
    print(f"map saved: {out_html} ({out_html.stat().st_size/1048576:.1f} MB)")
    print(f"next: python3 scripts/check_city_data.py --city {args.city} "
          f"--data-dir {data_dir} --out-root {args.out_root} --stage output")


if __name__ == "__main__":
    main()
