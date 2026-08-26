"""P1-05 Confidence Calibration: predicted confidence vs actual correctness.

Uses Gold Cases to establish calibration curves.
Not heuristic score tuning — uses empirical calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GoldCase:
    """A single gold-standard case for calibration.

    Gold must not be a single person drawing a polygon (spec section 30).
    """
    case_id: str
    predicted_confidence: float  # 0.0-1.0
    actual_correct: bool  # Was the prediction correct?
    source: str = ""  # Which provider/algorithm produced this


@dataclass
class CalibrationBin:
    """A bin in the reliability diagram."""

    bin_index: int
    confidence_range: tuple[float, float]  # e.g. (0.8, 0.9)
    n_samples: int = 0
    n_correct: int = 0
    avg_confidence: float = 0.0
    accuracy: float = 0.0  # actual correctness in this bin

    @property
    def gap(self) -> float:
        """Calibration gap: |avg_confidence - accuracy|."""
        return abs(self.avg_confidence - self.accuracy)

    @property
    def ece_contribution(self) -> float:
        """Contribution to Expected Calibration Error."""
        return self.gap * (self.n_samples / max(self._total_samples, 1))

    _total_samples: int = 0


@dataclass
class CalibrationReport:
    """Complete calibration analysis.

    Expected Calibration Error (ECE) is the primary metric.
    """

    n_cases: int = 0
    bins: list[CalibrationBin] = field(default_factory=list)
    ece: float = 0.0  # Expected Calibration Error
    mce: float = 0.0  # Maximum Calibration Error
    overall_accuracy: float = 0.0
    overall_avg_confidence: float = 0.0

    def summary(self) -> str:
        lines = [
            f"=== Confidence Calibration Report ===",
            f"  Cases:           {self.n_cases}",
            f"  Overall Accuracy: {self.overall_accuracy:.1%}",
            f"  Avg Confidence:   {self.overall_avg_confidence:.1%}",
            f"  ECE:              {self.ece:.2%}",
            f"  MCE:              {self.mce:.2%}",
            "",
            "  Bins:",
        ]
        for b in self.bins:
            lines.append(
                f"    [{b.confidence_range[0]:.1f}-{b.confidence_range[1]:.1f}): "
                f"n={b.n_samples:3d}, conf={b.avg_confidence:.2f}, "
                f"acc={b.accuracy:.2f}, gap={b.gap:.2f}"
            )
        return "\n".join(lines)


class ConfidenceCalibrator:
    """Calibrates predicted confidence using Gold Cases.

    Uses empirical calibration (not Platt scaling or isotonic regression)
    to establish the true relationship between predicted confidence and accuracy.
    """

    N_BINS = 10

    def __init__(self):
        self._gold_cases: list[GoldCase] = []

    def add_gold_case(self, case: GoldCase) -> None:
        self._gold_cases.append(case)

    def add_cases(self, cases: list[GoldCase]) -> None:
        self._gold_cases.extend(cases)

    @property
    def n_cases(self) -> int:
        return len(self._gold_cases)

    def calibrate(self) -> CalibrationReport:
        """Run calibration analysis on all Gold Cases.

        Returns a CalibrationReport with ECE, MCE, and per-bin breakdown.
        """
        if not self._gold_cases:
            return CalibrationReport()

        # Sort by confidence
        sorted_cases = sorted(self._gold_cases, key=lambda c: c.predicted_confidence)

        # Create bins
        bins = []
        for i in range(self.N_BINS):
            lo = i / self.N_BINS
            hi = (i + 1) / self.N_BINS
            bin_cases = [
                c for c in sorted_cases
                if lo <= c.predicted_confidence < hi
            ]
            if not bin_cases:
                bins.append(CalibrationBin(
                    bin_index=i,
                    confidence_range=(lo, hi),
                    avg_confidence=(lo + hi) / 2,
                ))
                continue

            n_correct = sum(1 for c in bin_cases if c.actual_correct)
            avg_conf = sum(c.predicted_confidence for c in bin_cases) / len(bin_cases)
            accuracy = n_correct / len(bin_cases)

            bins.append(CalibrationBin(
                bin_index=i,
                confidence_range=(lo, hi),
                n_samples=len(bin_cases),
                n_correct=n_correct,
                avg_confidence=avg_conf,
                accuracy=accuracy,
                _total_samples=len(sorted_cases),
            ))

        # Compute ECE and MCE
        ece = sum(b.ece_contribution for b in bins if b.n_samples > 0)
        mce = max((b.gap for b in bins if b.n_samples > 0), default=0.0)

        # Overall metrics
        n_correct = sum(1 for c in self._gold_cases if c.actual_correct)
        overall_accuracy = n_correct / max(len(self._gold_cases), 1)
        overall_avg_confidence = sum(
            c.predicted_confidence for c in self._gold_cases
        ) / max(len(self._gold_cases), 1)

        return CalibrationReport(
            n_cases=len(self._gold_cases),
            bins=bins,
            ece=ece,
            mce=mce,
            overall_accuracy=overall_accuracy,
            overall_avg_confidence=overall_avg_confidence,
        )

    def calibrated_confidence(self, raw_confidence: float) -> float:
        """Map raw predicted confidence to calibrated confidence.

        Uses interpolation from the calibration bins.
        """
        report = self.calibrate()
        if not report.bins:
            return raw_confidence

        for b in report.bins:
            lo, hi = b.confidence_range
            if lo <= raw_confidence < hi:
                if b.n_samples > 0:
                    return b.accuracy
                # No data in this bin — interpolate
                return raw_confidence
        return raw_confidence