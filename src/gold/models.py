"""R5 Core Gold Data Structures: Source Manifest, Assertions, Entity & Boundary Gold.

Design Note §10–§28. All dataclasses are frozen for immutability after Gold freeze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.gold import (
    AuthorityScope,
    BuildingMembershipState,
    CueType,
    DependencyType,
    EvidenceSufficiency,
    GoldState,
    SegmentStatus,
    SourceFamily,
    SourceSemanticRole,
)


# ── Source Manifest (G1) ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceManifestEntry:
    source_id: str = ""
    source_family: SourceFamily = SourceFamily.OPEN_MAP
    provider: str = ""
    dataset: str = ""
    theme: str = ""
    release: str = ""
    source_url: str = ""
    license: str = ""
    license_version: str = ""
    license_url: str = ""
    retrieved_at: str = ""
    observation_time: str = ""
    spatial_extent: str = ""
    query_parameters: str = ""
    content_hash: str = ""
    source_semantic_role: SourceSemanticRole = SourceSemanticRole.OTHER
    dependency_group: str = ""
    availability_status: str = "AVAILABLE"


@dataclass(frozen=True)
class SourceDependency:
    source_a: str = ""
    source_b: str = ""
    dependency_type: DependencyType = DependencyType.UNKNOWN
    dependency_scope: str = ""
    known_derivation: str = ""
    confidence_of_dependency: float = 0.5


@dataclass(frozen=True)
class CaseSourceManifest:
    case_id: str = ""
    entries: tuple[SourceManifestEntry, ...] = ()
    dependencies: tuple[SourceDependency, ...] = ()
    frozen_at: str = ""


# ── Evidence Bundle (G4/G5) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str = ""
    target_assertion_id: str = ""
    supporting_observation_ids: tuple[str, ...] = ()
    contradicting_observation_ids: tuple[str, ...] = ()
    independent_evidence_groups: tuple[str, ...] = ()
    spatial_scope: str = ""
    temporal_scope: str = ""
    adjudication_notes: str = ""
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.INSUFFICIENT


# ── Gold Assertion ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldAssertion:
    assertion_id: str = ""
    case_id: str = ""
    assertion_text: str = ""
    ontology_type: str = ""
    evidence_bundle_id: str = ""
    status: GoldState = GoldState.GOLD_UNRESOLVED


# ── Entity Gold (G3) ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldEntityState:
    case_id: str = ""
    canonical_entities: tuple[str, ...] = ()
    ontology_types: tuple[str, ...] = ()
    canonical_names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    parent_relations: tuple[str, ...] = ()
    child_relations: tuple[str, ...] = ()
    identity_assertions: tuple[str, ...] = ()
    identity_conflicts: tuple[str, ...] = ()
    entity_gold_state: GoldState = GoldState.GOLD_UNRESOLVED
    entity_evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.INSUFFICIENT
    assertions: tuple[GoldAssertion, ...] = ()


# ── Boundary Gold (G5) ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldBoundarySegment:
    segment_id: str = ""
    geometry: str = ""
    cue_type: CueType = CueType.OTHER
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    separator_feature_ids: tuple[str, ...] = ()
    status: SegmentStatus = SegmentStatus.UNRESOLVED
    uncertainty_width_m: float = 0.0
    adjudication_note: str = ""


@dataclass(frozen=True)
class BoundaryUncertaintyZone:
    zone_id: str = ""
    geometry: str = ""
    uncertainty_range_m: float = 0.0
    evidence_bundle_id: str = ""
    note: str = ""


@dataclass(frozen=True)
class GoldBoundaryState:
    compound_id: str = ""
    boundary_role: str = "PHYSICAL_BOUNDARY"
    gold_geometry: Optional[str] = None
    segments: tuple[GoldBoundarySegment, ...] = ()
    uncertainty_zones: tuple[BoundaryUncertaintyZone, ...] = ()
    building_membership: tuple[tuple[str, BuildingMembershipState], ...] = ()
    separator_features: tuple[str, ...] = ()
    connector_features: tuple[str, ...] = ()
    neighbor_relations: tuple[str, ...] = ()
    boundary_gold_state: GoldState = GoldState.GOLD_UNRESOLVED
    boundary_evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.INSUFFICIENT


# ── Review & Conflict (G7) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldReviewConflict:
    case_id: str = ""
    assertion_id: str = ""
    review_a: str = ""
    review_b: str = ""
    conflict_type: str = ""
    evidence_difference: str = ""
    resolution: str = ""
    resolution_reason: str = ""


# ── Gold Freeze & Versioning (G8) ─────────────────────────────────────────────


@dataclass(frozen=True)
class GoldCaseVersion:
    case_id: str = ""
    gold_version: str = "0.1"
    source_manifest_version: str = "0.1"
    ontology_version: str = "1.0"
    adjudication_protocol_version: str = "1.0"
    reviewer_records: tuple[str, ...] = ()
    freeze_timestamp: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class GoldCorrectionRecord:
    case_id: str = ""
    gold_version_from: str = ""
    gold_version_to: str = ""
    changed_assertions: tuple[str, ...] = ()
    reason: str = ""
    new_evidence: str = ""
    reviewer: str = ""
    timestamp: str = ""


# ── Metric Eligibility ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricEligibility:
    eligible_entity_metrics: bool = False
    eligible_geometry_metrics: bool = False
    eligible_membership_metrics: bool = False
    eligible_abstention_metrics: bool = False


# ── Complete Gold Case ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GoldCase:
    case_id: str = ""
    source_manifest: Optional[CaseSourceManifest] = None
    entity_state: Optional[GoldEntityState] = None
    boundary_states: tuple[GoldBoundaryState, ...] = ()
    assertions: tuple[GoldAssertion, ...] = ()
    evidence_bundles: tuple[EvidenceBundle, ...] = ()
    review_conflicts: tuple[GoldReviewConflict, ...] = ()
    metric_eligibility: Optional[MetricEligibility] = None
    version: Optional[GoldCaseVersion] = None
    corrections: tuple[GoldCorrectionRecord, ...] = ()