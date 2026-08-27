"""R16 v2: POI-KDE + concave hull 景区边界重建 (替换圆形兜底)
园区内部设施 POI (长椅/垃圾桶/监控/亭/售票处) 只在围墙内出现 —
它们的分布就是景区真实形状。"""
import warnings; warnings.filterwarnings("ignore")
import os, re, json
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union

FACILITY_WHITELIST = {
    "bench","shelter","waste_basket","toilet","picnic_site","ticket","gate",
    "viewpoint","information","camera_surveillance","drinking_water",
    "hunting_stand","picnic_table","guidepost","atm","telephone",
}

def concave_hull(points: list, k: float = 0.55):
    """简化 Duckham: 距离场内收缩点簇"""
    from shapely.geometry import MultiPoint
    if len(points) < 3:
        return None
    mp = MultiPoint(points)
    hull = mp.convex_hull
    # 直接返回凸包的向内 buffer 收缩 (替代复杂算法; 消除凸包多余真空区)
    area = hull.area
    if area > 0:
        shrink = min(0.30, 300/ max(area**0.5, 1))
        shrunk = hull.buffer(-shrink)
        if not shrunk.is_empty and shrunk.area > 0.3*area:
            return shrunk
    return hull

# ---- 主流程: 对每个 CONSTRUCTED 圆升级为 POI-HULL ----
import json as J

gj_path = "outputs/scenic_spots/beijing_alevel_scenic.geojson"
fc = json.load(open(gj_path))

pois_pts = gpd.read_file("data/beijing_shp/gis_osm_pois_free_1.shp")
print(f"全北京 POI 点: {len(pois_pts)}")

new_features = []
upgraded = 0
kept = []
for f in fc["features"]:
    p = f["properties"]
    if p["disposition"] != "CONSTRUCTED":
        new_features.append(f); kept.append(p["name"]); continue

    # 找到景区点位 (从 CONSTRUCTED 圆心近似)
    geom = f["geometry"]
    if geom["type"] != "Polygon":
        new_features.append(f); continue
    coords = geom["coordinates"][0]
    clng = sum(c[0] for c in coords)/len(coords)
    clat = sum(c[1] for c in coords)/len(coords)

    win = Point(clng,clat).buffer(0.008)  # 800m 窗口
    sub = pois_pts[pois_pts.within(win)]
    facility = sub[sub.fclass.isin(FACILITY_WHITELIST)]
    pts_list = [(p.x,p.y) for p in facility.geometry]

    if len(pts_list) >= 6:
        from src.geometry.concave_hull import hull_for_cluster
        hull = hull_for_cluster(pts_list)
        if hull and not hull.is_empty and hull.geom_type in ("Polygon","MultiPolygon"):
            new_features.append({
                "type":"Feature","geometry":hull.__geo_interface__,
                "properties":{**p,
                    "source":f"POI-HULL({len(pts_list)} facilities)",
                    "conf":0.7}})
            upgraded += 1
            print(f"↑ {p['name'][:20]:22s} {len(pts_list):3d}设施 → POI-HULL ({hull.area*111320**2/10000:.0f}ha)")
            continue

    new_features.append(f)

fc["features"] = new_features
json.dump(fc, open(gj_path,"w"), ensure_ascii=False)
print(f"\n升级完成: {upgraded}/{sum(1 for f in fc['features'] if f['properties']['disposition']=='CONSTRUCTED')} 圆形→POI-HULL")

