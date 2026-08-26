"""R2 Provider Framework: contracts, request/response types, provenance.

Design Note v1.1 §§2, 6, 11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from src.domain.contracts import (
    BoundaryHypothesis,
    BoundaryType,
    Evidence,
    HypothesisStatus,
    ProviderResult,
    ProviderStatus,
)


class BuildingSourcePolicy(str, Enum):
    OSM_ONLY = "OSM_ONLY"
    OVERTURE_ONLY = "OVERTURE_ONLY"
    MICROSOFT_ONLY = "MICROSOFT_ONLY"
    MULTI_SOURCE = "MULTI_SOURCE"


class RoadProfileVariant(str, Enum):
    STRONG_ONLY = "STRONG_ONLY"
    STRONG_PLUS_WEAK = "STRONG_PLUS_WEAK"


@dataclass
class SeedObservation:
    point: tuple[float, float]
    source: str = ""
    observed_at: str = ""
    positional_quality: str = "MEDIUM"
    uncertainty_radius_m: float = 50.0


@dataclass
class AreaPrior:
    value_m2: float
    source_observation_id: str = ""
    provenance: str = ""
    allowed_experiments: tuple[str, ...] = ("B0",)


@dataclass
class Priors:
    area_prior: Optional[AreaPrior] = None


@dataclass
class ProviderContext:
    """Context passed to all providers."""
    boundary_role: BoundaryType = BoundaryType.PHYSICAL
    metric_service: Optional[object] = None  # MetricGeometryService reference


@dataclass
class ProviderRequest:
    target_entity_id: str = ""
    target_boundary_role: BoundaryType = BoundaryType.PHYSICAL
    seed_observations: tuple[SeedObservation, ...] = ()
    context: Optional[ProviderContext] = None
    optional_priors: Optional[Priors] = None


@dataclass
class ProviderProvenance:
    provider_id: str = ""
    provider_version: str = "1.0"
    algorithm_version: str = "1.0"
    source_observation_ids: tuple[str, ...] = ()
    source_dataset_releases: tuple[str, ...] = ()
    parameter_profile: str = ""
    metric_crs: str = "EPSG:32650"
    transform_chain: str = ""
    generated_at: str = ""


@dataclass
class ProviderOutput:
    status: ProviderStatus = ProviderStatus.NOT_APPLICABLE
    hypotheses: tuple[BoundaryHypothesis, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    provenance: ProviderProvenance = field(default_factory=ProviderProvenance)


@dataclass
class CandidateRankRecord:
    hypothesis_id: str = ""
    ranking_score: float = 0.0
    ranking_features: dict[str, float] = field(default_factory=dict)
    ranking_policy_version: str = "1.0"
@dataclass(frozen=True)
class ProviderHypothesis:
    """Wraps BoundaryHypothesis with provider-specific features (not confidence)."""
    hypothesis: BoundaryHypothesis
    generation_score: float = 0.5
    provider_features: dict = field(default_factory=dict)


@dataclass
class BaselineExperimentProfile:
    """B0-B7 composition contract (Design Note §4)."""
    experiment_id: str = ""
    enabled_providers: tuple[str, ...] = ()
    building_source_policy: BuildingSourcePolicy = BuildingSourcePolicy.OSM_ONLY
    ranking_policy: str = "geometric"
    semantic_features_enabled: bool = False
    area_prior_enabled: bool = False


# Predefined experiment profiles
EXPERIMENT_PROFILES = {
    "B0": BaselineExperimentProfile("B0", ("AreaPriorBaseline",), area_prior_enabled=True),
    "B1": BaselineExperimentProfile("B1", ("ExistingOpenBoundary",)),
    "B2": BaselineExperimentProfile("B2", ("RoadBlock",)),
    "B3": BaselineExperimentProfile("B3", ("BuildingCluster",)),
    "B4": BaselineExperimentProfile("B4", ("RoadBlock", "BuildingCluster"), ranking_policy="geometric"),
    "B5": BaselineExperimentProfile("B5", ("BuildingCluster",), building_source_policy=BuildingSourcePolicy.MULTI_SOURCE, ranking_policy="geometric"),
    "B6": BaselineExperimentProfile("B6", ("ExistingOpenBoundary", "RoadBlock", "BuildingCluster"), ranking_policy="geometric"),
    "B7": BaselineExperimentProfile("B7", ("ExistingOpenBoundary", "RoadBlock", "BuildingCluster"), ranking_policy="semantic", semantic_features_enabled=True),
}