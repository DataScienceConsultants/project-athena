"""Immutable public models for descriptive observatory time series."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from src.anomaly import AnomalyScoringConfiguration, SeismicAnomalyResult
from src.baseline import BaselineConfiguration, CurrentPeriodComparison
from src.trends import TemporalTrendResult, TrendConfiguration


class TimeSeriesFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def _utc_datetime(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a timezone-aware datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class TimeSeriesConfiguration:
    frequency: TimeSeriesFrequency = TimeSeriesFrequency.DAILY
    baseline_lookback_periods: int = 30
    minimum_baseline_periods: int = 7
    analysis_start: datetime | None = None
    analysis_end: datetime | None = None
    include_unavailable_periods: bool = True
    baseline_configuration: BaselineConfiguration | None = None
    anomaly_configuration: AnomalyScoringConfiguration | None = None
    trend_configuration: TrendConfiguration | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.frequency, TimeSeriesFrequency):
            raise TypeError("frequency must be a TimeSeriesFrequency.")
        for name in ("baseline_lookback_periods", "minimum_baseline_periods"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer, not boolean.")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero.")
        if self.minimum_baseline_periods > self.baseline_lookback_periods:
            raise ValueError("minimum_baseline_periods cannot exceed baseline_lookback_periods.")
        start = _utc_datetime(self.analysis_start, "analysis_start")
        end = _utc_datetime(self.analysis_end, "analysis_end")
        if start is not None and end is not None and end <= start:
            raise ValueError("analysis_end must be later than analysis_start.")
        object.__setattr__(self, "analysis_start", start)
        object.__setattr__(self, "analysis_end", end)
        if not isinstance(self.include_unavailable_periods, bool):
            raise TypeError("include_unavailable_periods must be a bool.")
        for name, expected in (
            ("baseline_configuration", BaselineConfiguration),
            ("anomaly_configuration", AnomalyScoringConfiguration),
            ("trend_configuration", TrendConfiguration),
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, expected):
                raise TypeError(f"{name} must be a {expected.__name__} or None.")


@dataclass(frozen=True, slots=True)
class ObservatoryTimeSeriesPoint:
    period_start: datetime
    period_end: datetime
    baseline_start: datetime
    baseline_end: datetime
    baseline_period_count: int
    current_event_count: int
    baseline_available: bool
    comparison: CurrentPeriodComparison | None
    anomaly: SeismicAnomalyResult | None
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        for name in ("period_start", "period_end", "baseline_start", "baseline_end"):
            value = _utc_datetime(getattr(self, name), name)
            assert value is not None
            object.__setattr__(self, name, value)
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be later than period_start.")
        if self.baseline_end != self.period_start:
            raise ValueError("baseline_end must equal period_start.")
        if self.anomaly is None:
            if self.comparison is not None or self.unavailable_reason is None:
                raise ValueError("Unavailable points require a reason and no comparison.")
        elif self.comparison is None or self.unavailable_reason is not None:
            raise ValueError("Available points require comparison and anomaly without a reason.")


@dataclass(frozen=True, slots=True)
class ObservatoryTimeSeriesResult:
    analysis_start: datetime | None
    analysis_end: datetime | None
    frequency: TimeSeriesFrequency
    source_event_count: int
    candidate_period_count: int
    available_period_count: int
    unavailable_period_count: int
    anomaly_results: tuple[SeismicAnomalyResult, ...]
    points: tuple[ObservatoryTimeSeriesPoint, ...]
    trend: TemporalTrendResult
    metadata: Mapping[str, object]
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.frequency, TimeSeriesFrequency):
            raise TypeError("frequency must be a TimeSeriesFrequency.")
        if not isinstance(self.points, tuple) or not isinstance(self.anomaly_results, tuple):
            raise TypeError("points and anomaly_results must be tuples.")
        if tuple(sorted(self.points, key=lambda point: point.period_start)) != self.points:
            raise ValueError("points must be ordered by period_start.")
        if tuple(sorted(self.anomaly_results, key=lambda item: item.current_start)) != self.anomaly_results:
            raise ValueError("anomaly_results must be ordered by current_start.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic, JSON-serializable representation."""
        def convert(value: object) -> object:
            if isinstance(value, datetime):
                return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, Mapping):
                return {str(key): convert(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            if hasattr(value, "__dataclass_fields__"):
                return {
                    name: convert(getattr(value, name))
                    for name in value.__dataclass_fields__
                }
            if hasattr(value, "to_dict"):
                return convert(value.to_dict())
            return value

        return {
            "analysis_start": convert(self.analysis_start),
            "analysis_end": convert(self.analysis_end),
            "frequency": convert(self.frequency),
            "source_event_count": self.source_event_count,
            "candidate_period_count": self.candidate_period_count,
            "available_period_count": self.available_period_count,
            "unavailable_period_count": self.unavailable_period_count,
            "anomaly_results": convert(self.anomaly_results),
            "points": convert(self.points),
            "trend": convert(self.trend),
            "metadata": convert(self.metadata),
            "summary": self.summary,
        }
