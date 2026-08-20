"""
Semantic-Aware Feature Extraction for Entity Resolution Pairs.
Accurately decomposes Chinese community names, courtyard numbers, house numbers, phases, and entity types.
"""

import re
import math
from typing import Dict, Any, Tuple, Optional, List
from difflib import SequenceMatcher
from src.domain.models import EntityType, SourceRecord
from src.entity_resolution.component_matcher import (
    extract_components, component_similarity, sibling_relation_for, DiscriminatorType,
)


def parse_chinese_community_semantics(record: SourceRecord) -> Dict[str, Any]:
    """
    Decomposes Chinese community name and metadata into structured semantic components.
    """
    name = str(record.name_raw).strip()
    addr = str(record.address_raw).strip()
    btype = str(record.attributes_raw.get("小区建筑类型", ""))
    ptype = str(record.attributes_raw.get("产权性质", ""))

    # 1. Linguistic markers
    is_dorm = bool(re.search(r"宿舍|家属|职工住宅|教师楼|干部楼|家属院|家属区|生活区|生活小区|住宅区", name))
    is_court = bool(re.search(r"([甲乙丙丁]?\d+|[一二三四五六七八九十百]+)号院", name))
    is_estate = bool(re.search(r"小区|家园|花园|苑|里|庄|村|公寓|住宅", name))

    # Strict non-residential checks
    is_pure_commercial = bool(re.search(r"商业街|商场|超市|批发市场|物流园|产业园|科技园|写字楼|宾馆|酒店|商厦|商务大厦|购物中心", name)) and not is_dorm and not is_estate
    is_commercial_building = bool(re.search(r"大厦|广场|中心", name)) and not is_estate and not is_dorm and not is_court
    
    # Institution / Facility (schools, companies, hospitals, factories)
    is_institution = (bool(re.search(r"(研究所|科研所|设计院|公司|厂|医院|中学|小学|幼儿园|大学|学院|局|站)$", name)) or
                      bool(re.search(r"(研究所|科研所|设计院|公司|制药厂|化工厂|人民医院|附属医院)", name))) and not is_dorm and not is_court and not is_estate

    if is_pure_commercial:
        entity_type = EntityType.NON_RESIDENTIAL_COMMERCIAL
    elif is_commercial_building:
        if "住宅" in btype or "商品房" in ptype:
            entity_type = EntityType.MIXED_COMMERCIAL_RESIDENTIAL
        else:
            entity_type = EntityType.NON_RESIDENTIAL_COMMERCIAL
    elif is_institution:
        entity_type = EntityType.NON_RESIDENTIAL_FACILITY
    elif is_dorm:
        entity_type = EntityType.RESIDENTIAL_DORMITORY
    elif is_court:
        entity_type = EntityType.RESIDENTIAL_COURTYARD
    else:
        entity_type = EntityType.RESIDENTIAL_COMMUNITY

    # 2. Token Extraction
    court_match = re.search(r"([甲乙丙丁]?\d+|[一二三四五六七八九十]+)号院", name)
    court_no = court_match.group(0) if court_match else None

    # House / Door number (e.g. 25号, 130号) - ensure it's not confused with 号院/号楼
    house_match = re.search(r"([甲乙丙丁]?\d+|[一二三四五六七八九十]+)号(?![院楼])", name)
    house_no = house_match.group(0) if house_match else None

    phase_match = re.search(r"([一二三四五六七八九十\d]+)期", name)
    phase = phase_match.group(0) if phase_match else None

    sub_match = re.search(r"(东区|西区|南区|北区|中区|东院|西院|南院|北院|[A-Z]区|[A-Z]\d+|[一二三四五六七八九十\d]+区)", name)
    subarea = sub_match.group(0) if sub_match else None

    # Clean Base name
    clean = re.sub(r"\(.*?\)|（.*?）", "", name)
    for token in [court_no, house_no, phase, subarea]:
        if token:
            clean = clean.replace(token, "")
    clean = clean.strip(" -_#")
    # 仅剥离完整的城市前缀词（整词匹配，绝不能用字符集合，否则会误剥"北竹杆胡同"的"北"）
    for city_prefix in ["北京市", "北京城区", "北京", "石家庄市", "石家庄"]:
        if clean.startswith(city_prefix) and len(clean) - len(city_prefix) >= 2:
            clean = clean[len(city_prefix):]
            break
    if not clean:
        clean = name

    return {
        "entity_type": entity_type,
        "base_name": clean,
        "court_no": court_no,
        "house_no": house_no,
        "phase": phase,
        "subarea": subarea
    }


def _geo_distance_meters(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    lng1, lat1 = p1
    lng2, lat2 = p2
    avg_lat = math.radians((lat1 + lat2) / 2.0)
    dx = (lng1 - lng2) * 111412.84 * math.cos(avg_lat)
    dy = (lat1 - lat2) * 111132.954
    return math.hypot(dx, dy)


def _string_similarity(s1: str, s2: str) -> float:
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1, s2).ratio()


class PairFeatureExtractor:
    """Extracts semantic, geometric, and topological features for entity pairs."""

    @staticmethod
    def extract_features(
        rec_a: SourceRecord,
        rec_b: SourceRecord,
        geom_a,
        geom_b,
        coords_a: Tuple[float, float],
        coords_b: Tuple[float, float],
        sem_a: Dict[str, Any],
        sem_b: Dict[str, Any],
        bge_sim: float = 0.0
    ) -> Dict[str, Any]:
        # Semantic Match Flags
        exact_name_match = (rec_a.name_raw.strip() == rec_b.name_raw.strip())
        name_sim = _string_similarity(rec_a.name_raw, rec_b.name_raw)
        base_exact = (sem_a["base_name"] == sem_b["base_name"]) and len(sem_a["base_name"]) >= 2
        base_sim = _string_similarity(sem_a["base_name"], sem_b["base_name"])

        # Number Conflicts (Absolute Red Lines for Merging)
        # 1. Courtyard numbers (9号院 vs 5号院)
        court_conflict = (sem_a["court_no"] is not None and sem_b["court_no"] is not None and sem_a["court_no"] != sem_b["court_no"])
        # 2. Door/House numbers (25号 vs 23号)
        house_conflict = (sem_a["house_no"] is not None and sem_b["house_no"] is not None and sem_a["house_no"] != sem_b["house_no"])
        # 3. Cross House vs Court (e.g. 25号 vs 23号院)
        # 北京门牌规则: 甲2号/乙2号是插号，与2号是不同门牌。前缀字母必须参与比较。
        def _num_key(tok: str):
            m = re.match(r"([甲乙丙丁]?)(\d+)", tok)
            return (m.group(1), m.group(2)) if m else (None, None)

        cross_num_conflict = False
        if sem_a["house_no"] and sem_b["court_no"]:
            cross_num_conflict = _num_key(sem_a["house_no"]) != _num_key(sem_b["court_no"])
        elif sem_b["house_no"] and sem_a["court_no"]:
            cross_num_conflict = _num_key(sem_b["house_no"]) != _num_key(sem_a["court_no"])

        phase_conflict = (sem_a["phase"] is not None and sem_b["phase"] is not None and sem_a["phase"] != sem_b["phase"])
        subarea_conflict = (sem_a["subarea"] is not None and sem_b["subarea"] is not None and sem_a["subarea"] != sem_b["subarea"])

        has_number_or_sub_conflict = (court_conflict or house_conflict or cross_num_conflict or phase_conflict or subarea_conflict)

        # Hierarchy Flags
        one_has_phase_one_not = ((sem_a["phase"] is not None and sem_b["phase"] is None) or (sem_a["phase"] is None and sem_b["phase"] is not None))
        one_has_sub_one_not = ((sem_a["subarea"] is not None and sem_b["subarea"] is None) or (sem_a["subarea"] is None and sem_b["subarea"] is not None))
        is_hierarchical_phase = (base_exact or base_sim >= 0.85) and (one_has_phase_one_not or one_has_sub_one_not)

        # === Component-Aware Attribute Similarity (DeepMatcher / Magellan) ===
        # Decompose each name into typed attributes and compare with the
        # type-appropriate operator. Numeric/ordinal discriminators are compared
        # with EXACT-MATCH, so embedding blindness to numeric suffixes is
        # impossible here. This replaces the ad-hoc court/house/phase/subarea
        # checks with a single principled conflict signal.
        comp_a = extract_components(rec_a.name_raw)
        comp_b = extract_components(rec_b.name_raw)
        comp_sim = component_similarity(comp_a, comp_b)
        comp_conflicts: List[str] = [t.value for t in comp_sim.conflicts]
        comp_conflict_type: Optional[str] = comp_conflicts[0] if comp_conflicts else None
        comp_base_sim = float(comp_sim.base_sim)
        # The sibling relation to emit if a conflict exists (driven by schema,
        # not by hand-written per-type rules).
        comp_sibling_rel = sibling_relation_for(comp_sim.conflicts[0]) if comp_conflicts else None

        # Spatial Metrics
        dist_m = _geo_distance_meters(coords_a, coords_b)
        iou = 0.0
        intersection_over_min = 0.0
        if geom_a and geom_b and not geom_a.is_empty and not geom_b.is_empty:
            try:
                area_a = geom_a.area
                area_b = geom_b.area
                if area_a > 0 and area_b > 0:
                    inter = geom_a.intersection(geom_b).area
                    union = geom_a.union(geom_b).area
                    iou = inter / union if union > 0 else 0.0
                    intersection_over_min = inter / min(area_a, area_b)
            except Exception:
                pass

        district_match = (rec_a.district_raw == rec_b.district_raw) if (rec_a.district_raw and rec_b.district_raw) else True

        return {
            "bge_sim": float(bge_sim),
            "exact_name_match": exact_name_match,
            "name_sim": float(name_sim),
            "base_exact": bool(base_exact),
            "base_sim": float(base_sim),
            "sem_a": sem_a,
            "sem_b": sem_b,
            "court_conflict": bool(court_conflict),
            "house_conflict": bool(house_conflict),
            "cross_num_conflict": bool(cross_num_conflict),
            "phase_conflict": bool(phase_conflict),
            "subarea_conflict": bool(subarea_conflict),
            "has_number_or_sub_conflict": bool(has_number_or_sub_conflict),
            "is_hierarchical_phase": bool(is_hierarchical_phase),
            "comp_conflicts": comp_conflicts,
            "comp_conflict_type": comp_conflict_type,
            "comp_sibling_rel": comp_sibling_rel,
            "comp_base_sim": comp_base_sim,
            "centroid_dist_meters": float(dist_m),
            "iou": float(iou),
            "intersection_over_min": float(intersection_over_min),
            "district_match": bool(district_match),
        }
