"""
Tests for the Perception Operator Algebra
(src/perception/operators.py + adapters).

Covers:
  INV-12 plug-in seam: new perception registers by id; zero engine change
  INV-13 lineage: refine appends, never rewrites
  INV-14 veto semantics: verify never deletes; vetoed candidates survive
  real adapters: the four baseline providers run through the pipeline;
  a mock SAM operator demonstrates tomorrow's perception plugging in.
"""

import pytest

from src.perception.operators import (
    GenerateOp,
    ObservationBundle,
    OperatorRegistry,
    PerceptionPipeline,
    PipelinePlan,
    SpatialHypothesis,
    VerifyOp,
    VerifyReport,
)
from src.perception.adapters import (
    AreaBoundsVerifyOp,
    ConcaveHullRefineOp,
    SeedContainmentVerifyOp,
    make_default_generate_ops,
)

SEED = ObservationBundle(
    seed_lng=116.321,
    seed_lat=40.075,
    target_entity_id="TEST_ENT",
    prior_area_m2=25_000.0,
    carriers={
        "roads_wkt": "POLYGON((116.31 40.07, 116.33 40.07, 116.33 40.08, 116.31 40.08, 116.31 40.07))",
        "buildings_wkt": [
            "POLYGON((116.315 40.072, 116.317 40.072, 116.317 40.074, 116.315 40.074, 116.315 40.072))",
            "POLYGON((116.322 40.076, 116.325 40.076, 116.325 40.079, 116.322 40.079, 116.322 40.076))",
        ],
    },
)


def _registry() -> OperatorRegistry:
    reg = OperatorRegistry()
    for op in make_default_generate_ops():
        reg.register_generate(op)
    reg.register_refine(ConcaveHullRefineOp())
    reg.register_verify(SeedContainmentVerifyOp())
    reg.register_verify(AreaBoundsVerifyOp(min_m2=500.0, max_m2=5_000_000.0))
    return reg


# ---------------------------------------------------------------------------
# INV-12: plug-in seam.
# ---------------------------------------------------------------------------

class MockSAMGenerateOp(GenerateOp):
    """Tomorrow's perception: a segmentation model operator. Nothing in the
    engine knows this class exists - it plugs in by registration only."""

    op_id = "gen:mock_sam"
    requires = frozenset({"imagery_ref"})

    def generate(self, obs):
        # Stand-in for a model emitting a mask polygon.
        wkt = ("POLYGON((116.318 40.070, 116.328 40.070, 116.328 40.081, "
               "116.318 40.081, 116.318 40.070))")
        return [SpatialHypothesis(
            geometry_wkt=wkt,
            method="gen:mock_sam",
            lineage=("gen:mock_sam",),
            metrics={"model": "mock-sam-v0", "iou_proxy": 0.77},
        )]


def test_new_perception_plugs_in_by_registration():
    reg = _registry()
    reg.register_generate(MockSAMGenerateOp())  # <- the entire integration
    plan = PipelinePlan(
        generate_ops=("gen:mock_sam", "area_prior"),
        refine_ops=("ref:concave_hull",),
        verify_ops=("ver:seed_containment", "ver:area_bounds"),
    )
    obs = ObservationBundle(
        seed_lng=SEED.seed_lng, seed_lat=SEED.seed_lat,
        target_entity_id=SEED.target_entity_id,
        prior_area_m2=SEED.prior_area_m2,
        carriers={**SEED.carriers, "imagery_ref": "tile_z16_x_y"},
    )
    results = PerceptionPipeline(reg, plan).run(obs)
    sam = [r for r in results if r.hypothesis.method == "gen:mock_sam"]
    assert len(sam) == 1
    assert sam[0].hypothesis.lineage[0] == "gen:mock_sam"
    assert len(sam[0].reports) == 2


def test_unregistered_op_fails_at_plan_resolution():
    reg = _registry()
    plan = PipelinePlan(generate_ops=("gen:does_not_exist",))
    with pytest.raises(KeyError):
        PerceptionPipeline(reg, plan).run(SEED)


# ---------------------------------------------------------------------------
# INV-13: lineage append-only.
# ---------------------------------------------------------------------------

def test_lineage_grows_through_pipeline():
    plan = PipelinePlan(
        generate_ops=("area_prior",),
        refine_ops=("ref:concave_hull",),
        verify_ops=("ver:area_bounds",),
    )
    results = PerceptionPipeline(_registry(), plan).run(SEED)
    assert results, "area_prior should always produce a candidate"
    lineage = results[0].hypothesis.lineage
    assert lineage == ("gen:area_prior", "ref:concave_hull")
    assert lineage.index("gen:area_prior") < lineage.index("ref:concave_hull")


def test_refine_never_rewrites_ancestor_lineage():
    hyp = SpatialHypothesis(
        geometry_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        method="gen:x",
        lineage=("gen:x",),
    )
    refined = ConcaveHullRefineOp().refine(hyp, SEED)
    assert refined.lineage == ("gen:x", "ref:concave_hull")
    assert hyp.lineage == ("gen:x",)  # original untouched (frozen dataclass)


def test_hull_refine_noop_flags_degenerate_ring():
    tiny = SpatialHypothesis(
        geometry_wkt="POLYGON((0 0, 1 0, 0 1, 0 0))",  # 3 points
        method="gen:x",
        lineage=("gen:x",),
    )
    out = ConcaveHullRefineOp().refine(tiny, SEED)
    assert out.lineage[-1] == "ref:concave_hull"
    assert out.metrics.get("hull_applied") is False
    assert out.metrics.get("hull_reason") == "degenerate_ring"


# ---------------------------------------------------------------------------
# INV-14: veto semantics.
# ---------------------------------------------------------------------------

def test_vetoed_candidate_survives_with_report():
    reg = OperatorRegistry()
    reg.register_generate(MockSAMGenerateOp())

    class GiantOp(GenerateOp):
        op_id = "gen:giant"
        def generate(self, obs):
            wkt = ("POLYGON((100 10, 102 10, 102 12, 100 12, 100 10))")
            return [SpatialHypothesis(geometry_wkt=wkt, method="gen:giant",
                                      lineage=("gen:giant",))]

    reg.register_generate(GiantOp())
    reg.register_verify(AreaBoundsVerifyOp(min_m2=500.0, max_m2=5_000_000.0))
    plan = PipelinePlan(
        generate_ops=("gen:giant",),
        verify_ops=("ver:area_bounds",),
    )
    results = PerceptionPipeline(reg, plan).run(SEED)
    assert len(results) == 1
    assert results[0].vetoed is True
    assert any("area_out_of_bounds" in f for r in results[0].reports
               for f in r.findings)


def test_passing_verify_marks_not_vetoed():
    plan = PipelinePlan(
        generate_ops=("area_prior",),
        refine_ops=("ref:concave_hull",),
        verify_ops=("ver:area_bounds",),
    )
    results = PerceptionPipeline(_registry(), plan).run(SEED)
    assert results[0].vetoed is False


# ---------------------------------------------------------------------------
# Requirement contracts.
# ---------------------------------------------------------------------------

def test_generate_requires_carrier_checked():
    plan = PipelinePlan(generate_ops=("road_block",), verify_ops=())
    sparse = ObservationBundle(seed_lng=116.3, seed_lat=40.0)  # no roads_wkt
    with pytest.raises(KeyError):
        PerceptionPipeline(_registry(), plan).run(sparse)


def test_refine_with_missing_carrier_is_skipped():
    class CarrierBoundRefine(ConcaveHullRefineOp):
        pass

    reg = _registry()
    op = CarrierBoundRefine()
    op.requires = frozenset({"never_present"})
    reg.register_refine(op)
    plan = PipelinePlan(
        generate_ops=("area_prior",),
        refine_ops=(op.op_id,),
        verify_ops=(),
    )
    results = PerceptionPipeline(reg, plan).run(SEED)
    assert results[0].hypothesis.lineage == ("gen:area_prior",)


def test_osm_face_without_carrier_keeps_lineage_honest():
    """With no OSM carrier the wrapped provider may fall back to a
    seed-derived candidate - the algebra's contract is that whatever it
    emits carries an honest gen:osm_face lineage, not that it is empty.
    (Zero IS permitted; this provider chooses fallback.)"""
    plan = PipelinePlan(generate_ops=("osm_face",), verify_ops=())
    results = PerceptionPipeline(_registry(), plan).run(SEED)
    for r in results:
        assert r.hypothesis.lineage[0] == "gen:osm_face"


# ---------------------------------------------------------------------------
# Real end-to-end smoke through all four baseline providers.
# ---------------------------------------------------------------------------

def test_full_default_pipeline_smoke():
    reg = _registry()
    plan = PipelinePlan(
        generate_ops=("osm_face", "road_block", "building_cluster",
                      "area_prior"),
        refine_ops=("ref:concave_hull",),
        verify_ops=("ver:seed_containment", "ver:area_bounds"),
    )
    results = PerceptionPipeline(reg, plan).run(SEED)
    methods = {r.hypothesis.method for r in results}
    assert "gen:area_prior" in methods
    # Every candidate carries full lineage and two verify reports.
    for r in results:
        assert r.hypothesis.lineage[0].startswith("gen:")
        assert len(r.reports) == 2
        assert all(rep.op_id.startswith("ver:") for rep in r.reports)
