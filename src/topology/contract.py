"""R11 TopologyAssertion: common contract for evidence-aware spatial topology reasoning.

Semantic judgment separated from deterministic GIS execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TopologyRelation(str, Enum):
    SEPARATED_BY = "SEPARATED_BY"          # Road/barrier separates two compounds
    CONNECTED_BY = "CONNECTED_BY"          # Passage/courtyard connects two compounds
    SHARED_BOUNDARY = "SHARED_BOUNDARY"    # Compounds share a boundary edge
    OVERLAP_CONFLICT = "OVERLAP_CONFLICT"  # Compounds overlap (conflict)
    GAP_CONFLICT = "GAP_CONFLICT"          # Gap between compounds (conflict)
    UNKNOWN = "UNKNOWN"                    # Insufficient evidence


@dataclass(frozen=True)
class TopologyAssertion:
    entity_a: str = ""
    entity_b: str = ""
    relation: TopologyRelation = TopologyRelation.UNKNOWN
    confidence: float = 0.0
    supporting_evidence: tuple[str, ...] = ()
    conflicting_evidence: tuple[str, ...] = ()
    affected_segments: tuple[str, ...] = ()
    separator_feature: str = ""
    connector_feature: str = ""


@dataclass(frozen=True)
class TopologyRepairOperation:
    operation: str = ""  # SNAP, SPLIT, MERGE, REMOVE_OVERLAP, REPAIR_GAP
    geometry_wkt: str = ""
    assertion_id: str = ""
    parameters: dict[str, float] = field(default_factory=dict)