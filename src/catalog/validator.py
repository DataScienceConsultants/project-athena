"""Parsing and validation for USGS historical GeoJSON."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from src.catalog.models import CatalogEvent


class CatalogValidationError(ValueError):
    """Raised when source catalog data is malformed."""


def _timestamp(value: object, field: str) -> datetime:
    if isinstance(value, bool):
        raise CatalogValidationError(f"{field} must be an epoch-millisecond number.")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise CatalogValidationError(f"{field} is outside the timestamp range.") from exc
    raise CatalogValidationError(f"{field} must be an epoch-millisecond number.")


def parse_usgs_feature(feature: Mapping[str, Any]) -> CatalogEvent:
    """Parse and validate one raw USGS GeoJSON feature."""
    if not isinstance(feature, Mapping):
        raise CatalogValidationError("USGS feature must be an object.")
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
        raise CatalogValidationError("USGS feature requires properties and geometry objects.")
    coordinates = geometry.get("coordinates")
    if geometry.get("type") not in (None, "Point") or not isinstance(coordinates, (list, tuple)) or len(coordinates) < 3:
        raise CatalogValidationError("USGS feature geometry must be a Point with three coordinates.")
    event_id = feature.get("id") or properties.get("code")
    if properties.get("time") is None:
        raise CatalogValidationError("USGS feature requires properties.time.")
    updated = properties.get("updated")
    try:
        return CatalogEvent(
            event_id=event_id,
            time=_timestamp(properties["time"], "time"),
            longitude=coordinates[0], latitude=coordinates[1], depth=coordinates[2],
            magnitude=properties.get("mag"), magnitude_type=properties.get("magType"),
            place=properties.get("place"), status=properties.get("status"),
            event_type=properties.get("type"), source=properties.get("net") or "USGS",
            updated_at=_timestamp(updated, "updated") if updated is not None else None,
        )
    except (TypeError, ValueError) as exc:
        raise CatalogValidationError(f"Invalid USGS feature {event_id!r}: {exc}") from exc


def parse_usgs_feature_collection(payload: Mapping[str, Any]) -> tuple[CatalogEvent, ...]:
    """Parse a GeoJSON FeatureCollection while preserving source order."""
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise CatalogValidationError("USGS response must be a GeoJSON FeatureCollection.")
    features = payload.get("features")
    if not isinstance(features, list):
        raise CatalogValidationError("USGS FeatureCollection requires a features list.")
    return tuple(parse_usgs_feature(feature) for feature in features)
