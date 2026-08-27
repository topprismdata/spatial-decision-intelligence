"""论文消融实验: 逐级测量 IoU 提升"""
import warnings; warnings.filterwarnings("ignore")
import math, io, requests, numpy as np
from PIL import Image
from shapely.geometry import Point, Polygon, MultiPoint
from shapely.ops import unary_union
import geopandas as gpd
from src.geometry.concave_hull import hull_for_cluster

def deg2num(lat,lng,z):
    lr=math.radians(lat); n=2**z
    return int((lng+180)/360*n), int((1-math.log(math.tan(lr)+1/math.cos(lr))/math.pi)/2*n)
def num2deg(x,y,z):
    n=2**z; lon=x/n*360-180
    return math.degrees(2*math.atan(math.exp(math.pi*(1-2*y/n)))-math.pi/2), lon

roads = gpd.read_file("data/beijing_shp/gis_osm_roads_free_1.shp")
CASES = [("天坛公园",116.4051,39.8817,"天坛"),("颐和园",116.2672,39.9896,"颐和园"),
         ("圆明园遗址公园",116.3018,40.0022,"圆明园")]
lu = gpd.read_file("data/beijing_shp/gis_osm_landuse_a_free_1.shp")

def get_veg(lng,lat,z=16,span=5):
    cx,cy=deg2num(lat,lng,z)
    canvas=Image.new("RGB",(256*span,256*span))
    sess=requests.Session(); sess.headers.update({"Referer":"https://amap.com"})
    for dy in range(span):
        for dx in range(span):
            try:
                r=sess.get(f"https://webst01.is.autonavi.com/appmaptile?style=6&x={cx+dx}&y={cy+dy}&z={z}",timeout=10)
                if r.status_code==200: canvas.paste(Image.open(io.BytesIO(r.content)).convert("RGB"),(dx*256,dy*256))
            except Exception: pass
    img=np.array(canvas).astype(float)
    veg=(img[:,:,1]-img[:,:,0])/(img[:,:,0]+img[:,:,1]+1e-6)
    return veg,cx,cy,z,span

def veg_points(veg,cx,cy,z,span,mode="uniform",tau=0.05,tau_min=0.01,tau_max=0.11):
    step=8; rows,cols=veg.shape[0]//step,veg.shape[1]//step
    cp=span*256//2
    pts=[]
    for y in range(rows):
        for x in range(cols):
            v=veg[y*step,x*step]
            thr = tau if mode=="uniform" else tau_min+(tau_max-tau_min)*(math.hypot(x*step-cp,y*step-cp)/cp)
            if v>thr:
                tx=cx+(x*step)/256-span//2; ty=cy+(y*step)/256-span//2
                lat,ln=num2deg(tx,ty,z); pts.append((ln,lat))
    return pts

def road_clip(poly,lng,lat):
    c=Point(lng,lat)
    sub=roads[roads.intersects(c.buffer(0.015)) & roads.fclass.isin(["primary","secondary","tertiary"])]
    if not len(sub): return poly
    bufs=[r.geometry.buffer(10/111000.0) for _,r in sub.iterrows()]
    out=poly.difference(unary_union(bufs))
    return out if out.is_valid else out.buffer(0)

def iou(a,b):
    try: return a.intersection(b).area/max(a.union(b).area,1e-12)
    except Exception: return 0.0

results=[]
for name,tlng,tlat,osm_kw in CASES:
    tr=lu[lu.name.fillna("").str.contains(osm_kw,na=False)]
    if not len(tr): continue
    truth=tr.geometry.iloc[0]
    veg,cx,cy,z,span=get_veg(tlng,tlat)
    p1=veg_points(veg,cx,cy,z,span,"uniform",0.05)
    h1=MultiPoint(p1).convex_hull if len(p1)>3 else None
    h2=hull_for_cluster(p1) if len(p1)>3 else None
    p3=veg_points(veg,cx,cy,z,span,"weighted")
    h3=hull_for_cluster(p3) if len(p3)>3 else None
    h4=road_clip(h3,tlng,tlat) if h3 else None
    row={"name":name,"A1_convex":round(iou(truth,h1),3) if h1 else 0,
         "A2_concave":round(iou(truth,h2),3) if h2 else 0,
         "A3_concave_w":round(iou(truth,h3),3) if h3 else 0,
         "A4_plus_road":round(iou(truth,h4),3) if h4 else 0}
    results.append(row); print(row)

if results:
    import pandas as pd
    df=pd.DataFrame(results)
    print("\n=== 消融平均 IoU ===")
    for c in ["A1_convex","A2_concave","A3_concave_w","A4_plus_road"]:
        print(f"  {c}: {df[c].mean():.3f}")
