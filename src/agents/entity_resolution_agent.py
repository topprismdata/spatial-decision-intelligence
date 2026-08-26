"""
Agent 1: Entity Resolution Agent (小区识别智能体).
Parses unstructured community names/addresses into typed components,
classifies entity scale levels, and establishes canonical identity.

REFACTORED (M1): now delegates to component_matcher and pair_features
for name parsing and entity classification, eliminating duplicate logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from src.domain.world_model import EntityCategory

# Delegate to the validated component infrastructure
from src.entity_resolution.component_matcher import extract_components
from src.entity_resolution.pair_features import parse_chinese_community_semantics
from src.domain.models import SourceRecord, EntityType


@dataclass
class ResolvedEntityContext:
    """Structured semantic understanding of a spatial entity."""
    raw_name: str
    raw_address: str
    canonical_name: str
    category: EntityCategory
    scale_level: str  # "COURTYARD_LEVEL", "COMMUNITY_LEVEL", "LARGE_ESTATE"
    base_name: str
    phase_id: Optional[str] = None
    subarea_id: Optional[str] = None
    courtyard_id: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0


# Mapping from v1 EntityType to v2 EntityCategory (used by this agent)
_ENTITY_TYPE_TO_CATEGORY = {
    EntityType.RESIDENTIAL_COMMUNITY: EntityCategory.RESIDENTIAL_COMMUNITY,
    EntityType.RESIDENTIAL_COURTYARD: EntityCategory.RESIDENTIAL_COURTYARD,
    EntityType.RESIDENTIAL_DORMITORY: EntityCategory.RESIDENTIAL_DORMITORY,
    EntityType.MIXED_COMMERCIAL_RESIDENTIAL: EntityCategory.MIXED_COMMERCIAL_RESIDENTIAL,
    EntityType.NON_RESIDENTIAL_COMMERCIAL: EntityCategory.COMMERCIAL_STORE,
    EntityType.NON_RESIDENTIAL_FACILITY: EntityCategory.FACILITY,
}


class EntityResolutionAgent:
    """Understands spatial entity semantics before any geometry is constructed.

    Uses the validated component_matcher and pair_features infrastructure
    for name parsing, retaining only scale-level inference as unique logic.
    """

    COMMUNITY_SUFFIXES = ("小区", "花园", "家园", "苑", "湾", "城", "华庭", "景苑", "名邸", "山庄", "世家")

    def __init__(self):
        pass

    def resolve(
        self,
        name: str,
        address: str = "",
        city: str = "北京市",
        district: str = ""
    ) -> ResolvedEntityContext:
        """Parses entity into structured components and scale hints.

        Delegates name parsing to component_matcher.extract_components()
        and entity type classification to pair_features.parse_chinese_community_semantics().
        """
        # Build a lightweight SourceRecord-like dict for parse_chinese_community_semantics
        # (it expects a SourceRecord but we can construct a minimal one)
        from types import SimpleNamespace
        mock_record = SimpleNamespace(
            name_raw=name,
            address_raw=address,
            attributes_raw={"小区建筑类型": "", "产权性质": ""},
        )

        # Delegate 1: entity type classification via pair_features
        semantics = parse_chinese_community_semantics(mock_record)  # type: ignore
        v1_type = semantics.get("entity_type", EntityType.RESIDENTIAL_COMMUNITY)
        category = _ENTITY_TYPE_TO_CATEGORY.get(v1_type, EntityCategory.RESIDENTIAL_COMMUNITY)

        # Delegate 2: component extraction via component_matcher
        components = extract_components(name)
        base_name = components.base_name or semantics.get("base_name", name)
        phase_id = semantics.get("phase") or next(
            (d for d in components.discriminators if d in ("phase",)), None
        )
        subarea_id = semantics.get("subarea") or next(
            (d for d in components.discriminators if d in ("subarea",)), None
        )
        courtyard_id = semantics.get("court_no") or next(
            (d for d in components.discriminators if d in ("court",)), None
        )

        # Build canonical name
        canonical = self._build_canonical_name(base_name, phase_id, subarea_id, courtyard_id)

        # Scale level inference (unique to this agent — no duplication)
        scale_level = self._infer_scale_level(base_name, name, category, address)

        # Aliases
        aliases = self._generate_aliases(name, base_name, address)

        return ResolvedEntityContext(
            raw_name=name,
            raw_address=address,
            canonical_name=canonical,
            category=category,
            scale_level=scale_level,
            base_name=base_name,
            phase_id=phase_id,
            subarea_id=subarea_id,
            courtyard_id=courtyard_id,
            aliases=aliases,
            confidence=1.0,
        )

    def _build_canonical_name(
        self,
        base_name: str,
        phase_id: Optional[str],
        subarea_id: Optional[str],
        courtyard_id: Optional[str],
    ) -> str:
        parts = [base_name]
        if courtyard_id:
            parts.append(courtyard_id)
        if phase_id:
            parts.append(phase_id)
        if subarea_id:
            parts.append(subarea_id)
        return " ".join(parts)

    def _infer_scale_level(
        self,
        base_name: str,
        raw_name: str,
        category: EntityCategory,
        address: str,
    ) -> str:
        """Infer entity scale level from name, category, and address cues.

        This is the primary unique logic of this agent — not duplicated
        in component_matcher or pair_features.
        """
        has_large_suffix = any(s in raw_name for s in ("城", "庄", "村", "园", "苑"))
        is_estate_category = category in (
            EntityCategory.MIXED_COMMERCIAL_RESIDENTIAL,
            EntityCategory.RESIDENTIAL_DORMITORY,
        )
        has_district = bool(re.search(r"(街道|镇|乡)", address))

        if has_district or is_estate_category:
            return "LARGE_ESTATE"
        if has_large_suffix:
            return "COMMUNITY_LEVEL"
        return "COURTYARD_LEVEL"

    def _generate_aliases(
        self, raw_name: str, base_name: str, address: str
    ) -> List[str]:
        aliases = []
        # Common alias: drop the suffix
        for suffix in self.COMMUNITY_SUFFIXES:
            if raw_name.endswith(suffix):
                alias = raw_name[: -len(suffix)]
                if len(alias) >= 2:
                    aliases.append(alias)
        # Address-based alias
        if address and base_name and base_name in address:
            addr_part = address.split(base_name)[0].strip()
            if addr_part:
                aliases.append(f"{addr_part}{base_name}")
        return list(dict.fromkeys(aliases))  # deduplicate preserving order