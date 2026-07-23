"""Deterministic scoring of current seismic activity against historical baselines."""

from __future__ import annotations

import math
from collections import OrderedDict

from src.anomaly.models import (
    AnomalyDirection,
    AnomalyLevel,
    AnomalyMetricConfiguration,
    AnomalyScoringConfiguration,
    MetricAnomalyScore,
    SeismicAnomalyResult,
)
from src.baseline.models import CurrentMetricComparison, CurrentPeriodComparison


def _is_finite(value: float | None) -> bool:
    return (
        value is not None
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _unavailable_explanation(
    metric: AnomalyMetricConfiguration, comparison: CurrentMetricComparison | None
) -> str:
    if comparison is None:
        reason = "it was not included in the current-period comparison"
    elif comparison.current_value is None:
        if "magnitude" in metric.metric_name or "energy" in metric.metric_name:
            reason = "the current interval contains no magnitude values"
        elif "depth" in metric.metric_name:
            reason = "the current interval contains no depth values"
        else:
            reason = "the current interval contains no values"
    elif comparison.historical_mean is None:
        reason = "no historical mean is available"
    elif comparison.percentile_rank is None:
        reason = "no historical percentile rank is available"
    else:
        reason = "its comparison values are invalid"
    return f"{metric.metric_name} is unavailable because {reason}."


def _level(score: float, configuration: AnomalyScoringConfiguration) -> AnomalyLevel:
    if score < configuration.noteworthy_threshold:
        return AnomalyLevel.TYPICAL
    if score < configuration.elevated_threshold:
        return AnomalyLevel.NOTEWORTHY
    if score < configuration.extreme_threshold:
        return AnomalyLevel.ELEVATED
    return AnomalyLevel.EXTREME


def calculate_anomaly_score(
    comparison: CurrentPeriodComparison,
    configuration: AnomalyScoringConfiguration | None = None,
) -> SeismicAnomalyResult:
    """Describe how unusual a current period is without making predictions or warnings."""
    if not isinstance(comparison, CurrentPeriodComparison):
        raise TypeError("comparison must be a CurrentPeriodComparison.")
    configuration = configuration or AnomalyScoringConfiguration()
    if not isinstance(configuration, AnomalyScoringConfiguration):
        raise TypeError("configuration must be an AnomalyScoringConfiguration.")

    available: list[tuple[AnomalyMetricConfiguration, CurrentMetricComparison]] = []
    for metric in configuration.metrics:
        value = comparison.metrics.get(metric.metric_name)
        if (
            value is None
            or not all(
                _is_finite(item)
                for item in (
                    value.current_value,
                    value.historical_mean,
                    value.percentile_rank,
                )
            )
            or not 0 <= float(value.percentile_rank) <= 100
        ):
            continue
        available.append((metric, value))
    total_weight = sum(metric.weight for metric, _ in available)
    scores: OrderedDict[str, MetricAnomalyScore] = OrderedDict()
    weighted_values: list[tuple[str, float]] = []
    available_by_name = {metric.metric_name: value for metric, value in available}
    for metric in configuration.metrics:
        value = available_by_name.get(metric.metric_name)
        if value is None:
            comparison_value = comparison.metrics.get(metric.metric_name)
            scores[metric.metric_name] = MetricAnomalyScore(
                metric.metric_name,
                None if comparison_value is None else comparison_value.current_value,
                None if comparison_value is None else comparison_value.historical_mean,
                None if comparison_value is None else comparison_value.percentile_rank,
                AnomalyDirection.UNAVAILABLE,
                metric.two_sided,
                None,
                metric.weight,
                0.0,
                None,
                _unavailable_explanation(metric, comparison_value),
            )
            continue
        current, historical, rank = (
            float(value.current_value),
            float(value.historical_mean),
            float(value.percentile_rank),
        )
        direction = (
            AnomalyDirection.ABOVE
            if current > historical
            else AnomalyDirection.BELOW
            if current < historical
            else AnomalyDirection.TYPICAL
        )
        raw = (
            abs(rank - 50.0) * 2.0
            if metric.two_sided
            else max(0.0, (rank - 50.0) * 2.0)
        )
        raw = min(100.0, max(0.0, raw))
        normalized = metric.weight / total_weight
        weighted = raw * normalized
        detail = f"{metric.metric_name} is {direction.value} its historical mean and ranks at the {rank:.1f}th historical percentile"
        if metric.two_sided:
            detail += "; this metric is scored in both directions"
        scores[metric.metric_name] = MetricAnomalyScore(
            metric.metric_name,
            current,
            historical,
            rank,
            direction,
            metric.two_sided,
            raw,
            metric.weight,
            normalized,
            weighted,
            f"{detail}.",
        )
        weighted_values.append((metric.metric_name, weighted))
    if not weighted_values:
        return SeismicAnomalyResult(
            comparison.current_start,
            comparison.current_end,
            None,
            AnomalyLevel.UNAVAILABLE,
            0,
            len(configuration.metrics),
            scores,
            "An anomaly score could not be calculated because none of the configured metrics were available. This result is descriptive and nonpredictive.",
        )
    score = min(100.0, max(0.0, sum(value for _, value in weighted_values)))
    level = _level(score, configuration)
    strongest = max(weighted_values, key=lambda item: item[1])[0]
    summary = f"Current seismic activity has an anomaly score of {score:.1f}/100, classified as {level.value}. The strongest contribution came from {strongest}. This is a descriptive historical comparison and is not an earthquake prediction or warning."
    return SeismicAnomalyResult(
        comparison.current_start,
        comparison.current_end,
        score,
        level,
        len(weighted_values),
        len(configuration.metrics),
        scores,
        summary,
    )
