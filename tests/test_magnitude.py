"""Tests for Project Athena magnitude metrics."""

from __future__ import annotations

import pandas as pd
import pytest

from src.metrics.magnitude import (
    add_magnitude_categories,
    add_rolling_magnitude_metrics,
    build_daily_magnitude,
    classify_magnitude_band,
    summarize_magnitude,
    validate_magnitude_catalog,
)


def sample_magnitude_catalog() -> pd.DataFrame:
    """Return a small synthetic earthquake catalog."""

    return pd.DataFrame(
        {
            "event_id": [
                "eq1",
                "eq2",
                "eq3",
                "eq4",
                "eq5",
                "eq6",
            ],
            "source": [
                "USGS",
                "USGS",
                "USGS",
                "USGS",
                "USGS",
                "USGS",
            ],
            "event_time_utc": [
                "2024-01-01T01:00:00Z",
                "2024-01-01T12:00:00Z",
                "2024-01-03T06:00:00Z",
                "2024-01-04T08:00:00Z",
                "2024-01-04T10:00:00Z",
                "2024-01-04T12:00:00Z",
            ],
            "magnitude": [
                0.8,
                1.4,
                2.6,
                3.5,
                4.7,
                None,
            ],
            "place": [
                "Location A",
                "Location B",
                "Location C",
                "Location D",
                "Location E",
                "Location F",
            ],
        }
    )


@pytest.mark.parametrize(
    ("magnitude", "expected"),
    [
        (0.5, "below_1"),
        (0.999, "below_1"),
        (1.0, "1_to_1_9"),
        (1.999, "1_to_1_9"),
        (2.0, "2_to_2_9"),
        (2.999, "2_to_2_9"),
        (3.0, "3_to_3_9"),
        (3.999, "3_to_3_9"),
        (4.0, "4_to_4_9"),
        (4.999, "4_to_4_9"),
        (5.0, "5_plus"),
        (6.2, "5_plus"),
        (None, "unavailable"),
    ],
)
def test_classify_magnitude_band(
    magnitude: float | None,
    expected: str,
):
    """Magnitudes should be assigned to the correct band."""

    assert classify_magnitude_band(magnitude) == expected


def test_validate_catalog_removes_duplicates():
    """Duplicate provider event IDs should be removed."""

    catalog = sample_magnitude_catalog()

    duplicate = catalog.iloc[[0]].copy()
    duplicate["magnitude"] = 1.1

    combined = pd.concat(
        [catalog, duplicate],
        ignore_index=True,
    )

    validated = validate_magnitude_catalog(combined)

    assert len(validated) == len(catalog)

    retained = validated.loc[
        validated["event_id"] == "eq1",
        "magnitude",
    ].iloc[0]

    assert retained == pytest.approx(1.1)


def test_add_magnitude_categories():
    """Threshold and magnitude-band columns should be added."""

    result = add_magnitude_categories(
        sample_magnitude_catalog()
    )

    eq4 = result.loc[
        result["event_id"] == "eq4"
    ].iloc[0]

    assert eq4["magnitude_band"] == "3_to_3_9"
    assert bool(eq4["magnitude_1_plus"]) is True
    assert bool(eq4["magnitude_2_plus"]) is True
    assert bool(eq4["magnitude_3_plus"]) is True
    assert bool(eq4["magnitude_4_plus"]) is False


def test_daily_magnitude_contains_inactive_day():
    """Missing calendar days should be inserted."""

    daily = build_daily_magnitude(
        sample_magnitude_catalog(),
        include_inactive_days=True,
    )

    jan2 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-02")
    ].iloc[0]

    assert jan2["event_count"] == 0
    assert jan2["events_with_magnitude"] == 0
    assert jan2["missing_magnitude_count"] == 0
    assert pd.isna(jan2["average_magnitude"])


def test_daily_magnitude_statistics():
    """Daily magnitude statistics should be calculated correctly."""

    daily = build_daily_magnitude(
        sample_magnitude_catalog(),
        include_inactive_days=False,
    )

    jan1 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-01")
    ].iloc[0]

    assert jan1["event_count"] == 2
    assert jan1["events_with_magnitude"] == 2
    assert jan1["average_magnitude"] == pytest.approx(1.1)
    assert jan1["minimum_magnitude"] == pytest.approx(0.8)
    assert jan1["maximum_magnitude"] == pytest.approx(1.4)
    assert jan1["magnitude_1_plus"] == 1
    assert jan1["magnitude_2_plus"] == 0


def test_daily_missing_magnitude_count():
    """Events without magnitude should be counted."""

    daily = build_daily_magnitude(
        sample_magnitude_catalog(),
        include_inactive_days=False,
    )

    jan4 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-04")
    ].iloc[0]

    assert jan4["event_count"] == 3
    assert jan4["events_with_magnitude"] == 2
    assert jan4["missing_magnitude_count"] == 1


def test_magnitude_summary():
    """The period summary should identify the largest event."""

    summary = summarize_magnitude(
        sample_magnitude_catalog()
    )

    assert summary.total_events == 6
    assert summary.events_with_magnitude == 5
    assert summary.missing_magnitude_count == 1
    assert summary.minimum_magnitude == 0.8
    assert summary.maximum_magnitude == 4.7
    assert summary.magnitude_3_plus == 2
    assert summary.magnitude_4_plus == 1
    assert summary.magnitude_5_plus == 0
    assert summary.largest_event_id == "eq5"
    assert summary.largest_event_place == "Location E"


def test_rolling_magnitude_columns():
    """Rolling magnitude calculations should be added."""

    daily = build_daily_magnitude(
        sample_magnitude_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_magnitude_metrics(daily)

    assert "average_magnitude_7d" in metrics.columns
    assert "maximum_magnitude_7d" in metrics.columns
    assert (
        "historical_expanding_average_magnitude"
        in metrics.columns
    )


def test_rolling_magnitude_avoids_future_leakage():
    """The first historical comparison must be unavailable."""

    daily = build_daily_magnitude(
        sample_magnitude_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_magnitude_metrics(daily)

    assert pd.isna(
        metrics.iloc[0][
            "historical_expanding_average_magnitude"
        ]
    )


def test_empty_magnitude_summary():
    """A catalog without usable magnitudes should return null metrics."""

    catalog = pd.DataFrame(
        {
            "event_id": ["eq1"],
            "event_time_utc": [
                "2024-01-01T01:00:00Z"
            ],
            "magnitude": [None],
        }
    )

    summary = summarize_magnitude(catalog)

    assert summary.total_events == 1
    assert summary.events_with_magnitude == 0
    assert summary.missing_magnitude_count == 1
    assert summary.average_magnitude is None
    assert summary.maximum_magnitude is None
    assert summary.largest_event_id is None