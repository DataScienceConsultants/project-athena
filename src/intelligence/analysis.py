"""Descriptive seismic-intelligence calculations built on Observatory outputs."""

from __future__ import annotations

from src.intelligence.models import (
    ActivityTrend,
    ConfidenceLevel,
    IntelligenceConfiguration,
    SeismicIntelligence,
)
from src.timeseries import ObservatoryTimeSeriesResult

DISCLAIMER = (
    "This intelligence describes observed historical seismic activity. It is not "
    "earthquake prediction, a forecast, or an official warning."
)


def _trend(scores: list[float], configuration: IntelligenceConfiguration) -> tuple[ActivityTrend, float | None]:
    values = scores[-configuration.trend_window :]
    if len(values) < 2:
        return ActivityTrend.INSUFFICIENT_DATA, None
    change = values[-1] - values[0]
    if abs(change) <= configuration.stable_change_threshold:
        return ActivityTrend.STABLE, change
    return (ActivityTrend.INCREASING if change > 0 else ActivityTrend.DECREASING), change


def _confidence(
    available: int, total: int, configuration: IntelligenceConfiguration
) -> tuple[ConfidenceLevel, float]:
    completeness = available / total if total else 0.0
    history = min(available / configuration.high_confidence_periods, 1.0)
    score = round(100.0 * completeness * history, 1)
    if (
        available >= configuration.high_confidence_periods
        and completeness >= configuration.high_completeness_threshold
    ):
        return ConfidenceLevel.HIGH, score
    if available >= configuration.moderate_confidence_periods:
        return ConfidenceLevel.MODERATE, score
    return ConfidenceLevel.LOW, score


def calculate_seismic_intelligence(
    time_series: ObservatoryTimeSeriesResult,
    configuration: IntelligenceConfiguration | None = None,
) -> SeismicIntelligence:
    """Summarize existing anomaly scores without altering Observatory intelligence.

    The activity index is the arithmetic mean of the most recent available anomaly
    scores and therefore retains their documented 0--100 scale. Missing scores are
    excluded rather than silently treated as zero.
    """
    if not isinstance(time_series, ObservatoryTimeSeriesResult):
        raise TypeError("time_series must be an ObservatoryTimeSeriesResult.")
    configuration = configuration or IntelligenceConfiguration()
    if not isinstance(configuration, IntelligenceConfiguration):
        raise TypeError("configuration must be an IntelligenceConfiguration or None.")
    scores = [float(item.score) for item in time_series.anomaly_results if item.score is not None]
    recent = scores[-configuration.activity_window :]
    activity_index = round(sum(recent) / len(recent), 1) if recent else None
    trend, change = _trend(scores, configuration)
    available = len(scores)
    total = time_series.candidate_period_count
    confidence, confidence_score = _confidence(available, total, configuration)
    activity = "unavailable" if activity_index is None else f"{activity_index:.1f}"
    summary = (
        f"The recent descriptive activity index is {activity}; observed activity is "
        f"{trend.value.replace('_', ' ')} with {confidence.value} data confidence. "
        "This result describes catalog history and does not predict earthquakes."
    )
    return SeismicIntelligence(
        activity_index,
        len(recent),
        trend,
        None if change is None else round(change, 1),
        confidence,
        confidence_score,
        available,
        total - available,
        summary,
        DISCLAIMER,
    )


# Concise alias for callers that use the package as a report builder.
build_seismic_intelligence = calculate_seismic_intelligence
