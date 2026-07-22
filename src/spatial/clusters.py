"""DBSCAN-based clustering helpers for geographic event coordinates."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from src.spatial.centroid import geographic_centroid
from src.spatial.distance import (
    EARTH_RADIUS_KM,
    haversine_distance,
    validate_latitude,
    validate_longitude,
)


@dataclass(frozen=True, slots=True)
class SpatialCluster:
    """Summary statistics and membership for one spatial DBSCAN cluster."""

    cluster_id: int
    event_count: int
    centroid_latitude: float
    centroid_longitude: float
    radius_km: float
    mean_distance_km: float
    max_distance_km: float
    member_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SpatialClusteringResult:
    """The clusters, labels, and noise produced from a coordinate collection."""

    clusters: tuple[SpatialCluster, ...]
    labels: tuple[int, ...]
    noise_indices: tuple[int, ...]
    event_count: int
    cluster_count: int
    noise_count: int


def _validate_eps_km(eps_km: Real) -> float:
    """Return a positive, finite DBSCAN neighborhood distance."""

    if isinstance(eps_km, bool) or not isinstance(eps_km, Real):
        raise TypeError("eps_km must be a real number.")

    eps = float(eps_km)
    if not math.isfinite(eps) or eps <= 0:
        raise ValueError("eps_km must be a positive, finite number.")
    return eps


def _validate_min_samples(min_samples: Integral) -> int:
    """Return a valid integer DBSCAN minimum sample count."""

    if isinstance(min_samples, bool) or not isinstance(min_samples, Integral):
        raise TypeError("min_samples must be an integer.")
    if min_samples < 1:
        raise ValueError("min_samples must be greater than or equal to 1.")
    return int(min_samples)


def _validated_coordinates(
    coordinates: Iterable[Sequence[Real]],
) -> list[tuple[float, float]]:
    """Validate coordinate pairs and return them as degree values."""

    validated: list[tuple[float, float]] = []
    for index, coordinate in enumerate(coordinates):
        if len(coordinate) != 2:
            raise ValueError(
                f"Coordinate at index {index} must contain latitude and longitude."
            )
        latitude, longitude = coordinate
        validated.append((validate_latitude(latitude), validate_longitude(longitude)))
    return validated


def _cluster_validated_coordinates(
    coordinates: list[tuple[float, float]],
    *,
    eps_km: float,
    min_samples: int,
    member_indices: Sequence[int],
) -> SpatialClusteringResult:
    """Cluster validated degree coordinates while retaining their source indices."""

    if not coordinates:
        return SpatialClusteringResult((), (), (), 0, 0, 0)

    radians = np.radians(np.asarray(coordinates, dtype=float))
    labels_array = DBSCAN(
        eps=eps_km / EARTH_RADIUS_KM,
        min_samples=min_samples,
        metric="haversine",
    ).fit_predict(radians)
    labels = tuple(int(label) for label in labels_array)
    noise_indices = tuple(
        member_indices[position]
        for position, label in enumerate(labels)
        if label == -1
    )

    clusters: list[SpatialCluster] = []
    for cluster_id in sorted(set(labels).difference({-1})):
        positions = [
            position for position, label in enumerate(labels) if label == cluster_id
        ]
        members = [coordinates[position] for position in positions]
        centroid = geographic_centroid(members)
        distances = [
            haversine_distance(
                centroid.latitude,
                centroid.longitude,
                latitude,
                longitude,
            )
            for latitude, longitude in members
        ]
        max_distance = max(distances)
        clusters.append(
            SpatialCluster(
                cluster_id=cluster_id,
                event_count=len(members),
                centroid_latitude=centroid.latitude,
                centroid_longitude=centroid.longitude,
                radius_km=max_distance,
                mean_distance_km=sum(distances) / len(distances),
                max_distance_km=max_distance,
                member_indices=tuple(
                    member_indices[position] for position in positions
                ),
            )
        )

    return SpatialClusteringResult(
        clusters=tuple(clusters),
        labels=labels,
        noise_indices=noise_indices,
        event_count=len(coordinates),
        cluster_count=len(clusters),
        noise_count=len(noise_indices),
    )


def cluster_coordinates(
    coordinates: Iterable[Sequence[Real]],
    *,
    eps_km: Real = 10.0,
    min_samples: Integral = 2,
) -> SpatialClusteringResult:
    """Cluster latitude/longitude coordinate pairs using Haversine DBSCAN.

    Cluster member indices and labels correspond to the order of the supplied
    coordinates. DBSCAN labels retain their numeric values, with ``-1`` denoting
    noise.
    """

    eps = _validate_eps_km(eps_km)
    samples = _validate_min_samples(min_samples)
    validated = _validated_coordinates(coordinates)
    return _cluster_validated_coordinates(
        validated,
        eps_km=eps,
        min_samples=samples,
        member_indices=tuple(range(len(validated))),
    )


def cluster_frame(
    dataframe: pd.DataFrame,
    *,
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    eps_km: Real = 10.0,
    min_samples: Integral = 2,
) -> SpatialClusteringResult:
    """Cluster complete coordinate rows in a pandas DataFrame.

    Missing coordinate rows are ignored, while cluster memberships and noise
    indices retain the source DataFrame index values.
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Data must be a pandas DataFrame.")

    required_columns = {latitude_column, longitude_column}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(f"DataFrame is missing required columns: {missing_text}")

    eps = _validate_eps_km(eps_km)
    samples = _validate_min_samples(min_samples)
    complete = dataframe[[latitude_column, longitude_column]].dropna()
    validated = _validated_coordinates(complete.itertuples(index=False, name=None))
    return _cluster_validated_coordinates(
        validated,
        eps_km=eps,
        min_samples=samples,
        member_indices=tuple(complete.index.tolist()),
    )
