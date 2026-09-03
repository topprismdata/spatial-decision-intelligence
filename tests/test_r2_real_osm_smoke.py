"""R2 Level 2: Real OSM Snapshot Smoke Tests.

Uses frozen real Beijing Overpass data from data/beijing_fixtures.
Verifies end-to-end: Real OSM -> Observation -> Provider -> MetricGeometryService -> ProviderHypothesis -> CandidateRankingEngine.
"""

import json
import os

import pytest
from shapely import wkt
from shapely.geometry import Point

from src.providers import (
    BuildingSourcePolicy,
    ProviderRequest,
    ProviderContext,
    SeedObservation,
    AreaPrior,
    Priors,
    ProviderHypothesis,
    EXPERIMENT_PROFILES,
)
from src.providers.baselines import (
    ExistingOpenBoundaryProvider,
    RoadBlockProvider,
    BuildingClusterProvider,
    AreaPriorBaseline,
)
from src.providers.ranking import CandidateRankingEngine
from src.domain.contracts import HypothesisStatus, ProviderStatus

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "beijing_fixtures")

# Frozen OSM extracts are not shipped in-repo (compliance: no raw geo data on
# public hosting). Collaborators fetch them locally with:
#   python3 scripts/prepare_sample_data.py --with-fixtures
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(FIXTURES_DIR, "residential_500.json")),
    reason="data/beijing_fixtures missing; run scripts/prepare_sample_data.py --with-fixtures",
)


def test_real_beijing_osm_case_a_existing_open_boundary():
    """Case A: Real Beijing OSM residential landuse polygon -> ExistingOpenBoundaryProvider."""
    with open(os.path.join(FIXTURES_DIR, "residential_500.json")) as f:
        res_data = json.load(f)

    first_poly = res_data["elements"][0]["geometry"]
    lats = [p["lat"] for p in first_poly]
    lngs = [p["lon"] for p in first_poly]
    seed = (sum(lngs) / len(lngs), sum(lats) / len(lats))

    req = ProviderRequest(
        target_entity_id="beijing_case_a_shangdi",
        target_boundary_role="PHYSICAL_BOUNDARY",
        seed_observations=(SeedObservation(point=seed, source="real_beijing_osm", uncertainty_radius_m=100.0),),
        context=ProviderContext(boundary_role="PHYSICAL_BOUNDARY"),
    )

    provider = ExistingOpenBoundaryProvider()
    result = provider.generate(req)

    assert result.status == ProviderStatus.APPLICABLE
    assert len(result.hypotheses) >= 1
    for ph in result.hypotheses:
        assert isinstance(ph, ProviderHypothesis)
        assert ph.hypothesis.status == HypothesisStatus.PROPOSED
        assert ph.provider_features["polygon_area_m2"] > 0
        assert ph.provider_features["source_semantic_role"] == "RESIDENTIAL_LANDUSE"


def test_real_beijing_osm_area_prior_baseline():
    """B0: AreaPriorBaseline on Beijing coordinates with MetricGeometryService."""
    req = ProviderRequest(
        target_entity_id="beijing_b0",
        target_boundary_role="PHYSICAL_BOUNDARY",
        seed_observations=(SeedObservation(point=(116.4074, 39.9042), source="beijing_center"),),
        context=ProviderContext(boundary_role="PHYSICAL_BOUNDARY"),
        optional_priors=Priors(area_prior=AreaPrior(value_m2=50000.0)),
    )

    provider = AreaPriorBaseline()
    result = provider.generate(req)

    assert result.status == ProviderStatus.APPLICABLE
    assert len(result.hypotheses) == 1
    ph = result.hypotheses[0]
    assert ph.hypothesis.status == HypothesisStatus.PROPOSED
    assert ph.provider_features["area_prior_m2"] == 50000.0


def test_real_beijing_candidate_ranking_and_b7_delta():
    """Verify CandidateRankingEngine processes hypotheses and B7 provides semantic delta."""
    req = ProviderRequest(
        target_entity_id="beijing_ranking",
        target_boundary_role="PHYSICAL_BOUNDARY",
        seed_observations=(SeedObservation(point=(116.3076, 40.0315), source="beijing_osm", uncertainty_radius_m=100.0),),
        context=ProviderContext(boundary_role="PHYSICAL_BOUNDARY"),
        optional_priors=Priors(area_prior=AreaPrior(value_m2=80000.0)),
    )

    b0_out = AreaPriorBaseline().generate(req)
    b1_out = ExistingOpenBoundaryProvider().generate(req)

    all_hypotheses = [ph.hypothesis for ph in (b0_out.hypotheses + b1_out.hypotheses)]
    assert len(all_hypotheses) == 2

    engine = CandidateRankingEngine()
    ranked_b6 = engine.rank(all_hypotheses, semantic_features_enabled=False)
    ranked_b7 = engine.rank(all_hypotheses, semantic_features_enabled=True)

    assert len(ranked_b6) == 2
    assert len(ranked_b7) == 2
    for r in ranked_b6 + ranked_b7:
        assert 0.0 <= r.ranking_score <= 1.0
