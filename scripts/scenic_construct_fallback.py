"""R16-T4: 路径C/D — 无 OSM 面的景区用 POI 投票面 或 类型化半径构造"""
import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd, geopandas as gpd
from shapely.geometry import Point

pts = pd.read_csv("outputs/scenic_spots/amap_points.csv")
osm = pd.read_csv("outputs/scenic_spots/osm_matches.csv")
matched = set(osm["primary"])

# 类型相关默认半径(米): 场馆小, 山岳大
TYPE_RADIUS = {
    "博物馆": 200, "纪念馆": 250, "故居": 150, "寺": 300, "庙": 250,
    "公园": 500, "园": 400, "山": 1000, "峡": 1200, "湖": 800,
    "洞": 600, "长城": 1500, "谷": 1000, "潭": 500, "度假": 800,
    "温泉": 500, "森林": 1500, "遗址": 600,
}
def radius_for(name):
    n=str(name or "")
    for k,v in TYPE_RADIUS.items():
        if k in n: return v
    return 400

new_rows=[]
for _,r in pts.iterrows():
    p=r["primary"]
    if p in matched: continue
    if r["match"]!=1:
        # 连点都没有 → NOT_FOUND
        new_rows.append({"primary":p,"grade":r.grade,"disposition":"NOT_FOUND","wkt":""})
        continue
    rad = radius_for(r["amap_name"] or p)
    circle = Point(float(r.wgs_lng), float(r.wgs_lat)).buffer(rad/111320.0)
    new_rows.append({"primary":p,"grade":r.grade,
                     "disposition":"CONSTRUCTED",
                     "wkt":circle.wkt,
                     "radius_m":rad})
nd=pd.DataFrame(new_rows)
out="outputs/scenic_spots/fallback_rows.csv"
old=pd.read_csv(out) if os.path.exists(out) else pd.DataFrame()
res=pd.concat([old,nd],ignore_index=True).drop_duplicates("primary")
res.to_csv(out,index=False)
print(f"\nCONSTRUCTED: {(res.disposition=='CONSTRUCTED').sum()}, NOT_FOUND: {(res.disposition=='NOT_FOUND').sum()}")
