"""
Component-Aware Attribute Matching for Chinese Residential Entity Resolution.

== Why this module exists (root-cause, not a patch) ==

The previous matcher used a *bi-encoder* (BGE) + cosine similarity as the
match DECISION signal. Per the entity-resolution / retrieval literature
(Ditto, VLDB'21; DeepMatcher, Magellan; cross-encoder surveys), a bi-encoder is
a *recall / blocking* architecture: it irreversibly pools each string into one
fixed-dimensional vector, which **washes out fine-grained numeric / ordinal
tokens**. That is exactly why "东四十条" and "东四十三条" collapsed to nearby
points (BGE sees the shared prefix 东四 and ignores 十条/十三条). Using a
bi-encoder for the *decision* is the architectural mistake.

The field's structural fix (DeepMatcher, Magellan, D-HAT) is **attribute-level
matching**: decompose each entity into a CLOSED SCHEMA of typed attributes,
compare each attribute with the operator appropriate to its type, then fuse
the per-attribute similarities into a decision. Numeric / ordinal
discriminators (号院, 门牌, 期, 分区, 里/条, 街坊, 场, 号楼) are compared with
an **exact-match** operator — they are never embedded, so the blindness
disappears *by construction*.

This module is the attribute-similarity layer. A separate cross-encoder
reranker (Ditto's precision stage) handles the residual *aliasing* cases
(和平西苑 vs 和平街西苑) that need token-level interaction; the two are fused
by the PairScorer.

== Attribute schema (closed, typed) ==
  BASE      : residual free-text after stripping discriminators (e.g. 和平, 东四)
  COURT     : 号院 / 院 number    (9号院, 甲2号院, 5号院, 六院, 七院)
  BUILDING  : 号楼 number        (27号楼, 29号楼)
  HOUSE     : standalone 门牌号   (23号, 甲26号)
  PHASE     : 期数               (一期, 二期)
  SUBAREA   : 方位/字母分区       (南区, 北区, A区, B区, 二区)
  LANE      : 里/条 巷号(后缀)    (二里, 三条, 十条, 十三条)
  BLOCK     : 街坊号(后缀)        (十街坊, 十一街坊)
  YARD      : 场号               (六场, 八场)
  COMM_NUM  : 小区内编号          (103小区, 105小区)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Tuple
from difflib import SequenceMatcher


class DiscriminatorType(str, Enum):
    COURT = "court"
    BUILDING = "building"
    HOUSE = "house"
    PHASE = "phase"
    SUBAREA = "subarea"
    LANE = "lane"
    BLOCK = "block"
    YARD = "yard"
    COMM_NUM = "comm_num"


# Priority order (most specific first). When a pattern matches, its FULL span
# is stripped so the residual BASE is what remains.
_NUM = r"(?:[甲乙丙丁]?\d+|[一二三四五六七八九十百]+)"
_PATTERNS: List[Tuple[DiscriminatorType, str]] = [
    (DiscriminatorType.COURT,    rf"({_NUM})号院"),
    (DiscriminatorType.BUILDING, rf"({_NUM})号楼"),
    (DiscriminatorType.HOUSE,    rf"({_NUM})号(?!院|楼)"),
    (DiscriminatorType.PHASE,    rf"([一二三四五六七八九十百\d]+)期"),
    # SUBAREA: trailing 方位区/字母区/数字区 (prefer last match via logic below)
    (DiscriminatorType.SUBAREA,  r"(?:东|西|南|北|中)(?:区|院)|[A-Za-z]区|[A-Za-z]\d*区|[一二三四五六七八九十百\d]+区"),
    (DiscriminatorType.BLOCK,    rf"({_NUM})街坊$"),
    (DiscriminatorType.LANE,     rf"({_NUM})(?:里|条)$"),
    (DiscriminatorType.YARD,     rf"({_NUM})场(?!景|广|市)"),
    (DiscriminatorType.COMM_NUM, rf"({_NUM})小区$"),
    (DiscriminatorType.COURT,    rf"({_NUM})院(?<![医研])"),
]

# When a discriminator type is present in BOTH records and the values DIFFER,
# the two are independent sibling entities (hard rule; exact-token compare so
# the embedding blindness is impossible). Maps to the sibling relation to emit.
_SIBLING_ON_CONFLICT = {
    DiscriminatorType.COURT:    "SIBLING_COURTYARD",
    DiscriminatorType.HOUSE:    "SIBLING_COURTYARD",
    DiscriminatorType.BUILDING: "SIBLING_COURTYARD",
    DiscriminatorType.PHASE:    "SIBLING_PHASE",
    DiscriminatorType.SUBAREA:  "SIBLING_SUBAREA",
    DiscriminatorType.LANE:     "SIBLING_SUBAREA",
    DiscriminatorType.BLOCK:    "SIBLING_SUBAREA",
    DiscriminatorType.YARD:     "SIBLING_SUBAREA",
    DiscriminatorType.COMM_NUM: "SIBLING_SUBAREA",
}


# ---- Chinese numeral parsing (correct, handles compounds) ----
_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
           '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def _chinese_to_int(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s == '十':
        return 10
    if '百' in s:
        l, r = s.split('百', 1)
        return (_DIGITS.get(l, 1) if l else 1) * 100 + (_chinese_to_int(r) if r else 0)
    if '十' in s:
        l, r = s.split('十', 1)
        return (_DIGITS.get(l, 1) if l else 1) * 10 + (_DIGITS.get(r, 0) if r else 0)
    return _DIGITS.get(s, 0)


_DIRECTIONS = {'东', '西', '南', '北', '中'}


def _normalize_token(token: str) -> str:
    """Canonical comparable form: 甲2→A2, 十三→13, 四十→40, 103→103,
    B区→B, 南区→南, 二区→2.

    甲乙丙丁 (插号) are kept as A/B/C/D letters so 甲2号 != 2号.
    方位字 (东南西北中) and letters are kept verbatim; trailing structural
    chars (区/院/里/条/街坊/小区) are stripped before numeral parsing.
    """
    token = token.strip()
    m = re.match(r"^([甲乙丙丁])(.*)$", token)
    prefix = m.group(1) if m else ""
    rest = m.group(2) if m else token
    rest = re.sub(r"(?:区|院|里|条|街坊|小区)$", "", rest)
    if not rest:
        return prefix
    if rest in _DIRECTIONS:
        return prefix + rest
    if re.match(r"^[A-Za-z]$", rest):
        return prefix + rest.upper()
    return prefix + str(_chinese_to_int(rest))


@dataclass
class EntityComponents:
    """Typed attribute representation of one entity name."""
    base_name: str
    discriminators: Dict[DiscriminatorType, str] = field(default_factory=dict)

    def has(self, k: DiscriminatorType) -> bool:
        return k in self.discriminators


def extract_components(name: str) -> EntityComponents:
    """Parse a Chinese community name into a typed-attribute vector."""
    name = str(name).strip()
    residual = name
    discs: Dict[DiscriminatorType, str] = {}

    for dtype, pat in _PATTERNS:
        matches = list(re.finditer(pat, residual))
        if not matches:
            continue
        m = matches[-1]  # prefer the trailing occurrence (fine-grained subarea)
        value = m.group(1) if dtype != DiscriminatorType.SUBAREA else m.group(0)
        value = _normalize_token(value)
        # For SUBAREA keep the raw token (方位/字母) as-is except normalize digit.
        if dtype == DiscriminatorType.SUBAREA and re.match(r"^[一二三四五六七八九十百\d]+区$", value):
            value = _normalize_token(value)
        discs[dtype] = value
        residual = residual[:m.start()] + residual[m.end():]

    residual = re.sub(r"\(.*?\)|（.*?）", "", residual)
    for city in ["北京市", "北京城区", "北京", "石家庄市", "石家庄"]:
        if residual.startswith(city) and len(residual) - len(city) >= 2:
            residual = residual[len(city):]
            break
    base = residual.strip(" -_#")
    if not base:
        base = name
    return EntityComponents(base_name=base, discriminators=discs)


def _base_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class ComponentSimilarity:
    base_sim: float
    disc_sim: Dict[DiscriminatorType, float] = field(default_factory=dict)
    conflicts: List[DiscriminatorType] = field(default_factory=list)
    matches: List[DiscriminatorType] = field(default_factory=list)


def component_similarity(a: EntityComponents, b: EntityComponents) -> ComponentSimilarity:
    """Per-attribute similarity with type-appropriate operators.

    Discrete/numeric attributes use EXACT-MATCH (1.0 equal, 0.0 differ, 0.5
    one-sided). BASE uses char-level similarity. This is the attribute
    similarity matrix of DeepMatcher / Magellan.
    """
    disc_sim: Dict[DiscriminatorType, float] = {}
    conflicts: List[DiscriminatorType] = []
    matches: List[DiscriminatorType] = []

    all_types = set(a.discriminators) | set(b.discriminators)
    for t in all_types:
        va, vb = a.discriminators.get(t), b.discriminators.get(t)
        if va is not None and vb is not None:
            if va == vb:
                disc_sim[t] = 1.0
                matches.append(t)
            else:
                disc_sim[t] = 0.0
                conflicts.append(t)
        else:
            disc_sim[t] = 0.5

    return ComponentSimilarity(
        base_sim=_base_similarity(a.base_name, b.base_name),
        disc_sim=disc_sim,
        conflicts=conflicts,
        matches=matches,
    )


def sibling_relation_for(conflict: DiscriminatorType) -> str:
    return _SIBLING_ON_CONFLICT.get(conflict, "SIBLING_SUBAREA")
