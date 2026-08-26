"""R2.1 Metric Geometry Service: unified entry point for all production metric operations.

Replaces legacy degree-based approximation for:
- area, buffer, distance, snapping, topology tolerance

Legacy (src.coordinate.metric_crs) is restricted to Search Approximation only.
"""

from __future__ import annotations

from typing import Optional, Tuple

import pyproj
from shapely import wkt as _wkt
from shapely.ops import transform as shapely_transform
from functools import partial

from src.coordinate.metric_crs_strategy import (
    AccuracyClass,
    MetricCRSSelection,
    MetricCRSStrategy,
    OperationType,
)
from src.coordinate.geometry_transformer import GeometryTransformer


class MetricGeometryService:
    """Unified service for all production metric operations.

    All area / buffer / distance / snapping / topology tolerance must go through this service.
    Uses projected CRS (EPSG:32650 for Beijing Benchmark).
    """

    def __init__(self, benchmark_profile: str = "Beijing"):
        self._strategy = MetricCRSStrategy()
        self._benchmark_profile = benchmark_profile

    def _select(self, geom_wkt: str, operation_type: OperationType) -> MetricCRSSelection:
        geom = _wkt.loads(geom_wkt) if isinstance(geom_wkt, str) else geom_wkt
        centroid = geom.centroid
        return self._strategy.select(
            geometry_extent=geom.bounds,
            geometry_centroid=(centroid.x, centroid.y),
            operation_type=operation_type,
            benchmark_profile=self._benchmark_profile,
        )

    def area_m2(self, geometry_wkt: str) -> float:
        """Compute area in m² using projected CRS."""
        selection = self._select(geometry_wkt, OperationType.AREA)
        if not selection.valid:
            return 0.0
        mg = GeometryTransformer.to_metric_geometry(geometry_wkt, selection, OperationType.AREA)
        if mg.accuracy_class != AccuracyClass.VALID_METRIC_COMPUTATION:
            return 0.0
        geom = _wkt.loads(mg.geometry_wkt)
        return abs(geom.area)

    def distance_m(self, geom_a_wkt: str, geom_b_wkt: str) -> float:
        """Compute distance in meters using projected CRS."""
        # Combine extents for CRS selection
        ga = _wkt.loads(geom_a_wkt) if isinstance(geom_a_wkt, str) else geom_a_wkt
        gb = _wkt.loads(geom_b_wkt) if isinstance(geom_b_wkt, str) else geom_b_wkt

        from shapely.ops import unary_union
        combined = unary_union([ga, gb])
        centroid = combined.centroid
        selection = self._strategy.select(
            geometry_extent=combined.bounds,
            geometry_centroid=(centroid.x, centroid.y),
            operation_type=OperationType.DISTANCE,
            benchmark_profile=self._benchmark_profile,
        )
        if not selection.valid:
            return 0.0

        mg_a = GeometryTransformer.to_metric_geometry(ga.wkt, selection, OperationType.DISTANCE)
        mg_b = GeometryTransformer.to_metric_geometry(gb.wkt, selection, OperationType.DISTANCE)
        if mg_a.accuracy_class != AccuracyClass.VALID_METRIC_COMPUTATION:
            return 0.0

        pa = _wkt.loads(mg_a.geometry_wkt)
        pb = _wkt.loads(mg_b.geometry_wkt)
        return pa.distance(pb)

    def buffer_meters(self, geometry_wkt: str, meters: float) -> str:
        """Buffer a geometry by meters in projected CRS, returning WKT."""
        selection = self._select(geometry_wkt, OperationType.BUFFER)
        if not selection.valid:
            return geometry_wkt
        mg = GeometryTransformer.to_metric_geometry(geometry_wkt, selection, OperationType.BUFFER)
        if mg.accuracy_class != AccuracyClass.VALID_METRIC_COMPUTATION:
            return geometry_wkt
        geom = _wkt.loads(mg.geometry_wkt)
        buffered = geom.buffer(abs(meters))
        # Transform back to source CRS
        result = GeometryTransformer.inverse_transform_from_wkt(
            buffered.wkt, selection.target_crs, "EPSG:4326"
        )
        return result

    def snap_tolerance_deg(self, meters: float, ref_lat: float) -> float:
        """Convert meter tolerance to degrees for use with shapely operations.

        This is the ONLY sanctioned bridge between metric and degree space.
        Uses projected CRS to compute accurate conversion.
        """
        from src.coordinate.metric_crs_strategy import OperationType
        center_lng = 116.4  # Beijing default
        center_lat = ref_lat
        selection = self._strategy.select(
            geometry_extent=(center_lng - 0.01, ref_lat - 0.01, center_lng + 0.01, ref_lat + 0.01),
            geometry_centroid=(center_lng, center_lat),
            operation_type=OperationType.TOPOLOGY,
            benchmark_profile=self._benchmark_profile,
        )
        if not selection.valid:
            return meters / 111_320.0  # Fallback approximation

        # Use forward transform of a known offset to calibrate
        test_point = f"POINT({center_lng} {ref_lat})"
        try:
            transformed = GeometryTransformer.forward_transform(test_point, "EPSG:4326", selection.target_crs)
            tp = _wkt.loads(transformed.geometry_wkt)
            shifted = f"POINT({tp.x + meters} {tp.y})"
            back = GeometryTransformer.forward_transform(shifted, selection.target_crs, "EPSG:4326")
            bp = _wkt.loads(back.geometry_wkt)
            dx = bp.x - center_lng
            dy = bp.y - ref_lat
            return max(abs(dx), abs(dy))
        except Exception:
            return meters / 111_320.0

    @property
    def benchmark_profile(self) -> str:
        return self._benchmark_profile