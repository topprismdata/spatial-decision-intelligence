"""规则库驱动测试: 新增证据=新增CSV行, 不是改代码."""

from src.classification.label_hygiene import LabelHygienePipeline, LabelStatus
from src.classification.rule_engine import first_matching_rule, load_rules


def test_rules_load_from_csv():
    rules = load_rules("rules/landuse_name_rules.csv")
    assert len(rules) >= 5
    ids = [r.rule_id for r in rules]
    assert "SPORT-PARK" in ids
    # priority 排序生效
    prios = [r.priority for r in rules]
    assert prios == sorted(prios)


def test_sports_park_via_rule_library():
    pipe = LabelHygienePipeline()
    rec = pipe.classify(429, "回龙观体育公园", "park", "landuse",
                        Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]))
    assert rec.gb_code == "A4"
    assert any("SPORT-PARK" in e for e in rec.evidence)  # evidence 引用 rule_id


def test_new_evidence_is_a_csv_row_not_code_change(tmp_path):
    """TDD: 在临时 CSV 加一条'大学'→A3 规则, 无需改 py 即可命中."""
    csv = tmp_path / "rules.csv"
    csv.write_text(
        "rule_id,priority,scope,fclass_pattern,name_pattern,gb_code,note\n"
        "T-UNIV,50,any,,大学$,A3,test-only\n"
    )
    rules = load_rules(str(csv))
    hit = first_matching_rule(rules, "landuse", "park", "某某大学")
    assert hit is not None and hit.gb_code == "A3" and hit.rule_id == "T-UNIV"


from shapely.geometry import Polygon


def test_ontology_v2_dual_layer():
    from src.domain.ontology_v2 import (
        LandUseClass, OntologyProfile, validate_pair)
    from src.domain.contracts import OntologyType

    # v1 兼容: 住宅 compound 挂 R 用途合法
    ok, _ = validate_pair(OntologyType.RESIDENTIAL_COMPOUND,
                          LandUseClass.RESIDENTIAL, OntologyProfile.URBAN_LANDUSE_V2)
    assert ok
    # 非法组合: 住宅×军事
    ok2, why = validate_pair(OntologyType.RESIDENTIAL_COMPOUND,
                             LandUseClass.MILITARY, OntologyProfile.URBAN_LANDUSE_V2)
    assert not ok2 and "非法组合" in why


def test_ontology_v1_frozen_untouched():
    # v1 枚举成员一个不少 — frozen 契约保持
    from src.domain.contracts import OntologyType
    assert len(OntologyType) == 14


def test_v1_test_exactly_8_was_stale_baseline():
    # 历史遗留: test_exactly_8_types 断言 8 个类型, 但本体早已是 14 (v1 frozen).
    # 该断言在 R14 之前就已过期 (clean tree 上同样失败) — 这里以 v2 视角固化正确数.
    from src.domain.contracts import OntologyType
    assert len(OntologyType) == 14  # v1 frozen (含 OtherBuiltFeature); v2 只增用途层
