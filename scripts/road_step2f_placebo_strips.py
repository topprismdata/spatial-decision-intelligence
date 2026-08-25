"""Step 2f: 窄条轴线检验的安慰剂 + 逐围栏蒙特卡洛 p 值.

对 2b 的北京 NARROW_STRIP 集合, 轴线(缓冲侵蚀骨架/矩形长轴)在每个假设位置测 med:
  raw 本身 (H_wgs), raw−s (H_gcj), raw+rot(s,θ) θ=8 个角度 (安慰剂)
输出:
  1) 群体层面: H_wgs 通过率 vs 安慰剂通过率 → 信号是否超过巧合
  2) 逐围栏: raw 的 med 在 {安慰剂 meds} 中的秩 → 经验 p 值 (越小越真实)
"""
import sys, os, json, math, time
sys.path.insert(0, "/Users/user/WorkBuddy/2026-08-18-17-47-15")

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt
from shapely.geometry import LineString, Point
from shapely.ops import transform as shp_transform
import shapely

from src.coordinate.transforms import gcj02_to_wgs84, transform_geometry_wkt

EXCEL = "data/client_a_sites.xlsx"
QA = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/qa_issues_report.csv"
ROAD_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/roads"
OUT = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/road_placebo_strips.csv"

LON0, LAT0 = 116.40, 39.90
M = 111320.0

def to_metric(geom):
    def _t(x, y, z=None):
        return ((x - LON0) * M * math.cos(math.radians(y)), (y - LAT0) * M)
    return shp_transform(_t, geom)

t0 = time.time()
ways, seen = [], set()
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
            ways.append(LineString(c))
lines_m = [to_metric(g) for g in ways]
kdt = cKDTree(np.vstack([np.asarray(g.segmentize(10.0).coords) for g in lines_m]))
print(f"路网 {len(lines_m)} way, {time.time()-t0:.0f}s")

def axis_med_m(axis_pts_m):
    xy = np.array([(p.x, p.y) for p in axis_pts_m])
    d, _ = kdt.query(xy)
    return float(np.median(d))

def centerline_points_m(geom_m, max_width_m):
    """在米制空间做骨架 (2b 逻辑的米制版)."""
    if max_width_m and max_width_m >= 8:
        try:
            eroded = geom_m.buffer(-0.35 * max_width_m)
            if not eroded.is_empty and eroded.geom_type in ("Polygon", "MultiPolygon"):
                dens = eroded.segmentize(max(1.5 * 0.35 * max_width_m, 20.0))
                if dens.geom_type == "MultiPolygon":
                    dens = max(dens.geoms, key=lambda g: g.area)
                pts = list(dens.exterior.coords)
                if len(pts) >= 4:
                    step = 20.0
                    out, acc = [], 0.0
                    for i in range(len(pts) - 1):
                        acc += math.dist(pts[i], pts[i + 1])
                        if acc >= step:
                            out.append(Point((pts[i][0] + pts[i + 1][0]) / 2,
                                             (pts[i][1] + pts[i + 1][1]) / 2))
                            acc = 0.0
                    if len(out) >= 5:
                        return out
        except Exception:
            pass
    rect = geom_m.minimum_rotated_rectangle
    try:
        coords = list(rect.exterior.coords)
    except Exception:
        return None
    pts = coords[:-1]
    edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    e_sorted = sorted(edges, key=lambda e: math.dist(e[0], e[1]), reverse=True)
    (x1, y1), (x2, y2) = e_sorted[0]
    (x3, y3), (x4, y4) = e_sorted[1]
    axis = LineString([((x1 + x2) / 2, (y1 + y2) / 2), ((x3 + x4) / 2, (y3 + y4) / 2)])
    n = max(int(axis.length / 20.0), 2)
    return [axis.interpolate(t / n, normalized=True) for t in range(n + 1)]

# 北京 NARROW_STRIP
df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
qa = pd.read_csv(QA)
m = qa.merge(df[["source_record_id", "小区名称", "城市", "坐标面[内置]"]], on="source_record_id", how="left")
m = m[m["坐标面[内置]"].notna() & (m["坐标面[内置]"].astype(str).str.len() > 10)]
bj_ns = m[m["城市"].astype(str).str.contains("北京") & m["qa_issues"].str.contains("NARROW_STRIP")]
print("北京 NARROW_STRIP:", len(bj_ns))

ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
rows = []
t0 = time.time()
for k, (_, r) in enumerate(bj_ns.iterrows()):
    if k % 100 == 0:
        print(f"  {k}/{len(bj_ns)} {time.time()-t0:.0f}s", flush=True)
    try:
        g_raw = wkt.loads(str(r["坐标面[内置]"]))
        if g_raw.is_empty or g_raw.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        wgs = wkt.loads(transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84))
    except Exception:
        continue
    mw = r.get("max_width_m")
    mw = float(mw) if pd.notnull(mw) else None

    raw_m = to_metric(g_raw)
    wgs_m = to_metric(wgs)
    ax_r = centerline_points_m(raw_m, mw)
    ax_t = centerline_points_m(wgs_m, mw)
    if not ax_r or len(ax_r) < 5 or not ax_t or len(ax_t) < 5:
        continue

    c = g_raw.centroid
    gx, gy = gcj02_to_wgs84(c.x, c.y)
    sx = (c.x - gx) * M * math.cos(math.radians(c.y))   # wgs→gcj 的逆: raw−s = wgs
    sy = (c.y - gy) * M
    # 注意: g_raw 是 GCJ 假设下的原始坐标; s = gcj − wgs → (gx,gy)=wgs, s=(c−gx, c−gy)
    # raw − s = wgs 位置; 安慰剂: raw + rot(−s, θ)

    med_raw = axis_med_m(ax_r)          # H_wgs 位置
    med_tfm = axis_med_m(ax_t)          # H_gcj 位置 (raw − s)
    pl_meds = {}
    for theta in ANGLES:
        a = math.radians(theta)
        dx = -sx * math.cos(a) + sy * math.sin(a)
        dy = -sx * math.sin(a) - sy * math.cos(a)
        shifted = shapely.affinity.translate(raw_m, dx, dy)
        ax_p = centerline_points_m(shifted, mw)
        if not ax_p or len(ax_p) < 5:
            continue
        pl_meds[theta] = axis_med_m(ax_p)

    pl_vals = np.array(list(pl_meds.values()))
    # raw 的 med 在安慰剂中的秩 (越小越极端)
    rank = int((pl_vals < med_raw).sum())
    p_emp = rank / (len(pl_vals) + 1)

    rows.append({
        "source_record_id": r["source_record_id"], "name": r["小区名称"],
        "med_raw": round(med_raw, 1), "med_tfm": round(med_tfm, 1),
        "placebo_med_med": round(float(np.median(pl_vals)), 1),
        "placebo_min": round(float(pl_vals.min()), 1),
        "p_emp": round(p_emp, 3),
        "n_placebo": len(pl_vals),
        **{f"pl_{t}": round(v, 1) for t, v in pl_meds.items()},
    })

out = pd.DataFrame(rows)
out.to_csv(OUT, index=False)
print(f"\n{len(out)} 条 → {OUT}")

print("\n=== 群体: 轴线 med<15 通过率 ===")
print(f"H_wgs (raw):        {100*(out['med_raw']<15).mean():.1f}%")
print(f"H_gcj (raw−s):      {100*(out['med_tfm']<15).mean():.1f}%")
for theta in ANGLES:
    print(f"placebo θ={theta:3d}°:  {100*(out[f'pl_{theta}']<15).mean():.1f}%")
print(f"placebo 最优方向:   {100*(out['placebo_min']<15).mean():.1f}%  (每条取8个方向最小med)")
print("\n=== 逐围栏 p 值分布 (raw 相对安慰剂) ===")
print(out["p_emp"].value_counts().sort_index().to_string())
sig = out[out["p_emp"] <= 0.11]
print(f"\np≤0.11 (raw 比全部8个安慰剂都贴路): {len(sig)} 条")
print(sig.nsmallest(12, "med_raw")[["source_record_id", "name", "med_raw", "med_tfm", "placebo_min"]].to_string(index=False))
