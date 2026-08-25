"""
Downstream Decision Engine Adapters with Fail-Closed Decision Readiness Gates.
Transforms TrustedSpatialState into type-safe, validated inputs for:
  * market-partition (Territory Planning)
  * visit-scheduling-optimizer (Sales Visit Scheduling / SVDE)
  * coverage-analysis (Store Network / Market Coverage)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from src.domain.world_model import (
    TrustedSpatialState,
    SpatialEntity,
    FindingSeverity,
    ValidationStatus
)

logger = logging.getLogger("decision_adapters")


@dataclass
class TerritoryPlanningRecord:
    """Type-safe payload for market-partition territory solvers."""
    entity_id: str
    canonical_name: str
    centroid_lng: float
    centroid_lat: float
    polygon_wkt: str
    effective_area_m2: float
    city: str
    district: str
    is_safe: bool = True
    quarantine_reason: Optional[str] = None


@dataclass
class VisitSchedulingRecord:
    """Type-safe payload for visit-scheduling-optimizer / SVDE solvers."""
    entity_id: str
    name: str
    address: str
    lng: float
    lat: float
    city: str
    is_safe: bool = True
    quarantine_reason: Optional[str] = None


@dataclass
class CoverageCellRecord:
    """Type-safe payload for market coverage and store network analysis."""
    entity_id: str
    name: str
    polygon_wkt: str
    net_area_m2: float
    is_deduplicated: bool = True


class TerritoryPlanningAdapter:
    """Adapter for territory design / market-partition solver with Fail-Closed gate."""
    CONSUMER_NAME = "market-partition"

    @classmethod
    def compile(cls, state: TrustedSpatialState) -> List[TerritoryPlanningRecord]:
        results = []
        blocked_count = 0

        # Build lookup for active critical findings
        critical_finding_targets = {
            f.target_id: f for f in state.findings if f.severity == FindingSeverity.CRITICAL
        }

        for ent_id, ent in state.entities.items():
            geom = state.geometries.get(ent.geometry_observation_id or "")

            # Gate 1: Check if entity has critical finding blocking this consumer
            if ent_id in critical_finding_targets:
                finding = critical_finding_targets[ent_id]
                if cls.CONSUMER_NAME in finding.decision_impact.blocked_consumers or not ent.is_decision_ready:
                    logger.warning(
                        f"[Fail-Closed] Quarantining {ent_id} ({ent.canonical_name}) from territory solver: "
                        f"{finding.evidence.explanation}"
                    )
                    blocked_count += 1
                    continue

            # Gate 2: Geometric & coordinate validity
            if not geom or geom.validation_status in (ValidationStatus.QUARANTINED, ValidationStatus.REJECTED):
                blocked_count += 1
                continue

            if not ent.point_wgs84:
                blocked_count += 1
                continue

            # Fail-Closed Rule: Area > 2 km² is an extreme outlier that would distort territory capacity
            area_m2 = geom.qa_score  # approximate or extracted
            if "area_m2" in ent.attributes and float(ent.attributes.get("area_m2", 0)) > 2_000_000.0:
                logger.warning(f"[Fail-Closed] Quarantining {ent_id}: Outlier Area > 2km2 would corrupt territory design.")
                blocked_count += 1
                continue

            rec = TerritoryPlanningRecord(
                entity_id=ent.entity_id,
                canonical_name=ent.canonical_name,
                centroid_lng=ent.point_wgs84[0],
                centroid_lat=ent.point_wgs84[1],
                polygon_wkt=geom.geometry_wkt,
                effective_area_m2=float(ent.attributes.get("area_m2", 0.0)),
                city=ent.city,
                district=ent.district,
                is_safe=True
            )
            results.append(rec)

        logger.info(f"[TerritoryAdapter] Compiled {len(results)} safe entities (Quarantined: {blocked_count}).")
        return results


class VisitSchedulingAdapter:
    """Adapter for sales visit scheduling (SVDE) with Fail-Closed gate."""
    CONSUMER_NAME = "visit-scheduling-optimizer"

    @classmethod
    def compile(cls, state: TrustedSpatialState) -> List[VisitSchedulingRecord]:
        results = []
        blocked_count = 0

        for ent_id, ent in state.entities.items():
            if not ent.is_decision_ready or not ent.point_wgs84:
                blocked_count += 1
                continue

            # Fail-Closed: (0,0) or missing coordinates strictly prohibited
            if ent.point_wgs84[0] == 0.0 or ent.point_wgs84[1] == 0.0:
                blocked_count += 1
                continue

            rec = VisitSchedulingRecord(
                entity_id=ent.entity_id,
                name=ent.canonical_name,
                address=ent.address,
                lng=ent.point_wgs84[0],
                lat=ent.point_wgs84[1],
                city=ent.city,
                is_safe=True
            )
            results.append(rec)

        logger.info(f"[VisitAdapter] Compiled {len(results)} visitable points (Quarantined: {blocked_count}).")
        return results


class CoverageAnalysisAdapter:
    """Adapter for store network / coverage analysis with deduplication gate."""
    CONSUMER_NAME = "coverage-analysis"

    @classmethod
    def compile(cls, state: TrustedSpatialState) -> List[CoverageCellRecord]:
        results = []
        # Exclude known duplicate object entities to eliminate double-counted ground
        quarantined_duplicates = set()
        for rel in state.relations:
            if rel.relation_type in ("SAME_ENTITY", "POSSIBLE_MERGE_ERROR") and rel.iou > 0.30:
                quarantined_duplicates.add(rel.object_id)

        for ent_id, ent in state.entities.items():
            if ent_id in quarantined_duplicates:
                continue

            geom = state.geometries.get(ent.geometry_observation_id or "")
            if not geom or not geom.geometry_wkt:
                continue

            rec = CoverageCellRecord(
                entity_id=ent.entity_id,
                name=ent.canonical_name,
                polygon_wkt=geom.geometry_wkt,
                net_area_m2=float(ent.attributes.get("area_m2", 0.0)),
                is_deduplicated=True
            )
            results.append(rec)

        logger.info(f"[CoverageAdapter] Compiled {len(results)} deduplicated coverage cells (Excluded duplicates: {len(quarantined_duplicates)}).")
        return results
