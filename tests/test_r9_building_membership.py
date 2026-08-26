"""R9 Building Membership REFACTOR tests."""

from src.membership.analyzer_v2 import (
    BuildingMembershipAnalyzerV2,
    MembershipLevel,
    MembershipEvidence,
    MembershipResult,
    BuildingFunction,
    BuildingFunctionClassifier,
)


def test_function_classifier_school():
    c = BuildingFunctionClassifier()
    assert c.classify("北京小学", osm_tags={"amenity": "school"}) == BuildingFunction.SCHOOL
    assert c.classify("XX小学教学楼") == BuildingFunction.SCHOOL


def test_function_classifier_hospital():
    c = BuildingFunctionClassifier()
    assert c.classify("人民医院", osm_tags={"amenity": "hospital"}) == BuildingFunction.HOSPITAL


def test_function_classifier_commercial():
    c = BuildingFunctionClassifier()
    assert c.classify("万达广场") == BuildingFunction.COMMERCIAL


def test_school_excluded():
    a = BuildingMembershipAnalyzerV2()
    result = a.analyze(
        building_id="b001", building_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        building_name="XX小学", compound_id="c001",
        osm_tags={"amenity": "school"},
    )
    assert result.level == MembershipLevel.EXCLUDED
    assert result.primary_function == BuildingFunction.SCHOOL


def test_commercial_allowed_in_mixed_use():
    a = BuildingMembershipAnalyzerV2()
    result = a.analyze(
        building_id="b002", building_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        building_name="底商", compound_id="c001",
        compound_boundary_wkt="POLYGON((-1 -1, 2 -1, 2 2, -1 2, -1 -1))",
        morphology="MIXED_USE",
    )
    assert result.level != MembershipLevel.EXCLUDED


def test_containment_strong():
    a = BuildingMembershipAnalyzerV2()
    result = a.analyze(
        building_id="b003", building_wkt="POLYGON((0.1 0.1, 0.9 0.1, 0.9 0.9, 0.1 0.9, 0.1 0.1))",
        building_name="住宅楼", compound_id="c001",
        compound_boundary_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )
    assert result.level == MembershipLevel.CONFIRMED


def test_outside_excluded():
    a = BuildingMembershipAnalyzerV2()
    result = a.analyze(
        building_id="b004", building_wkt="POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))",
        building_name="外部建筑", compound_id="c001",
        compound_boundary_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
    )
    assert result.level in (MembershipLevel.EXCLUDED, MembershipLevel.UNCERTAIN)


def test_membership_result():
    r = MembershipResult(
        building_id="b001", compound_id="c001",
        level=MembershipLevel.CONFIRMED, confidence=0.85,
        primary_function=BuildingFunction.RESIDENTIAL,
    )
    assert r.level == MembershipLevel.CONFIRMED
    assert r.primary_function == BuildingFunction.RESIDENTIAL