"""P0-10 Benchmark report generator.

Produces per-case, per-category, and aggregate reports with
Selective Accuracy, Trusted Coverage, and False Trusted Rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from src.benchmark.case import BenchmarkCase, CaseCategory
from src.benchmark.experiment import (
    CategoryBreakdown,
    ExperimentResult,
    FailureReport,
)


@dataclass
class TrustQualityMetrics:
    """Trust Benchmark metrics (P0-10 spec section 29).

    Selective Accuracy: accuracy on TRUSTED samples only.
    Trusted Coverage: what fraction of cases are TRUSTED.
    False Trusted Rate: TRUSTED but actually wrong.
    Correct Abstention: UNRESOLVED when truly uncertain.
    """

    selective_accuracy: float = 0.0
    trusted_coverage: float = 0.0
    false_trusted_rate: float = 0.0
    correct_abstention_rate: float = 0.0

    def summary(self) -> str:
        return (
            f"Trust Quality:\n"
            f"  Selective Accuracy:     {self.selective_accuracy:.1%}\n"
            f"  Trusted Coverage:       {self.trusted_coverage:.1%}\n"
            f"  False Trusted Rate:     {self.false_trusted_rate:.1%} ⚠️\n"
            f"  Correct Abstention:     {self.correct_abstention_rate:.1%}"
        )


@dataclass
class BenchmarkReport:
    """Complete benchmark report for one experiment.

    Must include per-category breakdown, per-case details,
    failure analysis, and trust metrics.
    """

    experiment_id: str
    experiment_result: ExperimentResult = field(default_factory=ExperimentResult)
    category_breakdown: CategoryBreakdown = field(default_factory=CategoryBreakdown)
    trust_quality: TrustQualityMetrics = field(default_factory=TrustQualityMetrics)
    failure_report: FailureReport = field(default_factory=FailureReport)
    per_case_results: dict[str, bool] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"=== {self.experiment_id} ===",
            f"  Overall Accuracy:        {self.experiment_result.accuracy:.1%}",
            f"  Trusted Coverage:        {self.experiment_result.trusted_coverage:.1%}",
            f"  False Trusted Rate:      {self.experiment_result.false_trusted_rate:.1%}",
            f"  Incremental Data:        {self.experiment_result.incremental_data}",
        ]
        lines.append("")
        lines.append("  Per-Category Breakdown:")
        for cat, acc in self.category_breakdown.to_dict().items():
            lines.append(f"    {cat:20s}: {acc:.1%}")
        lines.append("")
        lines.append(self.trust_quality.summary())
        lines.append("")
        lines.append(self.failure_report.summary())
        return "\n".join(lines)


def generate_empty_report(experiment_id: str) -> BenchmarkReport:
    """Generate an empty report template for an experiment."""
    from src.benchmark.experiment import ExperimentID
    eid = ExperimentID(experiment_id) if experiment_id in [e.value for e in ExperimentID] else None
    return BenchmarkReport(
        experiment_id=experiment_id,
        experiment_result=ExperimentResult(
            experiment_id=eid or ExperimentID.B0,
        ),
    )


def aggregate_category_breakdown(
    cases: Sequence[BenchmarkCase],
    case_results: dict[str, bool],
) -> CategoryBreakdown:
    """Compute accuracy per category."""
    by_category: dict[CaseCategory, list[bool]] = {}
    for c in cases:
        by_category.setdefault(c.category, [])
        by_category[c.category].append(case_results.get(c.case_id, False))

    return CategoryBreakdown(
        modern_gated=_mean(by_category.get(CaseCategory.MODERN_GATED, [])),
        multi_phase=_mean(by_category.get(CaseCategory.MULTI_PHASE, [])),
        danwei_courtyard=_mean(by_category.get(CaseCategory.DANWEI_COURTYARD, [])),
        old_open=_mean(by_category.get(CaseCategory.OLD_OPEN, [])),
        road_split=_mean(by_category.get(CaseCategory.ROAD_SPLIT, [])),
        mixed_use=_mean(by_category.get(CaseCategory.MIXED_USE, [])),
    )


def _mean(values: list[bool]) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v) / len(values)