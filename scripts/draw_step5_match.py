"""A4/B4 变体: 在种子点 300m 内选面积最匹配目标的街区/建筑簇."""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, os, json, math
sys.path.insert(0, str(_REPO))

import numpy as np
import pandas as pd
from shapely import wkt, make_valid
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
ROAD_WIN = str(_REPO / 'data/roads_windows')
BLD_DIR = str(_REPO / 'data/buildings')
OUT = str(_REPO / 'outputs/selfdraw_eval.csv')

WINDOWS = {"W1_oldcity": (116.37, 39.93), "W2_chaoyang": (116.43, 39.93)}
HALF_LNG, HALF_LAT = 0.0117, 0.009
M = 111320.0
COS = math.cos(math.radians(39.93))

def area_m2(g): return g.area * M * M * COS
def radius_deg(a): return math.sqrt(a / math.pi) / (M * COS)

def load_ways(fp):
    data = json.loads(open(fp, "rb").read())
    return [LineString([(p["lon"], p["lat"]) for p in el["geometry"]])
            for el in data.get("elements", []) if el.get("type") == "way" and "geometry" in el and len(el["geometry"]) >= 2]

def blocks_for(name):
    lines = load_ways(os.path.join(ROAD_WIN, f"{name}_all.json"))
    clon, clat = WINDOWS[name]
    clip = box(clon - HALF_LNG - 0.001, clat - HALF_LAT - 0.001, clon + HALF_LNG + 0.001, clat + HALF_LAT + 0.001)
    segs = [l.intersection(clip) for l in lines]
    segs = [g for g in segs if (not g.is_empty) and g.geom_type in ("LineString", "MultiLineString")]
    faces = [f for f in polygonize(unary_union(segs)) if f.geom_type == "Polygon"]
    win = box(clon - HALF_LNG, clat - HALF_LAT, clon + HALF_LNG, clat + HALF_LAT)
    return [f for f in faces if f.intersection(win).area > 0.5 * f.area]

def clusters_for(name, buf_m=8.0):
    data = json.loads(open(os.path.join(BLD_DIR, f"{name}.json"), "rb").read())
    polys = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        c = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(c) >= 4:
            try:
                p = Polygon(c)
                if p.is_valid and p.area > 0:
                    polys.append(p)
            except Exception:
                pass
    if not polys:
        return []
    buf = unary_union([p.buffer(buf_m / (M * COS)) for p in polys])
    parts = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
    return [p for p in parts if area_m2(p) > 300]

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
recs = []
for _, r in df.iterrows():
    try:
        g = wkt.loads(transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84))
        if g.is_empty:
            continue
        lon, lat = float(r["经度"]), float(r["纬度"])
    except Exception:
        continue
    if not (115 < lon < 118 and 39 < lat < 42):
        lon, lat = g.centroid.x, g.centroid.y
    c = g.centroid
    for wn, (clon, clat) in WINDOWS.items():
        if abs(c.x - clon) < HALF_LNG and abs(c.y - clat) < HALF_LAT:
            recs.append({"window": wn, "source_record_id": r["source_record_id"], "lon": lon, "lat": lat,
                         "fence_wkt": g.wkt, "A": area_m2(g)})
            break
recs = pd.DataFrame(recs)

rows = []
for wn in WINDOWS:
    sub = recs[recs["window"] == wn]
    blocks = blocks_for(wn)
    clusters = clusters_for(wn)
    for _, r in sub.iterrows():
        seed = Point(r["lon"], r["lat"])
        target = make_valid(wkt.loads(r["fence_wkt"]))
        A = r["A"]
        row = {"source_record_id": r["source_record_id"]}
        near = [b for b in blocks if b.distance(seed) < 0.0034]
        if near:
            b4 = min(near, key=lambda b: abs(math.log(area_m2(b) / A)))
            if area_m2(b4) > 1.5 * A:
                b4 = b4.intersection(seed.buffer(radius_deg(A)))
            try:
                b4 = make_valid(b4)
                inter = b4.intersection(target).area
                row["iou_A4"] = round(inter / (b4.area + target.area - inter), 3)
            except Exception:
                row["iou_A4"] = np.nan
        else:
            row["iou_A4"] = np.nan
        nearc = [c for c in clusters if c.distance(seed) < 0.0034]
        if nearc:
            c4 = min(nearc, key=lambda c: abs(math.log(area_m2(c) / A)))
            if area_m2(c4) > 1.5 * A:
                c4 = c4.intersection(seed.buffer(radius_deg(A)))
            try:
                c4 = make_valid(c4).buffer(6.0 / (M * COS))
                inter = c4.intersection(target).area
                row["iou_B4"] = round(inter / (c4.area + target.area - inter), 3)
            except Exception:
                row["iou_B4"] = np.nan
        else:
            row["iou_B4"] = np.nan
        rows.append(row)

out = pd.DataFrame(rows)
ev = pd.read_csv(OUT)
ev = ev.drop(columns=[c for c in ("iou_A4", "iou_B4") if c in ev.columns])
ev = ev.merge(out, on="source_record_id", how="left")
ev.to_csv(OUT, index=False)

for t in ["iou_A3_block", "iou_A4", "iou_B3_bldg", "iou_B4"]:
    s = ev[t].dropna()
    print("%s: n=%d 中位 %.3f  >0.5 占 %.0f%%  >0.7 占 %.0f%%" % (t, len(s), s.median(), 100 * (s > 0.5).mean(), 100 * (s > 0.7).mean()))
best = ev[["iou_A3_block", "iou_A4", "iou_B3_bldg", "iou_B4"]].max(axis=1)
print("四法择优: 中位 %.3f  >0.5 占 %.0f%%  >0.7 占 %.0f%%" % (best.median(), 100 * (best > 0.5).mean(), 100 * (best > 0.7).mean()))
for wn in WINDOWS:
    sub = ev[ev["window"] == wn]
    print(wn, "A3 %.3f A4 %.3f B3 %.3f B4 %.3f" % (sub["iou_A3_block"].median(), sub["iou_A4"].median(),
                                                   sub["iou_B3_bldg"].median(), sub["iou_B4"].median()))
