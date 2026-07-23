"""Immutable models used by the historical catalog ingestion pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class GeographicBounds:
    """A validated rectangular geographic query area."""

    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.min_latitude <= 90 or not -90 <= self.max_latitude <= 90:
            raise ValueError("Latitude bounds must be between -90 and 90.")
        if not -180 <= self.min_longitude <= 180 or not -180 <= self.max_longitude <= 180:
            raise ValueError("Longitude bounds must be between -180 and 180.")
        if self.min_latitude >= self.max_latitude:
            raise ValueError("min_latitude must be less than max_latitude.")
        if self.min_longitude >= self.max_longitude:
            raise ValueError("min_longitude must be less than max_longitude.")


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    """Parameters for retrieving one historical catalog slice."""

    start_time: datetime
    end_time: datetime
    bounds: GeographicBounds
    minimum_magnitude: float | None = None

    def __post_init__(self) -> None:
        for name, value in (("start_time", self.start_time), ("end_time", self.end_time)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware.")
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        if self.minimum_magnitude is not None and self.minimum_magnitude < -2:
            raise ValueError("minimum_magnitude cannot be less than -2.")

    @property
    def start_time_utc(self) -> datetime:
        """Return the start time normalized to UTC."""
        return self.start_time.astimezone(timezone.utc)

    @property
    def end_time_utc(self) -> datetime:
        """Return the end time normalized to UTC."""
        return self.end_time.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CatalogEvent:
    """One normalized, analysis-ready seismic catalog record."""

    event_id: str
    time: datetime
    latitude: float
    longitude: float
    depth: float
    magnitude: float
    magnitude_type: str | None
    place: str | None
    event_type: str | None
    source: str
    updated_time: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation with UTC timestamps."""
        record = asdict(self)
        record["time"] = self.time.astimezone(timezone.utc).isoformat()
        record["updated_time"] = (
            self.updated_time.astimezone(timezone.utc).isoformat()
            if self.updated_time is not None
            else None
        )
        return record


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    """Immutable quality and retrieval summary for a catalog ingestion."""

    requested_count: int
    accepted_count: int
    excluded_incomplete_count: int
    excluded_invalid_count: int
    duplicate_count: int
    final_count: int
    start_time: datetime
    end_time: datetime
    minimum_magnitude: float | None
    bounds: GeographicBounds
    source: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        result = asdict(self)
        result["start_time"] = self.start_time.astimezone(timezone.utc).isoformat()
        result["end_time"] = self.end_time.astimezone(timezone.utc).isoformat()
        return result


@dataclass(frozen=True, slots=True)
class CatalogIngestionResult:
    """Immutable deterministic output of a historical catalog ingestion."""

    events: tuple[CatalogEvent, ...]
    summary: IngestionSummary

    def records(self) -> tuple[dict[str, Any], ...]:
        """Return JSON-serializable event records in deterministic order."""
        return tuple(event.to_dict() for event in self.events)
