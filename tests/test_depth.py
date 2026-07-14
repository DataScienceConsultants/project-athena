"""Tests for Project Athena depth metrics."""

from __future__ import annotations

import pandas as pd
import pytest

from src.metrics.depth import (
    add_depth_categories,
    add_rolling_depth_metrics,
    build_daily_depth,
    classify_depth,
    summarize_depth,
)


def sample_depth_catalog() -> pd.DataFrame:
    """Return a synthetic earthquake catalog."""

    return pd.DataFrame(
        {
            "event_id": [
                "eq1",
                "eq2",
                "eq3",
                "eq4",
                "eq5",
            ],
            "source": [
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
            ],
            "depth_km": [
                10.0,
                80.0,
                350.0,
                None,
                25.0,
            ],
        }
    )


@pytest.mark.parametrize(
    ("depth_km", "expected"),
    [
        (10.0, "shallow"),
        (69.999, "shallow"),
        (70.0, "intermediate"),
        (299.999, "intermediate"),
        (300.0, "deep"),
        (None, None),
    ],
)
def test_classify_depth(
    depth_km: float | None,
    expected: str | None,
):
    """Depth categories should follow configured boundaries."""

    assert classify_depth(depth_km) == expected


def test_add_depth_categories():
    """Every usable depth should receive a category."""

    result = add_depth_categories(
        sample_depth_catalog()
    )

    assert result.loc[
        result["event_id"] == "eq1",
        "depth_category",
    ].iloc[0] == "shallow"

    assert result.loc[
        result["event_id"] == "eq2",
        "depth_category",
    ].iloc[0] == "intermediate"

    assert result.loc[
        result["event_id"] == "eq3",
        "depth_category",
    ].iloc[0] == "deep"


def test_daily_depth_contains_inactive_day():
    """Missing calendar days should be inserted."""

    daily = build_daily_depth(
        sample_depth_catalog(),
        include_inactive_days=True,
    )

    jan2 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-02")
    ].iloc[0]

    assert jan2["event_count"] == 0
    assert jan2["events_with_depth"] == 0
    assert pd.isna(jan2["average_depth_km"])


def test_daily_depth_metrics():
    """Daily averages and category counts should be correct."""

    daily = build_daily_depth(
        sample_depth_catalog(),
        include_inactive_days=False,
    )

    jan1 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-01")
    ].iloc[0]

    assert jan1["event_count"] == 2
    assert jan1["events_with_depth"] == 2
    assert jan1["average_depth_km"] == pytest.approx(45.0)
    assert jan1["shallow_events"] == 1
    assert jan1["intermediate_events"] == 1


def test_depth_summary():
    """Depth summary should identify extreme events."""

    summary = summarize_depth(
        sample_depth_catalog()
    )

    assert summary.events_with_depth == 4
    assert summary.minimum_depth_km == 10.0
    assert summary.maximum_depth_km == 350.0
    assert summary.shallow_events == 2
    assert summary.intermediate_events == 1
    assert summary.deep_events == 1
    assert summary.shallowest_event_id == "eq1"
    assert summary.deepest_event_id == "eq3"


def test_rolling_depth_avoids_future_leakage():
    """The first historical comparison must be unavailable."""

    daily = build_daily_depth(
        sample_depth_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_depth_metrics(daily)

    assert pd.isna(
        metrics.iloc[0][
            "historical_expanding_depth_average_km"
        ]
    )