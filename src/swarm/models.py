"""Immutable result models for seismic swarm characterization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SwarmCluster:
    """Measured characteristics of one spatially clustered event sequence.

    ``is_swarm_like`` is a descriptive screening flag, not an earthquake
    prediction or a statement about the physical cause of a sequence.
    """

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
    magnitude_trend_per_day: float | None
    mean_depth_km: float
    depth_trend_km_per_day: float | None
    migration_distance_km: float
    migration_rate_km_per_day: float | None
    recent_event_count: int
    recent_activity_fraction: float
    is_swarm_like: bool
    member_indices: tuple[object, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of this cluster."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class SwarmAnalysisResult:
    """The swarm-characterization output for an event catalog."""

    swarms: tuple[SwarmCluster, ...]
    input_event_count: int
    analyzed_event_count: int
    excluded_event_count: int
    noise_indices: tuple[object, ...]
    recent_window_days: float

    @property
    def swarm_count(self) -> int:
        """Return the number of characterized spatial event sequences."""

        return len(self.swarms)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation of the analysis."""

        return {
            "swarms": [swarm.to_dict() for swarm in self.swarms],
            "input_event_count": self.input_event_count,
            "analyzed_event_count": self.analyzed_event_count,
            "excluded_event_count": self.excluded_event_count,
            "noise_indices": list(self.noise_indices),
            "recent_window_days": self.recent_window_days,
        }
