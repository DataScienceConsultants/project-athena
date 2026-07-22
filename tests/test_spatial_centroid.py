"""Tests for spherical geographic centroid helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from src.spatial.centroid import centroid_from_frame, geographic_centroid


def test_single_point_centroid_returns_original_coordinate():
    """A single coordinate should be its own centroid."""

    centroid = geographic_centroid([(12.5, -45.25)])

    assert centroid.as_tuple() == pytest.approx((12.5, -45.25))
    assert centroid.point_count == 1


def test_centroid_handles_international_date_line():
    """Nearby points across the date line should remain near 180 degrees."""

    centroid = geographic_centroid([(10, 179), (10, -179)])

    assert centroid.latitude == pytest.approx(10, abs=0.01)
    assert abs(centroid.longitude) == pytest.approx(180, abs=0.01)
    assert centroid.point_count == 2


def test_centroid_rejects_empty_coordinates():
    """An empty collection has no geographic centroid."""

    with pytest.raises(ValueError, match="empty"):
        geographic_centroid([])


def test_centroid_rejects_opposing_coordinates():
    """Antipodal points have an undefined vector-average centroid."""

    with pytest.raises(ValueError, match="opposing"):
        geographic_centroid([(0, 0), (0, 180)])


def test_centroid_from_frame_ignores_incomplete_rows():
    """Rows missing either coordinate should not contribute to the centroid."""

    frame = pd.DataFrame({"latitude": [0, None, 0], "longitude": [0, 1, 2]})

    centroid = centroid_from_frame(frame)

    assert centroid.point_count == 2
    assert centroid.longitude == pytest.approx(1, abs=0.01)


def test_centroid_from_frame_supports_custom_column_names():
    """Alternative coordinate column names should be accepted."""

    frame = pd.DataFrame({"lat": [5], "lon": [6]})

    centroid = centroid_from_frame(
        frame,
        latitude_column="lat",
        longitude_column="lon",
    )

    assert centroid.as_tuple() == pytest.approx((5, 6))


def test_centroid_from_frame_rejects_missing_required_columns():
    """Required coordinate columns should be reported clearly."""

    with pytest.raises(ValueError, match="missing required columns"):
        centroid_from_frame(pd.DataFrame({"latitude": [0]}))


def test_centroid_from_frame_rejects_no_complete_coordinates():
    """DataFrames with only incomplete rows should be rejected."""

    frame = pd.DataFrame({"latitude": [None], "longitude": [None]})

    with pytest.raises(ValueError, match="No complete"):
        centroid_from_frame(frame)
