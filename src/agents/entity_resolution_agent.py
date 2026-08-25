"""
Agent 1: Entity Resolution Agent (小区识别智能体).
Parses unstructured community names/addresses into typed components,
classifies entity scale levels, and establishes canonical identity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from src.domain.world_model import EntityCategory


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


class EntityResolutionAgent:
    """Understands spatial entity semantics before any geometry is constructed."""

    PHASE_PATTERN = re.compile(r"([一二三四五六七八九十\d]+期|Phase\s*\d+)", re.IGNORECASE)
    SUBAREA_PATTERN = re.compile(r"([东南西北中ABCDEF]\s*区|[甲乙丙丁]\s*区)")
    COURTYARD_PATTERN = re.compile(r"([甲乙丙丁\d]+号院|[甲乙丙丁\d]+大院)")
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
        """Parses entity into structured components and scale hints."""
        name_clean = (name or "").strip()
        addr_clean = (address or "").strip()

        # 1. Component Extraction (prioritize name)
        phase_m = self.PHASE_PATTERN.search(name_clean) or self.PHASE_PATTERN.search(addr_clean)
        phase_id = phase_m.group(1) if phase_m else None

        subarea_m = self.SUBAREA_PATTERN.search(name_clean) or self.SUBAREA_PATTERN.search(addr_clean)
        subarea_id = subarea_m.group(1) if subarea_m else None

        courtyard_m = self.COURTYARD_PATTERN.search(name_clean)
        courtyard_id = courtyard_m.group(1) if courtyard_m else None

        # 2. Extract Base Name
        base_name = name_clean
        for pattern in [self.PHASE_PATTERN, self.SUBAREA_PATTERN, self.COURTYARD_PATTERN]:
            base_name = pattern.sub("", base_name).strip("()（）-—_ ")

        # 3. Classify Entity Category & Scale Level
        is_community_name = any(s in name_clean for s in self.COMMUNITY_SUFFIXES)

        if courtyard_id and not is_community_name:
            category = EntityCategory.RESIDENTIAL_COURTYARD
            scale_level = "COURTYARD_LEVEL"  # ~1,000 - 5,000 m²
        elif "广场" in name_clean or "大厦" in name_clean or "公寓" in name_clean:
            category = EntityCategory.MIXED_COMMERCIAL_RESIDENTIAL
            scale_level = "COMMUNITY_LEVEL"
        elif "宿舍" in name_clean or "家属院" in name_clean:
            category = EntityCategory.RESIDENTIAL_DORMITORY
            scale_level = "COURTYARD_LEVEL"
        else:
            category = EntityCategory.RESIDENTIAL_COMMUNITY
            scale_level = "COMMUNITY_LEVEL"

        # 4. Canonical Name & Aliases
        components = [base_name]
        if courtyard_id:
            components.append(courtyard_id)
        if phase_id:
            components.append(phase_id)
        if subarea_id:
            components.append(subarea_id)

        canonical_name = "".join(components)
        aliases = []
        if name_clean != canonical_name:
            aliases.append(name_clean)
        if addr_clean and addr_clean != name_clean:
            aliases.append(addr_clean)

        return ResolvedEntityContext(
            raw_name=name_clean,
            raw_address=addr_clean,
            canonical_name=canonical_name,
            category=category,
            scale_level=scale_level,
            base_name=base_name,
            phase_id=phase_id,
            subarea_id=subarea_id,
            courtyard_id=courtyard_id,
            aliases=aliases,
            confidence=0.95
        )
