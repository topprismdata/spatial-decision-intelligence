"""R16 批量升级: 对所有 5A/4A CONSTRUCTED 景区用卫星植被+路网裁剪升级"""
import warnings; warnings.filterwarnings("ignore")
import json, math, io, requests, time, os, re
import numpy as np
from PIL import Image
from shapely.geometry import Point, Polygon, shape
from shapely.ops import unary_union
from scipy.ndimage import binary_closing, binary_fill_holes, binary_dilation, binary_erosion
import geopandas as gpd

def deg2num(lat,lng,z):
    lr=math.radians(lat); n=2**z
    return int((lng+180)/360*n), int((1-math.log(math.tan(lr)+1/math.cos(lr))/math.pi)/2*n)
def num2deg(x,y,z):
    n=2**z; lon=x/n*360-180
    lat=math.degrees(2*math.atan(math.exp(math.pi*(1-2*y/n)))-math.pi/2)
    return lat, lon

ROADS = None
def load_roads():
    global ROADS
    if ROADS is None:
        ROADS = gpd.read_file("data/beijing_shp/gis_osm_roads_free_1.shp")

def satellite_upgrade(lng, lat, zoom=16, span=5):
    """卫星植被 + 凸包 + 路网裁剪: 返回 Polygon 或 None"""
    cx,cy=deg2num(lat,lng,zoom)
    canvas=Image.new("RGB",(256*span,256*span))
    sess=requests.Session()
    sess.headers.update({"Referer":"https://amap.com"})
    for dy in range(span):
        for dx in range(span):
            url=f"https://webst01.is.autonavi.com/appmaptile?style=6&x={cx+dx}&y={cy+dy}&z={zoom}"
            try:
                r=sess.get(url,timeout=10)
                if r.status_code==200: canvas.paste(Image.open(io.BytesIO(r.content)).convert("RGB"),(dx*256,dy*256))
            except Exception: pass
    
    img=np.array(canvas).astype(float)
    veg=(img[:,:,1]-img[:,:,0])/(img[:,:,0]+img[:,:,1]+1e-6)
    
    # 高密度植被点
    step=8
    rows,cols=img.shape[0]//step, img.shape[1]//step
    pts=[]
    for y in range(rows):
        for x in range(cols):
            if veg[y*step,x*step] > 0.06:
                tile_x=cx+(x*step)/256-span//2
                tile_y=cy+(y*step)/256-span//2
                lat1,lng1=num2deg(tile_x,tile_y,zoom)
                pts.append((lng1,lat1))
    
    if len(pts)<10: return None
    
    from src.geometry.concave_hull import hull_for_cluster
    hull=hull_for_cluster(pts)
    if hull is None or hull.is_empty: return None
    
    # 路网裁剪
    load_roads()
    center=Point(lng,lat)
    sub=ROADS[ROADS.intersects(center.buffer(0.015)) & ROADS.fclass.isin({"primary","secondary","tertiary","residential"})]
    buf_map={"primary":12,"secondary":10,"tertiary":8,"residential":6}
    bufs=[r.geometry.buffer(buf_map.get(r.fclass,6)/111000.0) for _,r in sub.iterrows()]
    if bufs:
        hull=hull.difference(unary_union(bufs))
        if not hull.is_valid: hull=hull.buffer(0)
    
    return hull if (not hull.is_empty) else None

# 主流程
gj_path="outputs/scenic_spots/beijing_alevel_scenic.geojson"
fc=json.load(open(gj_path))
targets=[i for i,f in enumerate(fc["features"]) 
         if f["properties"].get("disposition")=="CONSTRUCTED" and f["properties"].get("grade") in ("5A","4A")]
print(f"待升级: {len(targets)} 个 5A/4A")

ok=0
t0=time.time()
for idx in targets:
    f=fc["features"][idx]
    p=f["properties"]
    # 获取中心点
    if f["geometry"]["type"]=="Polygon":
        c=f["geometry"]["coordinates"][0]
        clng=sum(c_[0] for c_ in c)/len(c)
        clat=sum(c_[1] for c_ in c)/len(c)
    else:
        continue
    
    poly=satellite_upgrade(clng,clat)
    if poly:
        fc["features"][idx]["geometry"]=json.loads(json.dumps(poly.__geo_interface__))
        fc["features"][idx]["properties"]["source"]="satellite_veg+roads"
        ok+=1
        print(f"✓ [{idx}] {str(p['name'])[:22]:24s} {poly.area*111320**2/10000:.0f}ha")

json.dump(fc,open(gj_path,"w"),ensure_ascii=False)
print(f"\n升级: {ok}/{len(targets)}, 耗时 {time.time()-t0:.0f}s")
