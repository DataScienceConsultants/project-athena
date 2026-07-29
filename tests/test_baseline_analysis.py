"""Tests for deterministic descriptive historical baseline analysis."""

from dataclasses import FrozenInstanceError
import json

import pandas as pd
import pytest

from src.baseline import BaselineConfiguration, BaselinePeriod, calculate_historical_baselines, compare_current_period
from src.metrics.energy import magnitude_to_energy_joules


def catalog() -> pd.DataFrame:
    return pd.DataFrame({"time": ["2024-01-01T01:00:00Z", "2024-01-03T02:00:00-05:00"], "magnitude": [0.0, 2.0], "depth": [0.0, 10.0]})


def test_daily_metrics_zero_periods_energy_and_utc() -> None:
    result = calculate_historical_baselines(catalog())
    assert result.period_count == 3
    assert [period.event_count for period in result.periods] == [1, 0, 1]
    assert result.periods[0].period_start.tzinfo is not None
    assert result.periods[0].mean_magnitude == 0.0
    assert result.periods[0].mean_depth_km == 0.0
    assert result.periods[0].total_energy_joules == magnitude_to_energy_joules(0.0)
    assert result.periods[1].mean_magnitude is None
    assert result.metrics["event_count"].mean == pytest.approx(2 / 3)
    assert [item.rolling_event_count_mean for item in result.periods] == [1.0, 0.5, pytest.approx(2 / 3)]


def test_weekly_and_monthly_calendar_periods() -> None:
    weekly = pd.DataFrame({"time": ["2024-01-01", "2024-01-08"], "magnitude": [1, 1], "depth": [1, 1]})
    assert calculate_historical_baselines(weekly, BaselineConfiguration(period=BaselinePeriod.WEEKLY)).period_count == 2
    assert calculate_historical_baselines(catalog(), BaselineConfiguration(period=BaselinePeriod.MONTHLY)).period_count == 1


def test_missing_and_custom_columns_do_not_mutate() -> None:
    frame = pd.DataFrame(
        {
            "when": ["2024-01-01", None],
            "mag": pd.Series([None, 3], dtype=object),
            "deep": pd.Series([None, 4], dtype=object),
        }
    )
    original = frame.copy(deep=True)
    result = calculate_historical_baselines(frame, timestamp_column="when", magnitude_column="mag", depth_column="deep")
    assert result.source_row_count == 2
    assert result.accepted_row_count == 1
    assert result.excluded_missing_timestamp_count == 1
    assert result.periods[0].event_count == 1
    assert result.periods[0].magnitude_event_count == 0
    pd.testing.assert_frame_equal(frame, original)


def test_pd_na_metric_values_are_allowed() -> None:
    frame = pd.DataFrame(
        {
            "time": ["2024-01-01"],
            "magnitude": pd.Series([pd.NA], dtype=object),
            "depth": pd.Series([pd.NA], dtype=object),
        }
    )

    result = calculate_historical_baselines(frame)

    assert result.periods[0].event_count == 1
    assert result.periods[0].magnitude_event_count == 0
    assert result.periods[0].depth_event_count == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_rejects_invalid_numeric_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_historical_baselines(pd.DataFrame({"time": ["2024-01-01"], "magnitude": [value], "depth": [1]}))


def test_invalid_input_configuration_immutability_and_json() -> None:
    with pytest.raises(ValueError, match="timestamps"):
        calculate_historical_baselines(pd.DataFrame({"time": ["nope"], "magnitude": [1], "depth": [1]}))
    with pytest.raises(ValueError):
        BaselineConfiguration(lower_percentile=90, upper_percentile=10)
    result = calculate_historical_baselines(catalog())
    with pytest.raises(FrozenInstanceError):
        result.configuration.rolling_window = 2  # type: ignore[misc]
    json.dumps(result.to_dict())


def test_current_comparison_ranks_ratios_and_zero_interval() -> None:
    historical = pd.DataFrame({"time": ["2024-01-01", "2024-01-02", "2024-01-03"], "magnitude": [1, 1, 1], "depth": [1, 1, 1]})
    baseline = calculate_historical_baselines(historical, BaselineConfiguration(lower_percentile=0, upper_percentile=100))
    current = pd.DataFrame({"time": [], "magnitude": [], "depth": []})
    comparison = compare_current_period(current, baseline, current_start="2024-02-01T00:00:00Z", current_end="2024-02-08T00:00:00Z")
    assert comparison.metrics["event_count"].current_value == 0
    assert comparison.metrics["event_rate_per_day"].current_value == 0
    assert comparison.metrics["event_count"].ratio_to_mean == 0
    assert comparison.metrics["mean_magnitude"].classification == "unavailable"
    assert comparison.metrics["event_count"].percentile_rank == 0
