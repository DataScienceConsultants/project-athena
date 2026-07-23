"""Immutable models for explainable, descriptive seismic anomaly scoring."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class AnomalyDirection(StrEnum):
    BELOW = "below"
    TYPICAL = "typical"
    ABOVE = "above"
    UNAVAILABLE = "unavailable"


class AnomalyLevel(StrEnum):
    TYPICAL = "typical"
    NOTEWORTHY = "noteworthy"
    ELEVATED = "elevated"
    EXTREME = "extreme"
    UNAVAILABLE = "unavailable"


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric, not boolean.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


@dataclass(frozen=True, slots=True)
class AnomalyMetricConfiguration:
    metric_name: str
    weight: float
    two_sided: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name:
            raise ValueError("metric_name must be a nonempty string.")
        weight = _finite_number(self.weight, "weight")
        if weight <= 0:
            raise ValueError("weight must be greater than zero.")
        object.__setattr__(self, "weight", weight)


_DEFAULT_METRICS = (
    AnomalyMetricConfiguration("event_count", 0.30),
    AnomalyMetricConfiguration("maximum_magnitude", 0.25),
    AnomalyMetricConfiguration("total_energy_joules", 0.30),
    AnomalyMetricConfiguration("mean_depth_km", 0.15, two_sided=True),
)


@dataclass(frozen=True, slots=True)
class AnomalyScoringConfiguration:
    metrics: tuple[AnomalyMetricConfiguration, ...] = _DEFAULT_METRICS
    noteworthy_threshold: float = 60.0
    elevated_threshold: float = 80.0
    extreme_threshold: float = 95.0

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, tuple):
            raise TypeError(
                "metrics must be a tuple of AnomalyMetricConfiguration values."
            )
        if not self.metrics:
            raise ValueError("metrics must not be empty.")
        if not all(
            isinstance(metric, AnomalyMetricConfiguration) for metric in self.metrics
        ):
            raise TypeError("metrics must contain AnomalyMetricConfiguration values.")
        names = tuple(metric.metric_name for metric in self.metrics)
        if len(names) != len(set(names)):
            raise ValueError("metric names must be unique.")
        thresholds = tuple(
            _finite_number(getattr(self, name), name)
            for name in (
                "noteworthy_threshold",
                "elevated_threshold",
                "extreme_threshold",
            )
        )
        if any(not 0 <= threshold <= 100 for threshold in thresholds):
            raise ValueError("thresholds must be between 0 and 100.")
        if not thresholds[0] < thresholds[1] < thresholds[2]:
            raise ValueError("thresholds must satisfy noteworthy < elevated < extreme.")
        for name, value in zip(
            ("noteworthy_threshold", "elevated_threshold", "extreme_threshold"),
            thresholds,
        ):
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class MetricAnomalyScore:
    metric_name: str
    current_value: float | None
    historical_mean: float | None
    historical_percentile_rank: float | None
    direction: AnomalyDirection
    two_sided: bool
    raw_score: float | None
    weight: float
    normalized_weight: float
    weighted_score: float | None
    explanation: str


@dataclass(frozen=True, slots=True)
class SeismicAnomalyResult:
    current_start: datetime
    current_end: datetime
    score: float | None
    level: AnomalyLevel
    available_metric_count: int
    configured_metric_count: int
    metric_scores: Mapping[str, MetricAnomalyScore]
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metric_scores", MappingProxyType(dict(self.metric_scores))
        )

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(value, StrEnum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {
                    key: convert(getattr(value, key))
                    for key in value.__dataclass_fields__
                }
            if isinstance(value, Mapping):
                return {key: convert(item) for key, item in value.items()}
            if isinstance(value, tuple):
                return [convert(item) for item in value]
            return value

        return convert(self)
