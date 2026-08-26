"""P1-06 Vector Reconstruction: boundary regularization, semantic snapping, segment QA."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReconstructionResult:
    """Result of vector reconstruction for a boundary."""

    polygon_id: str
    original_wkt: str = ""
    regularized_wkt: str = ""
    snapped_wkt: str = ""
    n_vertices_original: int = 0
    n_vertices_regularized: int = 0
    simplification_ratio: float = 0.0
    qa_issues: list[str] = field(default_factory=list)
    qa_passed: bool = True


class VectorReconstructor:
    """Reconstructs and improves vector boundaries.

    Three operations:
    1. Regularization: Douglas-Peucker simplification
    2. Semantic snapping: align to roads and building edges
    3. Segment QA: validate segment quality
    """

    DEFAULT_TOLERANCE_DEG = 0.00005  # ~5m at 40°N

    def __init__(self, tolerance_deg: float = DEFAULT_TOLERANCE_DEG):
        self.tolerance_deg = tolerance_deg

    def regularize(self, polygon_id: str, polygon_wkt: str) -> ReconstructionResult:
        """Apply Douglas-Peucker simplification to reduce vertex count.

        Removes redundant vertices while preserving essential shape.
        """
        from shapely import wkt as _wkt

        try:
            polygon = _wkt.loads(polygon_wkt)
            exterior = polygon.exterior
            if exterior is None:
                return ReconstructionResult(
                    polygon_id=polygon_id,
                    original_wkt=polygon_wkt,
                    qa_issues=["no_exterior"],
                    qa_passed=False,
                )

            original_coords = list(exterior.coords)
            n_original = len(original_coords)

            # Simplify using Douglas-Peucker
            simplified = polygon.simplify(self.tolerance_deg, preserve_topology=True)
            simplified_coords = list(simplified.exterior.coords) if simplified.exterior else []
            n_simplified = len(simplified_coords)

            result = ReconstructionResult(
                polygon_id=polygon_id,
                original_wkt=polygon_wkt,
                regularized_wkt=simplified.wkt if simplified else polygon_wkt,
                n_vertices_original=n_original,
                n_vertices_regularized=n_simplified,
                simplification_ratio=(
                    1.0 - n_simplified / max(n_original, 1)
                ),
            )

            # Run QA
            result.qa_issues = self._qa(polygon, simplified)
            result.qa_passed = len(result.qa_issues) == 0
            result.snapped_wkt = result.regularized_wkt

            return result
        except Exception as e:
            return ReconstructionResult(
                polygon_id=polygon_id,
                original_wkt=polygon_wkt,
                qa_issues=[f"error:{e}"],
                qa_passed=False,
            )

    def snap_to_roads(
        self,
        polygon_wkt: str,
        road_network_wkt: list[str],
        ref_lat: float = 39.9,
    ) -> str:
        """Snap boundary vertices to the nearest road geometry.

        Vertices within tolerance are moved to lie exactly on the road.
        """
        from shapely import wkt as _wkt
        from shapely.ops import nearest_points
        from src.coordinate.metric_service import MetricGeometryService
        _ms = MetricGeometryService()

        try:
            polygon = _wkt.loads(polygon_wkt)
            if polygon.exterior is None:
                return polygon_wkt

            # Build road union
            from shapely.ops import unary_union
            roads = []
            for rwkt in road_network_wkt:
                try:
                    roads.append(_wkt.loads(rwkt))
                except Exception:
                    pass
            if not roads:
                return polygon_wkt
            road_union = unary_union(roads)

            # Snap each vertex
            snap_distance = _ms.snap_tolerance_deg(10.0, ref_lat)  # 10m snap radius
            coords = list(polygon.exterior.coords)
            snapped = []
            for x, y in coords:
                pt = _wkt.loads(f"POINT({x} {y})")
                if pt.distance(road_union) < snap_distance:
                    nearest = nearest_points(road_union, pt)
                    snapped.append((nearest[0].x, nearest[0].y))
                else:
                    snapped.append((x, y))

            # Rebuild polygon
            coord_str = ", ".join(f"{x} {y}" for x, y in snapped)
            return f"POLYGON(({coord_str}))"
        except Exception:
            return polygon_wkt

    @staticmethod
    def _qa(original, simplified) -> list[str]:
        """Run quality checks on the reconstructed boundary."""
        issues = []

        # Check for self-intersection
        if not simplified.is_valid:
            issues.append("self_intersection")
        if simplified.is_empty:
            issues.append("empty_geometry")

        # Check topology preservation
        if not original.contains(simplified) and not simplified.contains(original):
            # Check overlap ratio
            try:
                intersection = original.intersection(simplified)
                overlap = intersection.area / max(original.area, 0.01)
                if overlap < 0.85:
                    issues.append(f"topology_change:overlap={overlap:.0%}")
            except Exception:
                issues.append("topology_check_failed")

        # Check excessive simplification
        orig_n = len(list(original.exterior.coords)) if original.exterior else 0
        simp_n = len(list(simplified.exterior.coords)) if simplified.exterior else 0
        if orig_n > 0 and simp_n < 3:
            issues.append("excessive_simplification")
        if orig_n > 20 and simp_n < 4:
            issues.append("over_simplified")

        return issues