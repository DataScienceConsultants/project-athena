"""Structured report models for Project Athena Observatory.

These models separate Athena's calculated results from terminal display.
The same Observatory report can later be:

- printed in the terminal,
- saved as JSON,
- returned from an API,
- displayed in Project Seismic,
- or used by dashboards and research notebooks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from src.anomaly import SeismicAnomalyResult
    from src.baseline import CurrentPeriodComparison
    from src.timeseries import (
        ObservatoryTimeSeriesPoint, ObservatoryTimeSeriesResult, TimeSeriesConfiguration,
    )
    from src.trends import TemporalTrendResult


def _default_time_series_configuration() -> "TimeSeriesConfiguration":
    from src.timeseries import TimeSeriesConfiguration, TimeSeriesFrequency

    return TimeSeriesConfiguration(
        frequency=TimeSeriesFrequency.DAILY, baseline_lookback_periods=30,
        minimum_baseline_periods=7, include_unavailable_periods=True,
    )


def _serialize(value: object) -> object:
    """Convert established nested models without recursively invoking this root."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if hasattr(value, "to_dict"):
        return _serialize(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return {name: _serialize(getattr(value, name)) for name in value.__dataclass_fields__}
    return value

from src.observatory.thresholds import (
    STATUS_DISPLAY_NAMES,
    ObservatoryStatus,
)


@dataclass(frozen=True, slots=True)
class CatalogSection:
    """Metadata describing the earthquake catalog used in a report."""

    catalog_path: str
    region_key: str
    region_name: str
    event_count: int
    first_event_time_utc: str | None
    last_event_time_utc: str | None
    calendar_days: int

    def to_dict(self) -> dict[str, Any]:
        """Return the catalog section as a dictionary."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class ActivitySection:
    """Earthquake-count metrics and interpretation."""

    total_events: int
    active_days: int
    calendar_days: int
    average_events_per_day: float
    maximum_events_in_one_day: int
    busiest_day: str | None
    events_last_7_days: int
    events_last_30_days: int
    average_events_last_7_days: float
    historical_average_events_per_day: float | None
    activity_ratio_7d: float | None
    status: ObservatoryStatus
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Return the activity section as a serializable dictionary."""

        result = asdict(self)
        result["status"] = self.status.value
        result["status_display"] = STATUS_DISPLAY_NAMES[self.status]
        return result


@dataclass(frozen=True, slots=True)
class MagnitudeSection:
    """Magnitude metrics for the selected reporting period."""

    events_with_magnitude: int
    missing_magnitude_count: int
    average_magnitude: float | None
    median_magnitude: float | None
    minimum_magnitude: float | None
    maximum_magnitude: float | None
    magnitude_3_plus: int
    magnitude_4_plus: int
    magnitude_5_plus: int
    largest_event_id: str | None
    largest_event_time_utc: str | None
    largest_event_place: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the magnitude section as a dictionary."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class EnergySection:
    """Estimated seismic-energy metrics and interpretation."""

    events_with_magnitude: int
    total_energy_joules: float
    equivalent_single_magnitude: float | None
    maximum_event_energy_joules: float
    maximum_energy_magnitude: float | None
    maximum_energy_event_id: str | None
    energy_last_7_days_joules: float
    historical_average_daily_energy_joules: float | None
    energy_ratio_7d: float | None
    status: ObservatoryStatus
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Return the energy section as a serializable dictionary."""

        result = asdict(self)
        result["status"] = self.status.value
        result["status_display"] = STATUS_DISPLAY_NAMES[self.status]
        return result


@dataclass(frozen=True, slots=True)
class DepthSection:
    """Earthquake-depth metrics and interpretation."""

    events_with_depth: int
    average_depth_km: float | None
    median_depth_km: float | None
    minimum_depth_km: float | None
    maximum_depth_km: float | None
    shallow_events: int
    intermediate_events: int
    deep_events: int
    average_depth_last_7_days_km: float | None
    historical_average_depth_km: float | None
    depth_difference_7d_km: float | None
    status: ObservatoryStatus
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        """Return the depth section as a serializable dictionary."""

        result = asdict(self)
        result["status"] = self.status.value
        result["status_display"] = STATUS_DISPLAY_NAMES[self.status]
        return result


@dataclass(frozen=True, slots=True)
class StatusSection:
    """Overall Observatory interpretation."""

    overall_status: ObservatoryStatus
    confidence: str
    methodology_version: str
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        """Return the status section as a serializable dictionary."""

        result = asdict(self)
        result["overall_status"] = self.overall_status.value
        result["overall_status_display"] = STATUS_DISPLAY_NAMES[
            self.overall_status
        ]
        return result


@dataclass(frozen=True, slots=True)
class ObservatoryReport:
    """Complete structured Project Athena Observatory report."""

    generated_at_utc: str
    catalog: CatalogSection
    activity: ActivitySection
    magnitude: MagnitudeSection
    energy: EnergySection
    depth: DepthSection
    status: StatusSection

    def to_dict(self) -> dict[str, Any]:
        """Return the complete report as a JSON-compatible dictionary."""

        return {
            "generated_at_utc": self.generated_at_utc,
            "catalog": self.catalog.to_dict(),
            "activity": self.activity.to_dict(),
            "magnitude": self.magnitude.to_dict(),
            "energy": self.energy.to_dict(),
            "depth": self.depth.to_dict(),
            "status": self.status.to_dict(),
        }
@dataclass(frozen=True, slots=True)
class ObservatoryIntelligenceConfiguration:
    """Configuration for the unified descriptive intelligence report."""

    time_series_configuration: "TimeSeriesConfiguration" = field(default_factory=_default_time_series_configuration)
    recent_period_limit: int = 10
    include_time_series_points: bool = True
    include_unavailable_periods: bool = True
    include_metric_details: bool = True

    def __post_init__(self) -> None:
        from src.timeseries import TimeSeriesConfiguration

        if not isinstance(self.time_series_configuration, TimeSeriesConfiguration):
            raise TypeError("time_series_configuration must be a TimeSeriesConfiguration.")
        if isinstance(self.recent_period_limit, bool) or not isinstance(self.recent_period_limit, int):
            raise TypeError("recent_period_limit must be an integer, not boolean.")
        if self.recent_period_limit <= 0:
            raise ValueError("recent_period_limit must be greater than zero.")
        for name in ("include_time_series_points", "include_unavailable_periods", "include_metric_details"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool.")


@dataclass(frozen=True, slots=True)
class ObservatoryIntelligenceSnapshot:
    latest_period_start: datetime | None
    latest_period_end: datetime | None
    latest_current_event_count: int | None
    latest_baseline_start: datetime | None
    latest_baseline_end: datetime | None
    latest_baseline_period_count: int | None
    latest_comparison: "CurrentPeriodComparison | None"
    latest_anomaly: "SeismicAnomalyResult | None"
    trend: "TemporalTrendResult"
    latest_available: bool
    unavailable_reason: str | None
    summary: str

    def __post_init__(self) -> None:
        if self.latest_available != (self.latest_anomaly is not None):
            raise ValueError("latest_available must match latest_anomaly availability.")


@dataclass(frozen=True, slots=True)
class ObservatoryIntelligenceReport:
    schema_version: str
    methodology_version: str
    observatory: ObservatoryReport
    time_series: "ObservatoryTimeSeriesResult"
    snapshot: ObservatoryIntelligenceSnapshot
    recent_periods: tuple["ObservatoryTimeSeriesPoint", ...]
    metadata: Mapping[str, object]
    executive_summary: str
    disclaimer: str
    include_time_series_points: bool = True
    include_metric_details: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.recent_periods, tuple):
            raise TypeError("recent_periods must be a tuple.")
        if tuple(sorted(self.recent_periods, key=lambda point: point.period_start)) != self.recent_periods:
            raise ValueError("recent_periods must be ordered by period_start.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        time_series = self.time_series.to_dict()
        if not self.include_time_series_points:
            time_series.pop("points", None)
        if not self.include_metric_details:
            time_series = _without_metric_details(time_series)
        snapshot = _serialize(self.snapshot)
        recent_periods = _serialize(self.recent_periods)
        if not self.include_metric_details:
            snapshot = _without_metric_details(snapshot)
            recent_periods = _without_metric_details(recent_periods)
        return {
            "schema_version": self.schema_version,
            "methodology_version": self.methodology_version,
            "observatory": self.observatory.to_dict(),
            "time_series": time_series,
            "snapshot": snapshot,
            "recent_periods": recent_periods,
            "metadata": _serialize(self.metadata),
            "executive_summary": self.executive_summary,
            "disclaimer": self.disclaimer,
        }


def _without_metric_details(value: object) -> object:
    """Remove detailed comparison and contributor payloads from serialization."""
    if isinstance(value, dict):
        return {
            key: _without_metric_details(item)
            for key, item in value.items()
            if key not in {"comparison", "latest_comparison", "metric_scores"}
        }
    if isinstance(value, list):
        return [_without_metric_details(item) for item in value]
    return value
