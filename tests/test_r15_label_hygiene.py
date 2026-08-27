"""R15 label hygiene pipeline tests — the 体育公园 regression guard."""

from shapely.geometry import Polygon
from src.classification.label_hygiene import (
    LabelHygienePipeline,
    LabelStatus,
)


def test_sports_park_name_overrides_park_tag():
    pipe = LabelHygienePipeline()
    rec = pipe.classify(429, "回龙观体育公园", "park", "landuse",
                        Polygon([(0,0),(1,0),(1,1),(0,0)]))
    assert rec.gb_code == "A4"
    assert rec.label_status == LabelStatus.NAME_OVERRIDE


def test_plain_park_stays_green():
    pipe = LabelHygienePipeline()
    rec = pipe.classify(1, "太平郊野公园", "park", "landuse")
    assert rec.gb_code == "G"
    assert rec.label_status == LabelStatus.TRUSTED_TAG


def test_unnamed_forest_keeps_tag():
    pipe = LabelHygienePipeline()
    rec = pipe.classify(2, "", "forest", "landuse")
    assert rec.gb_code == "G"


def test_residential_with_school_substring_not_flipped():
    # 公园悦府小区东侧社区公园: contains 小区 but is a park — must stay G.
    # (school rule requires explicit 学校/小学/etc, not bare 区)
    pipe = LabelHygienePipeline()
    rec = pipe.classify(242, "公园悦府小区东侧社区公园", "park", "landuse")
    assert rec.gb_code == "G"


def test_poi_vote_flips_unnamed_recreation_ground():
    # 3 basketball-pitch faces inside an unnamed recreation ground => A4
    pitches = [
        (Polygon([(0.1,0.1),(0.3,0.1),(0.3,0.3),(0.1,0.3)]), "A4"),
        (Polygon([(0.5,0.1),(0.7,0.1),(0.7,0.3),(0.5,0.3)]), "A4"),
        (Polygon([(0.1,0.5),(0.3,0.5),(0.3,0.7),(0.1,0.7)]), "A4"),
    ]
    pipe = LabelHygienePipeline(poi_faces=pitches)
    big = Polygon([(0,0),(1,0),(1,1),(0,1)])
    rec = pipe.classify(9, "", "recreation_ground", "landuse", big)
    assert rec.gb_code == "A4"
    assert rec.label_status == LabelStatus.POI_VOTE


def test_single_vote_no_flip():
    pipe = LabelHygienePipeline(poi_faces=[
        (Polygon([(0.1,0.1),(0.3,0.1),(0.3,0.3),(0.1,0.3)]), "A4"),
    ])
    big = Polygon([(0,0),(1,0),(1,1),(0,1)])
    rec = pipe.classify(9, "", "recreation_ground", "landuse", big)
    assert rec.gb_code == "G"  # 1 vote < threshold -> keep tag


def test_named_hospital_landuse_contradiction():
    # a 'residential' tagged face named XX医院 -> A5 via name override
    pipe = LabelHygienePipeline()
    rec = pipe.classify(77, "某某镇卫生院", "residential", "landuse")
    assert rec.gb_code == "A5"
