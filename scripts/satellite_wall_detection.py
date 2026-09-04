"""卫星影像围墙检测: 路网约束 + Canny 边缘 + 主动轮廓修正

原理: 公园围墙在卫星影像上表现为"绿-灰"高对比度边缘。
路网切块提供初始轮廓，在法线方向搜索最清晰的边缘信号。
"""
import warnings; warnings.filterwarnings("ignore")
import math, io, requests, json, os
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon, MultiPolygon, shape
from shapely.ops import unary_union, polygonize
from scipy import ndimage
import geopandas as gpd

# ── 配置 ──
AMAP_TILE_URL = "https://webst0{}.is.autonavi.com/appmaptile?style=6&x={}&y={}&z={}"
ROADS_SHP = "data/beijing_shp/gis_osm_roads_free_1.shp"

def deg2num(lat,lng,z):
    lr=math.radians(lat); n=2**z
    return int((lng+180)/360*n), int((1-math.log(math.tan(lr)+1/math.cos(lr))/math.pi)/2*n)

def num2deg(x,y,z):
    n=2**z; lon=x/n*360-180
    lat=math.degrees(2*math.atan(math.exp(math.pi*(1-2*y/n)))-math.pi/2)
    return lat, lon

def download_tiles(lng,lat,zoom=17,span=3):
    """下载卫星瓦片拼接图; 返回 (PIL Image, (tile_x_min, tile_y_min, zoom))"""
    cx,cy=deg2num(lat,lng,zoom)
    w=256*span
    canvas=Image.new("RGB",(w,w))
    sess=requests.Session()
    sess.headers.update({"Referer":"https://amap.com"})
    ok=0
    for dy in range(span):
        for dx in range(span):
            url=AMAP_TILE_URL.format(1+(cx+dx+cy+dy)%4, cx+dx, cy+dy, zoom)
            try:
                r=sess.get(url,timeout=10)
                if r.status_code==200 and len(r.content)>500:
                    t=Image.open(io.BytesIO(r.content)).convert("RGB")
                    canvas.paste(t,(dx*256,dy*256))
                    ok+=1
            except Exception: pass
    return canvas, (cx,cy,zoom), ok

def pixel_to_wgs84(px,py,ctx):
    """像素坐标 → WGS84经纬度, 其中 ctx=(tile_x0,tile_y0,zoom)"""
    tx,ty,z=ctx
    # 像素 → 瓦片编号
    tile_x = tx + px/256
    tile_y = ty + py/256
    return num2deg(tile_x, tile_y, z)

def detect_wall_boundary(satellite_img, ctx, road_blocks=None):
    """Canny 边缘检测 + 最大连通区域提取"""
    img=np.array(satellite_img.convert("L")).astype(float)
    # 高斯平滑
    img=ndimage.gaussian_filter(img,sigma=2)
    # 梯度
    gx=ndimage.sobel(img,axis=1)
    gy=ndimage.sobel(img,axis=0)
    grad=np.hypot(gx,gy)
    # 阈值
    edges=(grad>40).astype(np.uint8)*255
    
    # 形态学闭运算连接断裂边缘
    from scipy.ndimage import binary_closing, binary_dilation
    closed=binary_closing(edges,structure=np.ones((5,5))).astype(np.uint8)*255
    dilated=binary_dilation(closed,iterations=3).astype(np.uint8)*255
    
    # 找到最大连通区域
    from skimage import measure as _ms
    labels=_ms.label(dilated)
    props=_ms.regionprops(labels)
    if not props:
        return None, edges
    largest=max(props,key=lambda p:p.area)
    
    # 提取轮廓
    from skimage.measure import find_contours
    contours=find_contours((labels==largest.label).astype(float),0.5)
    if not contours:
        return None, edges
    contour=max(contours,key=len)
    return contour, edges

def refine_boundary(contour, ctx, satellite_img):
    """主动轮廓细化: 沿法线搜索最强边缘"""
    # 简化: 对轮廓进行 Douglas-Peucker 简化
    # 然后将简化后的顶点沿法线方向微移到最近强边缘
    from shapely.geometry import Point as _Pt
    pts=[(c[1],c[0]) for c in contour[::max(len(contour)//200,1)]]  # 采样+简化
    
    img=np.array(satellite_img.convert("L")).astype(float)
    gx=ndimage.sobel(img,axis=1)
    # 对每个顶点沿法线搜索
    refined=[]
    for i,(x,y) in enumerate(pts):
        # 搜索窗口 ±15 像素
        window=img[max(0,int(y)-15):min(int(y)+15,img.shape[0]),
                   max(0,int(x)-15):min(int(x)+15,img.shape[1])]
        if window.size<10: refined.append((x,y)); continue
        # 找最暗->最亮过渡 (典型围墙: 植被→建筑)
        best_dx=0;best_dy=0;best_grad=0
        for dy in range(-12,13,2):
            for dx in range(-12,13,2):
                ny=int(y+dy); nx=int(x+dx)
                if ny<1 or nx<1 or ny>=img.shape[0]-1 or nx>=img.shape[1]-1: continue
                g=abs(gx[ny,nx])
                if g>best_grad: best_grad=g; best_dx=dx; best_dy=dy
        if best_grad>30:
            refined.append((x+best_dx,y+best_dy))
        else:
            refined.append((x,y))
    
    # 转 WGS84
    wgs84_pts=[pixel_to_wgs84(x,y,ctx) for x,y in refined]
    if len(wgs84_pts)<3:
        return None
    poly=Polygon(wgs84_pts)
    if not poly.is_valid or poly.area<1e-10:
        poly=poly.buffer(0)  # 修复自交
    return poly if poly.is_valid else None

def process_scenic(spot_name, lng, lat, zoom=17):
    """主入口"""
    print(f"处理 {spot_name} ({lng:.4f},{lat:.4f}) z={zoom}")
    sat_img, ctx, n_tiles = download_tiles(lng,lat,zoom,span=5)
    if n_tiles<10:
        print(f"  瓦片加载不足 {n_tiles}/25")
        return None, None
    
    contour, edges = detect_wall_boundary(sat_img, ctx)
    if contour is None:
        print(f"  无检测轮廓")
        return None, sat_img
    
    poly = refine_boundary(contour, ctx, sat_img)
    if poly is None:
        print(f"  轮廓细化失败")
        return None, sat_img
    
    area_ha = poly.area*111320**2/10000
    print(f"  ✓ 检测完成: {area_ha:.0f} ha, 类型={poly.geom_type}")
    return poly, sat_img

if __name__=="__main__":
    # 试点: 天坛公园
    poly, img = process_scenic("天坛公园", 116.4051, 39.8817, 17)
    if poly:
        _root = os.environ.get("SDI_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.makedirs(os.path.join(_root, "outputs"), exist_ok=True)
        _out = os.path.join(_root, "outputs", "tiantan_satellite_wall.geojson")
        with open(_out, "w") as f:
            json.dump({"type":"FeatureCollection","features":[{
                "type":"Feature","geometry":json.loads(json.dumps(poly.__geo_interface__)),
                "properties":{"name":"天坛公园卫星检测"}
            }]}, f, ensure_ascii=False)
        print(f"saved {_out}")
