"""R16 视觉验证管线: Amap 卫星底图 + 边界叠加 + 截图对比生成
对每个 5A/4A 景区:
  1. WGS84 边界 → GCJ02 → 切片编号 → 下载卫星瓦片
  2. 边界投影到瓦片坐标系, 用 PIL 叠加绘制多边形轮廓
  3. 输出 带边界叠加的卫星图 (发给 GLM-5.2 或人工审核)
"""
import warnings; warnings.filterwarnings("ignore")
import json, math, os, io, re
import requests
import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape

KEY = "7cefa505e38404f1a83f8eea34565e6c"   # 仅 amap_point 查询用; 瓦片匿名
AMAP_STATIC_KEY = KEY

# GCJ02 → WGS84 反向: wgs → gcj02
from src.coordinate.transforms import wgs84_to_gcj02

def gcj02_deg2num(lat,lng,z):
    lat_rad=math.radians(lat); n=2**z
    x=int((lng+180)/360*n)
    y=int((1-math.log(math.tan(lat_rad)+1/math.cos(lat_rad))/math.pi)/2*n)
    return x,y

def lnglat_to_pixel_gcj02(lng,lat,zoom):
    """GCJ02 经纬度 → 全球像素坐标"""
    lat_rad=math.radians(lat); n=256*2**zoom
    x=(lng+180)/360*n
    y=(1-math.log(math.tan(lat_rad)+1/math.cos(lat_rad))/math.pi)/2*n
    return x,y

def build_overlay_image(geom_geojson,name,zoom=15,tiles_per_side=3):
    """下载卫星瓦片并叠加边界; 返回 PIL Image 或 None"""
    from src.coordinate.transforms import wgs84_to_gcj02
    g=shape(geom_geojson)
    # 遍历所有外环点做 GCJ02 转换并计算像素坐标
    polys=[g] if g.geom_type=="Polygon" else list(g.geoms)
    # 先算总体范围 (GCJ02)
    all_pts=[]
    for poly in polys:
        for c in poly.exterior.coords:
            glng,glat=wgs84_to_gcj02(c[0],c[1])
            px,py=lnglat_to_pixel_gcj02(glng,glat,zoom)
            all_pts.append((px,py))
            all_pts.append((c[0],c[1]))  # keep original too
    
    if not all_pts: return None
    # 瓦片范围
    tile_xs=[int(p[0]/256) for p in all_pts]
    tile_ys=[int(p[1]/256) for p in all_pts]
    tx_min,tx_max=min(tile_xs),max(tile_xs)
    ty_min,ty_max=min(tile_ys),max(tile_ys)
    
    # 限制 tile 数量
    if (tx_max-tx_min+1)>tiles_per_side or (ty_max-ty_min+1)>tiles_per_side:
        cx=(tx_min+tx_max)//2; cy=(ty_min+ty_max)//2
        half=tiles_per_side//2
        tx_min,tx_max=cx-half,cx+half
        ty_min,ty_max=cy-half,cy+half
    
    width=(tx_max-tx_min+1)*256
    height=(ty_max-ty_min+1)*256
    canvas=Image.new("RGB",(width,height))
    sess=requests.Session()
    sess.headers.update({"Referer":"https://amap.com"})
    
    for ty in range(ty_min,ty_max+1):
        for tx in range(tx_min,tx_max+1):
            url=f"https://webst01.is.autonavi.com/appmaptile?style=6&x={tx}&y={ty}&z={zoom}"
            try:
                r=sess.get(url,timeout=10)
                if r.status_code==200 and len(r.content)>500:
                    t=Image.open(io.BytesIO(r.content)).convert("RGB")
                    canvas.paste(t,((tx-tx_min)*256,(ty-ty_min)*256))
            except Exception:
                pass
    
    draw=ImageDraw.Draw(canvas)
    # 在 canvas 上绘制所有 polygons
    offset_x=tx_min*256; offset_y=ty_min*256
    for poly in polys:
        ring=[]
        for c in poly.exterior.coords:
            glng,glat=wgs84_to_gcj02(c[0],c[1])
            px,py=lnglat_to_pixel_gcj02(glng,glat,zoom)
            ring.append((px-offset_x,py-offset_y))
        if len(ring)>=3:
            draw.polygon(ring,outline=(255,0,0),width=3)
    
    return canvas

def process_all():
    gj_path="outputs/scenic_spots/beijing_alevel_scenic.geojson"
    fc=json.load(open(gj_path))
    out_dir="outputs/scenic_spots/visual_qc"
    os.makedirs(out_dir,exist_ok=True)
    done=set()
    results=[]
    grade_filter={"5A":18,"4A":15}  # zoom 按 5A/4A 不同
    processed=0
    for i,f in enumerate(fc["features"]):
        p=f["properties"]
        g=p.get("grade","")
        if g not in ("5A","4A"): continue
        name=str(p["name"])
        geom=f["geometry"]
        if geom["type"] not in ("Polygon","MultiPolygon"): continue
        zoom = grade_filter[g]
        try:
            img=build_overlay_image(geom,name,zoom=zoom)
        except Exception as e:
            print(f"✗ {name[:20]} err:{e}")
            continue
        if img is None:
            print(f"- {name[:20]} no tiles")
            continue
        safe=re.sub(r"[^\w\u4e00-\u9fa5]","_",name)[:30]
        fp=os.path.join(out_dir,f"{g}_{safe}.png")
        img.save(fp,"PNG")
        done.add(name)
        results.append({"name":name,"grade":g,"file":fp,
                        "area_km2":round(shape(geom).area*111320**2/1e6,2)})
        processed+=1
        if processed%10==0:
            print(f"  [{processed}] 完成")
    json.dump(results,open(f"{out_dir}/qc_manifest.json","w"),ensure_ascii=False,indent=1)
    print(f"\n总计处理 {processed} 张, 输出到 {out_dir}/")

if __name__=="__main__":
    process_all()
