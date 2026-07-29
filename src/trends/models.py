"""Immutable models for deterministic temporal anomaly trend analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class TrendDirection(StrEnum):
    RAPIDLY_DECREASING = "rapidly_decreasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    INCREASING = "increasing"
    RAPIDLY_INCREASING = "rapidly_increasing"
    INSUFFICIENT_DATA = "insufficient_data"


class TrendStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    INSUFFICIENT_DATA = "insufficient_data"


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric, not boolean.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


@dataclass(frozen=True, slots=True)
class TrendConfiguration:
    short_window: int = 7
    medium_window: int = 14
    long_window: int = 30
    slope_window: int = 7
    previous_slope_window: int = 7
    stable_slope_threshold: float = 0.25
    rapid_slope_threshold: float = 3.0
    moderate_strength_threshold: float = 35.0
    strong_strength_threshold: float = 70.0
    minimum_points: int = 3

    def __post_init__(self) -> None:
        for name in (
            "short_window", "medium_window", "long_window", "slope_window",
            "previous_slope_window", "minimum_points",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer, not boolean.")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero.")
        for name in (
            "stable_slope_threshold", "rapid_slope_threshold",
            "moderate_strength_threshold", "strong_strength_threshold",
        ):
            value = _finite_number(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} must be greater than or equal to zero.")
            object.__setattr__(self, name, value)
        if not self.short_window < self.medium_window < self.long_window:
            raise ValueError("short_window < medium_window < long_window is required.")
        if self.rapid_slope_threshold <= self.stable_slope_threshold:
            raise ValueError("rapid_slope_threshold must exceed stable_slope_threshold.")
        if self.strong_strength_threshold <= self.moderate_strength_threshold:
            raise ValueError("strong_strength_threshold must exceed moderate_strength_threshold.")
        if not 0 <= self.moderate_strength_threshold <= 100 or not 0 <= self.strong_strength_threshold <= 100:
            raise ValueError("strength thresholds must be between 0 and 100.")
        if self.minimum_points < 2:
            raise ValueError("minimum_points must be at least 2.")


@dataclass(frozen=True, slots=True)
class TrendPoint:
    current_start: datetime
    current_end: datetime
    score: float | None
    available: bool
    short_moving_average: float | None
    medium_moving_average: float | None
    long_moving_average: float | None


@dataclass(frozen=True, slots=True)
class TrendWindowSummary:
    window_size: int
    available_point_count: int
    slope_per_period: float | None
    first_score: float | None
    latest_score: float | None
    absolute_change: float | None
    percent_change: float | None


@dataclass(frozen=True, slots=True)
class TemporalTrendResult:
    analysis_start: datetime | None
    analysis_end: datetime | None
    source_result_count: int
    available_score_count: int
    unavailable_score_count: int
    direction: TrendDirection
    strength: TrendStrength
    latest_score: float | None
    short_moving_average: float | None
    medium_moving_average: float | None
    long_moving_average: float | None
    current_slope: float | None
    previous_slope: float | None
    acceleration: float | None
    momentum: float | None
    consecutive_increases: int
    consecutive_decreases: int
    maximum_score: float | None
    maximum_score_start: datetime | None
    minimum_score: float | None
    minimum_score_start: datetime | None
    percent_change_from_first: float | None
    points: tuple[TrendPoint, ...]
    windows: Mapping[str, TrendWindowSummary]
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "windows", MappingProxyType(dict(self.windows)))

    def to_dict(self) -> dict[str, Any]:
        """Return an ordered, JSON-serializable representation of this result."""
        def convert(value: Any) -> Any:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(value, StrEnum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {name: convert(getattr(value, name)) for name in value.__dataclass_fields__}
            if isinstance(value, Mapping):
                return {name: convert(item) for name, item in value.items()}
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            return value

        return convert(self)
