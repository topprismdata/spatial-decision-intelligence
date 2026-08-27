"""R16-T3: 路径 A — 名录 ↔ OSM 面层 fuzzy 匹配 (距离 ≤3km 双重校验)"""
import warnings; warnings.filterwarnings("ignore")
import re, os
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

def normalize_name(s):
    s = str(s or "")
    for suf in ["旅游区","风景名胜区","风景区","景区","旅游度假村"]:
        s = s.replace(suf,"")
    return re.sub(r"[（(].*?[)）]", "", s).strip()

def fuzzy(a, b):
    """字符级相似度 (Dice of bigrams)"""
    a2, b2 = set(re.findall(r"..", a)), set(re.findall(r"..", b))
    a2 |= {a[i] for i in range(len(a))} | {"a"}
    b2 |= {b[i] for i in range(len(b))} | {"b"}
    inter = len({a[i:i+2] for i in range(len(a)-1)} & {b[i:i+2] for i in range(len(b)-1)})
    return 2*inter/max(len(a)+len(b)-2,1)

pts = pd.read_csv("outputs/scenic_spots/amap_points.csv")
pts = pts[pts["match"]==1]

# 载入北京全部面层
lu = gpd.read_file("data/beijing_shp/gis_osm_landuse_a_free_1.shp")
pois_a = gpd.read_file("data/beijing_shp/gis_osm_pois_a_free_1.shp")
nat = gpd.read_file("data/beijing_shp/gis_osm_natural_a_free_1.shp")

candidates = []
for _, r in lu.iterrows():
    if r["fclass"] in ("park","forest","grass","recreation_ground","village_green"):
        candidates.append((r["name"] or "", r["fclass"], r.geometry, "landuse"))
for _, r in nat.iterrows():
    if r["fclass"] in ("wood","scrub","wetland","heath"):
        candidates.append((r["name"] or "", r["fclass"], r.geometry, "natural"))
for _, r in pois_a.iterrows():
    if r["fclass"] in ("attraction","museum","memorial","gallery","zoo","aquarium","theme_park","fort","castle","monument"):
        candidates.append((r["name"] or "", r["fclass"], r.geometry, "poi"))

print(f"候选面: {len(candidates)}")

results=[]
for _, spot in pts.iterrows():
    key = normalize_name(spot["primary"])
    plng, plat = float(spot["wgs_lng"]), float(spot["wgs_lat"])
    pt_wgs = Point(plng, plat)
    # 度→米近似: 用投影点
    best=None;best_score=0
    for name,fcls,geom,layer in candidates:
        if not name: continue
        cn = normalize_name(name)
        if not cn: continue
        # 名称相似
        score = fuzzy(key,cn)
        if score < 0.55: continue
        # 距离约束 ≤3km (度): 面质心或边界到点
        d_deg = geom.distance(pt_wgs)
        if d_deg > 3/111.0: continue
        final = score * (1 - min(d_deg*111/3, 0.5))
        if final > best_score:
            best_score=final; best=(name,fcls,geom,layer,score,d_deg)
    if best:
        results.append({"primary":spot["primary"],"grade":spot.grade,
                        "osm_name":best[0],"osm_fclass":best[1],"layer":best[3],
                        "score":round(best[4],2),"dist_km":round(best[5]*111,2),
                        "disposition":"OSM_MATCH",
                        "wkt":best[2].wkt})
        print(f"✓ {spot['primary'][:16]:18s} → {best[0][:20]} ({best[1]}, score={best[4]:.2f}, {best[5]*111:.1f}km)")

out=pd.DataFrame(results)
out.to_csv("outputs/scenic_spots/osm_matches.csv",index=False)
print(f"\n路径A命中: {len(out)}/{len(pts)}")
