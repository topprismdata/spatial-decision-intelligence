"""自绘围栏 Step 2: A代(路网街区) + B代(建筑簇) 生成器, 与采购围栏对比评估.

输入(模拟真实采购替代场景): 仅 小区名称+经纬度点 (点列已证=真实WGS位置)
学习先验(来自采购围栏训练集): 全局面积 lognormal + 局部近邻中位面积 (不逐条泄漏标签)
生成:
  A 代: 路网 polygonize → 街区面; 种子点所在街区为围栏; 若面积 << 局部先验则并邻街区
  B 代: 建筑 buffer(12m) 联通分量 → 建筑簇; 种子点所在(或最近)簇 buffer(8m) 为围栏
  C 代(基线): 种子点为圆心、局部先验面积为半径的圆 — 不用任何地图数据
评估: 与采购围栏(归一WGS空间)算 IoU / 召回(∩/采购) / 精确率(∩/自绘)
"""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, os, json, math
sys.path.insert(0, str(_REPO))

import numpy as np
import pandas as pd
from shapely import wkt, make_valid
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize, transform as shp_transform

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
ROAD_DIR = str(_REPO / 'data/roads')
BLD_DIR = str(_REPO / 'data/buildings')
OUT = str(_REPO / 'outputs/selfdraw_eval.csv')

WINDOWS = {
    "W1_oldcity": (116.37, 39.93),
    "W2_chaoyang": (116.43, 39.93),
}
HALF_LNG, HALF_LAT = 0.0117, 0.009
M = 111320.0

def wkt_wgs(s):
    return wkt.loads(transform_geometry_wkt(s, gcj02_to_wgs84))

def area_m2(g):
    return g.area * M * M * math.cos(math.radians(g.centroid.y))

# ---------- 数据 ----------
df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]

# 窗口内采购围栏 (归一 WGS)
recs = []
for _, r in df.iterrows():
    try:
        g = wkt_wgs(str(r["坐标面[内置]"]))
        if g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        lon, lat = float(r["经度"]), float(r["纬度"])
    except Exception:
        continue
    if not (115 < lon < 118 and 39 < lat < 42):
        lon, lat = g.centroid.x, g.centroid.y
        pt_from_centroid = True
    else:
        pt_from_centroid = False
    c = g.centroid
    for wn, (clon, clat) in WINDOWS.items():
        if abs(c.x - clon) < HALF_LNG and abs(c.y - clat) < HALF_LAT:
            recs.append({"window": wn, "source_record_id": r["source_record_id"],
                         "name": r["小区名称"], "lon": lon, "lat": lat,
                         "pt_from_centroid": pt_from_centroid,
                         "fence_wkt": g.wkt, "fence_area": area_m2(g)})
            break
recs = pd.DataFrame(recs)
print("窗口内采购围栏:", recs.groupby("window").size().to_dict())

# 局部先验: 每条记录用全城同窗近邻(k=5, 排除自身)采购面积中位 —— 只用"训练分布", 不泄漏自身标签
def local_prior(lon, lat, k=5):
    d = np.hypot((recs["lon"] - lon) * M * 0.77, (recs["lat"] - lat) * M)
    idx = d.sort_values().index[1:k+1]
    return float(recs.loc[idx, "fence_area"].median())

recs["prior_area"] = [local_prior(lo, la) for lo, la in zip(recs["lon"], recs["lat"])]

# ---------- 路网街区 (两窗口共用一次加载) ----------
def load_roads():
    lines, seen = [], set()
    for fn in sorted(os.listdir(ROAD_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.loads(open(os.path.join(ROAD_DIR, fn), "rb").read())
        except Exception:
            continue
        for el in data.get("elements", []):
            if el.get("type") != "way" or "geometry" not in el or el["id"] in seen:
                continue
            seen.add(el["id"])
            c = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(c) >= 2:
                lines.append(LineString(c))
    return lines

print("加载路网...")
all_roads = load_roads()

def blocks_for_window(clon, clat, margin=0.003):
    w, s = clon - HALF_LNG - margin, clat - HALF_LAT - margin
    e, n = clon + HALF_LNG + margin, clat + HALF_LAT + margin
    clip = box(w, s, e, n)
    segs = [l.intersection(clip) for l in all_roads]
    segs = [g for g in segs if (not g.is_empty) and g.geom_type in ("LineString", "MultiLineString")]
    merged = unary_union(segs)
    faces = [f for f in polygonize(merged) if f.geom_type == "Polygon"]
    win = box(clon - HALF_LNG, clat - HALF_LAT, clon + HALF_LNG, clat + HALF_LAT)
    inner = [f for f in faces if f.intersection(win).area > 0.5 * f.area]
    return inner, win

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

def clusters_for_window(name):
    polys = load_buildings(name)
    if not polys:
        return []
    buf = unary_union([p.buffer(0.00012) for p in polys])   # ~12m 联通
    parts = list(buf.geoms) if buf.geom_type == "MultiPolygon" else [buf]
    return [p for p in parts if area_m2(p) > 800]           # 去碎屑

results = []
for wn, (clon, clat) in WINDOWS.items():
    sub = recs[recs["window"] == wn]
    print(f"\n=== {wn}: {len(sub)} 条围栏 ===")
    blocks, win = blocks_for_window(clon, clat)
    print(f"  街区块: {len(blocks)}, 面积中位 {np.median([area_m2(b) for b in blocks]):.0f} m²")
    clusters = clusters_for_window(wn)
    print(f"  建筑簇: {len(clusters)}, 面积中位 {np.median([area_m2(c) for c in clusters]):.0f} m²")

    for _, r in sub.iterrows():
        seed = Point(r["lon"], r["lat"])
        target = wkt.loads(r["fence_wkt"])
        row = {"window": wn, "source_record_id": r["source_record_id"], "name": r["name"],
               "fence_area": round(r["fence_area"]), "prior_area": round(r["prior_area"]),
               "pt_from_centroid": r["pt_from_centroid"]}

        # ---- A 代: 街区 ----
        cand = [b for b in blocks if b.contains(seed)]
        if not cand:
            cand = sorted(blocks, key=lambda b: b.distance(seed))[:1]
            blk = cand[0] if cand[0].distance(seed) < 0.0005 else None
        else:
            blk = cand[0]
        # 面积过小则并邻街区 (贪心, 至局部先验的 0.8 倍)
        if blk is not None:
            cur = blk
            guard = 0
            while area_m2(cur) < 0.8 * r["prior_area"] and guard < 4:
                nbrs = sorted([b for b in blocks if b is not cur and b.distance(cur) < 1e-9 and b.intersects(cur)],
                              key=lambda b: b.intersection(cur).length, reverse=True)
                if not nbrs:
                    break
                cur = unary_union([cur, nbrs[0]])
                guard += 1
            a_g = cur
        else:
            a_g = None

        # ---- B 代: 建筑簇 ----
        b_g = None
        if clusters:
            contain = [c for c in clusters if c.contains(seed)]
            if contain:
                b_g = contain[0]
            else:
                near = sorted(clusters, key=lambda c: c.distance(seed))
                if near and near[0].distance(seed) < 0.0015:  # 150m
                    b_g = near[0]
            if b_g is not None:
                b_g = b_g.buffer(0.00008)  # ~8m 院落余量

        # ---- C 代: 先验圆 ----
        rr = math.sqrt(r["prior_area"] / math.pi) / (M * 0.77)
        c_g = seed.buffer(rr)

        for tag, g in (("A_block", a_g), ("B_bldg", b_g), ("C_circle", c_g)):
            if g is None:
                row[f"iou_{tag}"] = np.nan
                row[f"area_{tag}"] = np.nan
                continue
            try:
                g_v = make_valid(g)
                t_v = make_valid(target)
                inter = g_v.intersection(t_v).area
            except Exception:
                inter = 0.0
            row[f"iou_{tag}"] = round(inter / (g_v.area + t_v.area - inter), 3)
            row[f"area_{tag}"] = round(area_m2(g))
            row[f"recall_{tag}"] = round(inter / target.area, 3)
        results.append(row)

out = pd.DataFrame(results)
out.to_csv(OUT, index=False)
print("\n==== 评估汇总 →", OUT)
for tag in ("A_block", "B_bldg", "C_circle"):
    s = out[f"iou_{tag}"].dropna()
    print(f"{tag}: n={len(s)}  IoU 中位 {s.median():.3f}  >0.5 占 {(s>0.5).mean():.0%}  >0.3 占 {(s>0.3).mean():.0%}")
print()
for wn in WINDOWS:
    sub = out[out["window"] == wn]
    print(wn, {t: round(sub[f'iou_{t}'].dropna().median(), 3) for t in ("A_block", "B_bldg", "C_circle")})
