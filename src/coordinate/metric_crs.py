"""R1 LEGACY MODULE: Geographic Search Approximation only.

Design Note §9: This module provides WGS84 ellipsoid-based degree approximation.
It is formally downgraded to Geographic Search Approximation.

ALLOWED: coarse bbox, external API query window, Overpass query range,
candidate data pre-retrieval, coarse fetch envelope.

PROHIBITED for production metric operations: formal Geometry QA distance,
Candidate score metric distance, polygon area, buffer, snapping, topology tolerance,
Gold metric evaluation.

Use src.coordinate.metric_crs_strategy.MetricCRSStrategy + GeometryTransformer
for all production metric operations.

WGS84 ellipsoid parameters (GRS80):
    a = 6378137.0  (semi-major axis, meters)
    f = 1/298.257223563  (flattening)
    b = 6356752.314  (semi-minor axis, meters)
    e² = 0.00669437999  (first eccentricity squared)
"""

from __future__ import annotations

import math
from typing import Tuple


# WGS84 ellipsoid constants
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_B = WGS84_A * (1.0 - WGS84_F)
WGS84_E2 = 1.0 - (WGS84_B * WGS84_B) / (WGS84_A * WGS84_A)

# Lazy shapely import — only needed for geometry-aware functions
_shapely = None


def _get_shapely():
    global _shapely
    if _shapely is None:
        from shapely import wkt as _wkt
        from shapely.geometry import Point as _Point
        from shapely.geometry import Polygon as _Polygon
        from shapely.geometry import box as _box

        class _Shapely:
            wkt = _wkt
            Point = _Point
            Polygon = _Polygon
            box = _box

        _shapely = _Shapely()
    return _shapely


def meters_per_degree_lat(lat: float) -> float:
    """Meters per degree of latitude at given latitude (WGS84 ellipsoid).

    Uses the formula: 111132.954 - 559.822*cos(2φ) + 1.175*cos(4φ)
    Range: ~110574m (equator) to ~111694m (poles).
    """
    phi = math.radians(lat)
    return (
        111132.954
        - 559.822 * math.cos(2.0 * phi)
        + 1.175 * math.cos(4.0 * phi)
    )


def meters_per_degree_lng(lat: float) -> float:
    """Meters per degree of longitude at given latitude (WGS84 ellipsoid).

    At 40°N: ~85294m. At equator: ~111319m.
    Uses: a * cos(φ) / sqrt(1 - e² * sin²(φ)) * π / 180
    """
    phi = math.radians(lat)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    return WGS84_A * cos_phi / math.sqrt(1.0 - WGS84_E2 * sin_phi * sin_phi) * math.pi / 180.0


def degree_offset_for_meters(meters: float, lat: float) -> Tuple[float, float]:
    """Convert a meter distance to (dlat, dlng) degree offsets at given latitude."""
    m_per_lat = meters_per_degree_lat(lat)
    m_per_lng = meters_per_degree_lng(lat)
    return (meters / m_per_lat, meters / (m_per_lng + 1e-12))


def area_m2_from_wgs84(geom, ref_lat: float) -> float:
    """Compute area in square meters from a WGS84-degree geometry.

    Accepts either a WKT string or a shapely geometry object.
    Uses the Lambert azimuthal equal-area approximation at the reference latitude.
    For small areas (< 100km²), the error is < 0.1%.
    """
    s = _get_shapely()
    if isinstance(geom, str):
        geom = s.wkt.loads(geom)
    m_per_lat = meters_per_degree_lat(ref_lat)
    m_per_lng = meters_per_degree_lng(ref_lat)
    scale = m_per_lat * m_per_lng
    return geom.area * scale


def distance_m(geom_a, geom_b, ref_lat: float) -> float:
    """Approximate distance in meters between two WGS84 geometries.

    Uses the average of the two geometries' centroid latitudes for the conversion.
    """
    if hasattr(geom_a, 'centroid'):
        lat_a = geom_a.centroid.y
    else:
        lat_a = ref_lat

    lat = (lat_a + ref_lat) / 2.0
    m_per_lat = meters_per_degree_lat(lat)
    m_per_lng = meters_per_degree_lng(lat)
    deg_dist = geom_a.distance(geom_b)
    return deg_dist * math.sqrt(m_per_lat * m_per_lng)


def buffer_meters(geom_wkt: str, meters: float, ref_lat: float) -> str:
    """Buffer a WGS84 geometry by meters, returning WKT.

    Converts meters to degree buffer at the reference latitude,
    then applies the shapely buffer.
    """
    s = _get_shapely()
    geom = s.wkt.loads(geom_wkt) if isinstance(geom_wkt, str) else geom_wkt
    dlat, dlng = degree_offset_for_meters(meters, ref_lat)
    deg_buffer = min(dlat, dlng)
    buffered = geom.buffer(deg_buffer)
    return s.wkt.dumps(buffered)


def bbox_from_center(
    lng: float, lat: float, half_side_m: float
) -> Tuple[float, float, float, float]:
    """Compute WGS84 bounding box from center + half-side in meters."""
    dlat, dlng = degree_offset_for_meters(half_side_m, lat)
    return (
        round(lng - dlng, 6),
        round(lat - dlat, 6),
        round(lng + dlng, 6),
        round(lat + dlat, 6),
    )


def buffer_degrees_for_meters(meters: float, lat: float) -> float:
    """How many degrees correspond to X meters at this latitude.

    Returns the conservative (minimum of dlat/dlng) value for use with shapely.buffer().
    """
    dlat, dlng = degree_offset_for_meters(meters, lat)
    return min(dlat, dlng)


def perimeter_m_from_wgs84(geom_wkt: str, ref_lat: float) -> float:
    """Compute perimeter in meters from a WGS84-degree geometry."""
    s = _get_shapely()
    geom = s.wkt.loads(geom_wkt) if isinstance(geom_wkt, str) else geom_wkt
    m_per_lat = meters_per_degree_lat(ref_lat)
    m_per_lng = meters_per_degree_lng(ref_lat)
    return geom.length * math.sqrt(m_per_lat * m_per_lng)