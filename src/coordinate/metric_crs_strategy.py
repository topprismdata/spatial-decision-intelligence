"""R1 Metric CRS Strategy: projected CRS selection for reliable metric computation.

Design Note v1.0:
- Geographic CRS (EPSG:4326) for storage/exchange
- Projected Metric CRS for distance/area/buffer/snapping/topology
- Strategy pattern: not hardcoded to Beijing
- Valid extent check: fail closed when outside area of use
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OperationType(str, Enum):
    """Metric operation types (Design Note §4.1)."""
    DISTANCE = "DISTANCE"
    LENGTH = "LENGTH"
    AREA = "AREA"
    BUFFER = "BUFFER"
    SNAP = "SNAP"
    TOPOLOGY = "TOPOLOGY"
    CLUSTERING = "CLUSTERING"
    SPATIAL_MATCHING = "SPATIAL_MATCHING"


class AccuracyClass(str, Enum):
    """Accuracy class for metric computation (Design Note §11)."""
    VALID_METRIC_COMPUTATION = "VALID_METRIC_COMPUTATION"
    OUTSIDE_VALID_EXTENT = "OUTSIDE_VALID_EXTENT"
    UNKNOWN = "UNKNOWN"


class SelectionMethod(str, Enum):
    """How the CRS was selected (Design Note §4.2)."""
    BENCHMARK_PROFILE = "BENCHMARK_PROFILE"
    UTM_ZONE_AUTO = "UTM_ZONE_AUTO"
    LARGE_EXTENT_STRATEGY = "LARGE_EXTENT_STRATEGY"
    FALLBACK = "FALLBACK"
    UNRESOLVED = "UNRESOLVED"


class ValidExtentStatus(str, Enum):
    """Valid extent check result (Design Note §12)."""
    VALID = "VALID"
    VALID_WITH_WARNING = "VALID_WITH_WARNING"
    INVALID = "INVALID"


@dataclass(frozen=True)
class MetricCRSSelection:
    """Result of CRS selection (Design Note §4.2)."""
    target_crs: str  # EPSG code, e.g. "EPSG:32650"
    selection_method: SelectionMethod = SelectionMethod.UNRESOLVED
    selection_reason: str = ""
    area_of_use: str = ""
    operation_type: OperationType = OperationType.DISTANCE
    valid: bool = False
    warnings: tuple[str, ...] = ()
    estimated_distortion_class: str = ""


@dataclass(frozen=True)
class TransformedGeometry:
    """Result of coordinate transformation (Design Note §7.1)."""
    geometry_wkt: str
    source_crs: str
    target_crs: str
    transform_operation: str = ""
    transform_metadata: str = ""

    @property
    def provenance(self) -> str:
        return (
            f"src={self.source_crs}→tgt={self.target_crs} "
            f"op={self.transform_operation} meta={self.transform_metadata}"
        )


@dataclass(frozen=True)
class MetricGeometry:
    """Geometry in a metric CRS with full provenance (Design Note §11)."""
    geometry_wkt: str
    crs: str
    operation_type: OperationType
    operation_parameters: str = ""
    metric_units: str = "meter"
    crs_validated: bool = False
    accuracy_class: AccuracyClass = AccuracyClass.UNKNOWN
    transform_chain: str = ""


# ── Strategy ──────────────────────────────────────────────────────────────────


class MetricCRSStrategy:
    """Strategy for selecting an appropriate projected CRS for metric computation.

    Core principle (Design Note §3): CRS selection must be:
    - By strategy, not hardcoded
    - Operation-type-aware
    - Valid-extent-checked
    - Fail closed when unresolvable
    """

    def select(
        self,
        geometry_extent: tuple[float, float, float, float],  # min_lng, min_lat, max_lng, max_lat
        geometry_centroid: tuple[float, float],  # lng, lat
        operation_type: OperationType = OperationType.DISTANCE,
        source_crs: str = "EPSG:4326",
        requested_accuracy: str = "STANDARD",
        benchmark_profile: Optional[str] = None,
    ) -> MetricCRSSelection:
        """Select the best projected CRS for the given geometry and operation.

        Rule 1: If benchmark profile is specified and geometry is within its extent, use it.
        Rule 2: If geometry is within a single UTM zone, auto-select.
        Rule 3: If geometry crosses UTM zones, return UNRESOLVED.
        Rule 4: Large extent → NOT_SUPPORTED (city-scale only).
        """
        if source_crs != "EPSG:4326" and source_crs != "WGS84":
            return MetricCRSSelection(
                target_crs="",
                selection_method=SelectionMethod.UNRESOLVED,
                selection_reason=f"Source CRS not supported: {source_crs}",
                valid=False,
                warnings=("source_crs_unknown",),
            )

        # Rule 1: Benchmark Profile
        if benchmark_profile == "Beijing":
            return self._beijing_profile(geometry_extent, operation_type)

        # Rule 2: Single UTM Zone
        selection = self._auto_utm(geometry_extent, geometry_centroid, operation_type)
        if selection.valid:
            return selection

        # Rule 3: Cross-zone → UNRESOLVED for city-scale
        # Rule 4: Large extent → NOT_SUPPORTED
        return MetricCRSSelection(
            target_crs="",
            selection_method=SelectionMethod.UNRESOLVED,
            selection_reason=(
                "No applicable projected CRS found. "
                "Geometry may cross UTM zones or be too large. "
                "City-scale only."
            ),
            valid=False,
            warnings=("no_applicable_crs", "city_scale_only"),
        )

    def _beijing_profile(
        self,
        extent: tuple[float, float, float, float],
        operation_type: OperationType,
    ) -> MetricCRSSelection:
        """Beijing Metric Profile: EPSG:32650 (UTM 50N).

        Two-level valid extent check (Design Note §Gate 6):
        Level 1 — CRS area_of_use: UTM zone 50N (114°E-120°E, northern hemisphere)
        Level 2 — Benchmark Profile extent: Beijing administrative area (~115.4°E-117.5°E, ~39.4°N-41.1°N)
        """
        min_lng, min_lat, max_lng, max_lat = extent
        centroid_lng = extent[0] + (extent[2] - extent[0]) / 2
        centroid_lat = extent[1] + (extent[3] - extent[1]) / 2

        warnings = []

        # Level 1: CRS area_of_use (UTM zone 50N: 114°E-120°E, global north)
        if min_lng < 114.0 or max_lng > 120.0:
            warnings.append(
                f"CRS_AREA_OF_USE: geometry extends beyond UTM 50N (114°E-120°E): "
                f"{min_lng:.2f}°E-{max_lng:.2f}°E"
            )
        if min_lat < 0:
            warnings.append(
                f"CRS_AREA_OF_USE: southern hemisphere geometry "
                f"outside UTM 50N valid range"
            )

        # Level 2: Benchmark Profile extent (Beijing ~115.4°E-117.5°E, ~39.4°N-41.1°N)
        beijing_extent = (115.4, 39.4, 117.5, 41.1)
        if (min_lng < beijing_extent[0] or max_lng > beijing_extent[2] or
            min_lat < beijing_extent[1] or max_lat > beijing_extent[3]):
            warnings.append(
                f"BENCHMARK_EXTENT: geometry extends beyond Beijing Benchmark "
                f"({beijing_extent[0]}°E,{beijing_extent[1]}°N)-"
                f"({beijing_extent[2]}°E,{beijing_extent[3]}°N): "
                f"({min_lng:.2f}°E,{min_lat:.2f}°N)-({max_lng:.2f}°E,{max_lat:.2f}°N)"
            )

        if warnings:
            return MetricCRSSelection(
                target_crs="EPSG:32650",
                selection_method=SelectionMethod.BENCHMARK_PROFILE,
                selection_reason=(
                    f"Beijing Benchmark Profile: EPSG:32650 (WGS84 / UTM zone 50N). "
                    f"Centroid at ({centroid_lng:.2f}°E, {centroid_lat:.2f}°N). "
                    f"Operation: {operation_type.value}. "
                    f"Valid extent warnings: {len(warnings)}"
                ),
                area_of_use="CRS: UT50N (114°E-120°E); Benchmark: Beijing (115.4°E-117.5°E)",
                operation_type=operation_type,
                valid=False,
                warnings=tuple(warnings),
                estimated_distortion_class="LOW (local urban scale)",
            )

        return MetricCRSSelection(
            target_crs="EPSG:32650",
            selection_method=SelectionMethod.BENCHMARK_PROFILE,
            selection_reason=(
                f"Beijing Benchmark Profile: EPSG:32650 (WGS84 / UTM zone 50N). "
                f"Centroid at ({centroid_lng:.2f}°E, {centroid_lat:.2f}°N). "
                f"Operation: {operation_type.value}. "
                f"Both CRS area_of_use and Benchmark extent validated."
            ),
            area_of_use="CRS: UT50N (114°E-120°E); Benchmark: Beijing (115.4°E-117.5°E)",
            operation_type=operation_type,
            valid=True,
            estimated_distortion_class="LOW (local urban scale)",
        )

    @staticmethod
    def _auto_utm(
        extent: tuple[float, float, float, float],
        centroid: tuple[float, float],
        operation_type: OperationType,
    ) -> MetricCRSSelection:
        """Auto-select UTM zone for a single-zone geometry.

        UTM zones are 6° wide. Zone = floor((lng + 180) / 6) + 1.
        """
        min_lng, min_lat, max_lng, max_lat = extent
        c_lng, c_lat = centroid

        # Check if geometry is within a single UTM zone
        zone_min = int((min_lng + 180.0) / 6.0) + 1
        zone_max = int((max_lng + 180.0) / 6.0) + 1

        if zone_min != zone_max:
            return MetricCRSSelection(
                target_crs="",
                selection_method=SelectionMethod.UNRESOLVED,
                selection_reason=(
                    f"Geometry crosses UTM zones: {zone_min}-{zone_max}. "
                    f"Single-zone UTM not applicable."
                ),
                valid=False,
                warnings=("cross_utm_zone",),
            )

        # Determine N/S hemisphere
        hemisphere = "N" if c_lat >= 0 else "S"
        epsg_code = 32600 + zone_min if hemisphere == "N" else 32700 + zone_min
        target_crs = f"EPSG:{epsg_code}"

        zone_lng_min = (zone_min - 1) * 6 - 180
        zone_lng_max = zone_min * 6 - 180

        return MetricCRSSelection(
            target_crs=target_crs,
            selection_method=SelectionMethod.UTM_ZONE_AUTO,
            selection_reason=(
                f"Auto-selected UTM zone {zone_min}{hemisphere} (EPSG:{epsg_code}). "
                f"Geometry within {zone_lng_min}°E-{zone_lng_max}°E. "
                f"Operation: {operation_type.value}."
            ),
            area_of_use=f"UTM zone {zone_min}{hemisphere} ({zone_lng_min}°E-{zone_lng_max}°E)",
            operation_type=operation_type,
            valid=True,
            estimated_distortion_class="LOW (local, single UTM zone)",
        )