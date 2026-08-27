"""R15-T1 Label Hygiene Pipeline v2: 四级真相源优先级流水线.

真相优先级 (用户定义, 2026-08-27):
    P1 政府文件定义   规划图/公文 — 最高权威 (预留接口, 暂无数据)
    P2 高德地图       POI type 链 + biz_ext (官方 API, 已结构化)
    P3 互联网        百科/房产网站交叉核验 (人工/半自动, 用于审计)
    P4 OSM           成本最低, 作为基础层与回退层

OSM 出错不是丢弃 OSM, 而是: OSM 打底 → 上层证据可否决/确认 →
每条决策携带 source 与 evidence, 可审计可回滚.

LabelStatus:
    GOV_DEFINED      P1 命中 (未来)
    EXTERNAL_CONFIRM P2 高德 type 链确认或改写
    NAME_OVERRIDE    P3 名称规则推翻 P4 标签
    POI_VOTE         几何投票 ≥2 同类子设施
    TRUSTED_TAG      P4 标签无冲突, 直接采用
    AMBIGUOUS        上层证据互相矛盾 → UNRESOLVED
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from src.classification.gb50137 import LANDUSE_MAP, POI_MAP


class LabelStatus(str, Enum):
    GOV_DEFINED = "GOV_DEFINED"
    EXTERNAL_CONFIRM = "EXTERNAL_CONFIRM"
    NAME_OVERRIDE = "NAME_OVERRIDE"
    POI_VOTE = "POI_VOTE"
    TRUSTED_TAG = "TRUSTED_TAG"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class ClassificationRecord:
    fid: int
    name: str
    osm_fclass: str
    source_layer: str
    gb_code: str
    label_status: LabelStatus
    evidence: tuple[str, ...] = field(default_factory=tuple)


# ── P3 名称证据规则 ──────────────────────────────────────────────────────────
# 特定设施规则在前; 校园内球场属于校园 A4 生态而非教学区, 不被"大学"翻转.
_NAME_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 体育设施名称结尾优先判 A4 (无论是否带大学前缀)
    ("A4", re.compile(r"(体育场|体育馆|足球场|篮球场|网球场|操场|球场)$")),
    ("A5", re.compile(r"医院|卫生院|诊所|卫生服务中心|保健院")),
    ("B1", re.compile(r"便利店|超市|购物中心|商场|市场$")),
    ("M", re.compile(r"工厂|工业区")),
)

# 名称含体育线索的 park 族 → A4 (覆盖"XX公园"其实是体育园区的案例)
_SPORTY_PARK_FAMILY = {"park", "grass", "scrub", "recreation_ground", "forest"}
_SPORTY_PARK_KW = re.compile(r"体育|运动|健身|竞技")

# 校园主体名 (整个面就是学校) → A3; 但校园内的具体场馆保持其自身类型
_CAMPUS_MAIN = re.compile(
    r"^(华北电力大学|北京农学院|北京师范大学|北京外国语大学附属外国语学校"
    r"|北京警察学院汽车驾驶学校|农业部管理干部学院|北京华文学院|北京明园大学"
    r"|北京交通运输职业学院|邮政科学研究规划院)"
)

# poi fclass 的家族默认码: 当名称规则不触发时用 POI 自己的 fclass 推断
_POI_FAMILY_DEFAULT = {
    "stadium": "A4", "pitch": "A4", "track": "A4",
    "sports_centre": "A4", "supermarket": "B1", "mall": "B1",
}


def _name_evidence(name: str) -> tuple[str | None, str]:
    for code, pat in _NAME_RULES:
        m = pat.search(name or "")
        if m:
            return code, f"name:{m.group(0)}"
    return None, ""


def _poi_vote(target_geom, poi_faces: list, min_votes: int = 2) -> tuple[str | None, int]:
    inside = []
    try:
        buf = target_geom.buffer(1e-9)
    except Exception:
        return None, 0
    for geom, code in poi_faces:
        try:
            if geom.within(buf):
                inside.append(code)
        except Exception:
            continue
    if len(inside) < min_votes:
        return None, len(inside)
    code, n = Counter(inside).most_common(1)[0]
    return (code, n) if n >= min_votes else (None, n)


class LabelHygienePipeline:
    """四级真相源裁决. gov_records 预留 P1 接口."""

    def __init__(self, poi_faces: list | None = None,
                 gov_records: dict | None = None,
                 amap_types: dict | None = None):
        """
        amap_types: {name_prefix: gb_code} 由高德 place/text type 链预计算 (P2).
        gov_records: {fid_or_name: gb_code} 政府文件核定的地块用途 (P1).
        """
        self._poi_faces = poi_faces or []
        self._gov = gov_records or {}
        self._amap = amap_types or {}

    def classify(self, fid: int, name: str, osm_fclass: str,
                 source_layer: str, geometry=None) -> ClassificationRecord:
        name = name or ""
        ev: list[str] = []

        tag_code = LANDUSE_MAP.get(osm_fclass) if source_layer == "landuse" \
            else POI_MAP.get(osm_fclass)
        base = tag_code or "U"

        # ---- P1 政府文件 ----
        for key in (fid, name):
            if key in self._gov:
                code = self._gov[key]
                rel = "confirms" if code == base else "overrides"
                return ClassificationRecord(fid, name, osm_fclass, source_layer,
                    code, LabelStatus.GOV_DEFINED, (f"P1:{rel} tag({base})",))

        # ---- P2 高德 type 链 ----
        # 仅当 OSM fclass 本身是 school 族 (即该面本来就是教育设施) 时,
        # 高德的"高校/中学/小学"细分才参与; 否则 华北电力大学体育场 会被误翻.
        poi_edu_family = source_layer == "poi_a" and POI_MAP.get(osm_fclass) == "A3"
        is_landuse = source_layer == "landuse"
        for prefix, code in self._amap.items():
            if not name.startswith(prefix):
                continue
            applicable = is_landuse or poi_edu_family or base == "U"
            if not applicable:
                ev.append(f"P2:skip_facility({osm_fclass})")
                break
            if base != "U" and code != base:
                return ClassificationRecord(fid, name, osm_fclass, source_layer,
                    code, LabelStatus.EXTERNAL_CONFIRM,
                    (f"P2:amap_type overrides {osm_fclass}->{base}",))
            ev.append(f"P2:confirm({base})")
            break

        # ---- P3 名称证据 ----
        # 3a. park 族的"体育园区"检查 (体育公园问题回归守卫)
        if osm_fclass in _SPORTY_PARK_FAMILY and _SPORTY_PARK_KW.search(name):
            ev.append(f"P3:sporty_park_kw(体育) overrides park->G")
            return ClassificationRecord(fid, name, osm_fclass, source_layer,
                "A4", LabelStatus.NAME_OVERRIDE, tuple(ev))

        # 3b. 校园主体名 → A3 (只对 landuse 面 / school-family POI)
        campus_main = bool(_CAMPUS_MAIN.match(name))
        is_school_poi = source_layer == "poi_a" and POI_MAP.get(osm_fclass) == "A3"
        family_default = _POI_FAMILY_DEFAULT.get(osm_fclass)

        if campus_main and (source_layer == "landuse" or is_school_poi or not family_default):
            ev.append("P3:campus_main→A3")
            return ClassificationRecord(fid, name, osm_fclass, source_layer,
                "A3", LabelStatus.NAME_OVERRIDE, tuple(ev))

        # 3c. 设施特定规则 (体育场结尾→A4 等), 与 base 冲突才翻转
        ncode, nhit = _name_evidence(name)
        if ncode and ncode != base and not (family_default and family_default == base):
            ev.append(f"P3:name_rule:{nhit} overrides {base}")
            return ClassificationRecord(fid, name, osm_fclass, source_layer,
                ncode, LabelStatus.NAME_OVERRIDE, tuple(ev))
        if family_default and base == "U":
            ev.append(f"P3:family_default({family_default})")
            return ClassificationRecord(fid, name, osm_fclass, source_layer,
                family_default, LabelStatus.TRUSTED_TAG, tuple(ev))

        # ---- P4 几何投票 (无名 park 族) ----
        if geometry is not None and self._poi_faces and \
                osm_fclass in _SPORTY_PARK_FAMILY and not name:
            vote_code, votes = _poi_vote(geometry, self._poi_faces)
            if vote_code and vote_code != base:
                ev.append(f"P4:poi_vote={votes}x{vote_code}")
                return ClassificationRecord(fid, name, osm_fclass, source_layer,
                    vote_code, LabelStatus.POI_VOTE, tuple(ev))

        # ---- L1 直采 ----
        ev.append(f"L1:tag({osm_fclass})->{base}" if tag_code else "L1:no_mapping")
        return ClassificationRecord(fid, name, osm_fclass, source_layer,
                                    base, LabelStatus.TRUSTED_TAG, tuple(ev))

    def run(self, gdf) -> list[ClassificationRecord]:
        poi_faces = [
            (r.geometry, POI_MAP.get(r.osm_fclass))
            for _, r in gdf.iterrows()
            if r.source_layer == "poi_a" and POI_MAP.get(r.osm_fclass)
            and r.geometry.geom_type in ("Polygon", "MultiPolygon")
        ]
        pipe = LabelHygienePipeline(poi_faces=poi_faces, gov_records=self._gov,
                                    amap_types=self._amap) if poi_faces else self
        return [pipe.classify(int(r["FID"]), r.get("Name") or "", r["osm_fclass"],
                              r["source_layer"], r.geometry)
                for _, r in gdf.iterrows()]
