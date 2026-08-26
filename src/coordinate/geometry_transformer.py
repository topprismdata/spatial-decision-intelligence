"""R1 Geometry Transformer: forward/inverse CRS transformation with provenance.

Design Note §7: GeometryTransformationContract
- always_xy=True for consistent lon,lat axis order
- Strict error handling: inf/NaN detection, fail closed
- Full provenance: transformer definition, description, accuracy, area_of_use
"""

from __future__ import annotations

from functools import partial
from typing import Optional

import pyproj
from shapely import wkt as _wkt
from shapely.ops import transform as shapely_transform

from src.coordinate.metric_crs_strategy import (
    MetricCRSSelection,
    OperationType,
    TransformedGeometry,
    MetricGeometry,
    AccuracyClass,
)


class TransformationError(Exception):
    pass


class GeometryTransformer:
    _crs_cache: dict[str, object] = {}

    @classmethod
    def _get_crs(cls, epsg: str):
        if epsg not in cls._crs_cache:
            cls._crs_cache[epsg] = pyproj.CRS(epsg)
        return cls._crs_cache[epsg]

    @classmethod
    def _get_transformer(cls, source_crs: str, target_crs: str):
        key = f"{source_crs}→{target_crs}"
        if key not in cls._crs_cache:
            src = cls._get_crs(source_crs)
            tgt = cls._get_crs(target_crs)
            transformer = pyproj.Transformer.from_crs(src, tgt, always_xy=True)
            cls._crs_cache[key] = {
                "transformer": transformer,
                "definition": getattr(transformer, "definition", ""),
                "description": getattr(transformer, "description", ""),
                "accuracy": cls._get_transformer_accuracy(transformer),
                "area_of_use": cls._get_area_of_use(target_crs),
            }
        return cls._crs_cache[key]

    @staticmethod
    def _get_transformer_accuracy(transformer) -> str:
        try:
            if hasattr(transformer, "accuracy") and transformer.accuracy is not None:
                return f"{transformer.accuracy:.2f}m"
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def _get_area_of_use(crs: str) -> str:
        try:
            c = GeometryTransformer._get_crs(crs)
            if hasattr(c, "area_of_use") and c.area_of_use:
                b = c.area_of_use
                return f"west={b.west_degree:.2f} south={b.south_degree:.2f} east={b.east_degree:.2f} north={b.north_degree:.2f}"
        except Exception:
            pass
        return "unknown"

    @classmethod
    def forward_transform(cls, geometry_wkt: str, source_crs: str, target_crs: str) -> TransformedGeometry:
        if source_crs == target_crs:
            return TransformedGeometry(
                geometry_wkt=geometry_wkt, source_crs=source_crs, target_crs=target_crs,
                transform_operation="identity", transform_metadata="no_transform_needed",
            )
        info = cls._get_transformer(source_crs, target_crs)
        transformer = info["transformer"]
        project = partial(transformer.transform)
        geom = _wkt.loads(geometry_wkt)
        try:
            transformed = shapely_transform(project, geom)
        except Exception as e:
            raise TransformationError(f"CRS transform failed: {source_crs}→{target_crs}: {e}")
        wkt_str = transformed.wkt
        if "inf" in wkt_str.lower() or "nan" in wkt_str.lower():
            raise TransformationError(f"CRS transform produced invalid coordinates: {wkt_str[:100]}")
        metadata = (
            f"pyproj v{pyproj.__version__} "
            f"proj={info['description']} "
            f"accuracy={info['accuracy']} "
            f"area_of_use=[{info['area_of_use']}]"
        )
        return TransformedGeometry(
            geometry_wkt=wkt_str, source_crs=source_crs, target_crs=target_crs,
            transform_operation=f"{source_crs}→{target_crs} (always_xy=True)",
            transform_metadata=metadata,
        )

    @classmethod
    def inverse_transform(cls, transformed: TransformedGeometry, original_source_crs: str) -> TransformedGeometry:
        return cls.forward_transform(transformed.geometry_wkt, transformed.target_crs, original_source_crs)

    @classmethod
    def to_metric_geometry(cls, geometry_wkt: str, selection: MetricCRSSelection,
                           operation_type: OperationType, source_crs: str = "EPSG:4326") -> MetricGeometry:
        if not selection.valid:
            return MetricGeometry(
                geometry_wkt=geometry_wkt, crs=source_crs, operation_type=operation_type,
                accuracy_class=AccuracyClass.OUTSIDE_VALID_EXTENT, crs_validated=False,
            )
        try:
            transformed = cls.forward_transform(geometry_wkt, source_crs, selection.target_crs)
            return MetricGeometry(
                geometry_wkt=transformed.geometry_wkt, crs=selection.target_crs,
                operation_type=operation_type, crs_validated=selection.valid,
                accuracy_class=AccuracyClass.VALID_METRIC_COMPUTATION,
                transform_chain=transformed.provenance,
            )
        except TransformationError as e:
            return MetricGeometry(
                geometry_wkt=geometry_wkt, crs=source_crs, operation_type=operation_type,
                accuracy_class=AccuracyClass.UNKNOWN, crs_validated=False,
                transform_chain=f"transform_failed: {e}",
            )
    @classmethod
    def inverse_transform_from_wkt(cls, geometry_wkt: str, source_crs: str, target_crs: str) -> str:
        """Transform a WKT string from one CRS to another and return WKT."""
        result = cls.forward_transform(geometry_wkt, source_crs, target_crs)
        return result.geometry_wkt
