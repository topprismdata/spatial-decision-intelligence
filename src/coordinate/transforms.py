"""
Coordinate Transformations between WGS84, GCJ-02 (Mars), and BD-09 (Baidu).
Standard implementation with accurate math.
"""

import math
from typing import Tuple, Optional
from shapely import wkt
from shapely.geometry import mapping, shape, Polygon, MultiPolygon

PI = 3.1415926535897932384626
A = 6378245.0  # Semi-major axis
EE = 0.00669342162296594323  # Eccentricity squared


def _transform_lat(lng: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 * math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    ret += (20.0 * math.sin(6.0 * lng * PI) + 20.0 * math.sin(2.0 * lng * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * PI) + 40.0 * math.sin(lng / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * PI) + 300.0 * math.sin(lng / 30.0 * PI)) * 2.0 / 3.0
    return ret


def out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def wgs84_to_gcj02(lng: float, lat: float) -> Tuple[float, float]:
    if out_of_china(lng, lat):
        return lng, lat
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lng = (d_lng * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    return lng + d_lng, lat + d_lat


def gcj02_to_wgs84(lng: float, lat: float) -> Tuple[float, float]:
    if out_of_china(lng, lat):
        return lng, lat
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((A * (1 - EE)) / (magic * sqrt_magic) * PI)
    d_lng = (d_lng * 180.0) / (A / sqrt_magic * math.cos(rad_lat) * PI)
    mg_lat = lat + d_lat
    mg_lng = lng + d_lng
    return lng * 2 - mg_lng, lat * 2 - mg_lat


def bd09_to_gcj02(lng: float, lat: float) -> Tuple[float, float]:
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * PI * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * PI * 3000.0 / 180.0)
    gg_lng = z * math.cos(theta)
    gg_lat = z * math.sin(theta)
    return gg_lng, gg_lat


def bd09_to_wgs84(lng: float, lat: float) -> Tuple[float, float]:
    gcj_lng, gcj_lat = bd09_to_gcj02(lng, lat)
    return gcj02_to_wgs84(gcj_lng, gcj_lat)


def transform_geometry_wkt(wkt_str: str, transform_fn=gcj02_to_wgs84) -> Optional[str]:
    """Transforms every vertex in a WKT polygon/multipolygon using transform_fn."""
    if not wkt_str:
        return None
    try:
        geom = wkt.loads(wkt_str)
        if isinstance(geom, Polygon):
            ext_coords = [transform_fn(c[0], c[1]) for c in geom.exterior.coords]
            int_coords = [[transform_fn(c[0], c[1]) for c in ring.coords] for ring in geom.interiors]
            new_geom = Polygon(ext_coords, int_coords)
            return new_geom.wkt
        elif isinstance(geom, MultiPolygon):
            polys = []
            for poly in geom.geoms:
                ext_coords = [transform_fn(c[0], c[1]) for c in poly.exterior.coords]
                int_coords = [[transform_fn(c[0], c[1]) for c in ring.coords] for ring in poly.interiors]
                polys.append(Polygon(ext_coords, int_coords))
            new_geom = MultiPolygon(polys)
            return new_geom.wkt
        else:
            return geom.wkt
    except Exception:
        return wkt_str
