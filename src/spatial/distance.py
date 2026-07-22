"""Great-circle distance helpers for geographic coordinates."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from numbers import Real

import numpy as np

EARTH_RADIUS_KM = 6371.0088
"""Standard mean Earth radius in kilometers."""

Coordinate = tuple[float, float]


def _validate_coordinate_value(
    value: Real,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    """Return a finite coordinate value within its valid range."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}.")

    numeric_value = float(value)

    if not math.isfinite(numeric_value):
        raise ValueError(f"{name} must be finite.")

    if not minimum <= numeric_value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum} degrees.")

    return numeric_value


def validate_latitude(latitude: Real) -> float:
    """Validate and return a latitude in degrees."""

    return _validate_coordinate_value(
        latitude,
        name="Latitude",
        minimum=-90.0,
        maximum=90.0,
    )


def validate_longitude(longitude: Real) -> float:
    """Validate and return a longitude in degrees."""

    return _validate_coordinate_value(
        longitude,
        name="Longitude",
        minimum=-180.0,
        maximum=180.0,
    )


def _validate_radius(radius_km: Real) -> float:
    """Return a positive, finite distance radius."""

    if isinstance(radius_km, bool) or not isinstance(radius_km, Real):
        raise TypeError("Radius must be a real number.")

    radius = float(radius_km)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be a positive, finite number.")
    return radius


def haversine_distance(
    latitude_a: Real,
    longitude_a: Real,
    latitude_b: Real,
    longitude_b: Real,
    *,
    radius_km: Real = EARTH_RADIUS_KM,
) -> float:
    """Return the Haversine great-circle distance between two points in kilometers."""

    lat_a = math.radians(validate_latitude(latitude_a))
    lon_a = math.radians(validate_longitude(longitude_a))
    lat_b = math.radians(validate_latitude(latitude_b))
    lon_b = math.radians(validate_longitude(longitude_b))
    radius = _validate_radius(radius_km)

    latitude_delta = lat_b - lat_a
    longitude_delta = lon_b - lon_a
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(longitude_delta / 2) ** 2
    )
    central_angle = 2 * math.asin(min(1.0, math.sqrt(haversine)))
    return radius * central_angle


def pairwise_haversine_distances(
    coordinates: Iterable[Sequence[Real]],
    *,
    radius_km: Real = EARTH_RADIUS_KM,
) -> np.ndarray:
    """Return a symmetric matrix of Haversine distances for coordinate pairs.

    Each coordinate must contain exactly ``(latitude, longitude)`` in degrees.
    """

    radius = _validate_radius(radius_km)
    validated_coordinates: list[Coordinate] = []

    for index, coordinate in enumerate(coordinates):
        if len(coordinate) != 2:
            raise ValueError(
                f"Coordinate at index {index} must contain latitude and longitude."
            )
        latitude, longitude = coordinate
        validated_coordinates.append(
            (validate_latitude(latitude), validate_longitude(longitude))
        )

    point_count = len(validated_coordinates)
    distances = np.zeros((point_count, point_count), dtype=float)

    for row in range(point_count):
        latitude_a, longitude_a = validated_coordinates[row]
        for column in range(row + 1, point_count):
            latitude_b, longitude_b = validated_coordinates[column]
            distance = haversine_distance(
                latitude_a,
                longitude_a,
                latitude_b,
                longitude_b,
                radius_km=radius,
            )
            distances[row, column] = distance
            distances[column, row] = distance

    return distances
