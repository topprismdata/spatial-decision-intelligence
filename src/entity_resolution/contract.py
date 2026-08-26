"""R12 EntityStructureAssertion: common contract for Estate/Phase/Compound hierarchy resolution.

Addresses D2 failures: Estate/Phase/Compound confusion, same-name-different-entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EntityRole(str, Enum):
    RESIDENTIAL_ESTATE = "RESIDENTIAL_ESTATE"
    RESIDENTIAL_PHASE = "RESIDENTIAL_PHASE"
    RESIDENTIAL_COMPOUND = "RESIDENTIAL_COMPOUND"
    AMBIGUOUS = "AMBIGUOUS"


class EntityRelation(str, Enum):
    SAME_ENTITY = "SAME_ENTITY"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    SIBLING = "SIBLING"
    DISTINCT = "DISTINCT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EntityStructureAssertion:
    entity_id: str = ""
    entity_role: EntityRole = EntityRole.AMBIGUOUS
    canonical_name: str = ""
    parent_entity_id: str = ""
    child_entity_ids: tuple[str, ...] = ()
    sibling_entity_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityPairRelation:
    entity_a: str = ""
    entity_b: str = ""
    relation: EntityRelation = EntityRelation.UNKNOWN
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()