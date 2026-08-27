"""R16 v3: Road-Block + POI-Fingerprint + Visual-Judge
以回龙观体育公园为试点跑通, 然后推广到所有 CONSTRUCTED 景区."""
import warnings; warnings.filterwarnings("ignore")
import json, os, re
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import unary_union, polygonize
from src.geometry.concave_hull import hull_for_cluster

# ---- 输入 ----
SCENIC_JSON = "outputs/scenic_spots/beijing_alevel_scenic.geojson"
ROADS_SHP   = "data/beijing_shp/gis_osm_roads_free_1.shp"
POIS_SHP    = "data/beijing_shp/gis_osm_pois_free_1.shp"

EXCLUDE_ROADS = {"footway","cycleway","path","steps","pedestrian","track"}
FACILITY = {"bench","shelter","waste_basket","toilet","picnic_site","gate",
            "viewpoint","ticket","information","camera_surveillance","atm",
            "drinking_water","monument","memorial"}

def road_blocks(center_lng, center_lat, radius_m=1000):
    """生成景区周边道路切块"""
    roads = gpd.read_file(ROADS_SHP)
    pt = Point(center_lng, center_lat).buffer(radius_m/111000.0)
    sub = roads[roads.intersects(pt) & ~roads.fclass.isin(EXCLUDE_ROADS)]
    if len(sub)==0:
        return []
    buffered = sub.geometry.buffer(6/111000.0)
    unioned = unary_union(buffered.values.tolist())
    return [g for g in polygonize(unioned)]

def poi_fingerprint(blocks, center_lng, center_lat, radius_m=600):
    """POI 指纹打分到 block"""
    pois = gpd.read_file(POIS_SHP)
    pt = Point(center_lng, center_lat).buffer(radius_m/111000.0)
    sub = pois[pois.within(pt)]
    fac = sub[sub.fclass.isin(FACILITY)]
    scored=[]
    for b in blocks:
        cnt = sum(b.contains(Point(p.x,p.y)) for p in fac.geometry)
        scored.append((b,cnt))
    return scored

def boundary_for_spot(spot_name, lng, lat, grade="4A"):
    """主入口: 返回最优边界 WKT 或 None"""
    blocks = road_blocks(lng, lat, 1000)
    if not blocks:
        print(f"  ✗ {spot_name[:18]}: 无路网切块")
        return None
    scored = poi_fingerprint(blocks, lng, lat, 800)

    # 选择含最多设施 POI 的 top-k 相邻 block 合并
    ranked = sorted(scored, key=lambda x:-x[1])
    chosen = [b for b,c in ranked[:5] if c>=2]
    if len(chosen) < 2:
        # 兜底: 只取最高分单块
        if ranked and ranked[0][1]>=1:
            chosen=[ranked[0][0]]
        else:
            return None
    merged = unary_union(chosen)
    # 凹包收缩
    pts = [(c[0],c[1]) for c in merged.exterior.coords]
    hull = hull_for_cluster(pts, k=0.65)
    return hull.wkt if (hull and not hull.is_empty) else None

if __name__ == "__main__":
    # 单例测试: 回龙观体育公园
    name = "回龙观体育公园"
    wkt_out = boundary_for_spot(name, 116.3489, 40.0862)
    if wkt_out:
        from shapely import wkt as _wkt
        g=_wkt.loads(wkt_out)
        print(f"✓ {name}: {g.geom_type}, area={g.area*111320**2:.0f} m²")
        with open("outputs/scenic_spots/road_block_test.wkt","w") as f: f.write(wkt_out)
