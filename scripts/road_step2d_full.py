"""Step 2d: 全量北京围栏双假设 CRS 普查（不限 NARROW_STRIP）.

对每条北京围栏多边形测两个假设:
  H_gcj: 原始坐标是 GCJ-02 → gcj→wgs 转换后与 OSM 路网嵌合
  H_wgs: 原始坐标已是 WGS-84 → 原始坐标直接与路网嵌合
度量(块状围栏用边界贴路度, 窄条用轴线也行但统一用边界):
  边界每 60m 采样(8..40 点), 到最近车行道路的距离 → med / cov30(边界30m内占比)
  主干道(motorway/trunk/primary/secondary 含link)在多边形内的长度 → 真小区≈0
路网统一转局部米制坐标(北京原点), KDTree 最近查询, 精确到米.
"""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, os, json, math, time
sys.path.insert(0, str(_REPO))

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import wkt, make_valid
from shapely.geometry import LineString
from shapely.strtree import STRtree
from shapely.ops import transform as shp_transform

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
QA = str(_REPO / 'outputs/qa_issues_report.csv')
ROAD_DIR = str(_REPO / 'data/roads')
OUT = str(_REPO / 'outputs/road_alignment_beijing_full.csv')

LON0, LAT0 = 116.40, 39.90
M = 111320.0

def to_metric(geom):
    def _t(x, y, z=None):
        return ((x - LON0) * M * math.cos(math.radians(y)),
                (y - LAT0) * M)
    return shp_transform(_t, geom)

# ---------- 1. 路网 (米制) ----------
t0 = time.time()
ways, seen = [], set()          # (geom_metric, is_major)
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
        hw = el.get("tags", {}).get("highway", "")
        is_major = hw.split("_")[0] in ("motorway", "trunk", "primary", "secondary")
        c = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(c) >= 2:
            ways.append((LineString(c), is_major))

lines_m = [to_metric(g) for g, _ in ways]
major_flags = [f for _, f in ways]
total_km = sum(g.length for g in lines_m) / 1000.0
print(f"路网 way: {len(ways)} 条, 总长 {total_km:.0f} km, 加载 {time.time()-t0:.0f}s")

# KDTree: 沿线每 10m 采点
t0 = time.time()
pts = []
for g in lines_m:
    dens = g.segmentize(10.0)
    pts.append(np.asarray(dens.coords))
P = np.vstack(pts)
kdt = cKDTree(P)
print(f"KDTree: {len(P)/1e6:.2f}M 点, {time.time()-t0:.0f}s")

majors = [g for g, f in zip(lines_m, major_flags) if f]
major_tree = STRtree(majors)
print(f"主干道 way: {len(majors)} 条")

def road_metrics(poly_m):
    """边界采样 → (med, cov30, cov15, p90) 米."""
    perim = poly_m.length
    n = max(8, min(40, int(perim / 60.0) + 1))
    # 沿外边界均匀采样
    try:
        if poly_m.geom_type == "MultiPolygon":
            parts = list(poly_m.geoms)
        else:
            parts = [poly_m]
        samp = []
        for part in parts:
            ring = part.exterior
            step = max(1, int(ring.length / max(1, n / len(parts))))
            for i in range(int(ring.length / 60.0) + 1):
                samp.append(ring.interpolate(min(i * 60.0, ring.length - 1e-6)))
            # 简化: 每 60m 一个
        # 统一改用按总周长均匀采样
        samp = []
        total = sum(p.exterior.length for p in parts)
        for k in range(n):
            d = total * k / n
            acc = 0.0
            for p in parts:
                L = p.exterior.length
                if d - acc <= L:
                    samp.append(p.exterior.interpolate(d - acc))
                    break
                acc += L
        xy = np.array([(q.x, q.y) for q in samp])
    except Exception:
        return None
    d, _ = kdt.query(xy)
    return (float(np.median(d)), float((d < 30).mean()),
            float((d < 15).mean()), float(np.percentile(d, 90)))

def major_len_km(poly_m):
    try:
        poly_m = make_valid(poly_m)
    except Exception:
        pass
    try:
        idxs = major_tree.query(poly_m)
    except Exception:
        return 0.0
    tot = 0.0
    for i in idxs:
        try:
            g = majors[int(i)].intersection(poly_m)
        except Exception:
            continue
        if g.is_empty:
            continue
        tot += g.length if g.geom_type == "LineString" else sum(s.length for s in getattr(g, "geoms", []))
    return tot / 1000.0

# ---------- 2. 北京围栏 ----------
df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
qa = pd.read_csv(QA, usecols=["source_record_id", "qa_issues"])
bj = df[df["城市"].astype(str).str.contains("北京")].merge(qa, on="source_record_id", how="left")
print("北京围栏:", len(bj))

rows = []
t0 = time.time()
for k, (_, r) in enumerate(bj.iterrows()):
    if k % 1000 == 0:
        print(f"  {k}/{len(bj)} {time.time()-t0:.0f}s", flush=True)
    try:
        g_raw = wkt.loads(str(r["坐标面[内置]"]))
        if g_raw.is_empty or g_raw.geom_type not in ("Polygon", "MultiPolygon"):
            continue
    except Exception:
        continue
    try:
        wgs = wkt.loads(transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84))
    except Exception:
        continue
    raw_m = to_metric(g_raw)
    wgs_m = to_metric(wgs)

    try:
        mr = road_metrics(raw_m)
        mt = road_metrics(wgs_m)
    except Exception:
        continue
    if mr is None or mt is None:
        continue
    med_r, cov30_r, cov15_r, p90_r = mr
    med_t, cov30_t, cov15_t, p90_t = mt

    rows.append({
        "source_record_id": r["source_record_id"], "name": r["小区名称"],
        "perim_m": round(raw_m.length, 0),
        "med_r": round(med_r, 1), "cov30_r": round(cov30_r, 2),
        "med_t": round(med_t, 1), "cov30_t": round(cov30_t, 2),
        "major_km_r": round(major_len_km(raw_m), 2),
        "major_km_t": round(major_len_km(wgs_m), 2),
        "narrow": int("NARROW_STRIP" in str(r["qa_issues"])),
    })

out = pd.DataFrame(rows)
out.to_csv(OUT, index=False)
print(f"\n完成 {len(out)} 条 → {OUT}  ({time.time()-t0:.0f}s)")
print("\nmed_t 分位数:", out["med_t"].quantile([.1, .25, .5, .75, .9]).round(1).to_dict())
print("med_r 分位数:", out["med_r"].quantile([.1, .25, .5, .75, .9]).round(1).to_dict())
