"""R2 Candidate Ranking Engine: separate from Provider generation.

Design Note v1.1 §5. B7 adds semantic features to the same candidates.
"""

from __future__ import annotations

from typing import Optional

from src.domain.contracts import BoundaryHypothesis
from src.providers import CandidateRankRecord


class CandidateRankingEngine:
    """Ranks boundary hypotheses without modifying them.

    B6: geometric features only
    B7: geometric + public semantic evidence features
    """

    def rank(
        self,
        hypotheses: list[BoundaryHypothesis],
        semantic_features_enabled: bool = False,
    ) -> list[CandidateRankRecord]:
        records = []
        for h in hypotheses:
            meta = getattr(h, "metadata", {}) or {}
            features = meta.get("provider_features", {})
            score = self._compute_score(h, features, semantic_features_enabled)
            records.append(CandidateRankRecord(
                hypothesis_id=h.id,
                ranking_score=round(score, 4),
                ranking_features={k: float(v) for k, v in features.items() if isinstance(v, (int, float))},
                ranking_policy_version="1.0",
            ))
        records.sort(key=lambda r: -r.ranking_score)
        return records

    @staticmethod
    def _compute_score(h: BoundaryHypothesis, features: dict, semantic: bool) -> float:
        base = 0.3

        # Area alignment with typical residential compound range
        area = features.get("polygon_area_m2") or features.get("block_area_m2") or features.get("cluster_area_m2") or 0.0
        if 5000 <= area <= 200000:
            base += 0.25
        elif 1000 <= area < 5000 or 200000 < area <= 1000000:
            base += 0.10

        # Seed proximity bonus
        dist = features.get("seed_distance_m", 9999)
        if dist < 50:
            base += 0.15
        elif dist < 150:
            base += 0.08

        # Name presence bonus
        if features.get("name_present", 0) > 0:
            base += 0.05

        # Building count bonus for cluster providers
        building_count = features.get("building_count", 0)
        if 3 <= building_count <= 100:
            base += 0.10

        # Semantic features for B7
        if semantic:
            if "source_semantic_role" in features:
                role = str(features.get("source_semantic_role", ""))
                if role == "RESIDENTIAL_LANDUSE":
                    base += 0.10

            # Road profile variant preference
            road_variant = features.get("road_profile_variant", "")
            if road_variant == "STRONG_ONLY":
                base += 0.03

        return min(1.0, max(0.0, base))