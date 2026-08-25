"""
Unit tests for Spatial World Model and Downstream Decision Adapters.
"""

from __future__ import annotations

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.domain.world_model import (
    SpatialEntity,
    EntityCategory,
    GeometryObservation,
    ValidationStatus,
    QualityFinding,
    FindingSeverity,
    EvidencePacket,
    DecisionImpact,
    TrustedSpatialState
)
from src.adapters.decision_adapters import (
    TerritoryPlanningAdapter,
    VisitSchedulingAdapter,
    CoverageAnalysisAdapter
)


def test_world_model_and_adapters():
    # 1. Create a safe entity
    ent1 = SpatialEntity(
        entity_id="ENT_001",
        category=EntityCategory.RESIDENTIAL_COMMUNITY,
        canonical_name="阳光花园",
        city="北京市",
        district="朝阳区",
        address="朝阳路1号",
        point_wgs84=(116.45, 39.92),
        geometry_observation_id="GEO_001",
        attributes={"area_m2": 35000.0},
        is_decision_ready=True
    )
    geom1 = GeometryObservation(
        observation_id="GEO_001",
        geometry_wkt="POLYGON((116.45 39.92, 116.453 39.92, 116.453 39.923, 116.45 39.923, 116.45 39.92))",
        geometry_type="POLYGON",
        crs="WGS84",
        observed_at="2026-08-25T00:00:00",
        source="SYSTEM_INGEST",
        qa_score=1.0,
        validation_status=ValidationStatus.VERIFIED_VALID
    )

    # 2. Create a corrupted entity (Outlier area > 2km2)
    ent2 = SpatialEntity(
        entity_id="ENT_002",
        category=EntityCategory.RESIDENTIAL_COMMUNITY,
        canonical_name="异常超大园区",
        city="北京市",
        district="海淀区",
        point_wgs84=(116.30, 39.95),
        geometry_observation_id="GEO_002",
        attributes={"area_m2": 5_740_000.0},  # 5.74 km²!
        active_findings=["FIND_002"],
        is_decision_ready=False
    )
    finding2 = QualityFinding(
        finding_id="FIND_002",
        target_id="ENT_002",
        category="OUTLIER_SUPER_AREA",
        severity=FindingSeverity.CRITICAL,
        evidence=EvidencePacket(
            diagnostic_rule="AREA_OUTLIER_MAX_THRESHOLD",
            explanation="围栏面积 5.74 km² 超出住宅小区合理上限 200 倍",
            metrics={"area_m2": 5740000.0}
        ),
        decision_impact=DecisionImpact(
            risk_level="HIGH_CORRUPTION",
            polluted_decisions=["TERRITORY_CAPACITY_OVERESTIMATION"],
            blocked_consumers=["market-partition"]
        ),
        recommended_review="在源头重新核定地块或拆分为子社区"
    )

    # 3. Assemble TrustedSpatialState
    state = TrustedSpatialState(
        state_version="2026.08.25.v1",
        published_at="2026-08-25T12:00:00",
        entities={"ENT_001": ent1, "ENT_002": ent2},
        geometries={"GEO_001": geom1},
        findings=[finding2]
    )

    # 4. Test TerritoryPlanningAdapter Fail-Closed Gate
    territory_inputs = TerritoryPlanningAdapter.compile(state)
    assert len(territory_inputs) == 1, f"Expected 1 safe entity, got {len(territory_inputs)}"
    assert territory_inputs[0].entity_id == "ENT_001"
    print("✓ TerritoryPlanningAdapter correctly quarantined ENT_002 via Fail-Closed gate!")

    # 5. Test VisitSchedulingAdapter
    visit_inputs = VisitSchedulingAdapter.compile(state)
    assert len(visit_inputs) == 1
    assert visit_inputs[0].entity_id == "ENT_001"
    print("✓ VisitSchedulingAdapter successfully compiled safe visit locations!")

    # 6. Test CoverageAnalysisAdapter
    cov_inputs = CoverageAnalysisAdapter.compile(state)
    assert len(cov_inputs) == 1
    print("✓ CoverageAnalysisAdapter successfully compiled safe coverage cells!")

    print("\nALL WORLD MODEL & ADAPTER TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_world_model_and_adapters()
