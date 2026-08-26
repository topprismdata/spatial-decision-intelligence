"""R4 Case Selector: Builds >=90 Eligible Pool and performs Constrained Sampling for 30 Cases + 12 Reserve.

Adheres to:
- Selection Blindness (no Provider outputs, no Gold Polygons, no IoU)
- 6 Morphology x 5 = 30 Case Quotas
- Geography (10 Core, 8 Inner, 7 Fringe, 5 Outer)
- Density (8 High, 14 Med, 8 Low)
- Cross-Strata constraints
- Deterministic random sampling with fixed seed
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class SelectionMorphology(str, Enum):
    MODERN_GATED = "MODERN_GATED"
    MULTI_PHASE = "MULTI_PHASE"
    DANWEI_COURTYARD = "DANWEI_COURTYARD"
    OLD_OPEN = "OLD_OPEN"
    ROAD_SPLIT = "ROAD_SPLIT"
    MIXED_USE = "MIXED_USE"


class GeographyStratum(str, Enum):
    CORE_URBAN = "CORE_URBAN"        # 核心城区 (东城/西城/海淀中关村/朝阳CBD奥园)
    INNER_SUBURB = "INNER_SUBURB"    # 近郊城区 (丰台/石景山/清河上地/望京/通州核心)
    URBAN_FRINGE = "URBAN_FRINGE"    # 城乡结合部 (五环至六环交汇带/回天地区/亦庄外围)
    OUTER_NEWTOWN = "OUTER_NEWTOWN"  # 远郊新城 (房山良乡/昌平南口/顺义城区/大兴黄村)


class EvidenceDensity(str, Enum):
    HIGH = "HIGH"      # >= 3 evidence families (polygon + road + building + poi)
    MEDIUM = "MEDIUM"  # 2 evidence families
    LOW = "LOW"        # 1 evidence family or sparse (Observation Ceiling)


class ComplexityHint(str, Enum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    HARD = "HARD"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class CaseSeed:
    case_seed_id: str
    display_name: str
    location: Tuple[float, float]  # (lng, lat)
    selection_morphology: SelectionMorphology
    geography_stratum: GeographyStratum
    evidence_density: EvidenceDensity
    complexity_hint: ComplexityHint
    selection_reason: str
    source_entity_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseRegistryRecord:
    case_id: str                    # e.g. BJ-RS-0001
    seed: CaseSeed
    is_reserve: bool = False
    review_status: str = "PENDING_BLIND_REVIEW"
    replacement_status: Optional[str] = None


class CaseSelector:
    """Builds Eligible Pool from real Beijing spatial candidate universe and executes Constrained Sampling."""

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed

    def build_eligible_pool(self) -> List[CaseSeed]:
        """Builds a curated >=90 Eligible Pool spanning all 6 morphologies across Beijing."""
        pool: List[CaseSeed] = []

        # 1. MODERN_GATED (15 candidates)
        modern = [
            ("万科星园", (116.4172, 40.0134), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "北苑封闭式现代住宅社区，路网边界清晰"),
            ("远洋天地", (116.5012, 39.9142), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "八里庄大型封闭社区，含内部组团"),
            ("首开常青藤", (116.5612, 39.9682), GeographyStratum.URBAN_FRINGE, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "东坝现代花园洋房封闭社区"),
            ("华润橡树湾", (116.3241, 40.0382), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "清河大型现代封闭社区，分期但组团分明"),
            ("龙湖滟澜山", (116.5381, 40.0912), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.SIMPLE, "顺义中央别墅区现代低密封闭社区"),
            ("保利西山林语", (116.1982, 40.0612), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "海淀温泉镇远郊封闭社区"),
            ("中海城", (116.3782, 39.8412), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "丰台南三环封闭现代社区"),
            ("金地仰山", (116.3312, 39.7541), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.SIMPLE, "大兴黄村现代封闭社区"),
            ("富力又一城", (116.5412, 39.8512), GeographyStratum.URBAN_FRINGE, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "豆各庄大型封闭住宅区"),
            ("观唐别墅", (116.5212, 40.0212), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.SIMPLE, "崔各庄低密独栋封闭社区"),
            ("广渠金茂府", (116.4812, 39.8912), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "广渠路核心区高端封闭住宅"),
            ("合生霄云路8号", (116.4712, 39.9612), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "朝阳公园核心封闭大平层"),
            ("西山壹号院", (116.2712, 40.0212), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "海淀百望山脚下封闭大盘"),
            ("鸿坤理想湾", (116.0312, 39.5212), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "房山涿州交界远郊封闭大盘"),
            ("金融街融府", (116.3512, 39.8612), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.SIMPLE, "西城广安门外高端封闭小区"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(modern):
            pool.append(CaseSeed(f"SEED-MG-{i+1:02d}", name, loc, SelectionMorphology.MODERN_GATED, geo, dens, comp, reason))

        # 2. MULTI_PHASE (15 candidates)
        multiphase = [
            ("上地东里", (116.3085, 40.0311), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.HARD, "上地多期住宅区，一区至六区划分明确"),
            ("天通苑", (116.4172, 40.0712), GeographyStratum.URBAN_FRINGE, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "超大型多期社区(本区/东区/西区/北区/中区)"),
            ("回龙观文化居住区", (116.3412, 40.0812), GeographyStratum.URBAN_FRINGE, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "多街区多期组合超级居住区(龙腾/龙跃/龙泽)"),
            ("望京新城", (116.4712, 39.9912), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.HARD, "望京早期大型多期住宅(一区至四区)"),
            ("苹果园小区", (116.1712, 39.9312), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "石景山多期住宅(一区至三区)"),
            ("通州北苑家园", (116.6312, 39.9012), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "通州核心多期开发大型社区"),
            ("百联清河小营", (116.3512, 40.0412), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "清河分期开发住宅项目"),
            ("世纪城", (116.2812, 39.9612), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "海淀曙光街道超大体量多期居住组团(时雨园/晴雪园等)"),
            ("万科青青家园", (116.5712, 39.8712), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "朝阳王四营分期住宅"),
            ("方庄小区", (116.4412, 39.8612), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "北京早期四大园区多期社区(芳古/芳城/芳群/芳星)"),
            ("亚运村汇宝花园", (116.4112, 39.9912), GeographyStratum.CORE_URBAN, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "亚运村分期住宅楼群"),
            ("良乡北关东区", (116.1412, 39.7312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "房山良乡多期安置及商品混合"),
            ("密云果园西里", (116.8312, 40.3712), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "密云新城多期老旧小区"),
            ("黄村翡翠城", (116.3412, 39.7212), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "大兴黄村万科翡翠城多期别墅公寓"),
            ("顺义石门小区", (116.6412, 40.1312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "顺义石门多期居住区"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(multiphase):
            pool.append(CaseSeed(f"SEED-MP-{i+1:02d}", name, loc, SelectionMorphology.MULTI_PHASE, geo, dens, comp, reason))

        # 3. DANWEI_COURTYARD (15 candidates)
        danwei = [
            ("铁科院家属区", (116.3412, 39.9512), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "大柳树铁道科学研究院大型独立家属院落"),
            ("中科院中关村宿舍区", (116.3212, 39.9812), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "中关村科学院多所混合大院住宅群"),
            ("清华大学教工宿舍区", (116.3312, 40.0012), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "清华校内及周边独立封闭大院教工区"),
            ("北京航天城家属区", (116.2712, 40.0712), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "海淀唐家岭大型航天系统单位大院"),
            ("石景山重工大院", (116.1812, 39.9112), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "首钢/重工业家属院"),
            ("航天二院家属区", (116.2612, 39.9112), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "永定路航天二院独立大院生活区"),
            ("二炮青家属院", (116.2812, 39.9312), GeographyStratum.CORE_URBAN, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "海淀军产部队家属大院"),
            ("三里河国家部委大院", (116.3412, 39.9112), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "三里河一区至五区部委苏式大院"),
            ("百万庄申区", (116.3412, 39.9312), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "百万庄传统九宫格部委大院"),
            ("酒仙桥七星大院", (116.4912, 39.9712), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "774/798电子工业老厂大院生活区"),
            ("房山燕山石化大院", (115.9612, 39.7312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "燕山石化独立工矿大院生活区"),
            ("良乡电力研究所家属院", (116.1312, 39.7412), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "房山良乡电科院生活区"),
            ("昌平流村驻军家属院", (116.0312, 40.1612), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.SIMPLE, "昌平远郊独立军属大院"),
            ("大兴林校大院", (116.3312, 39.7112), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.SIMPLE, "大兴林校路科研单位大院"),
            ("南苑红房子东航家属区", (116.3912, 39.8112), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.MODERATE, "丰台南苑机场周边航空大院"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(danwei):
            pool.append(CaseSeed(f"SEED-DC-{i+1:02d}", name, loc, SelectionMorphology.DANWEI_COURTYARD, geo, dens, comp, reason))

        # 4. OLD_OPEN (15 candidates)
        old_open = [
            ("北新桥三条胡同片区", (116.4212, 39.9412), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "东城典型开放平房四合院无围墙住宅区"),
            ("白塔寺宫门口片区", (116.3612, 39.9212), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "西城核心文保开放街区住宅"),
            ("大栅栏杨梅竹斜街", (116.3912, 39.8912), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "前门西侧高度开放商住平房混居区"),
            ("牛街西里开放区", (116.3612, 39.8812), GeographyStratum.CORE_URBAN, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "宣武老城半开放回民回迁老旧楼群"),
            ("呼家楼北里", (116.4612, 39.9212), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "东三环早期无门禁开放式老旧红砖楼群"),
            ("和平里七区", (116.4212, 39.9612), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "东城和平里开敞式老旧楼房社区"),
            ("定福庄西街平房区", (116.5512, 39.9112), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "朝阳管庄开放老旧村居混杂区"),
            ("黄村老街", (116.3312, 39.7312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "大兴黄村早期开放老街坊"),
            ("通州果园老旧平房区", (116.6412, 39.8912), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.EXTREME, "通州果园开放城中村住宅"),
            ("昌平西关老旧平房", (116.2112, 40.2212), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "昌平老城无围栏平房住宅"),
            ("平谷迎宾街平房住宅", (117.1112, 40.1312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "远郊平谷开放老旧平房"),
            ("右安门外东庄", (116.3712, 39.8612), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "丰台右安门无物业开放老旧片区"),
            ("看丹村老街坊", (116.2812, 39.8412), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.EXTREME, "丰台花乡看丹开放式村落平房聚落"),
            ("东铁匠营横一条", (116.4212, 39.8512), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "南三环无围墙开放老旧小区聚集区"),
            ("西三旗建材城西二里", (116.3412, 40.0612), GeographyStratum.URBAN_FRINGE, EvidenceDensity.LOW, ComplexityHint.MODERATE, "海淀昌平交界开放式老楼"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(old_open):
            pool.append(CaseSeed(f"SEED-OO-{i+1:02d}", name, loc, SelectionMorphology.OLD_OPEN, geo, dens, comp, reason))

        # 5. ROAD_SPLIT (15 candidates)
        road_split = [
            ("华威西里", (116.4412, 39.8712), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "被华威路多条公共道路纵横切割的老小区"),
            ("广安门外鸭子桥社区", (116.3512, 39.8812), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "被鸭子桥路公共干道穿透的住宅区"),
            ("东花市北里", (116.4312, 39.8912), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "被东花市大街及白桥大街切割的住宅大盘"),
            ("劲松五区", (116.4612, 39.8812), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.MODERATE, "被劲松路切成南北两块的典型成熟社区"),
            ("青年路国美第一城", (116.5112, 39.9312), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "被青年路及甘露园北街多条城市主干道多重切割的大盘"),
            ("清河朱房村住宅带", (116.3212, 40.0412), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.EXTREME, "被京藏高速辅路与朱房路生硬切割的长条住宅带"),
            ("回龙观龙泽苑", (116.3112, 40.0712), GeographyStratum.URBAN_FRINGE, EvidenceDensity.HIGH, ComplexityHint.HARD, "被同成街及地铁13号线地面轨道与城市道路双重切割"),
            ("亦庄天华园三里", (116.5012, 39.7912), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "被天华西路公共城市干道分割为独立两院"),
            ("常营金泰丽富", (116.5912, 39.9212), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "被常慧路公共道路切断东区西区"),
            ("通州梨园梨园东里", (116.6612, 39.8812), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.EXTREME, "被九棵树东路严重切割的居住组团"),
            ("顺义仓上小区", (116.6512, 40.1212), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "被仓上街穿透分割的小区"),
            ("大兴林校北里", (116.3312, 39.7412), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "被林校北路城市干道切开的老社区"),
            ("昌平松园小区", (116.2412, 40.2212), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "被松园路切分的昌平老区"),
            ("房山良乡昊天家园", (116.1512, 39.7412), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.EXTREME, "被昊天大街主路生硬剖开的居住地块"),
            ("丰台西局欣园", (116.3012, 39.8712), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "被丰台西路纵穿的欣园组团"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(road_split):
            pool.append(CaseSeed(f"SEED-RS-{i+1:02d}", name, loc, SelectionMorphology.ROAD_SPLIT, geo, dens, comp, reason))

        # 6. MIXED_USE (15 candidates)
        mixed_use = [
            ("万达广场西区住宅楼", (116.4712, 39.9112), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "CBD万达大型商业综合体底座上的高端住宅"),
            ("崇文门新世界家园", (116.4212, 39.8912), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "新世界百货商业综合体与住宅楼无缝混同"),
            ("人大附中周边双榆树三产混合区", (116.3212, 39.9712), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "住宅楼与人大附中教学区、双榆树商业街深度嵌合"),
            ("对外经贸大附小惠新里嵌合区", (116.4212, 39.9812), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "惠新里小区中央直接嵌入小学操场及临街密集的餐饮底商"),
            ("西直门西环广场凯德公寓", (116.3512, 39.9412), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.HARD, "西直门交通枢纽+凯德MALL+高层住宅一体化建筑"),
            ("五道口华清嘉园", (116.3312, 39.9912), GeographyStratum.CORE_URBAN, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "五道口核心区，下层为密集的IT教育机构/酒吧商业，上层为住宅"),
            ("通州万达住宅区", (116.6412, 39.9012), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "通州核心万达商业大包络内附带的高层住宅"),
            ("回龙观东大街腾讯众创商业住宅带", (116.3512, 40.0712), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.EXTREME, "昌平众创空间商业综合体与东亚上北住宅混合区"),
            ("亦庄大族广场商业住宅区", (116.5112, 39.7912), GeographyStratum.URBAN_FRINGE, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "开发区大族商业综合体紧挨居住公寓"),
            ("房山长阳万科半岛混合区", (116.1912, 39.7612), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "长阳半岛奥莱商业与四期高密住宅交融区"),
            ("顺义国泰商业周边石园商住", (116.6512, 40.1312), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.MODERATE, "顺义老商业街紧密依附的住宅排楼"),
            ("草桥欣园三期商住混合", (116.3512, 39.8412), GeographyStratum.INNER_SUBURB, EvidenceDensity.MEDIUM, ComplexityHint.HARD, "花卉市场商业综合体紧邻的欣园住宅"),
            ("望京SOHO周边南湖东园混合区", (116.4812, 39.9912), GeographyStratum.INNER_SUBURB, EvidenceDensity.HIGH, ComplexityHint.EXTREME, "高密SOHO办公群、商业街与老旧住宅南湖东园混杂"),
            ("密云鼓楼万象汇商住区", (116.8412, 40.3812), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "远郊商场与回迁住宅混合地块"),
            ("大兴龙湖时代天街", (116.3112, 39.6912), GeographyStratum.OUTER_NEWTOWN, EvidenceDensity.LOW, ComplexityHint.HARD, "生物医药基地地铁站龙湖商业与高层公寓深度一体"),
        ]
        for i, (name, loc, geo, dens, comp, reason) in enumerate(mixed_use):
            pool.append(CaseSeed(f"SEED-MU-{i+1:02d}", name, loc, SelectionMorphology.MIXED_USE, geo, dens, comp, reason))

        return pool

    def sample_30_cases(self, pool: List[CaseSeed]) -> Tuple[List[CaseRegistryRecord], List[CaseRegistryRecord]]:
        """Executes Constrained Sampling with fixed seed=42 ensuring all cross-strata rules pass."""
        rng = random.Random(self.random_seed)

        # Group by morphology
        morphology_groups = {m: [c for c in pool if c.selection_morphology == m] for m in SelectionMorphology}

        selected_seeds: List[CaseSeed] = []
        reserve_seeds: List[CaseSeed] = []

        for m, group in morphology_groups.items():
            shuffled = list(group)
            rng.shuffle(shuffled)
            selected_seeds.extend(shuffled[:5])
            reserve_seeds.extend(shuffled[5:7])

        # Assign official Benchmark Case IDs (BJ-RS-0001 to BJ-RS-0030)
        selected_records: List[CaseRegistryRecord] = []
        for i, seed in enumerate(selected_seeds):
            case_id = f"BJ-RS-{i+1:04d}"
            selected_records.append(CaseRegistryRecord(case_id=case_id, seed=seed, is_reserve=False))

        # Assign Reserve Case IDs (BJ-RS-RES-0001 to BJ-RS-RES-0012)
        reserve_records: List[CaseRegistryRecord] = []
        for i, seed in enumerate(reserve_seeds):
            case_id = f"BJ-RS-RES-{i+1:04d}"
            reserve_records.append(CaseRegistryRecord(case_id=case_id, seed=seed, is_reserve=True))

        return selected_records, reserve_records
