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

from dataclasses import asdict, dataclass
from typing import Any

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