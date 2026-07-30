"""Immutable, validated models for historical catalogs."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def _number(value: object, name: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric, not boolean.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _utc(value: object, name: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _text(value: object, name: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    result = value.strip()
    if not result and not nullable:
        raise ValueError(f"{name} must be a nonempty string.")
    return result or None


@dataclass(frozen=True, slots=True)
class GeographicBounds:
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def __post_init__(self) -> None:
        for name in ("min_latitude", "max_latitude", "min_longitude", "max_longitude"):
            object.__setattr__(self, name, _number(getattr(self, name), name))
        if not -90 <= self.min_latitude < self.max_latitude <= 90:
            raise ValueError("Latitude bounds must be ordered between -90 and 90.")
        if not -180 <= self.min_longitude < self.max_longitude <= 180:
            raise ValueError("Longitude bounds must be ordered between -180 and 180.")

    def contains(self, latitude: float, longitude: float) -> bool:
        lat = _number(latitude, "latitude")
        lon = _number(longitude, "longitude")
        return self.min_latitude <= lat <= self.max_latitude and self.min_longitude <= lon <= self.max_longitude


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    start_time: datetime
    end_time: datetime
    bounds: GeographicBounds
    minimum_magnitude: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_time", _utc(self.start_time, "start_time"))
        object.__setattr__(self, "end_time", _utc(self.end_time, "end_time"))
        if not isinstance(self.bounds, GeographicBounds):
            raise TypeError("bounds must be GeographicBounds.")
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be earlier than end_time.")
        value = _number(self.minimum_magnitude, "minimum_magnitude", nullable=True)
        if value is not None and value < -2:
            raise ValueError("minimum_magnitude cannot be less than -2.")
        object.__setattr__(self, "minimum_magnitude", value)

    @property
    def start_time_utc(self) -> datetime:
        return self.start_time

    @property
    def end_time_utc(self) -> datetime:
        return self.end_time


@dataclass(frozen=True, slots=True, init=False)
class CatalogEvent:
    event_id: str
    time: datetime
    latitude: float
    longitude: float
    depth: float
    magnitude: float | None
    magnitude_type: str | None
    place: str | None
    status: str | None
    event_type: str | None
    source: str
    updated_at: datetime | None

    def __init__(self, event_id: str, time: datetime, latitude: float, longitude: float,
                 depth: float, magnitude: float | None, magnitude_type: str | None = None,
                 place: str | None = None, event_type: str | None = None, source: str = "USGS",
                 updated_at: datetime | None = None, status: str | None = None,
                 updated_time: datetime | None = None) -> None:
        if updated_at is not None and updated_time is not None and updated_at != updated_time:
            raise ValueError("updated_at and updated_time disagree.")
        values = {
            "event_id": _text(event_id, "event_id"),
            "time": _utc(time, "time"),
            "latitude": _number(latitude, "latitude"),
            "longitude": _number(longitude, "longitude"),
            "depth": _number(depth, "depth"),
            "magnitude": _number(magnitude, "magnitude", nullable=True),
            "magnitude_type": _text(magnitude_type, "magnitude_type", nullable=True),
            "place": _text(place, "place", nullable=True),
            "status": _text(status, "status", nullable=True),
            "event_type": _text(event_type, "event_type", nullable=True),
            "source": _text(source, "source"),
            "updated_at": _utc(updated_at if updated_at is not None else updated_time, "updated_at", nullable=True),
        }
        if not -90 <= values["latitude"] <= 90:
            raise ValueError("latitude must be between -90 and 90.")
        if not -180 <= values["longitude"] <= 180:
            raise ValueError("longitude must be between -180 and 180.")
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def updated_time(self) -> datetime | None:
        """Backward-compatible alias for ``updated_at``."""
        return self.updated_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "time": self.time.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "depth": self.depth,
            "magnitude": self.magnitude,
            "magnitude_type": self.magnitude_type,
            "place": self.place,
            "status": self.status,
            "event_type": self.event_type,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True, slots=True)
class IngestionSummary:
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
        result = asdict(self)
        result["start_time"] = self.start_time.astimezone(timezone.utc).isoformat()
        result["end_time"] = self.end_time.astimezone(timezone.utc).isoformat()
        return result


@dataclass(frozen=True, slots=True)
class CatalogIngestionResult:
    events: tuple[CatalogEvent, ...]
    summary: IngestionSummary

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(event.to_dict() for event in self.events)
