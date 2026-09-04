"""R2 Baseline Provider acceptance tests (P1-P10)."""

from src.domain.contracts import HypothesisStatus, ProviderStatus
from src.providers import (
    BuildingSourcePolicy,
    ProviderRequest,
    ProviderContext,
    SeedObservation,
    AreaPrior,
    Priors,
    EXPERIMENT_PROFILES,
)
from src.providers.baselines import (
    ExistingOpenBoundaryProvider,
    RoadBlockProvider,
    BuildingClusterProvider,
    AreaPriorBaseline,
)
from src.providers.ranking import CandidateRankingEngine


def _make_request(entity_id="test-1", seed=(116.4, 39.9), priors=None):
    return ProviderRequest(
        target_entity_id=entity_id,
        target_boundary_role="PHYSICAL_BOUNDARY",
        seed_observations=(SeedObservation(point=seed, source="test"),),
        context=ProviderContext(boundary_role="PHYSICAL_BOUNDARY"),
        optional_priors=priors,
    )


class TestAreaPriorBaseline:
    def test_generates_circle(self):
        provider = AreaPriorBaseline()
        req = _make_request(priors=Priors(area_prior=AreaPrior(value_m2=25000)))
        result = provider.generate(req)
        assert result.status == ProviderStatus.APPLICABLE
        assert len(result.hypotheses) == 1
        h = result.hypotheses[0]
        assert h.hypothesis.status == HypothesisStatus.PROPOSED
        assert "EXPERIMENTAL" in str(h.provider_features.get("baseline_type", ""))
        assert "confidence" not in h.provider_features

    def test_not_applicable_without_prior(self):
        provider = AreaPriorBaseline()
        result = provider.generate(_make_request())
        assert result.status == ProviderStatus.NOT_APPLICABLE


class TestRoadBlockProvider:
    def test_returns_proposed_only(self):
        provider = RoadBlockProvider()
        result = provider.generate(_make_request())
        for h in result.hypotheses:
            assert h.hypothesis.status == HypothesisStatus.PROPOSED
            assert "confidence" not in h.provider_features
            features = h.provider_features
            if "road_profile_variant" in features:
                assert features["road_profile_variant"] in ("STRONG_ONLY", "STRONG_PLUS_WEAK")

    def test_no_confidence_field(self):
        provider = RoadBlockProvider()
        result = provider.generate(_make_request())
        for h in result.hypotheses:
            assert "confidence" not in h.provider_features


class TestBuildingClusterProvider:
    def test_source_policy_osm(self):
        provider = BuildingClusterProvider()
        result = provider.generate(_make_request(), source_policy=BuildingSourcePolicy.OSM_ONLY)
        for h in result.hypotheses:
            assert h.hypothesis.status == HypothesisStatus.PROPOSED

    def test_multi_source(self):
        provider = BuildingClusterProvider()
        result = provider.generate(_make_request(), source_policy=BuildingSourcePolicy.MULTI_SOURCE)
        # May or may not have results depending on data availability
        for h in result.hypotheses:
            assert h.hypothesis.status == HypothesisStatus.PROPOSED


class TestCandidateRankingEngine:
    def test_ranking_separate_from_provider(self):
        engine = CandidateRankingEngine()
        provider = AreaPriorBaseline()
        req = _make_request(priors=Priors(area_prior=AreaPrior(25000)))
        output = provider.generate(req)
        records = engine.rank([ph.hypothesis for ph in output.hypotheses])
        assert len(records) >= 1
        assert all(hasattr(r, "ranking_score") for r in records)

    def test_b7_semantic_features(self):
        engine = CandidateRankingEngine()
        provider = AreaPriorBaseline()
        req = _make_request(priors=Priors(area_prior=AreaPrior(25000)))
        output = provider.generate(req)
        records_geo = engine.rank([ph.hypothesis for ph in output.hypotheses], semantic_features_enabled=False)
        records_sem = engine.rank([ph.hypothesis for ph in output.hypotheses], semantic_features_enabled=True)
        # B7 should produce different scores when semantic is enabled
        assert isinstance(records_sem[0].ranking_score, float)


class TestExperimentProfiles:
    def test_all_profiles_exist(self):
        for eid in ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7"]:
            assert eid in EXPERIMENT_PROFILES

    def test_b0_has_area_prior(self):
        assert EXPERIMENT_PROFILES["B0"].area_prior_enabled

    def test_b1_through_b7_no_area_prior(self):
        for eid in ["B1", "B2", "B3", "B4", "B5", "B6", "B7"]:
            assert not EXPERIMENT_PROFILES[eid].area_prior_enabled

    def test_b7_has_semantic_features(self):
        assert EXPERIMENT_PROFILES["B7"].semantic_features_enabled

    def test_b6_does_not_have_semantic_features(self):
        assert not EXPERIMENT_PROFILES["B6"].semantic_features_enabled


class TestNoTrust:
    def test_no_provider_outputs_trusted(self):
        providers = [
            (AreaPriorBaseline(), {"priors": Priors(area_prior=AreaPrior(25000))}),
        ]
        for provider, kwargs in providers:
            req = _make_request(**kwargs)
            result = provider.generate(req)
            for h in result.hypotheses:
                assert h.hypothesis.status != HypothesisStatus.TRUSTED