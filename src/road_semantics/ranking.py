"""R8 Common Ranking Adapter: consumes RoadSemanticAssertion from both B8-D and B8-V.

Same downstream logic for both interpreters. Only the semantic feature source differs.
"""

from __future__ import annotations

from src.domain.contracts import BoundaryHypothesis
from src.providers import CandidateRankRecord
from src.road_semantics import RoadSemanticAssertion


class RoadSemanticRankingAdapter:
    """Ranking adapter that consumes RoadSemanticAssertion from any interpreter.

    Used by both B8-D and B8-V. The only variable is which interpreter
    produced the RoadSemanticAssertion.
    """

    def rank(self, hypotheses: list[BoundaryHypothesis], assertions: list[RoadSemanticAssertion]) -> list[CandidateRankRecord]:
        records = []
        for h in hypotheses:
            score = self._compute_score(h, assertions)
            records.append(CandidateRankRecord(
                hypothesis_id=h.id,
                ranking_score=round(score, 4),
                ranking_features={"road_semantic_score": score},
                ranking_policy_version="r8-v1",
            ))
        records.sort(key=lambda r: -r.ranking_score)
        return records

    @staticmethod
    def _compute_score(h: BoundaryHypothesis, assertions: list[RoadSemanticAssertion]) -> float:
        base = 0.3

        # Area alignment
        meta = getattr(h, "metadata", {}) or {}
        features = meta.get("provider_features", {}) if isinstance(meta, dict) else {}
        area = features.get("polygon_area_m2") or features.get("block_area_m2") or features.get("cluster_area_m2") or 0.0
        if 5000 <= area <= 200000:
            base += 0.20
        elif 1000 <= area < 5000:
            base += 0.08

        # Road semantic bonus
        for a in assertions:
            if a.road_role.value == "PUBLIC_SEPARATOR":
                base += 0.15
            elif a.road_role.value == "WEAK_SEPARATOR":
                base += 0.05
            if a.continuity.value == "THROUGH":
                base += 0.10
            if a.compound_split_support.value == "SUPPORT":
                base += 0.10

        return min(1.0, max(0.0, base))