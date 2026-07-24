"""Integration coverage for the descriptive observatory time-series API."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pandas.testing as pdt
import pytest

from src.timeseries import TimeSeriesConfiguration, TimeSeriesFrequency, build_observatory_time_series


def _catalog(days: int = 12) -> pd.DataFrame:
    return pd.DataFrame({"time": pd.date_range("2024-01-01T12:00:00Z", periods=days, freq="D"), "magnitude": [2.0] * days, "depth": [5.0] * days})


def test_daily_pipeline_is_ordered_immutable_and_deterministic() -> None:
    catalog = _catalog()
    original = catalog.copy(deep=True)
    config = TimeSeriesConfiguration(baseline_lookback_periods=3, minimum_baseline_periods=2)
    first = build_observatory_time_series(catalog, config)
    second = build_observatory_time_series(catalog.copy(deep=True), config)
    assert first.to_dict() == second.to_dict()
    assert first.candidate_period_count == 10
    assert first.available_period_count == 10
    assert first.points[0].period_start.isoformat() == "2024-01-03T00:00:00+00:00"
    assert first.points[0].baseline_start.isoformat() == "2023-12-31T00:00:00+00:00"
    assert first.points[0].comparison is not None
    assert first.points[0].anomaly is not None
    assert first.trend.source_result_count == 10
    with pytest.raises(TypeError):
        first.metadata["x"] = 1
    pdt.assert_frame_equal(catalog, original)
    assert json.dumps(first.to_dict())


def test_empty_current_period_and_insufficient_history_are_explicit() -> None:
    catalog = _catalog(4)
    result = build_observatory_time_series(catalog, TimeSeriesConfiguration(baseline_lookback_periods=2, minimum_baseline_periods=2, analysis_start=datetime(2024, 1, 1, tzinfo=timezone.utc), analysis_end=datetime(2024, 1, 6, tzinfo=timezone.utc)))
    assert result.points[0].unavailable_reason == "insufficient_baseline_history"
    empty = next(point for point in result.points if point.period_start.day == 5)
    assert empty.current_event_count == 0
    assert empty.anomaly is not None


def test_weekly_monthly_and_hard_end_boundaries() -> None:
    catalog = _catalog(100)
    weekly = build_observatory_time_series(catalog, TimeSeriesConfiguration(frequency=TimeSeriesFrequency.WEEKLY, baseline_lookback_periods=2, minimum_baseline_periods=1))
    assert all(point.period_start.weekday() == 0 for point in weekly.points)
    assert all((point.period_end - point.period_start).days == 7 for point in weekly.points)
    monthly = build_observatory_time_series(catalog, TimeSeriesConfiguration(frequency=TimeSeriesFrequency.MONTHLY, baseline_lookback_periods=2, minimum_baseline_periods=1))
    assert all(point.period_start.day == point.period_end.day == 1 for point in monthly.points)
    assert all(point.period_end > point.period_start for point in monthly.points)


def test_empty_catalog_and_validation() -> None:
    empty = pd.DataFrame({"time": [], "magnitude": [], "depth": []})
    result = build_observatory_time_series(empty)
    assert result.points == ()
    assert result.anomaly_results == ()
    assert "nonpredictive" in result.summary
    with pytest.raises(ValueError, match="missing required columns"):
        build_observatory_time_series(pd.DataFrame({"time": []}))
    with pytest.raises(TypeError):
        TimeSeriesConfiguration(frequency="daily")
