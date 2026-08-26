"""P1-01 Building Membership tests."""

import pytest
from src.membership.analyzer import (
    BuildingMembershipAnalyzer,
    MembershipLevel,
    MembershipEvidence,
    MembershipResult,
)


class TestBuildingMembership:
    """Tests for building membership analysis."""

    def setup_method(self):
        self.analyzer = BuildingMembershipAnalyzer()

    def test_building_fully_inside_compound(self):
        """Building fully inside compound boundary → CONFIRMED."""
        # Compound: 0.01° square in Beijing
        compound = "POLYGON((116.35 39.90, 116.36 39.90, 116.36 39.91, 116.35 39.91, 116.35 39.90))"
        # Building: smaller square inside
        building = "POLYGON((116.355 39.905, 116.358 39.905, 116.358 39.908, 116.355 39.908, 116.355 39.905))"

        result = self.analyzer.analyze(
            building_id="b-001",
            building_wkt=building,
            compound_id="c-001",
            compound_boundary_wkt=compound,
        )

        assert result.level == MembershipLevel.CONFIRMED
        assert result.confidence >= 0.80
        assert any(e.evidence_type == "CONTAINMENT" and e.supports for e in result.evidence)

    def test_building_outside_compound(self):
        """Building clearly outside compound boundary → EXCLUDED."""
        compound = "POLYGON((116.35 39.90, 116.36 39.90, 116.36 39.91, 116.35 39.91, 116.35 39.90))"
        # Building: far away
        building = "POLYGON((116.38 39.92, 116.39 39.92, 116.39 39.93, 116.38 39.93, 116.38 39.92))"

        result = self.analyzer.analyze(
            building_id="b-002",
            building_wkt=building,
            compound_id="c-001",
            compound_boundary_wkt=compound,
        )

        assert result.level == MembershipLevel.EXCLUDED
        assert result.confidence < 0.30

    def test_building_cluster_membership(self):
        """Building in compound building list → cluster evidence."""
        compound = "POLYGON((116.35 39.90, 116.36 39.90, 116.36 39.91, 116.35 39.91, 116.35 39.90))"
        building = "POLYGON((116.355 39.905, 116.358 39.905, 116.358 39.908, 116.355 39.908, 116.355 39.905))"

        result = self.analyzer.analyze(
            building_id="b-001",
            building_wkt=building,
            compound_id="c-001",
            compound_boundary_wkt=compound,
            compound_building_ids=["b-001", "b-003", "b-004"],
        )

        cluster_ev = [e for e in result.evidence if e.evidence_type == "CLUSTER"]
        assert len(cluster_ev) == 1
        assert cluster_ev[0].supports is True
        assert cluster_ev[0].confidence == 1.0

    def test_building_not_in_cluster(self):
        """Building not in compound building list → no cluster evidence."""
        result = self.analyzer._check_cluster_membership(
            "b-999", ["b-001", "b-002", "b-003"]
        )
        assert result.supports is False
        assert result.confidence == 0.0

    def test_name_match_full(self):
        """Building name contains compound name → naming evidence."""
        result = self.analyzer._check_name_match(
            "龙湖花园1号楼", "龙湖花园"
        )
        assert result.supports is True
        assert result.confidence >= 0.6

    def test_name_no_match(self):
        """No name overlap → no naming evidence."""
        result = self.analyzer._check_name_match(
            "远洋天地", "龙湖花园"
        )
        assert result.supports is False

    def test_road_separation(self):
        """Road between building and compound → separation evidence."""
        compound = "POLYGON((116.35 39.90, 116.36 39.90, 116.36 39.91, 116.35 39.91, 116.35 39.90))"
        building = "POLYGON((116.37 39.905, 116.38 39.905, 116.38 39.908, 116.37 39.908, 116.37 39.905))"
        # Road between them
        road = "LINESTRING(116.36 39.90, 116.36 39.91)"

        result = self.analyzer.analyze(
            building_id="b-003",
            building_wkt=building,
            compound_id="c-001",
            compound_boundary_wkt=compound,
            road_network_wkt=[road],
        )

        road_ev = [e for e in result.evidence if e.evidence_type == "ROAD_SEPARATION"]
        assert len(road_ev) == 1
        # Road should refute membership (separates building from compound)
        assert road_ev[0].supports is False

    def test_membership_result_properties(self):
        """MembershipResult helper properties work correctly."""
        result = MembershipResult(
            building_id="b-001",
            compound_id="c-001",
            level=MembershipLevel.LIKELY,
            confidence=0.65,
            evidence=[
                MembershipEvidence("CONTAINMENT", True, 0.8, "inside"),
                MembershipEvidence("ROAD_SEPARATION", False, 0.6, "road"),
            ],
        )
        assert len(result.supporting_evidence) == 1
        assert len(result.refuting_evidence) == 1

    def test_confidence_aggregation(self):
        """Weighted aggregation produces reasonable confidence."""
        evidence = [
            MembershipEvidence("CONTAINMENT", True, 1.0, "inside"),
            MembershipEvidence("ROAD_SEPARATION", True, 0.7, "no road"),
            MembershipEvidence("CLUSTER", True, 1.0, "in list"),
            MembershipEvidence("NAMING", True, 0.8, "name match"),
        ]
        confidence = self.analyzer._aggregate_confidence(evidence)
        assert 0.80 <= confidence <= 1.0

    def test_confidence_refuting_evidence(self):
        """Refuting evidence reduces confidence."""
        strong = [
            MembershipEvidence("CONTAINMENT", True, 1.0, "inside"),
        ]
        weak = [
            MembershipEvidence("CONTAINMENT", True, 1.0, "inside"),
            MembershipEvidence("ROAD_SEPARATION", False, 0.8, "road separates"),
        ]
        c_strong = self.analyzer._aggregate_confidence(strong)
        c_weak = self.analyzer._aggregate_confidence(weak)
        assert c_strong > c_weak

    def test_empty_evidence(self):
        """No evidence → confidence 0.0."""
        confidence = self.analyzer._aggregate_confidence([])
        assert confidence == 0.0

    def test_confidence_to_level(self):
        """Confidence mapping to levels is correct."""
        assert self.analyzer._confidence_to_level(0.90) == MembershipLevel.CONFIRMED
        assert self.analyzer._confidence_to_level(0.65) == MembershipLevel.LIKELY
        assert self.analyzer._confidence_to_level(0.35) == MembershipLevel.UNCERTAIN
        assert self.analyzer._confidence_to_level(0.10) == MembershipLevel.EXCLUDED