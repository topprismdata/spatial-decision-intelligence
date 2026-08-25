"""
Integration test for Spatial Intelligence Agent Platform (4-Agent Pipeline).
Verifies end-to-end execution from raw name/point brief to Trusted Spatial State and downstream adapters.
"""

from __future__ import annotations

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.agents import (
    EntityResolutionAgent,
    BoundaryReasoningAgent,
    GeometryGenerationAgent,
    GeometryQAAgent,
    SpatialIntelligencePlatform
)
from src.adapters.decision_adapters import TerritoryPlanningAdapter, VisitSchedulingAdapter


def test_agent_platform_pipeline():
    print("=== 1. Testing EntityResolutionAgent ===")
    entity_agent = EntityResolutionAgent()
    ctx = entity_agent.resolve("万科星河湾一期(南区)", "朝阳区朝阳北路88号")
    print(f"  Canonical: {ctx.canonical_name}, Base: {ctx.base_name}, Phase: {ctx.phase_id}, Subarea: {ctx.subarea_id}")
    assert ctx.base_name == "万科星河湾"
    assert ctx.phase_id == "一期"
    assert ctx.subarea_id == "南区"
    assert ctx.scale_level == "COMMUNITY_LEVEL"
    print("  ✓ EntityResolutionAgent passed!")

    print("\n=== 2. Testing BoundaryReasoningAgent ===")
    boundary_agent = BoundaryReasoningAgent()
    constraints = boundary_agent.reason_constraints(ctx, seed_lng=116.450, seed_lat=39.920, prior_area_m2=30000.0)
    print(f"  TargetArea: {constraints.target_area_m2}m², Radius: {constraints.search_radius_m:.1f}m, BBox: {constraints.search_bbox}")
    assert constraints.target_area_m2 == 30000.0
    assert constraints.search_radius_m > 100.0
    print("  ✓ BoundaryReasoningAgent passed!")

    print("\n=== 3. Testing GeometryGenerationAgent & Candidate Fusion ===")
    geom_agent = GeometryGenerationAgent()
    gen_res = geom_agent.generate(ctx, constraints)
    print(f"  Chosen Method: {gen_res.chosen_hypothesis.method}, Score: {gen_res.confidence_score:.3f}, Area: {gen_res.chosen_hypothesis.area_m2:.0f}m²")
    print(f"  Candidate Hypotheses ({len(gen_res.all_hypotheses)}):")
    for h in gen_res.all_hypotheses:
        print(f"    - [{h.method}] Score={h.score:.3f}, Area={h.area_m2:.0f}m² ({h.explanation})")
    assert len(gen_res.all_hypotheses) == 3
    assert gen_res.confidence_score > 0.60
    print("  ✓ GeometryGenerationAgent passed!")

    print("\n=== 4. Testing GeometryQAAgent ===")
    qa_agent = GeometryQAAgent()
    qa_audit = qa_agent.audit(ctx, constraints, gen_res)
    print(f"  Audit Status: {qa_audit.decision_summary}")
    print(f"  Decision Ready: {qa_audit.is_decision_ready}")
    assert qa_audit.is_decision_ready is True
    print("  ✓ GeometryQAAgent passed!")

    print("\n=== 5. Testing Master Orchestrator (SpatialIntelligencePlatform) ===")
    platform = SpatialIntelligencePlatform()
    test_briefs = [
        {"name": "万科星河湾一期", "address": "朝阳北路88号", "lng": 116.450, "lat": 39.920, "area_m2": 35000},
        {"name": "西黄城根北街甲9号院", "address": "西城区西黄城根北街", "lng": 116.375, "lat": 39.930, "area_m2": 2500},
    ]
    trusted_state = platform.batch_generate_and_govern(test_briefs)
    stats = trusted_state.summary_stats()
    print(f"  Trusted Spatial State: {stats}")
    assert stats["total_entities"] == 2
    assert stats["decision_ready_entities"] == 2
    print("  ✓ SpatialIntelligencePlatform passed!")

    print("\n=== 6. Testing Downstream Solver Compilation (Territory & Visit) ===")
    territory_payloads = TerritoryPlanningAdapter.compile(trusted_state)
    visit_payloads = VisitSchedulingAdapter.compile(trusted_state)
    assert len(territory_payloads) == 2
    assert len(visit_payloads) == 2
    print(f"  Compiled {len(territory_payloads)} territory records and {len(visit_payloads)} visit records.")
    print("  ✓ Downstream Decision Adapters passed!")

    print("\n🎉 ALL 4-AGENT PLATFORM & ORCHESTRATOR TESTS PASSED!")


if __name__ == "__main__":
    test_agent_platform_pipeline()
