"""P1-01 Building Membership: Building BELONGS_TO ResidentialCompound.

Determines whether a building is a member of a residential compound,
outputting membership confidence and evidence.

Four spatial analysis methods:
1. Containment — building fully inside compound boundary
2. Road Separation — road network between building and compound
3. Building Cluster — building is part of the same cluster as compound buildings
4. Naming — building name matches compound name
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MembershipLevel(str, Enum):
    """Confidence level of building membership."""

    CONFIRMED = "CONFIRMED"  # Building is clearly part of the compound
    LIKELY = "LIKELY"  # Strong evidence but not definitive
    UNCERTAIN = "UNCERTAIN"  # Partial or conflicting evidence
    EXCLUDED = "EXCLUDED"  # Building is clearly not part of the compound


@dataclass(frozen=True)
class MembershipEvidence:
    """A single piece of evidence supporting or refuting membership."""

    evidence_type: str  # "CONTAINMENT", "ROAD_SEPARATION", "CLUSTER", "NAMING", "PROXIMITY"
    supports: bool  # True = supports membership, False = refutes
    confidence: float  # 0.0-1.0
    detail: str = ""


@dataclass
class MembershipResult:
    """Result of building membership analysis for one building."""

    building_id: str
    compound_id: str
    level: MembershipLevel = MembershipLevel.UNCERTAIN
    confidence: float = 0.0  # 0.0-1.0 aggregate
    evidence: list[MembershipEvidence] = field(default_factory=list)

    @property
    def supporting_evidence(self) -> list[MembershipEvidence]:
        return [e for e in self.evidence if e.supports]

    @property
    def refuting_evidence(self) -> list[MembershipEvidence]:
        return [e for e in self.evidence if not e.supports]


class BuildingMembershipAnalyzer:
    """Analyzes building membership in a residential compound.

    Uses four methods: containment, road separation, cluster, naming.
    The aggregate confidence is computed from all evidence.
    """

    CONTAINMENT_WEIGHT = 0.40
    ROAD_WEIGHT = 0.25
    CLUSTER_WEIGHT = 0.20
    NAMING_WEIGHT = 0.15

    # Road types that form meaningful separation between buildings and compounds
    SEPARATING_ROAD_TYPES = frozenset({
        "primary", "secondary", "tertiary",
        "primary_link", "secondary_link", "tertiary_link",
        "trunk", "trunk_link",
        "motorway", "motorway_link",
    })

    def __init__(self):
        pass

    def analyze(
        self,
        building_id: str,
        building_wkt: str,
        compound_id: str,
        compound_boundary_wkt: str,
        road_network_wkt: Optional[list[str]] = None,
        compound_building_ids: Optional[list[str]] = None,
        building_name: str = "",
        compound_name: str = "",
    ) -> MembershipResult:
        """Run full membership analysis for one building against one compound."""
        evidence = []

        # Method 1: Spatial containment
        containment_evidence = self._check_containment(
            building_wkt, compound_boundary_wkt
        )
        evidence.append(containment_evidence)

        # Method 2: Road network separation
        if road_network_wkt:
            road_evidence = self._check_road_separation(
                building_wkt, compound_boundary_wkt, road_network_wkt
            )
            evidence.append(road_evidence)

        # Method 3: Building cluster membership
        if compound_building_ids is not None:
            cluster_evidence = self._check_cluster_membership(
                building_id, compound_building_ids
            )
            evidence.append(cluster_evidence)

        # Method 4: Naming convention
        if building_name and compound_name:
            naming_evidence = self._check_name_match(
                building_name, compound_name
            )
            evidence.append(naming_evidence)

        # Aggregate
        confidence = self._aggregate_confidence(evidence)
        level = self._confidence_to_level(confidence)

        return MembershipResult(
            building_id=building_id,
            compound_id=compound_id,
            level=level,
            confidence=confidence,
            evidence=evidence,
        )

    def _check_containment(
        self, building_wkt: str, compound_wkt: str
    ) -> MembershipEvidence:
        """Check if building is spatially contained within compound boundary.

        Containment is the strongest signal: a building fully inside a compound
        boundary is almost certainly part of that compound.
        """
        try:
            from shapely import wkt as _wkt

            building = _wkt.loads(building_wkt)
            compound = _wkt.loads(compound_wkt)

            if building.within(compound):
                # Calculate what fraction of the building is inside
                intersection = building.intersection(compound)
                ratio = intersection.area / max(building.area, 1e-10)
                if ratio > 0.95:
                    return MembershipEvidence(
                        "CONTAINMENT", True, 1.0,
                        f"building fully within compound boundary ({ratio:.0%})",
                    )
                return MembershipEvidence(
                    "CONTAINMENT", True, ratio,
                    f"building {ratio:.0%} inside compound boundary",
                )
            elif compound.within(building):
                return MembershipEvidence(
                    "CONTAINMENT", True, 1.0,
                    "compound boundary fully within building footprint",
                )
            else:
                dist = building.distance(compound)
                return MembershipEvidence(
                    "CONTAINMENT", False, max(0.0, 1.0 - dist * 10),
                    f"building outside compound boundary, distance={dist:.6f}°",
                )
        except Exception as e:
            return MembershipEvidence("CONTAINMENT", False, 0.0, f"error:{e}")

    def _check_road_separation(
        self, building_wkt: str, compound_wkt: str, road_network: list[str]
    ) -> MembershipEvidence:
        """Check if roads separate the building from the compound.

        A major road between building and compound is strong evidence
        that they are separate entities.
        """
        try:
            from shapely import wkt as _wkt
            from shapely.ops import unary_union

            building = _wkt.loads(building_wkt)
            compound = _wkt.loads(compound_wkt)

            # Find the shortest path between building and compound
            gap_line = _build_gap_line(building, compound)
            if gap_line is None:
                return MembershipEvidence(
                    "ROAD_SEPARATION", True, 0.5,
                    "building and compound overlap, no road separation",
                )

            # Check if any major road crosses the gap
            roads = []
            for rwkt in road_network:
                try:
                    roads.append(_wkt.loads(rwkt))
                except Exception:
                    pass

            if not roads:
                return MembershipEvidence(
                    "ROAD_SEPARATION", True, 0.5,
                    "no road data available for separation analysis",
                )

            road_union = unary_union(roads)
            gap_length = gap_line.length

            if gap_line.intersects(road_union):
                # Road crosses the gap — separation evidence
                intersection = gap_line.intersection(road_union)
                cross_ratio = intersection.length / max(gap_length, 0.001)
                # More road crossings = stronger separation
                separation_strength = min(1.0, cross_ratio * 2.0)
                return MembershipEvidence(
                    "ROAD_SEPARATION", False, separation_strength,
                    f"road crosses gap between building and compound",
                )
            else:
                return MembershipEvidence(
                    "ROAD_SEPARATION", True, 0.7,
                    "no road separates building from compound",
                )
        except Exception as e:
            return MembershipEvidence(
                "ROAD_SEPARATION", True, 0.3, f"error:{e}"
            )

    def _check_cluster_membership(
        self, building_id: str, compound_building_ids: list[str]
    ) -> MembershipEvidence:
        """Check if building appears in the same group as compound buildings.

        This is a simple membership check: if the building is already listed
        as a compound building, it's CONFIRMED.
        """
        if building_id in compound_building_ids:
            return MembershipEvidence(
                "CLUSTER", True, 1.0,
                "building is listed as compound building",
            )
        return MembershipEvidence(
            "CLUSTER", False, 0.0,
            "building not in compound building list",
        )

    def _check_name_match(
        self, building_name: str, compound_name: str
    ) -> MembershipEvidence:
        """Check if building name matches or contains compound name.

        Name overlap is weak evidence but useful when spatial data is ambiguous.
        """
        if not building_name or not compound_name:
            return MembershipEvidence(
                "NAMING", False, 0.0, "no name data available"
            )

        # Check if compound name is a substring of building name
        if compound_name in building_name:
            return MembershipEvidence(
                "NAMING", True, 0.8,
                f"building name '{building_name}' contains compound name '{compound_name}'",
            )

        # Check if building name is a substring of compound name
        if building_name in compound_name:
            return MembershipEvidence(
                "NAMING", True, 0.6,
                f"compound name contains building name",
            )

        # Common prefix
        min_len = min(len(building_name), len(compound_name))
        if min_len >= 2 and building_name[:min_len] == compound_name[:min_len]:
            return MembershipEvidence(
                "NAMING", True, 0.4,
                f"name prefix match: '{building_name[:min_len]}'",
            )

        return MembershipEvidence(
            "NAMING", False, 0.0,
            "no name match between building and compound",
        )

    def _aggregate_confidence(self, evidence: list[MembershipEvidence]) -> float:
        """Weighted aggregation of all evidence into a single confidence score."""
        if not evidence:
            return 0.0

        # Weighted sum with method-dependent weights
        weights = {
            "CONTAINMENT": self.CONTAINMENT_WEIGHT,
            "ROAD_SEPARATION": self.ROAD_WEIGHT,
            "CLUSTER": self.CLUSTER_WEIGHT,
            "NAMING": self.NAMING_WEIGHT,
        }

        total_weight = 0.0
        supporting_weight = 0.0
        refuting_weight = 0.0

        for ev in evidence:
            w = weights.get(ev.evidence_type, 0.1)
            if ev.supports:
                supporting_weight += w * ev.confidence
            else:
                refuting_weight += w * ev.confidence
            total_weight += w

        if total_weight == 0:
            return 0.0

        # 0 = all refuting, 1 = all supporting
        supporting_ratio = supporting_weight / max(total_weight, 1e-10)
        refuting_ratio = refuting_weight / max(total_weight, 1e-10)

        # Base: supporting evidence, reduced by half of refuting
        confidence = supporting_ratio - refuting_ratio * 0.5
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _confidence_to_level(confidence: float) -> MembershipLevel:
        if confidence >= 0.80:
            return MembershipLevel.CONFIRMED
        elif confidence >= 0.50:
            return MembershipLevel.LIKELY
        elif confidence >= 0.20:
            return MembershipLevel.UNCERTAIN
        return MembershipLevel.EXCLUDED


def _build_gap_line(geom_a, geom_b):
    """Build a line connecting the closest points of two geometries."""
    from shapely.geometry import LineString

    if geom_a.intersects(geom_b):
        return None

    # Get closest points
    p_a = geom_a.exterior if hasattr(geom_a, 'exterior') else geom_a
    p_b = geom_b.exterior if hasattr(geom_b, 'exterior') else geom_b

    # Find nearest points
    dist = p_a.distance(p_b)
    if dist == 0:
        return None

    # Simple approximation: connect centroids for line
    from shapely.geometry import Point
    ca = geom_a.centroid if hasattr(geom_a, 'centroid') else Point(0, 0)
    cb = geom_b.centroid if hasattr(geom_b, 'centroid') else Point(0, 0)
    return LineString([(ca.x, ca.y), (cb.x, cb.y)])