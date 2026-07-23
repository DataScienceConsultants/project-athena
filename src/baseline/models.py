"""Immutable models for descriptive historical seismic baselines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class BaselinePeriod(StrEnum):
    """UTC calendar aggregation periods; weeks start on Monday."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class BaselineConfiguration:
    """Validated configuration for a historical baseline calculation."""

    period: BaselinePeriod | str = BaselinePeriod.DAILY
    lower_percentile: float = 10.0
    upper_percentile: float = 90.0
    rolling_window: int = 7
    minimum_periods: int = 1

    def __post_init__(self) -> None:
        try:
            period = BaselinePeriod(self.period)
        except ValueError as exc:
            raise ValueError("period must be daily, weekly, or monthly.") from exc
        object.__setattr__(self, "period", period)
        for name in ("lower_percentile", "upper_percentile"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric, not boolean.")
            if not 0 <= float(value) <= 100:
                raise ValueError(f"{name} must be between 0 and 100.")
            object.__setattr__(self, name, float(value))
        if self.lower_percentile >= self.upper_percentile:
            raise ValueError("lower_percentile must be less than upper_percentile.")
        for name in ("rolling_window", "minimum_periods"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer, not boolean.")
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        if self.minimum_periods > self.rolling_window:
            raise ValueError("minimum_periods cannot exceed rolling_window.")


@dataclass(frozen=True, slots=True)
class BaselineMetric:
    metric_name: str
    sample_size: int
    mean: float | None
    median: float | None
    standard_deviation: float | None
    minimum: float | None
    maximum: float | None
    lower_percentile: float | None
    upper_percentile: float | None


@dataclass(frozen=True, slots=True)
class HistoricalPeriodSummary:
    period_start: datetime
    period_end: datetime
    period: BaselinePeriod
    event_count: int
    event_rate_per_day: float
    mean_magnitude: float | None
    median_magnitude: float | None
    maximum_magnitude: float | None
    minimum_magnitude: float | None
    magnitude_event_count: int
    mean_depth_km: float | None
    median_depth_km: float | None
    minimum_depth_km: float | None
    maximum_depth_km: float | None
    depth_event_count: int
    total_energy_joules: float | None
    mean_energy_joules: float | None
    maximum_energy_joules: float | None
    energy_event_count: int
    rolling_event_count_mean: float | None


@dataclass(frozen=True, slots=True)
class HistoricalBaselineResult:
    configuration: BaselineConfiguration
    historical_start: datetime
    historical_end: datetime
    source_row_count: int
    accepted_row_count: int
    excluded_missing_timestamp_count: int
    period_count: int
    periods: tuple[HistoricalPeriodSummary, ...]
    metrics: Mapping[str, BaselineMetric]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat().replace("+00:00", "Z")
            if isinstance(value, StrEnum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {key: convert(getattr(value, key)) for key in value.__dataclass_fields__}
            if isinstance(value, Mapping):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            return value
        return convert(self)


@dataclass(frozen=True, slots=True)
class CurrentMetricComparison:
    current_value: float | None
    historical_mean: float | None
    historical_median: float | None
    lower_percentile: float | None
    upper_percentile: float | None
    percentile_rank: float | None
    difference_from_mean: float | None
    ratio_to_mean: float | None
    classification: str


@dataclass(frozen=True, slots=True)
class CurrentPeriodComparison:
    current_start: datetime
    current_end: datetime
    metrics: Mapping[str, CurrentMetricComparison]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_start": self.current_start.isoformat().replace("+00:00", "Z"),
            "current_end": self.current_end.isoformat().replace("+00:00", "Z"),
            "metrics": {name: {
                key: getattr(comparison, key) for key in comparison.__dataclass_fields__
            } for name, comparison in self.metrics.items()},
        }
