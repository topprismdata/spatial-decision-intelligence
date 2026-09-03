"""Step 2b v2: 双假设 CRS 甄别 + 三类打标（北京 NARROW_STRIP）.

对每个窄条围栏同时测两个假设:
  H_gcj: 多边形原始坐标为 GCJ-02 → 转换后与路网对齐
  H_wgs: 多边形原始坐标已是 WGS-84 → 原始坐标直接与路网对齐
判定:
  ROAD_ALIGNED        H_gcj 成立 (当前处理正确)
  POLYGON_CRS_WGS84   H_wgs 成立 (被误转换 ~500m!)  ← 新发现
  ORPHAN_STRIP        两假设都不成立 + 路网密度护栏通过
  ORPHAN_UNCERTAIN    两假设都不成立 + 路网稀疏
轴线: 缓冲侵蚀骨架法, 退路最小外接矩形长轴.
"""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, os, json, math
import numpy as np
sys.path.insert(0, str(_REPO))

import pandas as pd
from shapely import wkt
from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
QA = str(_REPO / 'outputs/qa_issues_report.csv')
ROAD_DIR = str(_REPO / 'data/roads')
OUT = str(_REPO / 'outputs/road_alignment_beijing.csv')

M_PER_DEG_LAT = 111320.0
def m2deg_lng(m, lat): return m / (111320.0 * math.cos(math.radians(lat)))

# ---------- 1. 路网 ----------
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
road_tree = STRtree(lines)
print(f"路网: {len(lines)} 条 way")

def nearest_m(p):
    idx, d = road_tree.query_nearest(p, return_distance=True, all_matches=False)
    dd = float(np.atleast_1d(d)[0]) if np.ndim(d) else float(d)
    # 度→米（lat 分量 111320, lng 分量带 cos 修正——用中纬近似, 误差 <1%）
    return dd * M_PER_DEG_LAT

def nearest_pt(p):
    """返回 (距离m, 最近点 shapely Point)。"""
    idx, d = road_tree.query_nearest(p, return_distance=True, all_matches=False)
    i = int(idx[0]) if isinstance(idx, np.ndarray) else int(idx)
    road = lines[i]
    # 沿路网采样找最近点（路网折线上的真投影）
    best, bd = None, 1e18
    seg = road.segmentize(0.00005)
    for c in seg.coords:
        dd = math.hypot((c[0]-p.x) * 111320.0 * math.cos(math.radians(p.y)), (c[1]-p.y) * M_PER_DEG_LAT)
        if dd < bd:
            bd, best = dd, Point(c)
    return bd, best

def road_len_km(poly):
    idxs = road_tree.query(poly)
    total = 0.0
    for i in idxs:
        g = lines[i].intersection(poly)
        if g.is_empty:
            continue
        total += g.length if g.geom_type == "LineString" else sum(s.length for s in getattr(g, "geoms", []))
    lat = poly.centroid.y
    return total * M_PER_DEG_LAT * math.cos(math.radians(lat)) / 1000.0

# ---------- 2. 北京 NARROW_STRIP ----------
df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
qa = pd.read_csv(QA)
m = qa.merge(df[["source_record_id", "小区名称", "城市", "坐标面[内置]"]], on="source_record_id", how="left")
m = m[m["坐标面[内置]"].notna() & (m["坐标面[内置]"].astype(str).str.len() > 10)]
bj_ns = m[m["城市"].astype(str).str.contains("北京") & m["qa_issues"].str.contains("NARROW_STRIP")]
print("北京 NARROW_STRIP:", len(bj_ns))

def centerline_points(geom, max_width_m):
    lat = geom.centroid.y
    erode_deg = m2deg_lng(0.35 * max_width_m, lat) if max_width_m else None
    if erode_deg and max_width_m and max_width_m >= 8:
        try:
            eroded = geom.buffer(-erode_deg)
            if not eroded.is_empty and eroded.geom_type in ("Polygon", "MultiPolygon"):
                dens = eroded.segmentize(max(1.5 * erode_deg, 0.0002))
                if dens.geom_type == "MultiPolygon":
                    dens = max(dens.geoms, key=lambda g: g.area)
                pts = list(dens.exterior.coords)
                if len(pts) >= 4:
                    step_deg = m2deg_lng(20.0, lat)
                    out, acc = [], 0.0
                    for i in range(len(pts) - 1):
                        x1, y1 = pts[i]; x2, y2 = pts[i + 1]
                        acc += math.hypot(x2 - x1, y2 - y1)
                        if acc >= step_deg:
                            out.append(Point((x1 + x2) / 2, (y1 + y2) / 2)); acc = 0.0
                    if len(out) >= 5:
                        return out, "eroded_boundary"
        except Exception:
            pass
    rect = geom.minimum_rotated_rectangle
    try:
        coords = list(rect.exterior.coords)
    except Exception:
        return None, None
    pts = coords[:-1]
    edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    e_sorted = sorted(edges, key=lambda e: math.dist(e[0], e[1]), reverse=True)
    (x1, y1), (x2, y2) = e_sorted[0]
    (x3, y3), (x4, y4) = e_sorted[1]
    axis = LineString([((x1 + x2) / 2, (y1 + y2) / 2), ((x3 + x4) / 2, (y3 + y4) / 2)])
    n = max(int(axis.length / m2deg_lng(20.0, lat)), 2)
    return [axis.interpolate(t / n, normalized=True) for t in range(n + 1)], "rect_axis"

def measure(pts):
    """(med, p90, cov15, mean_dx, mean_dy) 米."""
    dists, dxs, dys = [], [], []
    for p in pts:
        d, q = nearest_pt(p)
        dists.append(d)
        dxs.append((q.x - p.x) * 111320.0 * math.cos(math.radians(p.y)))
        dys.append((q.y - p.y) * M_PER_DEG_LAT)
    ds = sorted(dists)
    k = len(ds)
    return (ds[k // 2], ds[int(k * 0.9)],
            sum(1 for d in dists if d < 15) / k,
            sum(dxs) / k, sum(dys) / k)

rows, drop = [], {"parse": 0, "axis": 0}
for _, r in bj_ns.iterrows():
    try:
        g_raw = wkt.loads(str(r["坐标面[内置]"]))
    except Exception:
        drop["parse"] += 1; continue
    if g_raw.is_empty or g_raw.geom_type not in ("Polygon", "MultiPolygon"):
        drop["parse"] += 1; continue
    wgs = transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84)
    if not wgs:
        drop["parse"] += 1; continue
    g_t = wkt.loads(wgs)

    mw = r.get("max_width_m")
    mw = float(mw) if pd.notnull(mw) else None

    pts_t, meth_t = centerline_points(g_t, mw)
    pts_r, meth_r = centerline_points(g_raw, mw)
    if not pts_t or len(pts_t) < 5 or not pts_r or len(pts_r) < 5:
        drop["axis"] += 1; continue

    med_t, p90_t, cov_t, dx_t, dy_t = measure(pts_t)
    med_r, p90_r, cov_r, dx_r, dy_r = measure(pts_r)

    # 路网密度护栏
    minx, miny, maxx, maxy = g_t.bounds
    pad = m2deg_lng(500, (miny + maxy) / 2)
    guard = box(minx - pad, miny - pad / 1.4, maxx + pad, maxy + pad / 1.4)
    area_km2 = guard.area * (M_PER_DEG_LAT ** 2) * math.cos(math.radians((miny + maxy) / 2)) / 1e6
    density = road_len_km(guard) / area_km2 if area_km2 > 0 else 0.0
    density_ok = density >= 3.0

    # 双假设判定
    gcj_hyp = med_t < 15 and cov_t >= 0.7
    wgs_hyp = med_r < 15 and cov_r >= 0.7
    if gcj_hyp:
        label = "ROAD_ALIGNED"
    elif wgs_hyp:
        label = "POLYGON_CRS_WGS84"
    elif med_r < 0.5 * med_t and med_r < 60:
        label = "POLYGON_CRS_WGS84_PROBABLE"
    elif min(med_t, med_r) < 50:
        label = "NONE"  # 不够贴也不够远，留白
    elif density_ok:
        label = "ORPHAN_STRIP"
    else:
        label = "ORPHAN_UNCERTAIN"

    rows.append({
        "source_record_id": r["source_record_id"], "name": r["小区名称"],
        "axle_method": meth_t, "n_pts": len(pts_t),
        "med_t": round(med_t, 1), "cov_t": round(cov_t, 2),
        "med_r": round(med_r, 1), "cov_r": round(cov_r, 2),
        "dx_t": round(dx_t, 1), "dy_t": round(dy_t, 1),
        "road_density": round(density, 1), "road_guard_ok": density_ok,
        "label": label,
    })

out = pd.DataFrame(rows)
out.to_csv(OUT, index=False)
print(f"\n打标 {len(out)} 条 (drop: {drop}) → {OUT}")
print("\n标签分布:")
print(out["label"].value_counts().to_string())
print("\nPOLYGON_CRS_WGS84 样例 8 条 (med_r 升序):")
sub = out[out["label"].str.startswith("POLYGON_CRS_WGS84")].nsmallest(8, "med_r")
print(sub[["source_record_id", "name", "med_t", "med_r"]].to_string(index=False))
print("\nORPHAN_STRIP top8 (med_t 降序):")
sub = out[out["label"] == "ORPHAN_STRIP"].nlargest(8, "med_t")
print(sub[["source_record_id", "name", "med_t", "med_r", "road_density"]].to_string(index=False))
print("\nROAD_ALIGNED 样例 5 条:")
sub = out[out["label"] == "ROAD_ALIGNED"].nsmallest(5, "med_t")
print(sub[["source_record_id", "name", "med_t", "cov_t"]].to_string(index=False))
