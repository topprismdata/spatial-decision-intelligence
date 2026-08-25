"""
Spatial World Model Integrity Layer - Core Domain Data Contracts.
Defines immutable, traceable, and decision-ready spatial entities, geometries, relations, and findings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple


class EntityCategory(str, Enum):
    RESIDENTIAL_COMMUNITY = "RESIDENTIAL_COMMUNITY"
    RESIDENTIAL_COURTYARD = "RESIDENTIAL_COURTYARD"
    RESIDENTIAL_DORMITORY = "RESIDENTIAL_DORMITORY"
    MIXED_COMMERCIAL_RESIDENTIAL = "MIXED_COMMERCIAL_RESIDENTIAL"
    COMMERCIAL_STORE = "COMMERCIAL_STORE"
    WAREHOUSE_DEPOT = "WAREHOUSE_DEPOT"
    FACILITY = "FACILITY"
    UNKNOWN = "UNKNOWN"


class ValidationStatus(str, Enum):
    VERIFIED_VALID = "VERIFIED_VALID"
    REPAIRED_AUTO = "REPAIRED_AUTO"
    RECONSTRUCTED = "RECONSTRUCTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"  # Blocks downstream decision solvers (Fail-Closed)
    WARNING = "WARNING"    # Potential estimation drift, requires flag
    INFO = "INFO"          # Informational note


@dataclass
class EvidencePacket:
    """Audit-proof, human-checkable evidence supporting a diagnostic finding."""
    diagnostic_rule: str
    explanation: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    visual_artifacts: List[str] = field(default_factory=list)


@dataclass
class DecisionImpact:
    """Explicit mapping of spatial data corruption to downstream decision failure modes."""
    risk_level: str  # "HIGH_CORRUPTION", "MEDIUM_DRIFT", "LOW_NOISE"
    polluted_decisions: List[str] = field(default_factory=list)
    blocked_consumers: List[str] = field(default_factory=list)
    impact_summary: str = ""


@dataclass
class QualityFinding:
    """A specific, explainable diagnostic finding on an entity, geometry, or pair."""
    finding_id: str
    target_id: str
    category: str
    severity: FindingSeverity
    evidence: EvidencePacket
    decision_impact: DecisionImpact
    recommended_review: str
    review_status: str = "PENDING"  # PENDING, CONFIRMED, DISMISSED, REPAIRED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class GeometryObservation:
    """Observable geometric boundary or point tied to a spatial entity."""
    observation_id: str
    geometry_wkt: str
    geometry_type: str  # "POINT", "POLYGON", "MULTIPOLYGON"
    crs: str            # "WGS84", "GCJ02", "BD09", "MIXED_CRS"
    observed_at: str
    source: str
    qa_score: float
    transformation_history: List[str] = field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.VERIFIED_VALID


@dataclass
class SpatialRelation:
    """Verified topological, geometric, or semantic relation between two entities."""
    relation_id: str
    subject_id: str
    object_id: str
    relation_type: str
    iou: float
    distance_m: float
    semantic_similarity: float
    cross_encoder_score: Optional[float] = None
    confidence: float = 1.0
    provenance: str = "SPATIAL_MDM_V2"


@dataclass
class ReviewDisposition:
    """Human-in-the-loop governance decision recorded for audit and active learning."""
    disposition_id: str
    finding_id: str
    reviewer: str
    action: str  # "CONFIRM_SAME", "SPLIT_SIBLING", "APPROVE_REPAIR", "ISOLATE", "WHITELIST"
    reason_code: str
    disposed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""


@dataclass
class SpatialEntity:
    """First-class canonical spatial entity in the TopPrism World Model."""
    entity_id: str
    category: EntityCategory
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    city: str = ""
    district: str = ""
    address: str = ""
    point_wgs84: Optional[Tuple[float, float]] = None
    geometry_observation_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    active_findings: List[str] = field(default_factory=list)
    is_decision_ready: bool = True


@dataclass
class TrustedSpatialState:
    """The verified, immutable spatial state published to downstream decision solvers."""
    state_version: str
    published_at: str
    entities: Dict[str, SpatialEntity] = field(default_factory=dict)
    geometries: Dict[str, GeometryObservation] = field(default_factory=dict)
    relations: List[SpatialRelation] = field(default_factory=list)
    findings: List[QualityFinding] = field(default_factory=list)
    dispositions: List[ReviewDisposition] = field(default_factory=list)

    def get_decision_ready_entities(self, consumer_name: str = "") -> List[SpatialEntity]:
        """Returns entities that are safe to consume by a specific downstream solver."""
        ready = []
        for ent in self.entities.values():
            if not ent.is_decision_ready:
                continue
            # Check if any active finding blocks this consumer
            is_blocked = False
            for fid in ent.active_findings:
                finding = next((f for f in self.findings if f.finding_id == fid), None)
                if finding and consumer_name in finding.decision_impact.blocked_consumers:
                    is_blocked = True
                    break
            if not is_blocked:
                ready.append(ent)
        return ready

    def summary_stats(self) -> Dict[str, Any]:
        total_ents = len(self.entities)
        ready_ents = sum(1 for e in self.entities.values() if e.is_decision_ready)
        return {
            "state_version": self.state_version,
            "published_at": self.published_at,
            "total_entities": total_ents,
            "decision_ready_entities": ready_ents,
            "decision_ready_rate": f"{ready_ents/max(total_ents, 1)*100:.1f}%",
            "total_geometries": len(self.geometries),
            "total_relations": len(self.relations),
            "active_findings_count": len(self.findings),
        }
