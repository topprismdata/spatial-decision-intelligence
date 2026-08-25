#!/usr/bin/env python3
"""
下载 143 条围栏样本的卫星图 + 生成 mask 标签

数据源：高德卫星图瓦片
坐标系：高德底图 = GCJ-02，瓦片网格用 GCJ-02 坐标索引
围栏数据：selfdraw_geoms.json (WGS-84 WKT) → 转 GCJ-02 对齐
自适应 zoom：按围栏面积选择 z，让围栏占 patch 30-70%
"""

import json, math, os, io, time
import urllib.request
import socket
import numpy as np
from PIL import Image
from shapely import wkt as swkt
from shapely.validation import make_valid
from shapely.geometry import Point
import pandas as pd
from skimage.draw import polygon as sk_polygon

socket.setdefaulttimeout(15)

from src.coordinate.transforms import wgs84_to_gcj02

# ========== 瓦片工具 (用 GCJ-02 坐标索引) ==========
def lnglat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y

def tile_to_lnglat(x, y, z):
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat

def tile_resolution(lat, z):
    return 40075016.686 * math.cos(math.radians(lat)) / (2**z * 256)

def download_tile(x, y, z, retries=3):
    url = f'https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}'
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                'Referer': 'https://gaode.com'
            })
            resp = urllib.request.urlopen(req)
            data = resp.read()
            if len(data) > 1000:
                return np.array(Image.open(io.BytesIO(data)).convert('RGB'))
        except Exception:
            time.sleep(0.5)
    return None

def pick_zoom(fence_area_m2, target_ratio=0.5):
    """根据围栏面积选择 zoom level，让围栏占 patch 约 target_ratio"""
    # patch 面积 m² @ z (256x256):
    # z=18: 117m²=13689  z=17: 234m²=54756  z=16: 468m²=219024
    # 要围栏占 target_ratio，则 patch 面积 = fence_area / target_ratio
    target_patch_m2 = fence_area_m2 / target_ratio
    # 找最接近的 zoom
    z_areas = {18: 13689, 17: 54756, 16: 219024, 15: 876096}
    best_z = min(z_areas.keys(), key=lambda z: abs(z_areas[z] - target_patch_m2))
    return best_z

def download_satellite_patch(seed_lon_wgs, seed_lat_wgs, z=17, patch_size=256):
    """下载以种子点(WGS-84)为中心的卫星图 patch，返回 (img, left_lon, top_lat, dpx, dpy)"""
    gcj_lon, gcj_lat = wgs84_to_gcj02(seed_lon_wgs, seed_lat_wgs)
    res = tile_resolution(gcj_lat, z)

    cx, cy = lnglat_to_tile(gcj_lon, gcj_lat, z)
    tiles = {}
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            tx, ty = cx + dx, cy + dy
            tile = download_tile(tx, ty, z)
            if tile is not None:
                tiles[(tx, ty)] = tile

    if len(tiles) < 5:
        return None, None, None, None, None

    all_x = sorted(set(tx for tx, _ in tiles.keys()))
    all_y = sorted(set(ty for _, ty in tiles.keys()))
    big_w = len(all_x) * 256
    big_h = len(all_y) * 256
    big_img = np.zeros((big_h, big_w, 3), dtype=np.uint8)
    x_offset = {x: i * 256 for i, x in enumerate(all_x)}
    y_offset = {y: i * 256 for i, y in enumerate(all_y)}
    for (tx, ty), tile in tiles.items():
        if tx in x_offset and ty in y_offset:
            big_img[y_offset[ty]:y_offset[ty]+256, x_offset[tx]:x_offset[tx]+256] = tile

    left_lon, top_lat = tile_to_lnglat(all_x[0], all_y[0], z)
    n = 2 ** z
    dpx = 360.0 / (n * 256)
    dpy = res / 111320.0
    px_x = (gcj_lon - left_lon) / dpx
    px_y = (top_lat - gcj_lat) / dpy

    half = patch_size // 2
    x0 = int(px_x) - half
    y0 = int(px_y) - half

    if x0 < 0 or y0 < 0 or x0 + patch_size > big_w or y0 + patch_size > big_h:
        pad_img = np.pad(big_img,
                        ((max(0, -y0), max(0, y0+patch_size-big_h)),
                         (max(0, -x0), max(0, x0+patch_size-big_w)),
                         (0, 0)), mode='edge')
        y0_adj = max(0, y0)
        x0_adj = max(0, x0)
        patch = pad_img[y0_adj:y0_adj+patch_size, x0_adj:x0_adj+patch_size]
    else:
        patch = big_img[y0:y0+patch_size, x0:x0+patch_size]

    patch_left_lon = left_lon + x0 * dpx
    patch_top_lat = top_lat - y0 * dpy
    return patch, patch_left_lon, patch_top_lat, dpx, dpy

def polygon_to_mask(poly_wkt, patch_left_lon, patch_top_lat, dpx, dpy, patch_size=256):
    """用 skimage 栅格化复杂多边形（处理凹多边形/自相交）"""
    poly = swkt.loads(poly_wkt)
    if not poly.is_valid:
        poly = make_valid(poly)

    # 拆分为多个多边形（处理 MultiPolygon, GeometryCollection 中的 Polygon）
    polys = []
    if poly.geom_type == 'Polygon':
        polys = [poly]
    elif poly.geom_type == 'MultiPolygon':
        polys = list(poly.geoms)
    elif poly.geom_type == 'GeometryCollection':
        for g in poly.geoms:
            if g.geom_type == 'Polygon':
                polys.append(g)
            elif g.geom_type == 'MultiPolygon':
                polys.extend(g.geoms)

    mask = np.zeros((patch_size, patch_size), dtype=np.uint8)
    for p in polys:
        if p.is_empty or p.area == 0:
            continue
        coords = list(p.exterior.coords)
        xs, ys = [], []
        for lon_wgs, lat_wgs in coords:
            gcj_lon, gcj_lat = wgs84_to_gcj02(lon_wgs, lat_wgs)
            xs.append((gcj_lon - patch_left_lon) / dpx)
            ys.append((patch_top_lat - gcj_lat) / dpy)
        if len(xs) < 3:
            continue
        try:
            rr, cc = sk_polygon(ys, xs, (patch_size, patch_size))
            mask[rr, cc] = 1
        except Exception:
            continue
        for interior in p.interiors:
            coords = list(interior.coords)
            xs, ys = [], []
            for lon_wgs, lat_wgs in coords:
                gcj_lon, gcj_lat = wgs84_to_gcj02(lon_wgs, lat_wgs)
                xs.append((gcj_lon - patch_left_lon) / dpx)
                ys.append((patch_top_lat - gcj_lat) / dpy)
            if len(xs) < 3:
                continue
            try:
                rr, cc = sk_polygon(ys, xs, (patch_size, patch_size))
                mask[rr, cc] = 0
            except Exception:
                continue
    return mask

# ========== 主流程 ==========
def main():
    geoms = json.load(open('outputs/selfdraw_geoms.json'))
    ev = pd.read_csv('outputs/selfdraw_eval.csv')
    ev_idx = ev.set_index('source_record_id')['fence_area'].to_dict()
    print(f'样本数: {len(geoms)}')

    os.makedirs('data/satellite', exist_ok=True)

    samples = []
    success = 0
    for i, (rid, item) in enumerate(geoms.items()):
        if not item.get('fence') or not item.get('seed'):
            continue
        seed_lon, seed_lat = item['seed']
        area = int(ev_idx.get(rid, 21000))

        # 自适应 zoom
        z = pick_zoom(area, target_ratio=0.4)

        result = download_satellite_patch(seed_lon, seed_lat, z=z)
        patch, pleft, ptop, dpx, dpy = result
        if patch is None:
            continue

        mask = polygon_to_mask(item['fence'], pleft, ptop, dpx, dpy)

        np.savez_compressed(f'data/satellite/{rid}.npz',
                           image=patch, mask=mask,
                           seed_lon=seed_lon, seed_lat=seed_lat,
                           patch_left_lon=pleft, patch_top_lat=ptop,
                           dpx=dpx, dpy=dpy, z=z, area=area)

        mask_ratio = float(mask.mean())
        samples.append({'rid': rid, 'z': z, 'mask_ratio': mask_ratio, 'area': area})
        success += 1

        if (i+1) % 20 == 0:
            print(f'  进度: {i+1}/{len(geoms)} 成功={success}')
        time.sleep(0.2)

    print(f'\n完成: {success}/{len(geoms)}')
    df = pd.DataFrame(samples)
    if len(df) > 0:
        print(f'zoom 分布: {df.z.value_counts().to_dict()}')
        print(f'mask 占比: mean={df.mask_ratio.mean():.3f} med={df.mask_ratio.median():.3f} '
              f'p10={df.mask_ratio.quantile(0.1):.3f} p90={df.mask_ratio.quantile(0.9):.3f}')
        print(f'面积: med={df.area.median():.0f}㎡')

if __name__ == '__main__':
    main()
