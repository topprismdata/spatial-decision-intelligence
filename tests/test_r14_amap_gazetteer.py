"""Tests for R14-P5 AmapGazetteer containment checks."""

from src.entity_resolution.amap_gazetteer import AmapGazetteer, GazetteerRecord


def _gaz(records):
    return AmapGazetteer(tuple(records))


class TestSplitPhase:
    def test_numeric_phase(self):
        base, phase = AmapGazetteer().split_phase("龙腾苑二区")
        assert base == "龙腾苑"
        assert phase == "二区"

    def test_qi_phase(self):
        base, phase = AmapGazetteer().split_phase("万科星河湾一期")
        assert base == "万科星河湾"
        assert phase == "一期"

    def test_no_phase(self):
        base, phase = AmapGazetteer().split_phase("上地东里")
        assert (base, phase) == ("上地东里", "")


class TestSameDistrict:
    def test_known_same_district(self):
        g = _gaz([
            GazetteerRecord(name="龙腾苑二区", district="昌平区"),
            GazetteerRecord(name="龙腾苑五区", district="昌平区"),
        ])
        assert g.same_district("龙腾苑二区", "龙腾苑五区") is True

    def test_known_different_district(self):
        g = _gaz([
            GazetteerRecord(name="幸福二区", district="朝阳区"),
            GazetteerRecord(name="幸福二区", district="海淀区"),
        ])
        assert g.same_district("幸福二区", "幸福二区分院") is None  # ambiguous chain → abstain

    def test_unknown_abstains(self):
        g = _gaz([GazetteerRecord(name="龙腾苑二区", district="昌平区")])
        assert g.same_district("龙腾苑二区", "未知小区") is None


class TestResolvesSameEstate:
    def test_same_base_same_district_true(self):
        g = _gaz([
            GazetteerRecord(name="龙腾苑二区", district="昌平区"),
            GazetteerRecord(name="龙腾苑五区", district="昌平区"),
        ])
        assert g.resolves_same_estate("龙腾苑二区", "龙腾苑五区") is True

    def test_different_base_false(self):
        g = _gaz([
            GazetteerRecord(name="龙腾苑二区", district="昌平区"),
            GazetteerRecord(name="回龙观一期", district="昌平区"),
        ])
        assert g.resolves_same_estate("龙腾苑二区", "回龙观一期") is False

    def test_missing_evidence_abstains(self):
        # Empty gazetteer must yield None so caller keeps heuristic path.
        # Both names share base "龙腾苑" with different phases; district data
        # is absent, so the method must abstain rather than vote.
        assert AmapGazetteer(()).resolves_same_estate("龙腾苑二期", "龙腾苑五期") is None

    def test_phase_absent_abstains(self):
        g = _gaz([GazetteerRecord(name="上地东里", district="海淀区")])
        assert g.resolves_same_estate("上地东里", "上地东里西院") is None
