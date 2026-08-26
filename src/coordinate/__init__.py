"""Coordinate package: alignment + metric CRS strategy."""

from src.coordinate.transforms import (
    wgs84_to_gcj02,
    gcj02_to_wgs84,
    bd09_to_gcj02,
    bd09_to_wgs84,
    transform_geometry_wkt,
    out_of_china,
)
from src.coordinate.assessment import CoordinateIntelligence
from src.coordinate.metric_crs_strategy import (
    MetricCRSStrategy,
    MetricCRSSelection,
    OperationType,
    SelectionMethod,
    ValidExtentStatus,
    AccuracyClass,
    MetricGeometry,
    TransformedGeometry,
)
from src.coordinate.geometry_transformer import GeometryTransformer

__all__ = [
    "wgs84_to_gcj02",
    "gcj02_to_wgs84",
    "bd09_to_gcj02",
    "bd09_to_wgs84",
    "transform_geometry_wkt",
    "out_of_china",
    "CoordinateIntelligence",
    "MetricCRSStrategy",
    "MetricCRSSelection",
    "OperationType",
    "SelectionMethod",
    "ValidExtentStatus",
    "AccuracyClass",
    "MetricGeometry",
    "TransformedGeometry",
    "GeometryTransformer",
]