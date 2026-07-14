"""Tests for Project Athena activity metrics."""

from __future__ import annotations

import pandas as pd

from src.metrics.activity import (
    add_rolling_activity_metrics,
    build_daily_activity,
    summarize_activity,
)


def sample_catalog() -> pd.DataFrame:
    """Return a small synthetic earthquake catalog."""

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
                "2024-01-02T06:00:00Z",
                "2024-01-04T08:00:00Z",
                "2024-01-04T22:00:00Z",
            ],
            "magnitude": [
                1.2,
                2.4,
                3.2,
                4.8,
                1.5,
            ],
        }
    )


def test_daily_activity_contains_missing_days():
    """Inactive days should be inserted."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=True,
    )

    assert len(daily) == 4

    jan3 = daily.loc[daily["date"] == "2024-01-03"]

    assert jan3.iloc[0]["event_count"] == 0


def test_daily_counts():
    """Daily earthquake counts should be correct."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=False,
    )

    assert daily.iloc[0]["event_count"] == 2
    assert daily.iloc[1]["event_count"] == 1
    assert daily.iloc[2]["event_count"] == 2


def test_magnitude_thresholds():
    """Magnitude bucket counts should be correct."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=False,
    )

    jan1 = daily.iloc[0]

    assert jan1["magnitude_1_plus"] == 2
    assert jan1["magnitude_2_plus"] == 1
    assert jan1["magnitude_3_plus"] == 0

    jan4 = daily.iloc[2]

    assert jan4["magnitude_4_plus"] == 1


def test_activity_summary():
    """Summary statistics should be correct."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=True,
    )

    summary = summarize_activity(daily)

    assert summary.total_events == 5
    assert summary.active_days == 3
    assert summary.calendar_days == 4
    assert summary.maximum_events_in_one_day == 2


def test_rolling_metrics():
    """Rolling metrics should be added."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_activity_metrics(
        daily,
    )

    assert "event_count_7d" in metrics.columns
    assert "daily_average_7d" in metrics.columns
    assert "activity_ratio_7d" in metrics.columns


def test_no_future_data_leakage():
    """Historical averages should not use future information."""

    daily = build_daily_activity(
        sample_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_activity_metrics(
        daily,
    )

    first_day = metrics.iloc[0]

    assert pd.isna(
        first_day["historical_expanding_average"]
    )