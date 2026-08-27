"""R15-T1: OSM fclass/amenity → GB50137 九大类 映射与标注器.

分类体系对标市场在售"城市建设用地类型"产品 (Class/ClassCn 四字段 schema):
  R   居住用地      RESIDENTIAL
  B1 商业服务用地   COMMERCIAL_RETAIL     (retail/mall/商业)
  B2 商务办公用地   BUSINESS_OFFICE       (commercial/office)
  M  工业用地       INDUSTRIAL            (industrial/works)
  S  交通枢纽用地   TRANSPORT_HUB         (station/terminal)
  A3 教育科研用地   EDUCATION_RESEARCH    (school/university/college/kindergarten)
  A4 体育文化用地   SPORTS_CULTURE        (stadium/pitch/library/museum/theatre)
  A5 医疗卫生用地   HEALTHCARE            (hospital/clinic)
  G  公园与绿地     PARK_GREEN            (park/forest/grass/meadow/scrub/orchard)

未匹配面 → UNCLASSIFIED (保留, 不臆断).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GBClass:
    code: str          # R / B1 / B2 / M / S / A3 / A4 / A5 / G / U
    name_cn: str       # 中文名
    name_en: str       # 英文 Class 字段值
    color: str         # GB50137 风格渲染色 (#RRGGBB)


GB_CLASSES = {
    "R":  GBClass("R",  "居住用地",     "RESIDENTIAL",      "#FFE97F"),
    "B1": GBClass("B1", "商业服务用地", "COMMERCIAL",       "#E8735C"),
    "B2": GBClass("B2", "商务办公用地", "BUSINESS_OFFICE",  "#D9455F"),
    "M":  GBClass("M",  "工业用地",     "INDUSTRIAL",       "#8A6FDF"),
    "S":  GBClass("S",  "交通枢纽用地", "TRANSPORT_HUB",    "#5CA8D9"),
    "A3": GBClass("A3", "教育科研用地", "EDUCATION",        "#C9955C"),
    "A4": GBClass("A4", "体育文化用地", "SPORTS_CULTURE",   "#E39BA7"),
    "A5": GBClass("A5", "医疗卫生用地", "HEALTHCARE",       "#E08AB8"),
    "G":  GBClass("G",  "公园与绿地",   "PARK_GREEN",       "#7FC97F"),
    "U":  GBClass("U",  "未分类",       "UNCLASSIFIED",     "#CCCCCC"),
}

# ---- landuse fclass → 分类码 ----
LANDUSE_MAP = {
    "residential": "R",
    "retail": "B1",
    "commercial": "B2",
    "industrial": "M",
    "park": "G", "forest": "G", "grass": "G", "meadow": "G",
    "scrub": "G", "orchard": "G", "recreation_ground": "G",
    "village_green": "G", "cemetery": "U",
}

# ---- POI fclass → 分类码 ----
POI_MAP = {
    # A3 教育
    "school": "A3", "kindergarten": "A3", "university": "A3", "college": "A3",
    # A5 医疗
    "hospital": "A5", "clinic": "A5", "dentist": "A5", "doctors": "A5",
    # A4 体育文化
    "stadium": "A4", "pitch": "A4", "track": "A4", "sports_centre": "A4",
    "library": "A4", "museum": "A4", "theatre": "A4", "community_centre": "A4",
    # B1 商业
    "mall": "B1", "supermarket": "B1", "marketplace": "B1",
    "department_store": "B1", "clothes": "B1", "bakery": "B1", "beverages": "B1",
    "beauty_shop": "B1", "furniture_shop": "B1", "computer_shop": "B1",
    "mobile_phone_shop": "B1", "gift_shop": "B1", "travel_agent": "B1",
    "laundry": "B1", "photo_shop": "B1", "kiosk": "B1", "outdoor_shop": "B1",
    "shoes_shop": "B1", "jewelry_shop": "B1", "sports_shop": "B1",
    "stationery": "B1", "bookshop": "B1", "florist": "B1", "hairdresser": "B1",
    "optician": "B1", "chemist": "B1", "toy_shop": "B1", "charity": "B1",
    # B2 办公
    "office": "B2", "company": "B2", "estate_agent": "B2", "insurance": "B2",
    "bank": "B2", "atm": "B2", "post_office": "B2", "courthouse": "B2",
    # S 交通
    "bus_station": "S", "railway_station": "S", "subway_station": "S",
    "airport": "S", "ferry_terminal": "S", "bus_stop": None,
    # A5/其他公共
    "police": "U", "fire_station": "U", "townhall": "U", "government": "U",
    "place_of_worship": "U", "public_building": "U", "hospital_railway": None,
}


def classify_landuse(fclass: str) -> str:
    """landuse fclass → 分类码."""
    return LANDUSE_MAP.get(fclass, "U")


def classify_poi(fclass: str) -> str | None:
    """POI fclass → 分类码; None 表示忽略该要素."""
    v = POI_MAP.get(fclass, None if fclass not in POI_MAP else POI_MAP[fclass])
    return v


def gb_class(code: str) -> GBClass:
    return GB_CLASSES.get(code, GB_CLASSES["U"])
