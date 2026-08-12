"""Immutable models for Athena's global retrospective research layer."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from src.catalog.models import GeographicBounds
from src.spatial.distance import validate_latitude, validate_longitude


GLOBAL_BOUNDS = GeographicBounds(
    min_latitude=-90.0,
    max_latitude=90.0,
    min_longitude=-180.0,
    max_longitude=180.0,
)


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class GlobalResearchProfile:
    """Frozen cohort definition for a reproducible global research run."""

    profile_id: str
    start_time: datetime
    end_time: datetime
    minimum_magnitude: float
    bounds: GeographicBounds = GLOBAL_BOUNDS
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a nonempty string.")
        object.__setattr__(self, "profile_id", self.profile_id.strip())
        object.__setattr__(self, "start_time", _utc(self.start_time, "start_time"))
        object.__setattr__(self, "end_time", _utc(self.end_time, "end_time"))
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        if isinstance(self.minimum_magnitude, bool) or not isinstance(
            self.minimum_magnitude, (int, float)
        ):
            raise TypeError("minimum_magnitude must be numeric.")
        magnitude = float(self.minimum_magnitude)
        if not math.isfinite(magnitude):
            raise ValueError("minimum_magnitude must be finite.")
        object.__setattr__(self, "minimum_magnitude", magnitude)
        if not isinstance(self.bounds, GeographicBounds):
            raise TypeError("bounds must be GeographicBounds.")


REFERENCE_50_YEAR_PROFILE = GlobalResearchProfile(
    profile_id="global-m6-1976-2025",
    start_time=datetime(1976, 1, 1, tzinfo=UTC),
    end_time=datetime(2026, 1, 1, tzinfo=UTC),
    minimum_magnitude=6.0,
    description=(
        "Exactly 50 complete calendar years of global M6.0+ seismicity for "
        "retrospective cross-region and sequence research."
    ),
)


@dataclass(frozen=True, slots=True)
class PlannedCatalogQuery:
    """One USGS-safe partition in an adaptive global catalog plan."""

    query_id: str
    expected_event_count: int
    start_time: datetime
    end_time: datetime
    bounds: GeographicBounds
    minimum_magnitude: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not self.query_id:
            raise ValueError("query_id must be a nonempty string.")
        if isinstance(self.expected_event_count, bool) or not isinstance(
            self.expected_event_count, int
        ):
            raise TypeError("expected_event_count must be an integer.")
        if self.expected_event_count < 0:
            raise ValueError("expected_event_count cannot be negative.")
        object.__setattr__(self, "start_time", _utc(self.start_time, "start_time"))
        object.__setattr__(self, "end_time", _utc(self.end_time, "end_time"))


@dataclass(frozen=True, slots=True)
class GlobalCatalogPlan:
    """Deterministic set of bounded queries for one global research profile."""

    profile: GlobalResearchProfile
    partitions: tuple[PlannedCatalogQuery, ...]
    expected_event_count: int

    @property
    def query_count(self) -> int:
        return len(self.partitions)


Coordinate = tuple[float, float]


@dataclass(frozen=True, slots=True)
class FaultTrace:
    """Normalized active-fault trace represented as latitude/longitude vertices."""

    fault_id: str
    name: str | None
    coordinates: tuple[Coordinate, ...]
    source: str
    properties: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.fault_id, str) or not self.fault_id.strip():
            raise ValueError("fault_id must be a nonempty string.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a nonempty string.")
        if len(self.coordinates) < 2:
            raise ValueError("Fault traces require at least two coordinates.")
        normalized = tuple(
            (validate_latitude(latitude), validate_longitude(longitude))
            for latitude, longitude in self.coordinates
        )
        object.__setattr__(self, "coordinates", normalized)
        object.__setattr__(self, "fault_id", self.fault_id.strip())
        object.__setattr__(self, "source", self.source.strip())
        if self.name is not None:
            if not isinstance(self.name, str):
                raise TypeError("name must be a string or None.")
            object.__setattr__(self, "name", self.name.strip() or None)


@dataclass(frozen=True, slots=True)
class FaultAssociation:
    """Nearest active-fault context for a historical catalog event."""

    event_id: str
    fault_id: str
    fault_name: str | None
    distance_km: float
    fault_source: str

    def __post_init__(self) -> None:
        if isinstance(self.distance_km, bool) or not isinstance(
            self.distance_km, (int, float)
        ):
            raise TypeError("distance_km must be numeric.")
        distance = float(self.distance_km)
        if not math.isfinite(distance) or distance < 0:
            raise ValueError("distance_km must be finite and nonnegative.")
        object.__setattr__(self, "distance_km", distance)
