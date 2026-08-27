"""R16 v3: 骨架(路网切块) + POI指纹(TF-IDF) + 视觉裁决 三层证据管线."""
import warnings; warnings.filterwarnings("ignore")
import json, os, re, math
from collections import Counter
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from shapely.ops import unary_union, polygonize
from src.geometry.concave_hull import hull_for_cluster

# ── 常量配置 ──
ROADS_SHP = "data/beijing_shp/gis_osm_roads_free_1.shp"
POIS_SHP  = "data/beijing_shp/gis_osm_pois_free_1.shp"
EXCLUDE   = {"footway","cycleway","path","steps","pedestrian","track"}
ROAD_BUFFER_M = {"motorway":10,"trunk":10,"primary":8,"secondary":8,
                 "tertiary":6,"residential":5,"living_street":4,"service":4}
FACILITY_STRONG = {"bench","shelter","waste_basket","toilet","picnic_site",
                   "gate","viewpoint","ticket","information","monument","memorial",
                   "camera_surveillance","artwork","attraction"}
FACILITY_MEDIUM = {"restaurant","cafe","fast_food","kiosk","gift_shop",
                   "marketplace","parking","bus_stop"}

def road_blocks(lng,lat,radius_m=1200):
    roads=gpd.read_file(ROADS_SHP)
    win=Point(lng,lat).buffer(radius_m/111000.0)
    sub=roads[roads.intersects(win)]
    geoms=[]
    for _,r in sub.iterrows():
        buf_m=ROAD_BUFFER_M.get(r.fclass,6)
        geoms.append(r.geometry.buffer(buf_m/111000.0))
    if not geoms: return []
    u=unary_union(geoms)
    return list(polygonize(u))

def poi_fingerprint_score(blocks, lng, lat, radius_m=800):
    pois=gpd.read_file(POIS_SHP)
    win=Point(lng,lat).buffer(radius_m/111000.0)
    sub=pois[pois.within(win)]
    # TF-IDF 简化: 分配 POI 到 block; 计算景区性得分
    results=[]
    strong = FACILITY_STRONG
    medium = FACILITY_MEDIUM
    for b in blocks:
        s_strong = sum(b.contains(Point(p.x,p.y)) for p in sub[sub.fclass.isin(strong)].geometry)
        s_medium = sum(b.contains(Point(p.x,p.y)) for p in sub[sub.fclass.isin(medium)].geometry)
        score = 3*s_strong + 1*s_medium
        results.append((b,score,s_strong))
    return results

def build_boundary(lng, lat, min_block_score=3):
    """构建边界: 路网切块 + POI 指纹加权 + 合并"""
    blocks = road_blocks(lng,lat)
    if not blocks:
        return None, []
    scored = poi_fingerprint_score(blocks,lng,lat,min_block_score*2)
    picked=[b for b,s,_ in scored if s>=min_block_score]
    if len(picked)<1:
        return None, scored
    merged=unary_union(picked)
    pts=[(c[0],c[1]) for c in merged.exterior.coords]
    hull=hull_for_cluster(pts)
    return hull,scored
