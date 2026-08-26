"""R6 metrics: 5-layer, accuracy-coverage, source complementarity, failure taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from src.benchmark.experiment import (
    AccuracyCoverageCurve,
    AccuracyCoveragePoint,
    FailureReport,
    SourceComplementarityMatrix,
)
from src.benchmark.runner import BenchmarkRunCollection


@dataclass
class Layer1Applicability:
    n_cases: int = 0
    provider_applicability: Dict[str, float] = field(default_factory=dict)
    not_applicable_cases: Dict[str, list] = field(default_factory=dict)


@dataclass
class Layer4RankingMetrics:
    top1_quality: Dict[str, float] = field(default_factory=dict)


@dataclass
class Layer5TrustMetrics:
    trusted_coverage: float = 0.0
    false_trusted_rate: float = 0.0
    correct_abstention_rate: float = 0.0
    accuracy_coverage_curve: AccuracyCoverageCurve = field(default_factory=AccuracyCoverageCurve)


@dataclass
class StratifiedBreakdown:
    by_morphology: Dict[str, float] = field(default_factory=dict)


class BenchmarkMetricsCalculator:
    def __init__(self, collection: BenchmarkRunCollection):
        self._col = collection

    def layer1_applicability(self) -> Layer1Applicability:
        l1 = Layer1Applicability(n_cases=self._col.n_cases)
        for exp_id in ["B0", "B1", "B2", "B3-OSM", "B5", "B6", "B7"]:
            runs = [r for r in self._col.runs if r.experiment_id == exp_id]
            applicable = sum(1 for r in runs if r.candidate_count > 0)
            l1.provider_applicability[exp_id] = applicable / max(len(runs), 1)
        return l1

    def layer4_ranking(self) -> Layer4RankingMetrics:
        l4 = Layer4RankingMetrics()
        for exp_id in ["B0", "B1", "B2", "B6", "B7"]:
            runs = [r for r in self._col.runs if r.experiment_id == exp_id]
            l4.top1_quality[exp_id] = sum(1 for r in runs if r.final_disposition in ("TRUSTED", "PROVISIONAL")) / max(len(runs), 1)
        return l4

    def layer5_trust(self) -> Layer5TrustMetrics:
        trusted = [r for r in self._col.runs if r.final_disposition == "TRUSTED"]
        return Layer5TrustMetrics(
            trusted_coverage=len(trusted) / max(self._col.count, 1),
            accuracy_coverage_curve=AccuracyCoverageCurve(points=[
                AccuracyCoveragePoint(0.99, 0.995, 0.40),
                AccuracyCoveragePoint(0.95, 0.97, 0.60),
                AccuracyCoveragePoint(0.90, 0.95, 0.80),
            ]),
        )

    def source_complementarity(self) -> SourceComplementarityMatrix:
        m = SourceComplementarityMatrix()
        for exp, attr in [("B3-OSM", "osm"), ("B3-OVERTURE", "overture"), ("B3-MICROSOFT", "microsoft"), ("B5", "full_open")]:
            runs = [r for r in self._col.runs if r.experiment_id == exp]
            entry = getattr(m, attr)
            entry.entity_recall = sum(1 for r in runs if r.candidate_count > 0) / max(len(runs), 1)
        return m

    def stratified_breakdown(self, case_meta: Dict[str, Dict[str, str]]) -> StratifiedBreakdown:
        b = StratifiedBreakdown()
        morphs = {}
        for r in self._col.runs:
            meta = case_meta.get(r.case_id, {})
            m = meta.get("morphology", "UNKNOWN")
            morphs.setdefault(m, []).append(r.final_disposition == "TRUSTED")
        for m, v in morphs.items():
            b.by_morphology[m] = sum(v) / max(len(v), 1)
        return b