"""P1-07 Shared Boundary: city-level topology and boundary consistency.

Detects shared boundaries between adjacent compounds, validates topology,
and checks for gaps/overlaps between neighboring boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SharedBoundary:
    """A boundary segment shared between two entities."""

    entity_a_id: str
    entity_b_id: str
    geometry_wkt: str  # LINESTRING of the shared portion
    length_m: float = 0.0
    confidence: float = 0.0
    gap: float = 0.0  # Gap between the two boundaries (0 = perfect alignment)
    overlap: float = 0.0  # Overlap area (0 = no overlap)


@dataclass
class TopologyReport:
    """Report of topology consistency across a set of boundaries."""

    n_entities: int = 0
    n_shared_boundaries: int = 0
    n_gaps: int = 0
    n_overlaps: int = 0
    total_gap_m: float = 0.0
    total_overlap_m2: float = 0.0
    shared_boundaries: list[SharedBoundary] = field(default_factory=list)
    topology_issues: list[str] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        return self.n_gaps == 0 and self.n_overlaps == 0 and len(self.topology_issues) == 0


class SharedBoundaryAnalyzer:
    """Analyzes shared boundaries between adjacent spatial entities.

    Detects:
    - Shared boundary segments (common edges)
    - Gaps between adjacent boundaries
    - Overlaps (conflicting claims to the same area)
    """

    MAX_GAP_M = 5.0  # Maximum gap considered a topology issue
    MIN_OVERLAP_M2 = 10.0  # Minimum overlap to report

    def __init__(self):
        pass

    def analyze(
        self,
        boundaries: dict[str, str],  # entity_id -> polygon_wkt
        ref_lat: float = 39.9,
    ) -> TopologyReport:
        """Analyze topology across all boundaries.

        For each pair of entities, check if they share a boundary,
        have a gap between them, or overlap.
        """
        from shapely import wkt as _wkt
        from src.coordinate.metric_service import MetricGeometryService
        _ms = MetricGeometryService()

        entities = {}
        for eid, wkt_str in boundaries.items():
            try:
                entities[eid] = _wkt.loads(wkt_str)
            except Exception:
                pass

        report = TopologyReport(n_entities=len(entities))

        # Tolerance for "shared" boundary (in degrees, via MetricGeometryService)
        tol = _ms.snap_tolerance_deg(self.MAX_GAP_M, ref_lat)

        entity_ids = list(entities.keys())
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                a_id = entity_ids[i]
                b_id = entity_ids[j]
                a_geom = entities[a_id]
                b_geom = entities[b_id]

                if not a_geom.intersects(b_geom.buffer(tol)):
                    continue  # Not adjacent

                # Check for overlap
                if a_geom.intersects(b_geom):
                    try:
                        intersection = a_geom.intersection(b_geom)
                        if intersection.area > 0:
                            overlap_m2 = _ms.area_m2(intersection.wkt)
                            if overlap_m2 > self.MIN_OVERLAP_M2:
                                report.n_overlaps += 1
                                report.total_overlap_m2 += overlap_m2
                                report.topology_issues.append(
                                    f"overlap:{a_id}↔{b_id}:{overlap_m2:.0f}m²"
                                )
                    except Exception:
                        pass

                # Check for gap
                gap = a_geom.distance(b_geom)
                if 0 < gap <= tol:
                    gap_m = gap * 111_000  # Approximate conversion
                    report.n_gaps += 1
                    report.total_gap_m += gap_m
                    report.topology_issues.append(
                        f"gap:{a_id}↔{b_id}:{gap_m:.0f}m"
                    )

                # Check for shared boundary (touching)
                if a_geom.touches(b_geom):
                    try:
                        shared = a_geom.intersection(b_geom)
                        if hasattr(shared, 'length') and shared.length > 0:
                            shared_length_m = shared.length * 111_000
                            report.shared_boundaries.append(
                                SharedBoundary(
                                    entity_a_id=a_id,
                                    entity_b_id=b_id,
                                    geometry_wkt=shared.wkt,
                                    length_m=shared_length_m,
                                    confidence=1.0 if shared_length_m > 10 else 0.5,
                                )
                            )
                            report.n_shared_boundaries += 1
                    except Exception:
                        pass

        return report

    @staticmethod
    def check_consistency(
        report: TopologyReport,
        max_gap_m: float = 5.0,
        max_overlap_m2: float = 100.0,
    ) -> bool:
        """Check if topology is consistent within thresholds."""
        return (
            report.n_gaps == 0
            and report.n_overlaps == 0
            and len(report.topology_issues) == 0
        )