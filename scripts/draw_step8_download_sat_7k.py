#!/usr/bin/env python3
"""
High-Performance Concurrent Satellite Patch & Mask Generator for 7k Silver Dataset.
Reads outputs/silver_fence_dataset.json, fetches GaoDe 256x256 satellite patches,
rasterizes ground-truth polygon masks, and saves to data/satellite/{record_id}.npz.
"""

from __future__ import annotations

import os
import sys
import json
import math
import io
import time
import socket
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
from PIL import Image
from shapely import wkt as swkt
from shapely.validation import make_valid
from skimage.draw import polygon as sk_polygon

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

socket.setdefaulttimeout(15)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("download_sat_7k")


# ========== 瓦片坐标转换工具 ==========
def lnglat_to_tile(lon: float, lat: float, z: int) -> Tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


def tile_to_lnglat(x: int, y: int, z: int) -> Tuple[float, float]:
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def tile_resolution(lat: float, z: int) -> float:
    return 40075016.686 * math.cos(math.radians(lat)) / (2 ** z * 256)


def download_tile(x: int, y: int, z: int, retries: int = 3) -> Optional[np.ndarray]:
    url = f"https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"
    for _ in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Referer": "https://gaode.com",
                },
            )
            with urllib.request.urlopen(req) as resp:
                data = resp.read()
                if len(data) > 1000:
                    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))
        except Exception:
            time.sleep(0.3)
    return None


def pick_zoom(fence_area_m2: float, target_ratio: float = 0.4) -> int:
    target_patch_m2 = fence_area_m2 / target_ratio
    z_areas = {18: 13689, 17: 54756, 16: 219024, 15: 876096}
    best_z = min(z_areas.keys(), key=lambda z: abs(z_areas[z] - target_patch_m2))
    return best_z


def download_satellite_patch(
    gcj_lon: float, gcj_lat: float, z: int = 17, patch_size: int = 256
) -> Tuple[Optional[np.ndarray], Optional[float], Optional[float], Optional[float], Optional[float]]:
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
            big_img[y_offset[ty] : y_offset[ty] + 256, x_offset[tx] : x_offset[tx] + 256] = tile

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
        pad_img = np.pad(
            big_img,
            (
                (max(0, -y0), max(0, y0 + patch_size - big_h)),
                (max(0, -x0), max(0, x0 + patch_size - big_w)),
                (0, 0),
            ),
            mode="edge",
        )
        y0_adj = max(0, y0)
        x0_adj = max(0, x0)
        patch = pad_img[y0_adj : y0_adj + patch_size, x0_adj : x0_adj + patch_size]
    else:
        patch = big_img[y0 : y0 + patch_size, x0 : x0 + patch_size]

    patch_left_lon = left_lon + x0 * dpx
    patch_top_lat = top_lat - y0 * dpy
    return patch, patch_left_lon, patch_top_lat, dpx, dpy


def polygon_to_mask(
    poly_gcj_wkt: str, patch_left_lon: float, patch_top_lat: float, dpx: float, dpy: float, patch_size: int = 256
) -> np.ndarray:
    poly = swkt.loads(poly_gcj_wkt)
    if not poly.is_valid:
        poly = make_valid(poly)

    polys = []
    if poly.geom_type == "Polygon":
        polys = [poly]
    elif poly.geom_type == "MultiPolygon":
        polys = list(poly.geoms)
    elif poly.geom_type == "GeometryCollection":
        for g in poly.geoms:
            if g.geom_type == "Polygon":
                polys.append(g)
            elif g.geom_type == "MultiPolygon":
                polys.extend(g.geoms)

    mask = np.zeros((patch_size, patch_size), dtype=np.uint8)
    for p in polys:
        if p.is_empty or p.area == 0:
            continue
        coords = list(p.exterior.coords)
        xs = [(lon - patch_left_lon) / dpx for lon, lat in coords]
        ys = [(patch_top_lat - lat) / dpy for lon, lat in coords]
        if len(xs) < 3:
            continue
        try:
            rr, cc = sk_polygon(ys, xs, (patch_size, patch_size))
            mask[rr, cc] = 1
        except Exception:
            continue
        for interior in p.interiors:
            icoords = list(interior.coords)
            ixs = [(lon - patch_left_lon) / dpx for lon, lat in icoords]
            iys = [(patch_top_lat - lat) / dpy for lon, lat in icoords]
            if len(ixs) < 3:
                continue
            try:
                irr, icc = sk_polygon(iys, ixs, (patch_size, patch_size))
                mask[irr, icc] = 0
            except Exception:
                continue
    return mask


def process_single_item(item: Dict[str, Any], out_dir: str) -> Optional[Dict[str, Any]]:
    rid = item["record_id"]
    npz_path = os.path.join(out_dir, f"{rid}.npz")
    if os.path.exists(npz_path):
        try:
            with np.load(npz_path) as d:
                mask = d["mask"]
                return {
                    "rid": rid,
                    "z": int(d.get("z", 17)),
                    "mask_ratio": float(mask.mean()),
                    "area": float(item.get("area_m2", 0)),
                    "cached": True,
                }
        except Exception:
            pass

    gcj_lng, gcj_lat = item["center_gcj02"]
    area_m2 = item.get("area_m2", 21000.0)
    wkt_geom = item.get("geometry_gcj02_wkt", "")
    if not wkt_geom:
        return None

    z = pick_zoom(area_m2, target_ratio=0.4)
    patch, pleft, ptop, dpx, dpy = download_satellite_patch(gcj_lng, gcj_lat, z=z)
    if patch is None or pleft is None:
        return None

    mask = polygon_to_mask(wkt_geom, pleft, ptop, dpx, dpy)
    if mask.sum() == 0:
        return None

    np.savez_compressed(
        npz_path,
        image=patch,
        mask=mask,
        seed_lon=gcj_lng,
        seed_lat=gcj_lat,
        patch_left_lon=pleft,
        patch_top_lat=ptop,
        dpx=dpx,
        dpy=dpy,
        z=z,
        area=area_m2,
    )

    return {
        "rid": rid,
        "z": z,
        "mask_ratio": float(mask.mean()),
        "area": area_m2,
        "cached": False,
    }


def main():
    json_path = os.path.join(PROJECT_ROOT, "outputs", "silver_fence_dataset.json")
    if not os.path.exists(json_path):
        logger.error(f"silver dataset not found: {json_path}")
        return 1

    with open(json_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    out_dir = os.path.join(PROJECT_ROOT, "data", "satellite")
    os.makedirs(out_dir, exist_ok=True)
    logger.info(f"[sat_downloader] Starting batch generation for {len(dataset)} items -> {out_dir}")

    t0 = time.time()
    results = []
    completed = 0
    total = len(dataset)

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(process_single_item, item, out_dir): item for item in dataset}
        for fut in as_completed(futures):
            completed += 1
            res = fut.result()
            if res:
                results.append(res)
            if completed % 250 == 0 or completed == total:
                elapsed = time.time() - t0
                speed = completed / max(elapsed, 0.001)
                logger.info(
                    f"Progress: {completed}/{total} ({completed/total*100:.1f}%) | "
                    f"Valid={len(results)} | Elapsed={elapsed:.1f}s ({speed:.1f} items/s)"
                )

    df = pd.DataFrame(results)
    csv_stat_path = os.path.join(PROJECT_ROOT, "outputs", "sat_7k_meta.csv")
    df.to_csv(csv_stat_path, index=False)
    logger.info(f"\n[sat_downloader] DONE! Successfully generated {len(results)} valid patches in {time.time()-t0:.1f}s")
    logger.info(f"Meta stats saved to: {csv_stat_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
