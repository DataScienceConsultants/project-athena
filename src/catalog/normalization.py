"""Normalization, validation, filtering, and deduplication for catalog records."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

from src.catalog.models import CatalogEvent, CatalogQuery

REQUIRED_FIELDS = ("event_id", "time", "latitude", "longitude", "depth", "magnitude")


class CatalogRecordError(ValueError):
    """Raised internally when a record cannot be normalized."""


def normalize_feature(feature: Any, *, source: str = "USGS") -> CatalogEvent:
    """Normalize one USGS GeoJSON feature into Athena's catalog schema.

    Missing required values are marked as incomplete; malformed or out-of-range
    values are invalid. Both outcomes are counted separately by the pipeline.
    """
    if not isinstance(feature, dict):
        raise CatalogRecordError("Feature must be an object.")
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    event_id = feature.get("id")
    if not isinstance(properties, dict) or not isinstance(geometry, dict):
        raise CatalogRecordError("Feature is incomplete.")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) < 3:
        raise CatalogRecordError("Feature is incomplete.")
    values = {
        "event_id": event_id,
        "time": properties.get("time"),
        "latitude": coordinates[1],
        "longitude": coordinates[0],
        "depth": coordinates[2],
        "magnitude": properties.get("mag"),
    }
    if any(value is None or value == "" for value in values.values()):
        raise CatalogRecordError("Feature is incomplete.")
    if not isinstance(event_id, str) or not event_id.strip():
        raise CatalogRecordError("event_id is invalid.")
    time = _timestamp(properties["time"], "time")
    updated_value = properties.get("updated")
    updated_time = _timestamp(updated_value, "updated_time") if updated_value is not None else None
    latitude = _number(coordinates[1], "latitude")
    longitude = _number(coordinates[0], "longitude")
    depth = _number(coordinates[2], "depth")
    magnitude = _number(properties["mag"], "magnitude")
    if not -90 <= latitude <= 90:
        raise CatalogRecordError("latitude is invalid.")
    if not -180 <= longitude <= 180:
        raise CatalogRecordError("longitude is invalid.")
    if depth < 0:
        raise CatalogRecordError("depth is invalid.")
    return CatalogEvent(
        event_id=event_id.strip(), time=time, latitude=latitude, longitude=longitude,
        depth=depth, magnitude=magnitude, magnitude_type=_optional_text(properties.get("magType")),
        place=_optional_text(properties.get("place")), event_type=_optional_text(properties.get("type")),
        source=source, updated_time=updated_time,
    )


def normalize_features(
    features: Iterable[Any], *, source: str = "USGS"
) -> tuple[list[CatalogEvent], int, int, int]:
    """Normalize features and return events plus requested/incomplete/invalid counts."""
    events: list[CatalogEvent] = []
    requested = incomplete = invalid = 0
    for feature in features:
        requested += 1
        try:
            events.append(normalize_feature(feature, source=source))
        except CatalogRecordError as exc:
            if "incomplete" in str(exc):
                incomplete += 1
            else:
                invalid += 1
    return events, requested, incomplete, invalid


def filter_events(events: Iterable[CatalogEvent], query: CatalogQuery) -> list[CatalogEvent]:
    """Apply query filters locally so output is correct even with broad source data."""
    bounds = query.bounds
    return [
        event for event in events
        if query.start_time_utc <= event.time < query.end_time_utc
        and bounds.min_latitude <= event.latitude <= bounds.max_latitude
        and bounds.min_longitude <= event.longitude <= bounds.max_longitude
        and (query.minimum_magnitude is None or event.magnitude >= query.minimum_magnitude)
    ]


def deduplicate_events(events: Iterable[CatalogEvent]) -> tuple[list[CatalogEvent], int]:
    """Keep the most recently updated version of each source/event ID deterministically."""
    selected: dict[tuple[str, str], CatalogEvent] = {}
    duplicates = 0
    for event in events:
        key = (event.source, event.event_id)
        current = selected.get(key)
        if current is None:
            selected[key] = event
            continue
        duplicates += 1
        if _dedupe_key(event) > _dedupe_key(current):
            selected[key] = event
    return sorted(selected.values(), key=lambda event: (event.time, event.event_id)), duplicates


def _dedupe_key(event: CatalogEvent) -> tuple[datetime, tuple[str, ...]]:
    updated = event.updated_time or event.time
    # The complete record breaks equal-update ties independently of response order.
    return updated, tuple(str(value) for value in event.to_dict().values())


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise CatalogRecordError(f"{name} is invalid.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CatalogRecordError(f"{name} is invalid.") from exc
    if not math.isfinite(number):
        raise CatalogRecordError(f"{name} is invalid.")
    return number


def _timestamp(value: Any, name: str) -> datetime:
    if isinstance(value, bool):
        raise CatalogRecordError(f"{name} is invalid.")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise CatalogRecordError(f"{name} is invalid.") from exc
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CatalogRecordError(f"{name} is invalid.") from exc
    else:
        raise CatalogRecordError(f"{name} is invalid.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CatalogRecordError(f"{name} is invalid.")
    return parsed.astimezone(timezone.utc)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
