"""Focused tests for descriptive temporal anomaly-score trend analysis."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json

import pytest
import pandas as pd

from src.anomaly import AnomalyLevel, SeismicAnomalyResult
from src.anomaly import calculate_anomaly_score
from src.baseline import BaselineConfiguration, calculate_historical_baselines, compare_current_period
from src.trends import (
    TrendConfiguration,
    TrendDirection,
    TrendStrength,
    calculate_temporal_trend,
)


def anomaly(score: float | None, day: int) -> SeismicAnomalyResult:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    return SeismicAnomalyResult(start, start + timedelta(days=1), score, AnomalyLevel.TYPICAL, 0, 0, {}, "test")


def results(scores: list[float | None]) -> tuple[SeismicAnomalyResult, ...]:
    return tuple(anomaly(score, day) for day, score in enumerate(scores))


def test_increasing_sequence_is_sorted_and_described() -> None:
    trend = calculate_temporal_trend(tuple(reversed(results([10, 20, 30, 40]))))
    assert [point.score for point in trend.points] == [10, 20, 30, 40]
    assert trend.current_slope == 10
    assert trend.direction is TrendDirection.RAPIDLY_INCREASING
    assert trend.consecutive_increases == 3
    assert trend.percent_change_from_first == 300
    assert trend.maximum_score_start == anomaly(40, 3).current_start
    assert trend.minimum_score_start == anomaly(10, 0).current_start
    assert trend.momentum == 15


def test_decreasing_flat_and_noisy_sequences() -> None:
    decreasing = calculate_temporal_trend(results([80, 60, 40, 20]))
    assert decreasing.current_slope == -20
    assert decreasing.consecutive_decreases == 3
    assert decreasing.percent_change_from_first == -75
    flat = calculate_temporal_trend(results([25, 25, 25]))
    assert flat.current_slope == 0
    assert flat.direction is TrendDirection.STABLE
    assert flat.strength is TrendStrength.WEAK
    assert flat.momentum == 0
    assert flat.percent_change_from_first == 0
    noisy = calculate_temporal_trend(results([1, 4, 2, 5]))
    assert noisy.current_slope == pytest.approx(1.2)


def test_missing_scores_and_moving_averages() -> None:
    config = TrendConfiguration(short_window=2, medium_window=3, long_window=4)
    trend = calculate_temporal_trend(results([10, None, 30, 50]), config)
    assert trend.available_score_count == 3
    assert trend.unavailable_score_count == 1
    assert trend.points[1].available is False
    assert trend.points[1].short_moving_average == 10
    assert trend.points[2].short_moving_average == 20
    assert trend.points[3].short_moving_average == 40
    assert trend.points[3].medium_moving_average == 30
    assert trend.points[3].long_moving_average == 30
    assert trend.current_slope == 20


def test_non_overlapping_slope_segments_and_percent_zero() -> None:
    trend = calculate_temporal_trend(results([0, 2, 4, 10, 14, 18]), TrendConfiguration(slope_window=3, previous_slope_window=3))
    assert trend.previous_slope == 2
    assert trend.current_slope == 4
    assert trend.acceleration == 2
    assert trend.percent_change_from_first is None
    only_current = calculate_temporal_trend(results([1, 2, 3]), TrendConfiguration(slope_window=3, previous_slope_window=3))
    assert only_current.previous_slope is None
    assert only_current.acceleration is None


@pytest.mark.parametrize(
    ("scores", "direction"),
    [([0, 0.25], TrendDirection.STABLE), ([0, 3], TrendDirection.INCREASING), ([3, 0], TrendDirection.DECREASING), ([3.25, 0], TrendDirection.RAPIDLY_DECREASING)],
)
def test_direction_threshold_boundaries(scores: list[float], direction: TrendDirection) -> None:
    trend = calculate_temporal_trend(results(scores), TrendConfiguration(minimum_points=2))
    assert trend.direction is direction


def test_strength_threshold_boundaries() -> None:
    moderate = calculate_temporal_trend(
        results([0, 3]),
        TrendConfiguration(minimum_points=2, moderate_strength_threshold=80, strong_strength_threshold=90),
    )
    assert moderate.strength is TrendStrength.MODERATE
    strong = calculate_temporal_trend(
        results([0, 3]),
        TrendConfiguration(minimum_points=2, moderate_strength_threshold=70, strong_strength_threshold=80),
    )
    assert strong.strength is TrendStrength.STRONG


def test_empty_unavailable_ties_immutability_and_serialization() -> None:
    empty = calculate_temporal_trend(())
    assert empty.points == ()
    assert tuple(empty.windows) == ("short", "medium", "long")
    assert empty.direction is TrendDirection.INSUFFICIENT_DATA
    unavailable = calculate_temporal_trend(results([None, None]))
    assert unavailable.available_score_count == 0
    tied = calculate_temporal_trend(results([10, 20, 20, 10]))
    assert tied.maximum_score_start == anomaly(20, 1).current_start
    assert tied.minimum_score_start == anomaly(10, 0).current_start
    with pytest.raises(FrozenInstanceError):
        TrendConfiguration().short_window = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        tied.points[0].score = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        tied.summary = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        tied.windows["short"] = tied.windows["short"]  # type: ignore[index]
    serialized = tied.to_dict()
    assert serialized["points"][0]["current_start"].endswith("Z")
    assert serialized["direction"] == "stable"
    assert list(serialized["windows"]) == ["short", "medium", "long"]
    json.dumps(serialized)


@pytest.mark.parametrize("bad_score", [True, float("nan"), float("inf"), -1, 101])
def test_validation_of_inputs_scores_and_configuration(bad_score: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_temporal_trend((anomaly(bad_score, 0),))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        calculate_temporal_trend([])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        calculate_temporal_trend(("not an anomaly",))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        calculate_temporal_trend((anomaly(1, 0), anomaly(2, 0)))
    bad_interval = SeismicAnomalyResult(datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc), 1, AnomalyLevel.TYPICAL, 0, 0, {}, "test")
    with pytest.raises(ValueError):
        calculate_temporal_trend((bad_interval,))
    with pytest.raises((TypeError, ValueError)):
        TrendConfiguration(short_window=True)  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        TrendConfiguration(stable_slope_threshold=float("nan"))
    with pytest.raises((TypeError, ValueError)):
        TrendConfiguration(moderate_strength_threshold=True)  # type: ignore[arg-type]


def test_baseline_comparison_anomaly_trend_integration() -> None:
    historical = pd.DataFrame({
        "time": ["2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"],
        "magnitude": [1.0, 2.0, 3.0],
        "depth": [5.0, 10.0, 15.0],
    })
    baseline = calculate_historical_baselines(historical, BaselineConfiguration(period="daily"))
    anomaly_results = []
    for day, magnitude in enumerate((2.0, 3.0, 4.0), start=10):
        current = pd.DataFrame({"time": [f"2024-01-{day:02d}T00:00:00Z"], "magnitude": [magnitude], "depth": [20.0]})
        comparison = compare_current_period(current, baseline, current_start=f"2024-01-{day:02d}T00:00:00Z", current_end=f"2024-01-{day + 1:02d}T00:00:00Z")
        anomaly_results.append(calculate_anomaly_score(comparison))
    trend = calculate_temporal_trend(tuple(anomaly_results))
    assert trend.source_result_count == 3
    assert trend.available_score_count == 3
