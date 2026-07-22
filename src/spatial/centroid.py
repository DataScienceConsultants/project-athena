"""Spherical geographic centroid helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from numbers import Real

import pandas as pd

from src.spatial.distance import validate_latitude, validate_longitude


@dataclass(frozen=True, slots=True)
class GeographicCentroid:
    """A spherical geographic centroid and the number of source points."""

    latitude: float
    longitude: float
    point_count: int

    def as_tuple(self) -> tuple[float, float]:
        """Return the centroid as ``(latitude, longitude)``."""

        return (self.latitude, self.longitude)


def geographic_centroid(
    coordinates: Iterable[Sequence[Real]],
) -> GeographicCentroid:
    """Calculate the spherical centroid of latitude/longitude coordinates.

    Raises:
        ValueError: If no coordinates are supplied or their vector mean is undefined.
    """

    x_total = 0.0
    y_total = 0.0
    z_total = 0.0
    point_count = 0

    for index, coordinate in enumerate(coordinates):
        if len(coordinate) != 2:
            raise ValueError(
                f"Coordinate at index {index} must contain latitude and longitude."
            )
        latitude, longitude = coordinate
        latitude_radians = math.radians(validate_latitude(latitude))
        longitude_radians = math.radians(validate_longitude(longitude))
        x_total += math.cos(latitude_radians) * math.cos(longitude_radians)
        y_total += math.cos(latitude_radians) * math.sin(longitude_radians)
        z_total += math.sin(latitude_radians)
        point_count += 1

    if point_count == 0:
        raise ValueError(
            "Cannot calculate a centroid from an empty coordinate collection."
        )

    vector_length = math.sqrt(x_total**2 + y_total**2 + z_total**2)
    if math.isclose(vector_length, 0.0, abs_tol=1e-12):
        raise ValueError("Centroid is undefined for opposing coordinates.")

    longitude = math.degrees(math.atan2(y_total, x_total))
    latitude = math.degrees(math.atan2(z_total, math.hypot(x_total, y_total)))
    return GeographicCentroid(latitude, longitude, point_count)


def centroid_from_frame(
    dataframe: pd.DataFrame,
    *,
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
) -> GeographicCentroid:
    """Calculate a centroid from complete coordinate rows in a DataFrame."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Data must be a pandas DataFrame.")

    required_columns = {latitude_column, longitude_column}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(f"DataFrame is missing required columns: {missing_text}")

    complete_coordinates = dataframe[[latitude_column, longitude_column]].dropna()
    if complete_coordinates.empty:
        raise ValueError("No complete latitude and longitude coordinates remain.")

    return geographic_centroid(complete_coordinates.itertuples(index=False, name=None))
