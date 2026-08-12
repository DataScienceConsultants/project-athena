"""Active-fault normalization and exact great-circle proximity measurements."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.catalog.models import CatalogEvent
from src.global_research.models import FaultAssociation, FaultTrace
from src.spatial.distance import (
    EARTH_RADIUS_KM,
    haversine_distance,
    validate_latitude,
    validate_longitude,
)

DEFAULT_FAULT_SOURCE = "GEM Global Active Faults Database"


def load_fault_geojson(
    payload: Mapping[str, Any],
    *,
    source: str = DEFAULT_FAULT_SOURCE,
) -> tuple[FaultTrace, ...]:
    """Normalize GeoJSON LineString/MultiLineString features into fault traces."""
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a GeoJSON mapping.")
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Fault GeoJSON must be a FeatureCollection.")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Fault GeoJSON FeatureCollection must contain a features list.")

    traces: list[FaultTrace] = []
    for feature_index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise ValueError(f"Fault feature {feature_index} is not an object.")
        geometry = feature.get("geometry")
        if not isinstance(geometry, Mapping):
            continue
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        properties = feature.get("properties") or {}
        if not isinstance(properties, Mapping):
            raise ValueError(f"Fault feature {feature_index} properties must be an object.")

        feature_id = _feature_id(feature, properties, feature_index)
        name = _fault_name(properties)
        if geometry_type == "LineString":
            traces.append(
                FaultTrace(
                    fault_id=feature_id,
                    name=name,
                    coordinates=_normalize_line(coordinates, feature_index),
                    source=source,
                    properties=dict(properties),
                )
            )
        elif geometry_type == "MultiLineString":
            if not isinstance(coordinates, list):
                raise ValueError(
                    f"Fault feature {feature_index} MultiLineString coordinates are invalid."
                )
            for part_index, line in enumerate(coordinates, start=1):
                traces.append(
                    FaultTrace(
                        fault_id=f"{feature_id}:part-{part_index}",
                        name=name,
                        coordinates=_normalize_line(line, feature_index),
                        source=source,
                        properties=dict(properties),
                    )
                )
        else:
            continue
    return tuple(sorted(traces, key=lambda trace: trace.fault_id))


def _feature_id(
    feature: Mapping[str, Any], properties: Mapping[str, Any], feature_index: int
) -> str:
    candidates = (
        feature.get("id"),
        _property(properties, "fault_id"),
        _property(properties, "id"),
        _property(properties, "fid"),
        _property(properties, "objectid"),
    )
    value = next((item for item in candidates if item not in (None, "")), None)
    return str(value) if value is not None else f"fault-{feature_index + 1:06d}"


def _fault_name(properties: Mapping[str, Any]) -> str | None:
    for key in ("name", "fault_name", "faultname", "fault_name_en"):
        value = _property(properties, key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _property(properties: Mapping[str, Any], requested: str) -> Any:
    requested_lower = requested.lower()
    for key, value in properties.items():
        if str(key).lower() == requested_lower:
            return value
    return None


def _normalize_line(value: Any, feature_index: int) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError(f"Fault feature {feature_index} must contain at least two vertices.")
    normalized: list[tuple[float, float]] = []
    for vertex in value:
        if not isinstance(vertex, Sequence) or isinstance(vertex, str) or len(vertex) < 2:
            raise ValueError(f"Fault feature {feature_index} contains an invalid vertex.")
        longitude, latitude = vertex[0], vertex[1]
        normalized.append(
            (validate_latitude(latitude), validate_longitude(longitude))
        )
    return tuple(normalized)


def great_circle_segment_distance_km(
    latitude: float,
    longitude: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Return shortest distance from a point to a finite great-circle segment."""
    point_lat = validate_latitude(latitude)
    point_lon = validate_longitude(longitude)
    start_lat, start_lon = _coordinate(start, "start")
    end_lat, end_lon = _coordinate(end, "end")

    segment_angle = haversine_distance(
        start_lat, start_lon, end_lat, end_lon
    ) / EARTH_RADIUS_KM
    if segment_angle <= 1e-15:
        return haversine_distance(point_lat, point_lon, start_lat, start_lon)

    point_angle = haversine_distance(
        start_lat, start_lon, point_lat, point_lon
    ) / EARTH_RADIUS_KM
    if point_angle <= 1e-15:
        return 0.0

    bearing_to_point = _initial_bearing_radians(
        start_lat, start_lon, point_lat, point_lon
    )
    bearing_to_end = _initial_bearing_radians(
        start_lat, start_lon, end_lat, end_lon
    )
    bearing_delta = bearing_to_point - bearing_to_end
    cross_track_angle = math.asin(
        max(-1.0, min(1.0, math.sin(point_angle) * math.sin(bearing_delta)))
    )
    along_track_angle = math.atan2(
        math.sin(point_angle) * math.cos(bearing_delta),
        math.cos(point_angle),
    )

    if along_track_angle < 0 or along_track_angle > segment_angle:
        return min(
            haversine_distance(point_lat, point_lon, start_lat, start_lon),
            haversine_distance(point_lat, point_lon, end_lat, end_lon),
        )
    return abs(cross_track_angle) * EARTH_RADIUS_KM


def _coordinate(value: Sequence[float], name: str) -> tuple[float, float]:
    if len(value) != 2:
        raise ValueError(f"{name} must contain latitude and longitude.")
    return validate_latitude(value[0]), validate_longitude(value[1])


def _initial_bearing_radians(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    longitude_delta = math.radians(longitude_b - longitude_a)
    y = math.sin(longitude_delta) * math.cos(lat_b)
    x = (
        math.cos(lat_a) * math.sin(lat_b)
        - math.sin(lat_a) * math.cos(lat_b) * math.cos(longitude_delta)
    )
    return math.atan2(y, x)


def distance_to_fault_km(
    latitude: float,
    longitude: float,
    fault: FaultTrace,
) -> float:
    """Measure exact minimum point-to-segment distance across a normalized trace."""
    if not isinstance(fault, FaultTrace):
        raise TypeError("fault must be FaultTrace.")
    return min(
        great_circle_segment_distance_km(latitude, longitude, start, end)
        for start, end in zip(fault.coordinates, fault.coordinates[1:], strict=True)
    )


def nearest_fault(
    *,
    event_id: str,
    latitude: float,
    longitude: float,
    faults: Iterable[FaultTrace],
    max_distance_km: float | None = None,
) -> FaultAssociation | None:
    """Return deterministic nearest-fault context for one historical event."""
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a nonempty string.")
    latitude = validate_latitude(latitude)
    longitude = validate_longitude(longitude)
    if max_distance_km is not None:
        if isinstance(max_distance_km, bool) or not isinstance(max_distance_km, (int, float)):
            raise TypeError("max_distance_km must be numeric or None.")
        max_distance_km = float(max_distance_km)
        if not math.isfinite(max_distance_km) or max_distance_km < 0:
            raise ValueError("max_distance_km must be finite and nonnegative.")

    measured: list[tuple[float, FaultTrace]] = []
    for fault in faults:
        if not isinstance(fault, FaultTrace):
            raise TypeError("faults must contain FaultTrace objects.")
        measured.append((distance_to_fault_km(latitude, longitude, fault), fault))
    if not measured:
        return None
    distance, fault = min(measured, key=lambda item: (item[0], item[1].fault_id))
    if max_distance_km is not None and distance > max_distance_km:
        return None
    return FaultAssociation(
        event_id=event_id.strip(),
        fault_id=fault.fault_id,
        fault_name=fault.name,
        distance_km=distance,
        fault_source=fault.source,
    )


def associate_catalog_events(
    events: Iterable[CatalogEvent],
    faults: Iterable[FaultTrace],
    *,
    max_distance_km: float | None = None,
) -> tuple[FaultAssociation, ...]:
    """Attach nearest active-fault context to a historical catalog cohort.

    This correctness-first implementation performs an exact trace scan. A spatial index can
    be added later without changing the public association model.
    """
    fault_set = tuple(faults)
    associations: list[FaultAssociation] = []
    for event in events:
        if not isinstance(event, CatalogEvent):
            raise TypeError("events must contain CatalogEvent objects.")
        association = nearest_fault(
            event_id=event.event_id,
            latitude=event.latitude,
            longitude=event.longitude,
            faults=fault_set,
            max_distance_km=max_distance_km,
        )
        if association is not None:
            associations.append(association)
    return tuple(associations)
