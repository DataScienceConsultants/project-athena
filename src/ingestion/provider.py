"""Shared earthquake-data provider definitions for Project Athena."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class RegionBounds:
    """Rectangular geographic boundaries used to query earthquake events."""

    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def validate(self) -> None:
        """Validate latitude and longitude boundaries."""

        if not -90 <= self.min_latitude <= 90:
            raise ValueError("min_latitude must be between -90 and 90.")

        if not -90 <= self.max_latitude <= 90:
            raise ValueError("max_latitude must be between -90 and 90.")

        if not -180 <= self.min_longitude <= 180:
            raise ValueError("min_longitude must be between -180 and 180.")

        if not -180 <= self.max_longitude <= 180:
            raise ValueError("max_longitude must be between -180 and 180.")

        if self.min_latitude >= self.max_latitude:
            raise ValueError(
                "min_latitude must be less than max_latitude."
            )

        if self.min_longitude >= self.max_longitude:
            raise ValueError(
                "min_longitude must be less than max_longitude."
            )


@dataclass(frozen=True, slots=True)
class EarthquakeEvent:
    """Provider-independent representation of one earthquake event."""

    event_id: str
    source: str
    event_time_utc: datetime
    updated_time_utc: datetime | None
    latitude: float
    longitude: float
    depth_km: float | None
    magnitude: float | None
    magnitude_type: str | None
    place: str | None
    event_type: str | None
    status: str | None
    tsunami_flag: bool | None
    felt_reports: int | None
    significance: int | None
    alert_level: str | None
    detail_url: str | None
    source_url: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert the event into a serializable dictionary."""

        record = asdict(self)
        record["event_time_utc"] = self.event_time_utc.isoformat()
        record["updated_time_utc"] = (
            self.updated_time_utc.isoformat()
            if self.updated_time_utc is not None
            else None
        )
        return record


class EarthquakeProvider(ABC):
    """Abstract interface implemented by earthquake-data providers."""

    provider_name: str

    @abstractmethod
    def fetch_events(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        bounds: RegionBounds,
        minimum_magnitude: float | None = None,
    ) -> list[EarthquakeEvent]:
        """Retrieve earthquake events for a time period and region."""

    def validate_request(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        bounds: RegionBounds,
        minimum_magnitude: float | None,
    ) -> None:
        """Validate common provider request parameters."""

        bounds.validate()

        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError(
                "start_time and end_time must include timezone information."
            )

        if start_time >= end_time:
            raise ValueError("start_time must be earlier than end_time.")

        if minimum_magnitude is not None and minimum_magnitude < -2:
            raise ValueError(
                "minimum_magnitude cannot be less than -2."
            )

    @staticmethod
    def deduplicate_events(
        events: Iterable[EarthquakeEvent],
    ) -> list[EarthquakeEvent]:
        """Remove duplicate events using provider and event ID."""

        unique_events: dict[tuple[str, str], EarthquakeEvent] = {}

        for event in events:
            key = (event.source, event.event_id)

            existing = unique_events.get(key)

            if existing is None:
                unique_events[key] = event
                continue

            existing_updated = existing.updated_time_utc or existing.event_time_utc
            candidate_updated = event.updated_time_utc or event.event_time_utc

            if candidate_updated > existing_updated:
                unique_events[key] = event

        return sorted(
            unique_events.values(),
            key=lambda event: event.event_time_utc,
        )