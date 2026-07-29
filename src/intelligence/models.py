"""Immutable models for the first descriptive seismic-intelligence layer."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ActivityTrend(StrEnum):
    """Direction of recent, observed activity-index movement."""

    INCREASING = "increasing"
    STABLE = "stable"
    DECREASING = "decreasing"
    INSUFFICIENT_DATA = "insufficient_data"


class ConfidenceLevel(StrEnum):
    """Evidence available for a descriptive result (not forecast confidence)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric, not boolean.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


@dataclass(frozen=True, slots=True)
class IntelligenceConfiguration:
    """Thresholds used to summarize an Observatory time series."""

    activity_window: int = 7
    trend_window: int = 7
    stable_change_threshold: float = 5.0
    moderate_confidence_periods: int = 7
    high_confidence_periods: int = 30
    high_completeness_threshold: float = 0.9

    def __post_init__(self) -> None:
        for name in (
            "activity_window",
            "trend_window",
            "moderate_confidence_periods",
            "high_confidence_periods",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer, not boolean.")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero.")
        if self.high_confidence_periods <= self.moderate_confidence_periods:
            raise ValueError(
                "high_confidence_periods must exceed moderate_confidence_periods."
            )
        for name in ("stable_change_threshold", "high_completeness_threshold"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if not 0 <= self.stable_change_threshold <= 100:
            raise ValueError("stable_change_threshold must be between 0 and 100.")
        if not 0 <= self.high_completeness_threshold <= 1:
            raise ValueError("high_completeness_threshold must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class SeismicIntelligence:
    """A deterministic, nonpredictive summary of observed anomaly scores."""

    activity_index: float | None
    activity_index_periods: int
    trend: ActivityTrend
    trend_change: float | None
    confidence: ConfidenceLevel
    confidence_score: float
    available_period_count: int
    unavailable_period_count: int
    summary: str
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_index": self.activity_index,
            "activity_index_periods": self.activity_index_periods,
            "trend": self.trend.value,
            "trend_change": self.trend_change,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "available_period_count": self.available_period_count,
            "unavailable_period_count": self.unavailable_period_count,
            "summary": self.summary,
            "disclaimer": self.disclaimer,
        }
