"""R12 Entity Structure Hierarchy Resolver: Estate/Phase/Compound disambiguation.

Addresses D2 failures: hierarchy confusion, same-name-different-entity.
"""

from __future__ import annotations

import re
from typing import Optional

from src.entity_resolution.contract import (
    EntityPairRelation,
    EntityRelation,
    EntityRole,
    EntityStructureAssertion,
)
from src.domain.contracts import OntologyType


class EntityHierarchyResolver:
    """Resolves Estate/Phase/Compound hierarchy from names and spatial evidence.

    Key capabilities:
    - Detect phase indicators (一期/二期, A区/B区)
    - Detect same-name-different-entity via spatial separation
    - Resolve Estate/Phase/Compound roles
    """

    PHASE_PATTERNS = re.compile(r"([一二三四五六七八九十\d]+期|[A-Z一二三四五六七八九十\d]+\s*区)")
    ESTATE_SUFFIXES = ("花园", "家园", "新城", "城", "庄", "苑", "园", "社区", "小区")
    COMPOUND_SUFFIXES = ("院", "里", "巷", "条", "号", "小区", "公寓")

    def resolve_hierarchy(self, names: list[str], locations: list[tuple[float, float]]) -> list[EntityStructureAssertion]:
        """Resolve entity hierarchy from a list of names and locations."""
        assertions = []
        name_groups = self._group_by_base_name(names, locations)

        for base_name, group in name_groups.items():
            if len(group) == 1:
                # Single entity: determine role
                name, loc = group[0]
                role = self._determine_role(name, base_name)
                assertions.append(EntityStructureAssertion(
                    entity_id=f"entity_{hash(name)}",
                    entity_role=role,
                    canonical_name=name,
                    confidence=0.7 if role != EntityRole.AMBIGUOUS else 0.3,
                    evidence=(f"single_entity:{name}",),
                ))
            else:
                # Multiple entities with same base name: check for phase/compound split
                parent_name = base_name
                parent_assertion = EntityStructureAssertion(
                    entity_id=f"estate_{hash(parent_name)}",
                    entity_role=EntityRole.RESIDENTIAL_ESTATE,
                    canonical_name=parent_name,
                    confidence=0.8,
                    evidence=(f"parent_entity:{parent_name}",),
                )
                assertions.append(parent_assertion)

                for name, loc in group:
                    role = self._determine_role(name, base_name)
                    phase_match = self.PHASE_PATTERNS.search(name)
                    child_id = f"entity_{hash(name)}"
                    parent_assertion = EntityStructureAssertion(
                        entity_id=child_id,
                        entity_role=EntityRole.RESIDENTIAL_PHASE if phase_match else EntityRole.RESIDENTIAL_COMPOUND,
                        canonical_name=name,
                        parent_entity_id=parent_assertion.entity_id,
                        confidence=0.75,
                        evidence=(f"child_of:{parent_name}", f"phase:{phase_match.group(0) if phase_match else 'none'}"),
                    )
                    assertions.append(parent_assertion)

        return assertions

    def disambiguate_same_name(self, entity_a: str, entity_b: str,
                                geom_a: str, geom_b: str) -> EntityPairRelation:
        """Determine if two entities with the same name are the same or different."""
        from shapely import wkt as _wkt
        ga = _wkt.loads(geom_a)
        gb = _wkt.loads(geom_b)

        dist = ga.distance(gb)
        dist_m = dist * 111_000

        if dist_m < 50:
            return EntityPairRelation(
                entity_a=entity_a, entity_b=entity_b,
                relation=EntityRelation.SAME_ENTITY,
                confidence=0.85,
                evidence=(f"proximity:{dist_m:.0f}m",),
            )
        elif 50 <= dist_m < 500:
            return EntityPairRelation(
                entity_a=entity_a, entity_b=entity_b,
                relation=EntityRelation.SIBLING,
                confidence=0.6,
                evidence=(f"nearby_but_separate:{dist_m:.0f}m",),
            )
        else:
            return EntityPairRelation(
                entity_a=entity_a, entity_b=entity_b,
                relation=EntityRelation.DISTINCT,
                confidence=0.9,
                evidence=(f"distant:{dist_m:.0f}m",),
            )

    @staticmethod
    def _group_by_base_name(names: list[str], locations: list[tuple[float, float]]) -> dict:
        """Group names by their base name (stripping phase indicators)."""
        groups = {}
        for name, loc in zip(names, locations):
            base = name
            for suffix in ["一期", "二期", "三期", "四期", "五期", "东区", "西区", "南区", "北区"]:
                base = base.replace(suffix, "")
            base = base.strip()
            groups.setdefault(base, []).append((name, loc))
        return groups

    @staticmethod
    def _determine_role(name: str, base_name: str) -> EntityRole:
        if name != base_name:
            return EntityRole.RESIDENTIAL_PHASE
        if any(suffix in name for suffix in ["院", "里", "巷", "号"]):
            return EntityRole.RESIDENTIAL_COMPOUND
        if any(suffix in name for suffix in ["花园", "家园", "新城", "城", "庄", "苑"]):
            return EntityRole.RESIDENTIAL_ESTATE
        return EntityRole.AMBIGUOUS