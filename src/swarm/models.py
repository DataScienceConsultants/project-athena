"""Immutable public models for descriptive seismic swarm analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

TrendDirection = Literal["increasing", "decreasing", "stable", "insufficient_data"]
ActivityStatus = Literal["active", "recently_active", "inactive", "insufficient_data"]


@dataclass(frozen=True, slots=True)
class SwarmTrend:
    """A linear event-property trend classified without forecasting."""

    slope_per_day: float | None
    direction: TrendDirection
    sample_count: int


@dataclass(frozen=True, slots=True)
class SwarmMigration:
    """Centroid movement from the early to late portion of a swarm."""

    distance_km: float
    bearing_degrees: float | None
    cardinal_direction: str
    is_stationary: bool


@dataclass(frozen=True, slots=True)
class SeismicSwarm:
    """Measured behavior of one DBSCAN event sequence, not a prediction."""

    swarm_id: str
    cluster_id: int
    event_count: int
    start_time_utc: str
    end_time_utc: str
    duration_days: float
    event_rate_per_day: float
    spatial_density_events_per_sq_km: float | None
    centroid_latitude: float
    centroid_longitude: float
    radius_km: float
    mean_magnitude: float
    magnitude_trend: SwarmTrend
    mean_depth_km: float
    depth_trend: SwarmTrend
    migration: SwarmMigration
    activity_status: ActivityStatus
    recent_event_count: int
    member_indices: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class SwarmAnalysisResult:
    """Complete output of a descriptive swarm analysis."""

    swarms: tuple[SeismicSwarm, ...]
    input_event_count: int
    analyzed_event_count: int
    excluded_event_count: int
    noise_indices: tuple[object, ...]
    reference_time_utc: str | None

    @property
    def swarm_count(self) -> int:
        """Return the number of qualifying swarm sequences."""

        return len(self.swarms)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return asdict(self)
