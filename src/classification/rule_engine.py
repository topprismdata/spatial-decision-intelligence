"""R15 框架升级: 数据驱动的版本化规则库.

设计原则 (2026-08-27 用户要求): 手工修单个地块不能防止下一个"体育公园".
新增证据 = 新增一行 CSV 数据, 不是改代码. 规则按 priority 排序执行,
evidence 引用 rule_id 可追溯. 规则文件带 version 字段头注释即变更日志.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


@dataclass(frozen=True)
class NameRule:
    rule_id: str
    priority: int
    scope: str             # "landuse" | "poi_a" | "any"
    fclass_pattern: str    # 空=任意; 否则正则匹配 osm_fclass
    name_pattern: str
    gb_code: str
    note: str = ""


def load_rules(csv_path) -> list[NameRule]:
    rules = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rules.append(NameRule(
                rule_id=row["rule_id"], priority=int(row["priority"]),
                scope=row["scope"],
                fclass_pattern=row.get("fclass_pattern", "") or "",
                name_pattern=row["name_pattern"], gb_code=row["gb_code"],
                note=row.get("note", "") or ""))
    rules.sort(key=lambda r: r.priority)
    return rules


def rule_applies(rule: NameRule, scope: str, fclass: str, name: str) -> bool:
    if rule.scope not in ("any", scope):
        return False
    if rule.fclass_pattern and not re.search(rule.fclass_pattern, fclass or ""):
        return False
    return bool(re.search(rule.name_pattern, name or ""))


def first_matching_rule(rules, scope, fclass, name):
    for rule in rules:
        if rule_applies(rule, scope, fclass, name):
            return rule
    return None
