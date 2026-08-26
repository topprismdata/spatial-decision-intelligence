"""P0-10 / v1.0 30-Case Data Reality Benchmark suite."""

from src.benchmark.case import (
    BenchmarkCase,
    CaseCategory,
    CaseData,
    CaseAnswers,
    ComplexityLevel,
    GeographyRegion,
    EvidenceDensity,
    create_30_case_templates,
)
from src.benchmark.experiment import (
    ExperimentID,
    ExperimentResult,
    CategoryBreakdown,
    AccuracyCoveragePoint,
    AccuracyCoverageCurve,
    SourceComplementarityEntry,
    SourceComplementarityMatrix,
    FailureCode,
    FailureRecord,
    FailureReport,
    FAILURE_DESCRIPTIONS,
)
from src.benchmark.report import (
    BenchmarkReport,
    TrustQualityMetrics,
    aggregate_category_breakdown,
    generate_empty_report,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "CaseCategory",
    "CaseData",
    "CaseAnswers",
    "CategoryBreakdown",
    "ComplexityLevel",
    "GeographyRegion",
    "EvidenceDensity",
    "ExperimentID",
    "ExperimentResult",
    "AccuracyCoveragePoint",
    "AccuracyCoverageCurve",
    "SourceComplementarityEntry",
    "SourceComplementarityMatrix",
    "FailureCode",
    "FailureRecord",
    "FailureReport",
    "FAILURE_DESCRIPTIONS",
    "TrustQualityMetrics",
    "aggregate_category_breakdown",
    "create_30_case_templates",
    "generate_empty_report",
]