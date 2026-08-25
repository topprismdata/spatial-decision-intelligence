"""Step 2e: 安慰剂检验 — 检验"raw 贴路"是否只是路网密度的巧合.

对每条围栏, 以 raw 位置为基准, 施加旋转后的 GCJ 偏移向量 s_θ (θ=0,90,180,270°):
  θ=0   → raw 本身 (即 H_wgs 检验位置)
  θ≠0   → 安慰剂位置 (假设多边形在某个"旋转 CRS"里 — 现实中不存在)
若 θ≠0 的贴路通过率 ≈ θ=0, 则 WGS84 判定主要是巧合; 若 θ=0 显著高于 θ≠0, 信号真实.
注意 θ=180° 对 GCJ 围栏 = true+2s (双重偏移), 对 WGS 围栏 = true+s (即 GCJ 假设位置).
"""
import sys, os, json, math, time
sys.path.insert(0, "/Users/user/WorkBuddy/2026-08-18-17-47-15")

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt
from shapely.geometry import LineString
from shapely.ops import transform as shp_transform
import shapely

from src.coordinate.transforms import wgs84_to_gcj02

EXCEL = "data/client_a_sites.xlsx"
ROAD_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/roads"
OUT = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/road_placebo_results.csv"

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
pts = [np.asarray(g.segmentize(10.0).coords) for g in lines_m]
kdt = cKDTree(np.vstack(pts))
print(f"路网 {len(lines_m)} way, KDTree {time.time()-t0:.0f}s")

def road_metrics(poly_m):
    parts = list(poly_m.geoms) if poly_m.geom_type == "MultiPolygon" else [poly_m]
    total = sum(p.exterior.length for p in parts)
    n = max(8, min(40, int(total / 60.0) + 1))
    samp = []
    for k in range(n):
        d = total * k / n
        acc = 0.0
        for p in parts:
            L = p.exterior.length
            if d - acc <= L:
                samp.append(p.exterior.interpolate(d - acc)); break
            acc += L
    xy = np.array([(q.x, q.y) for q in samp])
    d, _ = kdt.query(xy)
    return float(np.median(d)), float((d < 30).mean())

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
bj = df[df["城市"].astype(str).str.contains("北京")]
print("北京围栏:", len(bj))

rows = []
t0 = time.time()
for k, (_, r) in enumerate(bj.iterrows()):
    if k % 2000 == 0:
        print(f"  {k}/{len(bj)} {time.time()-t0:.0f}s", flush=True)
    try:
        g_raw = wkt.loads(str(r["坐标面[内置]"]))
        if g_raw.is_empty or g_raw.geom_type not in ("Polygon", "MultiPolygon"):
            continue
    except Exception:
        continue
    c = g_raw.centroid
    gx, gy = wgs84_to_gcj02(c.x, c.y)
    sx = (gx - c.x) * M * math.cos(math.radians(c.y))
    sy = (gy - c.y) * M
    g_m = to_metric(g_raw)
    rec = {"source_record_id": r["source_record_id"]}
    for theta in (0, 90, 180, 270):
        a = math.radians(theta)
        dx = sx * math.cos(a) - sy * math.sin(a)
        dy = sx * math.sin(a) + sy * math.cos(a)
        shifted = shapely.affinity.translate(g_m, dx, dy)
        try:
            med, cov30 = road_metrics(shifted)
        except Exception:
            med, cov30 = None, None
        rec[f"med_{theta}"] = round(med, 1) if med is not None else np.nan
        rec[f"cov30_{theta}"] = round(cov30, 2) if cov30 is not None else np.nan
    rows.append(rec)

out = pd.DataFrame(rows)
out.to_csv(OUT, index=False)
print(f"\n{len(out)} 条 → {OUT}")
print("\n=== 贴路通过率 (med<15 & cov30>=0.6) — 安慰剂对照 ===")
for theta in (0, 90, 180, 270):
    med, cov = out[f"med_{theta}"], out[f"cov30_{theta}"]
    ok = (med < 15) & (cov >= 0.6)
    print(f"θ={theta:3d}°: 通过 {ok.sum():5d} ({100*ok.mean():.1f}%)   med中位 {med.median():.1f}m")
