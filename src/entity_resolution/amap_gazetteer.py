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

    # Phase indicators: 一期/二期…, 1期/A期, A区/B区, 二区, 北区/南区/东区/西区
    # (cardinal-direction subareas like 建明里-北区 are common in matched POIs)
    _PHASE = re.compile(
        r"([一二三四五六七八九十\d]+期"
        r"|[A-Z一二三四五六七八九十\d]+区"
        r"|[东南西北]区)"
    )

    def __init__(self, records: tuple[GazetteerRecord, ...] = ()):
        self._by_name: dict[str, list[GazetteerRecord]] = {}
        for r in records:
            self._by_name.setdefault(r.name, []).append(r)

    @classmethod
    def from_match_csv(cls, csv_path: str) -> "AmapGazetteer":
        """Load from either the base match CSV (address-as-district, weak)
        or the R14-P5 admin CSV (pname/cityname/adname columns, preferred)."""
        records: list[GazetteerRecord] = []

        def _add(row):
            name = (row.get("amap_name") or "").strip()
            if not name:
                return
            district = (row.get("adname") or "").strip()  # authoritative when present
            if not district:
                addr = row.get("amap_address") or ""
                records.append(GazetteerRecord(name=name, district=addr))
                return
            records.append(GazetteerRecord(
                name=name, province=row.get("pname", ""),
                city=row.get("cityname", ""), district=district,
                business_area=(row.get("business") or "").strip(),
            ))

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    _add(row)
        except FileNotFoundError:
            pass
        return cls(tuple(records))

    def chains_for(self, name: str) -> list[GazetteerRecord]:
        return self._by_name.get(name.strip(), [])

    def same_district(self, name_a: str, name_b: str) -> Optional[bool]:
        """True iff EVERY chain of both names agrees on one district.

        Ambiguous names (multiple district candidates) abstain: intersecting
        district sets would produce false 'same' verdicts for cross-town
        twin estates sharing a name.
        """
        ra = self.chains_for(name_a)
        rb = self.chains_for(name_b)
        if not ra or not rb:
            return None
        da = {r.district for r in ra if r.district}
        db = {r.district for r in rb if r.district}
        if len(da) != 1 or len(db) != 1:
            return None
        return da == db

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


def gazetteer_from_batch_outputs(
    match_csv: str = "outputs/beijing_batch/amap_name_matches.csv",
    admin_csv: str = "outputs/beijing_batch/amap_name_admin.csv",
) -> AmapGazetteer:
    """Convenience loader. Prefers the admin-enriched CSV and falls back
    to the base match CSV for names absent from it."""
    gaz = AmapGazetteer.from_match_csv(admin_csv)
    if len(gaz._by_name) == 0:
        return AmapGazetteer.from_match_csv(match_csv)
    # Merge: add entries only for names not already covered.
    fallback = AmapGazetteer.from_match_csv(match_csv)
    for name, recs in fallback._by_name.items():
        for r in recs:
            if name not in gaz._by_name:
                gaz._by_name[name] = recs
    return gaz
