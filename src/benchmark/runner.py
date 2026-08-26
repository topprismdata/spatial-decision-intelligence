"""R6 Benchmark Runner: Pre-registration, 360 primary runs, run records.

Design Note v1.0 §§3–11, 39.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.domain.contracts import (
    BoundaryHypothesis,
    Evidence,
    HypothesisStatus,
    OntologyType,
    ProviderStatus,
    ValidationStatus,
)
from src.providers import (
    AreaPrior,
    BaselineExperimentProfile,
    BuildingSourcePolicy,
    EXPERIMENT_PROFILES,
    Priors,
    ProviderContext,
    ProviderRequest,
    ProviderHypothesis,
    SeedObservation,
)
from src.providers.baselines import (
    AreaPriorBaseline,
    BuildingClusterProvider,
    ExistingOpenBoundaryProvider,
    RoadBlockProvider,
)
from src.providers.ranking import CandidateRankingEngine
from src.validation.pipeline import (
    ConsumerDecision,
    PROFILE_TERRITORY_OPTIMIZATION,
    PROFILE_VISIT_CHECKIN,
    FinalDisposition,
    ValidationPipeline,
)


@dataclass
class BenchmarkPreRegistration:
    benchmark_version: str = "0.1"
    case_registry_version: str = "0.1"
    gold_version: str = "0.1"
    source_manifest_version: str = "0.1"
    ontology_version: str = "1.0"
    git_commit: str = ""
    environment_lock_hash: str = ""
    provider_versions: str = "1.0"
    ranking_policy_versions: str = "1.0"
    parameter_profiles: str = "default"
    random_seed: int = 42
    metric_definitions: str = "5-layer"
    experiment_matrix: tuple[str, ...] = (
        "B0", "B1", "B2",
        "B3-OSM", "B3-OVERTURE", "B3-MICROSOFT",
        "B4-OSM", "B4-OVERTURE", "B4-MICROSOFT",
        "B5", "B6", "B7",
    )
    run_timestamp: str = ""


@dataclass
class BenchmarkRunRecord:
    run_id: str = ""
    case_id: str = ""
    experiment_id: str = ""
    code_commit: str = ""
    provider_version: str = ""
    ranking_policy_version: str = ""
    parameter_profile: str = ""
    source_manifest_version: str = ""
    gold_version: str = ""
    candidate_ids: tuple[str, ...] = ()
    candidate_count: int = 0
    top_ranked_candidate_id: str = ""
    validation_results: tuple[str, ...] = ()
    final_disposition: str = ""
    decision_readiness: dict[str, str] = field(default_factory=dict)
    runtime_ms: float = 0.0
    error_code: str = ""
    run_hash: str = ""


@dataclass
class BenchmarkRunCollection:
    runs: list[BenchmarkRunRecord] = field(default_factory=list)

    def add(self, record: BenchmarkRunRecord) -> None:
        self.runs.append(record)

    @property
    def count(self) -> int:
        return len(self.runs)

    @property
    def n_cases(self) -> int:
        return len(set(r.case_id for r in self.runs))

    @property
    def n_experiments(self) -> int:
        return len(set(r.experiment_id for r in self.runs))


class BenchmarkRunner:
    """Executes B0-B7 benchmark across all 30 cases."""

    def __init__(self, gold_cases: Optional[Dict[str, object]] = None):
        self._gold_cases = gold_cases or {}
        self._collection = BenchmarkRunCollection()
        self._engine = CandidateRankingEngine()
        self._validation = ValidationPipeline()

    def run_all(self, case_seeds: list) -> BenchmarkRunCollection:
        for seed in case_seeds:
            for exp_id in self._experiment_ids():
                record = self._run_single(seed, exp_id)
                if record:
                    self._collection.add(record)
        return self._collection

    @staticmethod
    def _experiment_ids() -> list[str]:
        return [
            "B0", "B1", "B2",
            "B3-OSM", "B3-OVERTURE", "B3-MICROSOFT",
            "B4-OSM", "B4-OVERTURE", "B4-MICROSOFT",
            "B5", "B6", "B7",
        ]

    def _run_single(self, seed, exp_id: str) -> Optional[BenchmarkRunRecord]:
        start = time.time()
        try:
            hypotheses = self._generate_hypotheses(seed, exp_id)
            if not hypotheses:
                return None
            ranked = self._engine.rank(hypotheses, semantic_features_enabled=(exp_id == "B7"))
            top_id = ranked[0].hypothesis_id if ranked else ""
            results, disposition, decisions = self._validation.run(
                OntologyType.RESIDENTIAL_COMPOUND, hypotheses[0],
            )
            raw = f"{exp_id}:{seed.case_id if hasattr(seed, 'case_id') else 'unknown'}:{time.time()}"
            run_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
            elapsed = (time.time() - start) * 1000
            return BenchmarkRunRecord(
                run_id=run_hash,
                case_id=getattr(seed, "case_id", "unknown"),
                experiment_id=exp_id,
                candidate_count=len(hypotheses),
                top_ranked_candidate_id=top_id,
                final_disposition=disposition.value,
                decision_readiness={k: v.value for k, v in decisions.items()},
                runtime_ms=round(elapsed, 2),
            )
        except Exception as e:
            return None

    def _generate_hypotheses(self, seed, exp_id: str) -> list:
        seed_pt = getattr(seed, "location", (116.4, 39.9))
        req = ProviderRequest(
            target_entity_id=getattr(seed, "case_id", "unknown"),
            seed_observations=(SeedObservation(point=seed_pt, source="benchmark"),),
            context=ProviderContext(),
        )
        hypotheses = []
        if exp_id == "B0":
            req.optional_priors = Priors(area_prior=AreaPrior(value_m2=50000))
            res = AreaPriorBaseline().generate(req)
            hypotheses = [ph.hypothesis for ph in res.hypotheses]
        elif exp_id == "B1":
            res = ExistingOpenBoundaryProvider().generate(req)
            hypotheses = [ph.hypothesis for ph in res.hypotheses]
        elif exp_id == "B2":
            res = RoadBlockProvider().generate(req)
            hypotheses = [ph.hypothesis for ph in res.hypotheses]
        else:
            # B3-B7 use BuildingCluster
            policy = BuildingSourcePolicy.OSM_ONLY
            if "OVERTURE" in exp_id:
                policy = BuildingSourcePolicy.OVERTURE_ONLY
            elif "MICROSOFT" in exp_id:
                policy = BuildingSourcePolicy.MICROSOFT_ONLY
            elif "B5" in exp_id or exp_id in ("B6", "B7"):
                policy = BuildingSourcePolicy.MULTI_SOURCE
            res = BuildingClusterProvider().generate(req, source_policy=policy)
            hypotheses = [ph.hypothesis for ph in res.hypotheses]
            if "B4" in exp_id or exp_id in ("B6", "B7"):
                road_res = RoadBlockProvider().generate(req)
                hypotheses += [ph.hypothesis for ph in road_res.hypotheses]
            if "B6" in exp_id or "B7" in exp_id:
                open_res = ExistingOpenBoundaryProvider().generate(req)
                hypotheses += [ph.hypothesis for ph in open_res.hypotheses]
        return hypotheses