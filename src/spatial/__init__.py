"""Spatial foundations for Project Athena."""

from src.spatial.centroid import (
    GeographicCentroid,
    centroid_from_frame,
    geographic_centroid,
)
from src.spatial.distance import (
    EARTH_RADIUS_KM,
    haversine_distance,
    pairwise_haversine_distances,
    validate_latitude,
    validate_longitude,
)

__all__ = [
    "EARTH_RADIUS_KM",
    "GeographicCentroid",
    "centroid_from_frame",
    "geographic_centroid",
    "haversine_distance",
    "pairwise_haversine_distances",
    "validate_latitude",
    "validate_longitude",
]
