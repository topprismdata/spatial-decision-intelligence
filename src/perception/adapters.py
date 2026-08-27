"""Adapters: existing perception code (baseline providers, concave hull)
expressed as operators in the perception algebra (src/perception/operators.py).

This is the proof that the algebra wraps today's algorithms without
rewriting them - and therefore that a SAM/VLM operator tomorrow is just
another adapter registered under an id.
"""

from __future__ import annotations

from typing import List, Optional

from shapely import wkt as _wkt
from shapely.geometry import Point

from src.domain.contracts import BoundaryType
from src.geometry.concave_hull import hull_for_cluster
from src.perception.operators import (
    GenerateOp,
    ObservationBundle,
    RefineOp,
    SpatialHypothesis,
    VerifyOp,
    VerifyReport,
)
from src.providers import (
    ProviderContext,
    ProviderRequest,
    SeedObservation,
)
from src.providers.baselines import (
    AreaPriorBaseline,
    BuildingClusterProvider,
    ExistingOpenBoundaryProvider,
    RoadBlockProvider,
)


def _request_from(obs: ObservationBundle) -> ProviderRequest:
    seed = SeedObservation(
        point=(obs.seed_lng, obs.seed_lat),
        source="perception_bundle",
    )
    ctx = ProviderContext(boundary_role=BoundaryType.PHYSICAL)
    priors = None
    if obs.prior_area_m2 is not None:
        from src.providers import AreaPrior, Priors
        priors = Priors(area_prior=AreaPrior(value_m2=obs.prior_area_m2))
    return ProviderRequest(
        target_entity_id=obs.target_entity_id,
        seed_observations=(seed,),
        context=ctx,
        optional_priors=priors,
    )


class ProviderGenerateOp(GenerateOp):
    """Wraps any baseline provider's generate(request)->ProviderOutput."""

    def __init__(self, op_id: str, provider, requires: frozenset = frozenset()):
        self.op_id = op_id
        self.provider = provider
        self.requires = requires

    def generate(self, obs: ObservationBundle) -> List[SpatialHypothesis]:
        out = self.provider.generate(_request_from(obs))
        hyps: List[SpatialHypothesis] = []
        for h in out.hypotheses:
            hyps.append(SpatialHypothesis(
                geometry_wkt=h.hypothesis.geometry,
                method=f"gen:{self.op_id}",
                lineage=("gen:" + self.op_id,),
                metrics={
                    "generator": h.hypothesis.generator,
                    "provider_status": out.status.value,
                    "provider_features": dict(h.provider_features),
                },
            ))
        return hyps


def make_default_generate_ops() -> List[GenerateOp]:
    return [
        ProviderGenerateOp("osm_face", ExistingOpenBoundaryProvider()),
        ProviderGenerateOp("road_block", RoadBlockProvider(),
                           requires=frozenset({"roads_wkt"})),
        ProviderGenerateOp("building_cluster", BuildingClusterProvider(),
                           requires=frozenset({"buildings_wkt"})),
        ProviderGenerateOp("area_prior", AreaPriorBaseline()),
    ]


class ConcaveHullRefineOp(RefineOp):
    """Duckham-style concave hull over the polygon exterior ring."""

    def __init__(self, k: float = 0.8, min_points: int = 6):
        self.op_id = "ref:concave_hull"
        self.k = k
        self.min_points = min_points

    def refine(self, hyp: SpatialHypothesis,
               obs: ObservationBundle) -> SpatialHypothesis:
        try:
            geom = _wkt.loads(hyp.geometry_wkt)
        except Exception:
            return hyp.with_lineage(self.op_id, hull_applied=False,
                                    hull_reason="parse_error")
        if geom.geom_type != "Polygon" or len(geom.exterior.coords) < self.min_points:
            return hyp.with_lineage(self.op_id, hull_applied=False,
                                    hull_reason="degenerate_ring")
        pts = [(x, y) for x, y in geom.exterior.coords[:-1]]
        hull = hull_for_cluster(pts)
        if hull is None or hull.is_empty:
            return hyp.with_lineage(self.op_id, hull_applied=False,
                                    hull_reason="hull_failed")
        metrics = {**hyp.metrics, "hull_applied": True,
                   "area_before_m2": hyp.metrics.get("area_m2")}
        return SpatialHypothesis(
            geometry_wkt=hull.wkt,
            method=hyp.method,
            lineage=hyp.lineage + (self.op_id,),
            metrics=metrics,
        )


class SeedContainmentVerifyOp(VerifyOp):
    """A candidate that does not contain its own seed is defective."""

    def __init__(self, max_distance_m_deg: float = 0.01):
        self.op_id = "ver:seed_containment"

    def verify(self, hyp: SpatialHypothesis,
               obs: ObservationBundle) -> VerifyReport:
        try:
            geom = _wkt.loads(hyp.geometry_wkt)
            pt = Point(obs.seed_lng, obs.seed_lat)
            ok = geom.contains(pt) or geom.distance(pt) < 0.01
            return VerifyReport(
                op_id=self.op_id,
                passed=bool(ok),
                findings=() if ok else ("seed_outside_candidate",),
                metrics={"distance_deg": round(geom.distance(pt), 6)},
            )
        except Exception as e:
            return VerifyReport(op_id=self.op_id, passed=False,
                                findings=(f"verify_error:{e}",))


class AreaBoundsVerifyOp(VerifyOp):
    def __init__(self, min_m2: float, max_m2: float):
        self.op_id = "ver:area_bounds"
        self.min_m2 = min_m2
        self.max_m2 = max_m2

    def verify(self, hyp: SpatialHypothesis,
               obs: ObservationBundle) -> VerifyReport:
        try:
            geom = _wkt.loads(hyp.geometry_wkt)
            # Rough planar approximation in degrees squared -> degenerate
            # bounds are still meaningful for order-of-magnitude vetoes.
            deg2 = geom.area
            approx_m2 = deg2 * (111_000.0 ** 2) * 0.618  # cos(lat) proxy
            ok = self.min_m2 <= approx_m2 <= self.max_m2
            return VerifyReport(
                op_id=self.op_id,
                passed=bool(ok),
                findings=() if ok else (
                    f"area_out_of_bounds:{approx_m2:.0f}m2",),
                metrics={"approx_area_m2": round(approx_m2, 1)},
            )
        except Exception as e:
            return VerifyReport(op_id=self.op_id, passed=False,
                                findings=(f"verify_error:{e}",))
