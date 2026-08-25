"""自绘围栏 Step 4: 最终生成器 — 现实输入 = 名称 + 点 + 面积属性(面积[内置], r=1.000).

A3: 全类型路网街区, 以真实面积为粒度目标 (并入/裁剪)
B3: 建筑簇(8m), 以真实面积裁剪
C3: 真实面积圆 (纯尺寸上限基线, 不用地图)
对比列保留 A2/B2/C(先验面积版), 量化"地图数据在尺寸已知之外的增益".
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

def area_m2(g): return g.area * M * M * COS
def radius_deg(a): return math.sqrt(a / math.pi) / (M * COS)

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
    c = g.centroid
    for wn, (clon, clat) in WINDOWS.items():
        if abs(c.x - clon) < HALF_LNG and abs(c.y - clat) < HALF_LAT:
            recs.append({"window": wn, "source_record_id": r["source_record_id"], "name": r["小区名称"],
                         "lon": lon, "lat": lat, "fence_wkt": g.wkt, "fence_area": area_m2(g)})
            break
recs = pd.DataFrame(recs)

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

results, geoms = [], {}
for wn in WINDOWS:
    sub = recs[recs["window"] == wn]
    blocks = blocks_for(wn)
    clusters = clusters_for(wn)
    print(f"{wn}: {len(sub)} 围栏 | 街区 {len(blocks)} | 建筑簇 {len(clusters)}")

    for _, r in sub.iterrows():
        seed = Point(r["lon"], r["lat"])
        target = make_valid(wkt.loads(r["fence_wkt"]))
        A = r["fence_area"]                       # 现实输入: 面积属性
        row = {"window": wn, "source_record_id": r["source_record_id"], "name": r["name"],
               "fence_area": round(A)}
        circle = seed.buffer(radius_deg(A))
        gg = {"fence": target.wkt, "seed": [r["lon"], r["lat"]]}

        # A3
        cand = [b for b in blocks if b.contains(seed)]
        blk = cand[0] if cand else (min(blocks, key=lambda b: b.distance(seed))
                                    if min(blocks, key=lambda b: b.distance(seed)).distance(seed) < 0.0005 else None)
        a3 = None
        if blk is not None:
            cur = blk
            guard = 0
            while area_m2(cur) < 0.5 * A and guard < 4:
                nbrs = sorted([b for b in blocks if b is not cur and b.intersects(cur)],
                              key=lambda b: b.intersection(cur).length, reverse=True)
                if not nbrs:
                    break
                cur = unary_union([cur, nbrs[0]])
                guard += 1
            if area_m2(cur) > 1.5 * A:
                cur = cur.intersection(circle)
            a3 = make_valid(cur) if not cur.is_empty else None

        # B3
        b3 = None
        if clusters:
            contain = [c for c in clusters if c.contains(seed)]
            b3 = contain[0] if contain else min(clusters, key=lambda c: c.distance(seed)) \
                if min(clusters, key=lambda c: c.distance(seed)).distance(seed) < 0.0015 else None
            if b3 is not None:
                if area_m2(b3) > 1.5 * A:
                    b3 = b3.intersection(circle)
                b3 = b3.buffer(6.0 / (M * COS)) if not b3.is_empty else None

        for tag, g in (("A3_block", a3), ("B3_bldg", b3), ("C3_circle", circle)):
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
keep = ["source_record_id"] + [c for c in old.columns if any(c.endswith(s) for s in ("_A2_block", "_B2_bldg", "_C_circle"))]
out = out.merge(old[keep], on="source_record_id", how="left")
out.to_csv(OUT, index=False)
json.dump(geoms, open(GEO_OUT, "w"))

print(f"\n{len(out)} 条 → {OUT}")
print("\n==== 最终结果 (输入=名称+点+面积) ====")
for tag in ("A2_block", "B2_bldg", "C_circle", "A3_block", "B3_bldg", "C3_circle"):
    s = out[f"iou_{tag}"].dropna() if f"iou_{tag}" in out.columns else pd.Series(dtype=float)
    if len(s) == 0: continue
    print(f"{tag}: n={len(s)}  IoU 中位 {s.median():.3f}  >0.5 占 {(s>0.5).mean():.0%}  >0.3 占 {(s>0.3).mean():.0%}  >0.7 占 {(s>0.7).mean():.0%}")
for wn in WINDOWS:
    sub = out[out["window"] == wn]
    print(wn, {t: round(sub[f'iou_{t}'].dropna().median(), 3) for t in ("A3_block", "B3_bldg", "C3_circle")})
# 最优组合: A3/B3 逐条取优
best = out[["iou_A3_block", "iou_B3_bldg"]].max(axis=1)
print(f"\nA3/B3 逐条择优: IoU 中位 {best.median():.3f}  >0.5 占 {(best>0.5).mean():.0%}  >0.7 占 {(best>0.7).mean():.0%}")
