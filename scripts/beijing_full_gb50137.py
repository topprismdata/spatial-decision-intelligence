"""全北京 GB50137 分类: landuse + POI面 + transport → 统一 GeoJSON"""
import warnings; warnings.filterwarnings("ignore")
import geopandas as gpd, pandas as pd, json, os, time
from collections import Counter

t0 = time.time()

LANDUSE_GB = {
    "residential":"R","retail":"B1","commercial":"B2","industrial":"M",
    "park":"G","forest":"G","grass":"G","meadow":"G","scrub":"G",
    "orchard":"G","recreation_ground":"G","village_green":"G",
    "military":"MIL","farmland":"AGR","farmyard":"AGR","quarry":"M",
    "cemetery":"U","landfill":"U","vineyard":"AGR","allotments":"AGR",
    "railway":"S","education":"A3","hospital":"A5",
}
POI_GB = {
    "school":"A3","university":"A3","college":"A3","kindergarten":"A3",
    "hospital":"A5","clinic":"A5","dentist":"A5","doctors":"A5",
    "stadium":"A4","pitch":"A4","track":"A4","sports_centre":"A4",
    "library":"A4","museum":"A4","theatre":"A4","community_centre":"A4",
    "bus_station":"S","railway_station":"S","airport":"S","ferry_terminal":"S",
}
GB_CN = {
    "R":"居住用地","B1":"商业服务用地","B2":"商务办公用地","M":"工业用地",
    "S":"交通枢纽用地","A3":"教育科研用地","A4":"体育文化用地",
    "A5":"医疗卫生用地","G":"公园与绿地","MIL":"军事用地","AGR":"农林业用地","U":"未分类"
}

# Step 1: OSM landuse
lu = gpd.read_file("data/beijing_shp/gis_osm_landuse_a_free_1.shp")
lu["gb_code"] = lu.fclass.map(LANDUSE_GB).fillna("U")
lu["src_layer"] = "landuse"
print(f"landuse: {len(lu)}")

# Step 2: POI 面
pois_a = gpd.read_file("data/beijing_shp/gis_osm_pois_a_free_1.shp")
pois_a["gb_code"] = pois_a.fclass.map(POI_GB).fillna("")
pa_sub = pois_a[pois_a.gb_code != ""].copy()
pa_sub["src_layer"] = "poi_area"
print(f"POI 补充: {len(pa_sub)}")

# Step 3: Transport
tr = gpd.read_file("data/beijing_shp/gis_osm_transport_a_free_1.shp")
tr_sub = tr[tr.fclass.isin(["bus_station","railway_station","airport"])].copy()
tr_sub["gb_code"] = "S"; tr_sub["src_layer"] = "transport"
print(f"Transport: {len(tr_sub)}")

# 合并
gdf = pd.concat([
    lu[["name","fclass","gb_code","src_layer","geometry"]],
    pa_sub[["name","fclass","gb_code","src_layer","geometry"]],
    tr_sub[["name","fclass","gb_code","src_layer","geometry"]],
], ignore_index=True)
gdf = gpd.GeoDataFrame(gdf, crs="EPSG:4326")

total = len(gdf)
dist_final = Counter(gdf.gb_code)

print(f"\n=== 北京全量 GB50137 === ({time.time()-t0:.0f}s)")
for code in ["R","B1","B2","M","S","A3","A4","A5","G","MIL","AGR","U"]:
    print(f"  {code:3s} {GB_CN[code]:10s}: {dist_final.get(code,0):6d} 面")
print(f"  总计: {total}")

# 导出
os.makedirs("outputs/beijing_full", exist_ok=True)
out_geo = "outputs/beijing_full/beijing_gb50137_all.geojson"
features = []
for _, r in gdf.iterrows():
    props = {
        "gb_code": str(r.gb_code), "ClassCn": GB_CN.get(str(r.gb_code),""),
        "osm_fclass": str(r.fclass), "source": str(r.src_layer),
        "name": str(r.get("name") or "")
    }
    features.append({"type":"Feature","geometry":json.loads(json.dumps(r.geometry.__geo_interface__)),"properties":props})

with open(out_geo,"w") as f:
    json.dump({"type":"FeatureCollection","features":features}, f, ensure_ascii=False)
sz = os.path.getsize(out_geo)/1024/1024
print(f"\nsaved {len(features)} features -> {out_geo} ({sz:.1f} MB)")

# shp 格式 (对标市售产品)
out_shp = "outputs/beijing_full/beijing_gb50137_all.shp"
export = gdf[["gb_code","name","fclass","src_layer","geometry"]].copy()
export["ClassCn"] = export.gb_code.map(GB_CN)
try:
    export.to_file(out_shp.replace(".shp",""), encoding="utf-8", driver="ESRI Shapefile")
    print(f"SHP saved: {out_shp}")
except Exception as e:
    print(f"SHP skip: {str(e)[:60]}")

