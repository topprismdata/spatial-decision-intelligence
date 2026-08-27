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

    def __init__(self, gazetteer=None):
        # Optional R14-P5 AmapGazetteer for admin-chain-backed disambiguation.
        self._gazetteer = gazetteer

    def disambiguate_same_name(self, entity_a: str, entity_b: str,
                                geom_a: str, geom_b: str) -> EntityPairRelation:
        """Determine if two entities with the same name are the same or different.

        When a gazetteer is wired and both names carry phase tokens with a
        district verdict, the admin chains override pure geometry distance:
          same base + different districts  -> DISTINCT (cross-town twin names)
          same base + same district        -> SIBLING (confident)
          ambiguous own-chains + disjoint districts -> DISTINCT (twins)
        """
        if self._gazetteer is not None:
            verdict = self._gazetteer.resolves_same_estate(entity_a, entity_b)
            if verdict is True:
                return EntityPairRelation(
                    entity_a=entity_a, entity_b=entity_b,
                    relation=EntityRelation.SIBLING,
                    confidence=0.85,
                    evidence=("gazetteer:same_estate",),
                )
            if verdict is False:
                return EntityPairRelation(
                    entity_a=entity_a, entity_b=entity_b,
                    relation=EntityRelation.DISTINCT,
                    confidence=0.9,
                    evidence=("gazetteer:district_mismatch",),
                )
            # Ambiguous-gazetteer special case: a name whose own chains span
            # multiple districts is a cross-town twin — geometry alone must
            # never collapse two such candidates to SAME_ENTITY unless both
            # actually sit in one shared district.
            da = {r.district for r in self._gazetteer.chains_for(entity_a) if r.district}
            db = {r.district for r in self._gazetteer.chains_for(entity_b) if r.district}
            if len(da) > 1 and len(db) > 1:
                from shapely import wkt as _wkt_pre
                ga_pre = _wkt_pre.loads(geom_a)
                gb_pre = _wkt_pre.loads(geom_b)
                dist_m = ga_pre.distance(gb_pre) * 111_000
                return EntityPairRelation(
                    entity_a=entity_a, entity_b=entity_b,
                    relation=EntityRelation.DISTINCT,
                    confidence=0.75,
                    evidence=(f"gazetteer:ambiguous_multi_district:{sorted(da)}x{sorted(db)}",
                              f"twins:geom_dist={dist_m:.0f}m"),
                )
            # Otherwise None -> fall through to geometric heuristic below.
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