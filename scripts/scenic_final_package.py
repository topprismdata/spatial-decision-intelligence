"""R16-T6: 汇总 GeoJSON (OSM_MATCH + CONSTRUCTED + NOT_FOUND 点标记) + 分类地图"""
import warnings; warnings.filterwarnings("ignore")
import json, os, re
import pandas as pd, geopandas as gpd
from shapely import wkt as _wkt
from shapely.geometry import Point

os.makedirs("outputs/scenic_spots", exist_ok=True)
pts = pd.read_csv("outputs/scenic_spots/amap_points.csv")
osm = pd.read_csv("outputs/scenic_spots/osm_matches.csv")
fb  = pd.read_csv("outputs/scenic_spots/fallback_rows.csv")

features=[]
# OSM 面级
for _,r in osm.iterrows():
    g=_wkt.loads(r.wkt)
    p=pts[pts.primary==r.primary].iloc[0]
    features.append({"type":"Feature","geometry":g.__geo_interface__,
        "properties":{"name":r.primary,"grade":r.grade,"amap_name":p.amap_name,
                      "district":p.district,"disposition":"OSM_MATCH",
                      "source":f"{r.osm_fclass}({r.layer})","conf":float(r.score),
                      "area_m2":round(g.area*111320**2 if False else 0)}})
# CONSTRUCTED 圆形
for _,r in fb[fb.disposition=="CONSTRUCTED"].iterrows():
    g=_wkt.loads(r.wkt)
    p=pts[pts.primary==r.primary].iloc[0]
    features.append({"type":"Feature","geometry":g.__geo_interface__,
        "properties":{"name":r.primary,"grade":r.grade,"amap_name":p.amap_name,
                      "district":p.district,"disposition":"CONSTRUCTED",
                      "source":f"buffer {r.radius_m}m","conf":0.4,
                      "radius_m":int(r.radius_m)}})
# NOT_FOUND 用点标记
nf = fb[fb.disposition=="NOT_FOUND"]
for _,r in nf.iterrows():
    p=pts[pts.primary==r.primary]
    # NOT_FOUND 无高德点 → 只能登记名称
    features.append({"type":"Feature","geometry":{"type":"Point","coordinates":[0,0]},
        "properties":{"name":r.primary,"grade":r.grade,"amap_name":"","district":"",
                      "disposition":"NOT_FOUND","source":"no geocode","conf":0}})

fc={"type":"FeatureCollection","features":[f for f in features if f["geometry"]["coordinates"]!=[0,0]]}
gj="outputs/scenic_spots/beijing_alevel_scenic.geojson"
json.dump(fc, open(gj,"w"), ensure_ascii=False)
print(f"GeoJSON: {len(fc['features'])} features -> {gj}")

from collections import Counter
disp = Counter(f["properties"]["disposition"] for f in fc["features"])
print("Disposition 分布:", dict(disp))
print("\nNOT_FOUND 清单:", nf.primary.tolist())
