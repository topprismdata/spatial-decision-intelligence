"""B8-D: DeterministicRoadInterpreter. Extracts road semantic features from OSM data.

Outputs RoadSemanticAssertion. No ML, no VLM.
"""

from __future__ import annotations

from shapely import wkt as _wkt
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import unary_union

from src.road_semantics import (
    CompoundSplitSupport,
    Producer,
    RoadContinuity,
    RoadRole,
    RoadSemanticAssertion,
)


class DeterministicRoadInterpreter:
    """Deterministic road semantic interpretation.

    Features: road class, continuity, width proxy, building connectivity.
    """

    STRONG_SEPARATORS = frozenset({"primary", "secondary", "tertiary", "trunk", "motorway",
                                    "primary_link", "secondary_link", "tertiary_link"})
    WEAK_SEPARATORS = frozenset({"service", "unclassified", "residential"})
    EXCLUDED = frozenset({"footway", "path", "cycleway", "bridleway", "track", "pedestrian", "steps"})

    def interpret(self, road_wkt: str, highway_tag: str, compound_candidates: list[str], buildings: list[str]) -> RoadSemanticAssertion:
        road_geom = _wkt.loads(road_wkt) if isinstance(road_wkt, str) else road_wkt
        road_id = "road"

        # Role: classify by highway tag
        if highway_tag in self.STRONG_SEPARATORS:
            role = RoadRole.PUBLIC_SEPARATOR
        elif highway_tag in self.WEAK_SEPARATORS:
            role = RoadRole.WEAK_SEPARATOR
        elif highway_tag == "service":
            role = RoadRole.WEAK_SEPARATOR
        else:
            role = RoadRole.AMBIGUOUS

        # Continuity: check if road extends through the entire candidate area
        continuity = self._check_continuity(road_geom, compound_candidates)

        # Compound split support: does the road separate buildings on either side?
        split_support = self._check_split_support(road_geom, buildings)

        return RoadSemanticAssertion(
            road_segment_id=road_id,
            road_role=role,
            continuity=continuity,
            compound_split_support=split_support,
            evidence_features={
                "highway_tag_weight": 1.0 if highway_tag in self.STRONG_SEPARATORS else 0.5,
                "continuity_score": 0.9 if continuity == RoadContinuity.THROUGH else 0.3,
                "building_separation_score": 1.0 if split_support == CompoundSplitSupport.SUPPORT else 0.0,
            },
            producer=Producer.DETERMINISTIC,
        )

    @staticmethod
    def _check_continuity(road_geom, compound_candidates: list[str]) -> RoadContinuity:
        if not compound_candidates:
            return RoadContinuity.LOCAL
        intersects_all = 0
        for cwkt in compound_candidates:
            try:
                c = _wkt.loads(cwkt)
                if road_geom.intersects(c):
                    intersects_all += 1
            except Exception:
                pass
        if len(compound_candidates) > 0 and intersects_all >= len(compound_candidates):
            return RoadContinuity.THROUGH
        elif intersects_all > 0:
            return RoadContinuity.TERMINATING
        return RoadContinuity.LOCAL

    @staticmethod
    def _check_split_support(road_geom, buildings: list[str]) -> CompoundSplitSupport:
        if not buildings:
            return CompoundSplitSupport.UNKNOWN
        sides = set()
        for bwkt in buildings:
            try:
                b = _wkt.loads(bwkt)
                centroid = b.centroid
                if road_geom.distance(centroid) < 0.001:
                    sides.add(0)
                # Check which side of the road
                if road_geom.distance(centroid) > 0.01:
                    sides.add(1)
            except Exception:
                pass
        if len(sides) >= 2:
            return CompoundSplitSupport.SUPPORT
        return CompoundSplitSupport.AGAINST