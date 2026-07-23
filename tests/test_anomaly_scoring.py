from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from src.anomaly import (
    AnomalyDirection,
    AnomalyLevel,
    AnomalyMetricConfiguration,
    AnomalyScoringConfiguration,
    calculate_anomaly_score,
)
from src.baseline import (
    BaselineConfiguration,
    calculate_historical_baselines,
    compare_current_period,
)
from src.baseline.models import CurrentMetricComparison, CurrentPeriodComparison


def comparison(
    *metrics: tuple[str, float | None, float | None, float | None],
) -> CurrentPeriodComparison:
    values = {
        name: CurrentMetricComparison(
            current, mean, None, None, None, rank, None, None, "test"
        )
        for name, current, mean, rank in metrics
    }
    return CurrentPeriodComparison(
        datetime(2024, 1, 10, tzinfo=timezone.utc),
        datetime(2024, 1, 11, tzinfo=timezone.utc),
        values,
    )


@pytest.mark.parametrize(("rank", "expected"), [(25, 0), (50, 0), (75, 50), (100, 100)])
def test_one_sided_raw_score(rank: float, expected: float) -> None:
    result = calculate_anomaly_score(comparison(("event_count", 2, 1, rank)))
    assert result.metric_scores["event_count"].raw_score == expected


@pytest.mark.parametrize(
    ("rank", "expected"), [(0, 100), (25, 50), (50, 0), (75, 50), (100, 100)]
)
def test_two_sided_raw_score(rank: float, expected: float) -> None:
    config = AnomalyScoringConfiguration(
        (AnomalyMetricConfiguration("mean_depth_km", 1, True),)
    )
    result = calculate_anomaly_score(comparison(("mean_depth_km", 2, 2, rank)), config)
    assert result.metric_scores["mean_depth_km"].raw_score == expected
    assert result.metric_scores["mean_depth_km"].direction is AnomalyDirection.TYPICAL


def test_composite_score_and_renormalizes_available_weights() -> None:
    config = AnomalyScoringConfiguration(
        (
            AnomalyMetricConfiguration("event_count", 2),
            AnomalyMetricConfiguration("maximum_magnitude", 3),
            AnomalyMetricConfiguration("total_energy_joules", 5),
        )
    )
    result = calculate_anomaly_score(
        comparison(
            ("event_count", 3, 2, 75),
            ("maximum_magnitude", None, None, None),
            ("total_energy_joules", 4, 2, 100),
        ),
        config,
    )
    assert result.score == 85.71428571428572
    assert result.metric_scores["event_count"].normalized_weight == pytest.approx(2 / 7)
    assert result.metric_scores["maximum_magnitude"].weighted_score is None
    assert result.available_metric_count == 2


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (59.9, AnomalyLevel.TYPICAL),
        (60, AnomalyLevel.NOTEWORTHY),
        (80, AnomalyLevel.ELEVATED),
        (95, AnomalyLevel.EXTREME),
    ],
)
def test_level_threshold_boundaries(score: float, level: AnomalyLevel) -> None:
    rank = 50 + score / 2
    config = AnomalyScoringConfiguration(
        (AnomalyMetricConfiguration("event_count", 1),)
    )
    result = calculate_anomaly_score(comparison(("event_count", 2, 1, rank)), config)
    assert result.level is level


def test_unavailable_metrics_and_no_available_score() -> None:
    config = AnomalyScoringConfiguration(
        (AnomalyMetricConfiguration("maximum_magnitude", 1),)
    )
    result = calculate_anomaly_score(
        comparison(("maximum_magnitude", None, None, None)), config
    )
    metric = result.metric_scores["maximum_magnitude"]
    assert result.score is None
    assert result.level is AnomalyLevel.UNAVAILABLE
    assert metric.direction is AnomalyDirection.UNAVAILABLE
    assert "current interval contains no magnitude values" in metric.explanation


def test_configuration_and_result_are_immutable_and_serializable() -> None:
    config = AnomalyScoringConfiguration(
        (AnomalyMetricConfiguration("event_count", 1),)
    )
    result = calculate_anomaly_score(comparison(("event_count", 1, 1, 50)), config)
    with pytest.raises(FrozenInstanceError):
        config.extreme_threshold = 90  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.score = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.metric_scores["other"] = result.metric_scores["event_count"]  # type: ignore[index]
    serialized = result.to_dict()
    assert serialized["current_start"].endswith("Z")
    json.dumps(serialized)


@pytest.mark.parametrize("value", [True, 0, float("nan"), float("inf")])
def test_invalid_weights(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AnomalyMetricConfiguration("event_count", value)  # type: ignore[arg-type]


def test_invalid_configuration_values_and_duplicate_names() -> None:
    metric = AnomalyMetricConfiguration("event_count", 1)
    with pytest.raises(ValueError, match="unique"):
        AnomalyScoringConfiguration((metric, metric))
    with pytest.raises((TypeError, ValueError)):
        AnomalyScoringConfiguration((metric,), noteworthy_threshold=float("nan"))
    with pytest.raises(ValueError, match="thresholds"):
        AnomalyScoringConfiguration(
            (metric,), noteworthy_threshold=80, elevated_threshold=70
        )


def test_baseline_comparison_anomaly_integration() -> None:
    historical = pd.DataFrame(
        {
            "time": [
                "2024-01-01T00:00:00Z",
                "2024-01-02T00:00:00Z",
                "2024-01-03T00:00:00Z",
            ],
            "magnitude": [1.0, 2.0, 3.0],
            "depth": [5.0, 10.0, 15.0],
        }
    )
    baseline = calculate_historical_baselines(
        historical, BaselineConfiguration(period="daily")
    )
    current = pd.DataFrame(
        {"time": ["2024-01-10T00:00:00Z"], "magnitude": [4.0], "depth": [20.0]}
    )
    current_comparison = compare_current_period(
        current,
        baseline,
        current_start="2024-01-10T00:00:00Z",
        current_end="2024-01-11T00:00:00Z",
    )
    result = calculate_anomaly_score(current_comparison)
    assert result.available_metric_count == 4
    assert result.score is not None
