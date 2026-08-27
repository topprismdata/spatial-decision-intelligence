"""R14-P5 Amap Gazetteer: administrative containment checks for hierarchy resolution.

Hardens R12 EntityHierarchyResolver: same-named phases ("N区") that appear in
multiple estates get disambiguated by their Amap administrative chain
(pname/cityname/adname/business_area), turning name-only heuristics into
gazetteer-backed containment assertions.

Data source: offline cache built from outputs/beijing_batch/amap_name_matches.csv
(grid_key field) plus optional direct POI lookups. The gazetteer never issues
network calls at validation time.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GazetteerRecord:
    """One POI's full administrative chain (Amap regeo fields)."""

    name: str
    province: str = ""
    city: str = ""
    district: str = ""
    business_area: str = ""


class AmapGazetteer:
    """Offline lookup: name → set of administrative chains."""

    # Phase indicator used to split "龙腾苑二区" → base "龙腾苑" + phase "二区"
    _PHASE = re.compile(r"([一二三四五六七八九十\d]+期|[A-Z一二三四五六七八九十\d]+区)")

    def __init__(self, records: tuple[GazetteerRecord, ...] = ()):
        self._by_name: dict[str, list[GazetteerRecord]] = {}
        for r in records:
            self._by_name.setdefault(r.name, []).append(r)

    @classmethod
    def from_match_csv(cls, csv_path: str) -> "AmapGazetteer":
        records: list[GazetteerRecord] = []
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = (row.get("amap_name") or "").strip()
                    if not name:
                        continue
                    addr = row.get("amap_address") or ""
                    records.append(GazetteerRecord(
                        name=name,
                        district=addr,
                    ))
        except FileNotFoundError:
            pass
        return cls(tuple(records))

    def chains_for(self, name: str) -> list[GazetteerRecord]:
        return self._by_name.get(name.strip(), [])

    def same_district(self, name_a: str, name_b: str) -> Optional[bool]:
        """True/False if both names resolve to single comparable districts;
        None when either is unknown or ambiguous in the gazetteer."""
        ra = self.chains_for(name_a)
        rb = self.chains_for(name_b)
        if not ra or not rb:
            return None
        da = {r.district for r in ra if r.district}
        db = {r.district for r in rb if r.district}
        if not da or not db:
            return None
        return bool(da & db)

    def split_phase(self, name: str) -> tuple[str, str]:
        """Return (base_name, phase_token); phase is '' when absent."""
        m = self._PHASE.search(name)
        if not m:
            return name, ""
        return name[: m.start()], m.group(0)

    def resolves_same_estate(self, name_a: str, name_b: str) -> Optional[bool]:
        """Gazetteer-aware estate-membership check for two sibling-candidate phases.

        Logic: both must share the same stripped base name AND land in the
        same district. Returns None (abstain) whenever evidence is missing —
        callers keep their heuristic path in that case.
        """
        base_a, phase_a = self.split_phase(name_a)
        base_b, phase_b = self.split_phase(name_b)
        if not phase_a or not phase_b:
            return None
        if base_a != base_b:
            return False
        same = self.same_district(name_a, name_b)
        return True if same else None


def gazetteer_from_batch_outputs(match_csv: str = "outputs/beijing_batch/amap_name_matches.csv",
                                 ) -> AmapGazetteer:
    """Convenience loader wired to the 2026-08-27 Beijing batch artifacts."""
    return AmapGazetteer.from_match_csv(match_csv)
