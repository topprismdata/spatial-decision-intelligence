"""R14-P2 External Coverage Gate: Amap-coverage baseline rule.

Rule: An OSM residential polygon that (a) carries no name AND (b) has no
residential POI within search radius in an external POI gazetteer (Amap)
is classified as REJECTED (non-residential mislabel: farmland, scrub,
developing land), not UNRESOLVED.

Design Note: docs/r14-lit-review-optimization-proposal.md P2.
Empirical basis: full-batch Beijing run 2026-08-27 (1,691 API calls,
285 true compounds named, ~4,881 residual polygons farmland-dominated).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from src.domain.contracts import BoundaryHypothesis, ValidationResult, ValidationStatus


class ExternalPOIProvider(Protocol):
    """Gazetteer lookup contract so the gate stays provider-agnostic."""

    def has_residential_poi(
        self, lng: float, lat: float, radius_m: float = 200.0
    ) -> bool: ...


@dataclass(frozen=True)
class PolygonContext:
    """Everything the coverage gate needs to know about the source polygon."""

    osm_name: str = ""
    centroid_lng: float = 0.0
    centroid_lat: float = 0.0


class ExternalCoverageGate:
    """P2 gate: OSM unnamed + external gazetteer empty ⇒ REJECT."""

    SEARCH_RADIUS_M = 200.0

    def __init__(
        self,
        poi_provider: Optional[ExternalPOIProvider] = None,
        search_radius_m: float = SEARCH_RADIUS_M,
    ):
        self._provider = poi_provider
        self._radius = search_radius_m

    @staticmethod
    def _is_unnamed(name: str) -> bool:
        return name is None or not name.strip()

    def validate(
        self,
        context: PolygonContext,
        hypothesis: Optional[BoundaryHypothesis] = None,
    ) -> ValidationResult:
        entity_id = hypothesis.entity_id if hypothesis else context.osm_name

        # Named polygons pass unconditionally — naming itself is evidence of
        # a real compound even if the gazetteer disagrees.
        if not self._is_unnamed(context.osm_name):
            return ValidationResult(
                entity_id=entity_id, validator="ExternalCoverageGate",
                status=ValidationStatus.PASSED, findings=(), decision_ready=True,
            )

        # Unnamed but no provider wired → abstain from judgement; downstream
        # EvidenceGate still decides. The gate never fabricates coverage data.
        if self._provider is None:
            findings = ("external_coverage:no_provider_wired",)
            return ValidationResult(
                entity_id=entity_id, validator="ExternalCoverageGate",
                status=ValidationStatus.WARNED, findings=findings, decision_ready=True,
            )

        hit = self._provider.has_residential_poi(
            context.centroid_lng, context.centroid_lat, self._radius
        )
        if hit:
            # Unnamed in OSM but POI-positive: keep as candidate (naming happens
            # elsewhere); mild warning documents the provenance gap.
            findings = (f"external_coverage:unnamed_but_poi_hit(r={self._radius}m)",)
            return ValidationResult(
                entity_id=entity_id, validator="ExternalCoverageGate",
                status=ValidationStatus.WARNED, findings=findings, decision_ready=True,
            )

        # Core P2 rule: unnamed + no POI ⇒ farmland/scrub mislabel.
        findings = (
            f"external_coverage:unnamed_and_no_poi_within_{self._radius}m",
            "classification:probable_non_residential_landuse",
        )
        return ValidationResult(
            entity_id=entity_id, validator="ExternalCoverageGate",
            status=ValidationStatus.BLOCKED, findings=findings, decision_ready=False,
        )
