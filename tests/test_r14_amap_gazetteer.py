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


class TestDirectionSubareas:
    """R14-P5: cardinal-direction subareas (北区/南区) are phase tokens too."""

    def test_split_direction_phase(self):
        g = AmapGazetteer(())
        base, phase = g.split_phase("建明里-北区")
        assert base == "建明里-" and phase == "北区"

    def test_golden_mansion_north_south(self):
        base, phase = AmapGazetteer(()).split_phase("金隅·澜湾北区")
        assert base == "金隅·澜湾" and phase == "北区"


class TestAdminCsvLoader:
    def test_admin_fields_populate_district(self, tmp_path):
        csv = tmp_path / "admin.csv"
        csv.write_text(
            "osm_idx,amap_name,pname,cityname,adname,business,address\n"
            "1,国通家园,北京市,北京市,昌平区,,昌崔路201号\n"
        )
        gaz = AmapGazetteer.from_match_csv(str(csv))
        recs = gaz.chains_for("国通家园")
        assert len(recs) == 1
        assert recs[0].district == "昌平区"
        assert recs[0].province == "北京市"

    def test_fallback_loader_prefers_admin(self, tmp_path):
        admin = tmp_path / "admin.csv"
        admin.write_text(
            "osm_idx,amap_name,pname,cityname,adname,business,address\n"
            "1,国通家园,北京市,北京市,昌平区,,\n"
        )
        base = tmp_path / "base.csv"
        base.write_text(
            "osm_idx,grid_key,amap_name,amap_address\n"
            "9,g,某宿舍,某某路\n"
        )
        gaz = AmapGazetteer.from_match_csv.__self__ if False else None  # noqa
        from src.entity_resolution.amap_gazetteer import gazetteer_from_batch_outputs
        gaz = gazetteer_from_batch_outputs(match_csv=str(base), admin_csv=str(admin))
        assert "国通家园" in gaz._by_name
        assert "某宿舍" in gaz._by_name  # merged from fallback

    def test_same_estate_via_admin_districts(self, tmp_path):
        admin = tmp_path / "admin.csv"
        admin.write_text(
            "osm_idx,amap_name,pname,cityname,adname,business,address\n"
            "1,建明里-北区,北京市,北京市,昌平区,,\n"
            "2,建明里-南区,北京市,北京市,昌平区,,\n"
        )
        gaz = AmapGazetteer.from_match_csv(str(admin))
        assert gaz.resolves_same_estate("建明里-北区", "建明里-南区") is True


class TestHierarchyResolverIntegration:
    """R14-P5: gazetteer-backed EntityHierarchyResolver disambiguation."""

    def _resolver(self, records):
        from src.entity_resolution.hierarchy import EntityHierarchyResolver
        return EntityHierarchyResolver(gazetteer=AmapGazetteer(tuple(records)))

    def test_same_base_cross_district_is_distinct(self):
        # 龙腾苑 in 昌平 vs same-name estate in 海淀 => DISTINCT despite proximity
        r = self._resolver([
            GazetteerRecord(name="龙腾苑二区", district="昌平区"),
            GazetteerRecord(name="龙腾苑二区", district="海淀区"),
        ])
        rel = r.disambiguate_same_name("龙腾苑二区", "龙腾苑二区",
                                       "POLYGON((0 0,1 0,1 1,0 0))",
                                       "POLYGON((0 0.001,1 0.001,1 1.001,0 0.001))")
        assert rel.relation.value == "DISTINCT"
        assert any("ambiguous_multi_district" in e or "district_mismatch" in e
                   for e in rel.evidence)

    def test_sibling_boosted_by_gazetteer(self):
        r = self._resolver([
            GazetteerRecord(name="建明里-北区", district="昌平区"),
            GazetteerRecord(name="建明里-南区", district="昌平区"),
        ])
        rel = r.disambiguate_same_name("建明里-北区", "建明里-南区",
                                       "POLYGON((0 0,1 0,1 1,0 0))",
                                       "POLYGON((2 0,3 0,3 1,2 0))")
        assert rel.relation.value == "SIBLING"
        assert any("same_estate" in e for e in rel.evidence)

    def test_abstain_falls_back_to_geometry(self):
        # Empty gazetteer -> None verdict -> geometric path decides.
        r = self._resolver([])
        rel = r.disambiguate_same_name("X一期", "Y二期",
                                       "POLYGON((0 0,0.01 0,0.01 0.01,0 0))",
                                       "POLYGON((5 5,5.01 5,5.01 5.01,5 5))")
        assert rel.relation.value == "DISTINCT"  # geometric distance ~700km
