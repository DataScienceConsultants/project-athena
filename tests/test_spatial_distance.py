"""Tests for spatial distance helpers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.spatial.distance import (
    EARTH_RADIUS_KM,
    haversine_distance,
    pairwise_haversine_distances,
    validate_latitude,
    validate_longitude,
)


@pytest.mark.parametrize("value", [-90, 90, 0.0])
def test_validate_latitude_accepts_boundaries(value: float):
    """Latitude validation should accept inclusive boundaries."""

    assert validate_latitude(value) == value


@pytest.mark.parametrize("value", [-180, 180, 0.0])
def test_validate_longitude_accepts_boundaries(value: float):
    """Longitude validation should accept inclusive boundaries."""

    assert validate_longitude(value) == value


@pytest.mark.parametrize("value", [-90.1, 90.1, math.nan, math.inf, True, "10"])
def test_validate_latitude_rejects_invalid_values(value: object):
    """Latitude validation should reject invalid coordinate values."""

    with pytest.raises((TypeError, ValueError)):
        validate_latitude(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-180.1, 180.1, -math.inf, False, "10"])
def test_validate_longitude_rejects_invalid_values(value: object):
    """Longitude validation should reject invalid coordinate values."""

    with pytest.raises((TypeError, ValueError)):
        validate_longitude(value)  # type: ignore[arg-type]


def test_haversine_distance_matches_known_equatorial_distance():
    """One degree at the equator should have its known great-circle distance."""

    assert haversine_distance(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)


def test_haversine_distance_supports_custom_radius():
    """A custom radius should scale the resulting distance."""

    assert haversine_distance(0, 0, 0, 90, radius_km=1) == pytest.approx(math.pi / 2)


def test_haversine_distance_rejects_invalid_radius():
    """Distance calculation should require a positive finite radius."""

    with pytest.raises(ValueError, match="positive"):
        haversine_distance(0, 0, 0, 1, radius_km=0)


def test_pairwise_distances_are_symmetric_with_zero_diagonal():
    """Pairwise distances should be symmetric and self-distances zero."""

    matrix = pairwise_haversine_distances([(0, 0), (0, 1), (1, 1)])

    assert matrix.shape == (3, 3)
    assert np.allclose(matrix, matrix.T)
    assert np.allclose(np.diag(matrix), 0.0)
    assert matrix[0, 1] == pytest.approx(haversine_distance(0, 0, 0, 1))


def test_pairwise_distances_return_empty_matrix_for_no_coordinates():
    """No coordinates should produce an empty two-dimensional matrix."""

    matrix = pairwise_haversine_distances([])

    assert matrix.shape == (0, 0)
    assert matrix.dtype == float


def test_earth_radius_uses_standard_mean_value():
    """The exported radius should use the IUGG mean Earth radius."""

    assert EARTH_RADIUS_KM == 6371.0088
