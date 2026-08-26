"""R11 Evidence-aware Spatial Topology Reasoner + Deterministic GIS operations.

Semantic topology assertions are separate from deterministic geometry repair.
"""

from __future__ import annotations

from shapely import wkt as _wkt
from shapely.ops import unary_union

from src.topology.contract import (
    TopologyAssertion,
    TopologyRelation,
    TopologyRepairOperation,
)
from src.road_semantics import RoadSemanticAssertion, RoadRole
from src.membership.analyzer_v2 import BuildingMembershipAnalyzerV2


class EvidenceAwareTopologyReasoner:
    """Produces TopologyAssertion from candidate boundaries + evidence from R8/R9.

    Input: Candidate Boundaries + RoadSemanticAssertion + BuildingMembership
    Output: TopologyAssertion (semantic only, no geometry changes)
    """

    def analyze(self, entity_a: str, entity_b: str,
                geom_a: str, geom_b: str,
                road_assertions: list[RoadSemanticAssertion] | None = None,
                building_membership: dict | None = None) -> TopologyAssertion:
        from shapely import wkt as _wkt
        ga = _wkt.loads(geom_a)
        gb = _wkt.loads(geom_b)

        evidence = []
        conflict = []

        # Check for overlap
        if ga.intersects(gb):
            inter = ga.intersection(gb)
            if inter.area > 0:
                area_m2 = inter.area * 111_000 * 111_000
                if area_m2 > 100:
                    conflict.append(f"overlap:{area_m2:.0f}m2")
                    return TopologyAssertion(
                        entity_a=entity_a, entity_b=entity_b,
                        relation=TopologyRelation.OVERLAP_CONFLICT,
                        confidence=0.9,
                        conflicting_evidence=tuple(conflict),
                        separator_feature=f"overlap_area={area_m2:.0f}m2",
                    )

        # Check gap
        gap = ga.distance(gb)
        gap_m = gap * 111_000
        if 0 < gap_m < 50:
            # Check if road assertion explains the gap
            for ra in (road_assertions or []):
                if ra.road_role == RoadRole.PUBLIC_SEPARATOR and ra.continuity.value == "THROUGH":
                    return TopologyAssertion(
                        entity_a=entity_a, entity_b=entity_b,
                        relation=TopologyRelation.SEPARATED_BY,
                        confidence=ra.evidence_features.get("vlm_confidence", 0.85),
                        supporting_evidence=(f"public_road:{ra.road_segment_id}",),
                        separator_feature=f"road:{ra.road_segment_id}",
                        affected_segments=(f"gap:{gap_m:.0f}m",),
                    )
            return TopologyAssertion(
                entity_a=entity_a, entity_b=entity_b,
                relation=TopologyRelation.GAP_CONFLICT,
                confidence=0.6,
                conflicting_evidence=(f"unexplained_gap:{gap_m:.0f}m",),
            )

        # Check shared boundary
        if ga.touches(gb):
            shared = ga.intersection(gb)
            shared_len = shared.length * 111_000 if hasattr(shared, 'length') else 0
            if shared_len > 5:
                return TopologyAssertion(
                    entity_a=entity_a, entity_b=entity_b,
                    relation=TopologyRelation.SHARED_BOUNDARY,
                    confidence=0.85,
                    supporting_evidence=(f"shared_edge:{shared_len:.0f}m",),
                )

        return TopologyAssertion(
            entity_a=entity_a, entity_b=entity_b,
            relation=TopologyRelation.UNKNOWN,
            confidence=0.0,
        )


class TopologyRepairExecutor:
    """Deterministic GIS operations — separate from semantic reasoning."""

    @staticmethod
    def repair(assertion: TopologyAssertion, geom_a: str, geom_b: str) -> list[TopologyRepairOperation]:
        ops = []
        ga = _wkt.loads(geom_a)
        gb = _wkt.loads(geom_b)

        if assertion.relation == TopologyRelation.OVERLAP_CONFLICT:
            diff = ga.difference(gb)
            ops.append(TopologyRepairOperation(
                operation="REMOVE_OVERLAP",
                geometry_wkt=diff.wkt,
                assertion_id=assertion.entity_a,
                parameters={"type": "overlap_removal"},
            ))

        if assertion.relation == TopologyRelation.GAP_CONFLICT:
            # Simple gap repair: buffer and merge
            threshold = 0.0005
            merged = unary_union([ga.buffer(threshold), gb.buffer(threshold)])
            ops.append(TopologyRepairOperation(
                operation="REPAIR_GAP",
                geometry_wkt=merged.wkt,
                assertion_id=assertion.entity_a,
                parameters={"threshold_deg": threshold},
            ))

        if assertion.relation == TopologyRelation.SHARED_BOUNDARY:
            snapped = unary_union([ga, gb])
            ops.append(TopologyRepairOperation(
                operation="SNAP",
                geometry_wkt=snapped.wkt,
                assertion_id=assertion.entity_a,
                parameters={"type": "shared_edge_snap"},
            ))
        return ops