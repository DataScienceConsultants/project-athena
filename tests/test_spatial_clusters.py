"""Tests for DBSCAN-based spatial clustering helpers."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.spatial.clusters import cluster_coordinates, cluster_frame


def test_cluster_coordinates_finds_one_obvious_cluster():
    """Nearby events should be grouped into a single cluster."""

    result = cluster_coordinates([(0, 0), (0, 0.01), (0.01, 0)], eps_km=3)

    assert result.event_count == 3
    assert result.cluster_count == 1
    assert result.noise_count == 0
    assert result.labels == (0, 0, 0)
    assert result.clusters[0].member_indices == (0, 1, 2)


def test_cluster_coordinates_finds_two_separated_clusters():
    """Distant groups should receive distinct deterministic labels."""

    result = cluster_coordinates(
        [(0, 0), (0, 0.01), (10, 10), (10, 10.01)], eps_km=3
    )

    assert result.cluster_count == 2
    assert [cluster.cluster_id for cluster in result.clusters] == [0, 1]
    assert [cluster.member_indices for cluster in result.clusters] == [(0, 1), (2, 3)]


def test_cluster_coordinates_identifies_noise():
    """Points without enough neighbors should be identified as DBSCAN noise."""

    result = cluster_coordinates([(0, 0), (0, 0.01), (5, 5)], eps_km=3)

    assert result.labels == (0, 0, -1)
    assert result.noise_indices == (2,)
    assert result.noise_count == 1


def test_cluster_coordinates_returns_empty_result_for_no_coordinates():
    """An empty iterable should not require fitting DBSCAN."""

    result = cluster_coordinates([], eps_km=3)

    assert result.event_count == result.cluster_count == result.noise_count == 0
    assert result.clusters == result.labels == result.noise_indices == ()


def test_cluster_coordinates_supports_one_event_cluster():
    """A single event is a cluster when DBSCAN permits one sample."""

    result = cluster_coordinates([(12.5, -45.25)], eps_km=3, min_samples=1)

    cluster = result.clusters[0]
    assert cluster.event_count == 1
    assert cluster.radius_km == 0
    assert cluster.mean_distance_km == 0
    assert cluster.max_distance_km == 0


@pytest.mark.parametrize("eps_km", [0, -1, math.inf, math.nan, True, "3"])
def test_cluster_coordinates_rejects_invalid_eps_km(eps_km: object):
    """The DBSCAN neighborhood must be a positive finite real distance."""

    with pytest.raises((TypeError, ValueError)):
        cluster_coordinates([], eps_km=eps_km)  # type: ignore[arg-type]


@pytest.mark.parametrize("min_samples", [0, -1, 1.2, True, "2"])
def test_cluster_coordinates_rejects_invalid_min_samples(min_samples: object):
    """The DBSCAN minimum count must be an integer of at least one."""

    with pytest.raises((TypeError, ValueError)):
        cluster_coordinates([], min_samples=min_samples)  # type: ignore[arg-type]


@pytest.mark.parametrize("coordinates", [[(0,)], [(91, 0)], [(0, "east")]])
def test_cluster_coordinates_rejects_malformed_coordinates(coordinates: object):
    """Coordinate pairs should use existing latitude and longitude validation."""

    with pytest.raises((TypeError, ValueError)):
        cluster_coordinates(coordinates)  # type: ignore[arg-type]


def test_cluster_statistics_use_spherical_centroid_and_distances():
    """Cluster radii and average distances should be geographically plausible."""

    result = cluster_coordinates([(0, 0), (0, 0.02)], eps_km=5)

    cluster = result.clusters[0]
    assert cluster.centroid_latitude == pytest.approx(0, abs=0.001)
    assert cluster.centroid_longitude == pytest.approx(0.01, abs=0.001)
    assert cluster.radius_km == pytest.approx(1.112, abs=0.02)
    assert cluster.mean_distance_km == pytest.approx(cluster.radius_km, abs=0.001)
    assert cluster.max_distance_km == cluster.radius_km


def test_cluster_frame_uses_default_coordinate_columns():
    """DataFrames should use latitude and longitude columns by default."""

    frame = pd.DataFrame({"latitude": [0, 0], "longitude": [0, 0.01]})

    assert cluster_frame(frame, eps_km=3).clusters[0].member_indices == (0, 1)


def test_cluster_frame_supports_custom_coordinate_columns():
    """DataFrames should support alternative coordinate column names."""

    frame = pd.DataFrame({"lat": [0, 0], "lon": [0, 0.01]})

    result = cluster_frame(
        frame,
        latitude_column="lat",
        longitude_column="lon",
        eps_km=3,
    )

    assert result.cluster_count == 1


def test_cluster_frame_ignores_missing_rows_and_preserves_indices():
    """Incomplete rows are ignored and original indices remain traceable."""

    frame = pd.DataFrame(
        {"latitude": [0, None, 0], "longitude": [0, 0.01, 0.01]},
        index=[10, 11, 12],
    )

    result = cluster_frame(frame, eps_km=3)

    assert result.event_count == 2
    assert result.clusters[0].member_indices == (10, 12)


def test_cluster_frame_rejects_missing_required_columns():
    """Missing coordinate columns should be named in the error."""

    with pytest.raises(ValueError, match="missing required columns"):
        cluster_frame(pd.DataFrame({"latitude": [0]}))


def test_cluster_frame_rejects_non_dataframe_input():
    """Only pandas DataFrames should be accepted by the frame helper."""

    with pytest.raises(TypeError, match="pandas DataFrame"):
        cluster_frame([(0, 0)])  # type: ignore[arg-type]


def test_cluster_frame_returns_empty_result_without_complete_coordinates():
    """All-missing coordinate rows should produce a valid empty result."""

    frame = pd.DataFrame({"latitude": [None], "longitude": [None]})

    result = cluster_frame(frame)

    assert result.event_count == result.cluster_count == result.noise_count == 0
    assert result.clusters == result.labels == result.noise_indices == ()
