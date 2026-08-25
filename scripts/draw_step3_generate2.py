"""自绘围栏 Step 3: 二代生成器 — 全类型路网街区 + 粒度自适应.

A2: 全类型路网(含footway/service/steps) polygonize → 胡同级街区面;
    种子点所在街区为围栏; 面积>3×先验 → 与先验圆求交裁剪; <0.5×先验 → 贪心并邻街区
B2: 建筑簇 buffer(8m) 联通; 面积>3×先验 → 先验圆裁剪
对比保留一代结果 (A1/B1/C), 输出合并 selfdraw_eval.csv
"""
import sys, os, json, math
sys.path.insert(0, "/Users/user/WorkBuddy/2026-08-18-17-47-15")

import numpy as np
import pandas as pd
from shapely import wkt, make_valid
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = "data/client_a_sites.xlsx"
ROAD_WIN = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/roads_windows"
BLD_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/buildings"
OUT = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/selfdraw_eval.csv"
GEO_OUT = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/selfdraw_geoms.json"

WINDOWS = {"W1_oldcity": (116.37, 39.93), "W2_chaoyang": (116.43, 39.93)}
HALF_LNG, HALF_LAT = 0.0117, 0.009
M = 111320.0
COS = math.cos(math.radians(39.93))

def area_m2(g):
    return g.area * M * M * COS

def radius_deg(a):
    return math.sqrt(a / math.pi) / (M * COS)

# ---------- 数据 ----------
df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]

recs = []
for _, r in df.iterrows():
    try:
        g = wkt.loads(transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84))
        if g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        lon, lat = float(r["经度"]), float(r["纬度"])
    except Exception:
        continue
    if not (115 < lon < 118 and 39 < lat < 42):
        lon, lat = g.centroid.x, g.centroid.y
        fc = True
    else:
        fc = False
    c = g.centroid
    for wn, (clon, clat) in WINDOWS.items():
        if abs(c.x - clon) < HALF_LNG and abs(c.y - clat) < HALF_LAT:
            recs.append({"window": wn, "source_record_id": r["source_record_id"], "name": r["小区名称"],
                         "lon": lon, "lat": lat, "pt_from_centroid": fc,
                         "fence_wkt": g.wkt, "fence_area": area_m2(g)})
            break
recs = pd.DataFrame(recs)

def local_prior(lon, lat, k=5):
    d = np.hypot((recs["lon"] - lon) * M * COS, (recs["lat"] - lat) * M)
    idx = d.sort_values().index[1:k+1]
    return float(recs.loc[idx, "fence_area"].median())

recs["prior_area"] = [local_prior(lo, la) for lo, la in zip(recs["lon"], recs["lat"])]

# ---------- 窗口街区 (全类型路网) ----------
def load_ways(fp):
    data = json.loads(open(fp, "rb").read())
    out = []
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        c = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(c) >= 2:
            out.append(LineString(c))
    return out

def blocks_for(name):
    lines = load_ways(os.path.join(ROAD_WIN, f"{name}_all.json"))
    clon, clat = WINDOWS[name]
    clip = box(clon - HALF_LNG - 0.001, clat - HALF_LAT - 0.001, clon + HALF_LNG + 0.001, clat + HALF_LAT + 0.001)
    segs = [l.intersection(clip) for l in lines]
    segs = [g for g in segs if (not g.is_empty) and g.geom_type in ("LineString", "MultiLineString")]
    merged = unary_union(segs)
    faces = [f for f in polygonize(merged) if f.geom_type == "Polygon"]
    win = box(clon - HALF_LNG, clat - HALF_LAT, clon + HALF_LNG, clat + HALF_LAT)
    inner = [f for f in faces if f.intersection(win).area > 0.5 * f.area]
    return inner

def load_buildings(name):
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
    return polys

def clusters_for(name, buf_m=8.0):
    polys = load_buildings(name)
    if not polys:
        return []
    buf = unary_union([p.buffer(buf_m / (M * COS)) for p in polys])
    parts = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
    return [p for p in parts if area_m2(p) > 300]

results, geoms = [], {}
for wn in WINDOWS:
    sub = recs[recs["window"] == wn]
    blocks = blocks_for(wn)
    clusters = clusters_for(wn)
    print(f"{wn}: {len(sub)} 围栏 | 全类型街区 {len(blocks)} (中位 {np.median([area_m2(b) for b in blocks]):.0f} m²)"
          f" | 建筑簇 {len(clusters)} (中位 {np.median([area_m2(c) for c in clusters]):.0f} m²)")

    for _, r in sub.iterrows():
        seed = Point(r["lon"], r["lat"])
        target = make_valid(wkt.loads(r["fence_wkt"]))
        row = {"window": wn, "source_record_id": r["source_record_id"], "name": r["name"],
               "fence_area": round(r["fence_area"]), "prior_area": round(r["prior_area"])}
        prior_circle = seed.buffer(radius_deg(r["prior_area"]))
        gg = {"fence": target.wkt, "seed": [r["lon"], r["lat"]]}

        # ---- A2: 全类型街区 + 粒度自适应 ----
        cand = [b for b in blocks if b.contains(seed)]
        blk = cand[0] if cand else (min(blocks, key=lambda b: b.distance(seed))
                                    if min(blocks, key=lambda b: b.distance(seed)).distance(seed) < 0.0005 else None)
        if blk is not None:
            cur = blk
            guard = 0
            while area_m2(cur) < 0.5 * r["prior_area"] and guard < 4:
                nbrs = sorted([b for b in blocks if b is not cur and b.intersects(cur)],
                              key=lambda b: b.intersection(cur).length, reverse=True)
                if not nbrs:
                    break
                cur = unary_union([cur, nbrs[0]])
                guard += 1
            if area_m2(cur) > 3 * r["prior_area"]:
                cur = cur.intersection(prior_circle)
            a2 = make_valid(cur) if not cur.is_empty else None
        else:
            a2 = None

        # ---- B2: 建筑簇(8m) + 粒度自适应 ----
        b2 = None
        if clusters:
            contain = [c for c in clusters if c.contains(seed)]
            if contain:
                b2 = contain[0]
            else:
                near = min(clusters, key=lambda c: c.distance(seed))
                if near.distance(seed) < 0.0015:
                    b2 = near
            if b2 is not None:
                if area_m2(b2) > 3 * r["prior_area"]:
                    b2 = b2.intersection(prior_circle)
                b2 = b2.buffer(6.0 / (M * COS)) if not b2.is_empty else None

        for tag, g in (("A2_block", a2), ("B2_bldg", b2), ("C_circle", prior_circle)):
            if g is None or g.is_empty:
                row[f"iou_{tag}"] = np.nan
                row[f"area_{tag}"] = np.nan
                continue
            try:
                g_v = make_valid(g)
                inter = g_v.intersection(target).area
            except Exception:
                inter = 0.0
            row[f"iou_{tag}"] = round(inter / (g_v.area + target.area - inter), 3)
            row[f"recall_{tag}"] = round(inter / target.area, 3)
            row[f"area_{tag}"] = round(area_m2(g_v))
            gg[tag] = g_v.wkt
        results.append(row)
        geoms[r["source_record_id"]] = gg

out = pd.DataFrame(results)
old = pd.read_csv(OUT)
keep = ["source_record_id"] + [c for c in old.columns
                               if any(c.endswith(s) for s in ("_A_block", "_B_bldg"))]
out = out.merge(old[keep].rename(columns={c: c.replace("_A_block", "_A1").replace("_B_bldg", "_B1") for c in keep}),
                on="source_record_id", how="left")
out.to_csv(OUT, index=False)
json.dump(geoms, open(GEO_OUT, "w"))
print(f"\n{len(out)} 条 → {OUT}")
print("\n==== 二代 vs 一代 vs 基线 ====")
for tag in ("A1_block", "B1_bldg", "A2_block", "B2_bldg", "C_circle"):
    s = out[f"iou_{tag}"].dropna() if f"iou_{tag}" in out.columns else pd.Series(dtype=float)
    if len(s) == 0: continue
    print(f"{tag}: n={len(s)}  IoU 中位 {s.median():.3f}  >0.5 占 {(s>0.5).mean():.0%}  >0.3 占 {(s>0.3).mean():.0%}")
for wn in WINDOWS:
    sub = out[out["window"] == wn]
    print(wn, {t.replace("1_", "1").replace("2_", "2"): round(sub[f'iou_{t}'].dropna().median(), 3)
               for t in ("A1_block", "B1_bldg", "A2_block", "B2_bldg", "C_circle") if f"iou_{t}" in sub.columns})
