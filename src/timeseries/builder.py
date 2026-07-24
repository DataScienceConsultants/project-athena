"""Calendar-aware orchestration of baseline, anomaly, and trend APIs."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Final

import pandas as pd

from src.anomaly import AnomalyScoringConfiguration, SeismicAnomalyResult, calculate_anomaly_score
from src.baseline import BaselineConfiguration, BaselinePeriod, CurrentPeriodComparison, calculate_historical_baselines, compare_current_period
from src.trends import TrendConfiguration, calculate_temporal_trend
from src.timeseries.models import ObservatoryTimeSeriesPoint, ObservatoryTimeSeriesResult, TimeSeriesConfiguration, TimeSeriesFrequency

_INSUFFICIENT: Final = "insufficient_baseline_history"
_EMPTY_BASELINE: Final = "empty_baseline_catalog"


def _baseline_configuration(configuration: TimeSeriesConfiguration) -> BaselineConfiguration:
    if configuration.baseline_configuration is not None:
        return configuration.baseline_configuration
    return BaselineConfiguration(
        period=BaselinePeriod(configuration.frequency.value),
        rolling_window=configuration.baseline_lookback_periods,
        minimum_periods=configuration.minimum_baseline_periods,
    )


def _floor(value: datetime, frequency: TimeSeriesFrequency) -> datetime:
    value = value.astimezone(timezone.utc)
    day = value.replace(hour=0, minute=0, second=0, microsecond=0)
    if frequency is TimeSeriesFrequency.DAILY:
        return day
    if frequency is TimeSeriesFrequency.WEEKLY:
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def _next(start: datetime, frequency: TimeSeriesFrequency) -> datetime:
    if frequency is TimeSeriesFrequency.DAILY:
        return start + timedelta(days=1)
    if frequency is TimeSeriesFrequency.WEEKLY:
        return start + timedelta(days=7)
    return (pd.Timestamp(start) + pd.DateOffset(months=1)).to_pydatetime()


def _shift(start: datetime, count: int, frequency: TimeSeriesFrequency) -> datetime:
    result = start
    step = 1 if count >= 0 else -1
    for _ in range(abs(count)):
        if step > 0:
            result = _next(result, frequency)
        elif frequency is TimeSeriesFrequency.MONTHLY:
            result = (pd.Timestamp(result) - pd.DateOffset(months=1)).to_pydatetime()
        else:
            result -= timedelta(days=1 if frequency is TimeSeriesFrequency.DAILY else 7)
    return result


def _normalize_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(catalog, pd.DataFrame):
        raise TypeError("catalog must be a pandas DataFrame.")
    missing = {"time", "magnitude", "depth"}.difference(catalog.columns)
    if missing:
        raise ValueError(f"Catalog is missing required columns: {', '.join(sorted(missing))}")
    frame = catalog.copy(deep=True)
    parsed = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    if parsed.isna().any():
        raise ValueError("Catalog time column contains invalid timestamps.")
    frame["time"] = parsed
    return frame.sort_values("time", kind="mergesort").reset_index(drop=True)


def _empty_point(start: datetime, end: datetime, baseline_start: datetime, count: int, current_count: int, reason: str) -> ObservatoryTimeSeriesPoint:
    return ObservatoryTimeSeriesPoint(start, end, baseline_start, start, count, current_count, False, None, None, reason)


def _build_summary(result: ObservatoryTimeSeriesResult) -> str:
    disclaimer = "This observatory time series is descriptive and nonpredictive. It is not an earthquake prediction or warning."
    if result.candidate_period_count == 0:
        return f"No {result.frequency.value} observatory time-series periods could be built from {result.source_event_count} catalog events. {disclaimer}"
    trend = result.trend
    classification = ""
    if trend.direction.value != "insufficient_data":
        classification = f" The latest temporal classification is {trend.direction.value} with {trend.strength.value} strength."
    return (f"Built {result.candidate_period_count} {result.frequency.value} observatory periods from "
            f"{result.source_event_count} catalog events. Anomaly scores were available for "
            f"{result.available_period_count} periods and unavailable for {result.unavailable_period_count} periods."
            f"{classification} {disclaimer}")


def build_observatory_time_series(catalog: pd.DataFrame, configuration: TimeSeriesConfiguration | None = None) -> ObservatoryTimeSeriesResult:
    """Build complete, half-open UTC observation periods without future-data leakage.

    Naive catalog timestamps are interpreted as UTC. Explicit analysis ends are hard
    bounds: a final partial natural period is omitted.
    """
    configuration = configuration or TimeSeriesConfiguration()
    if not isinstance(configuration, TimeSeriesConfiguration):
        raise TypeError("configuration must be a TimeSeriesConfiguration or None.")
    frame = _normalize_catalog(catalog)
    baseline_config = _baseline_configuration(configuration)
    anomaly_config = configuration.anomaly_configuration or AnomalyScoringConfiguration()
    trend_config = configuration.trend_configuration or TrendConfiguration()
    if frame.empty:
        trend = calculate_temporal_trend((), trend_config)
        metadata = {"baseline_lookback_periods": configuration.baseline_lookback_periods, "minimum_baseline_periods": configuration.minimum_baseline_periods, "include_unavailable_periods": configuration.include_unavailable_periods, "first_catalog_timestamp": None, "last_catalog_timestamp": None, "period_boundary_timezone": "UTC", "baseline_excludes_current_period": True, "generated_periods_are_half_open": True}
        result = ObservatoryTimeSeriesResult(configuration.analysis_start, configuration.analysis_end, configuration.frequency, 0, 0, 0, 0, (), (), trend, metadata, "")
        return replace(result, summary=_build_summary(result))
    first = frame["time"].iloc[0].to_pydatetime()
    last = frame["time"].iloc[-1].to_pydatetime()
    coverage_start = _floor(first, configuration.frequency)
    inferred_end = _next(_floor(last, configuration.frequency), configuration.frequency)
    start = _floor(configuration.analysis_start, configuration.frequency) if configuration.analysis_start else _shift(coverage_start, configuration.minimum_baseline_periods, configuration.frequency)
    hard_end = configuration.analysis_end
    end = hard_end if hard_end is not None else inferred_end
    boundaries: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        natural_end = _next(cursor, configuration.frequency)
        if natural_end > end:
            break
        boundaries.append((cursor, natural_end))
        cursor = natural_end
    points: list[ObservatoryTimeSeriesPoint] = []
    anomalies: list[SeismicAnomalyResult] = []
    for period_start, period_end in boundaries:
        complete_prior = 0
        prior_cursor = coverage_start
        while prior_cursor < period_start:
            complete_prior += 1
            prior_cursor = _next(prior_cursor, configuration.frequency)
        baseline_count = min(complete_prior, configuration.baseline_lookback_periods)
        baseline_start = _shift(period_start, -configuration.baseline_lookback_periods, configuration.frequency)
        current = frame.loc[(frame["time"] >= period_start) & (frame["time"] < period_end)]
        current_count = len(current)
        if complete_prior < configuration.minimum_baseline_periods:
            point = _empty_point(period_start, period_end, baseline_start, baseline_count, current_count, _INSUFFICIENT)
        else:
            baseline = frame.loc[(frame["time"] >= baseline_start) & (frame["time"] < period_start)]
            if baseline.empty:
                point = _empty_point(period_start, period_end, baseline_start, baseline_count, current_count, _EMPTY_BASELINE)
            else:
                historical = calculate_historical_baselines(baseline, baseline_config)
                comparison: CurrentPeriodComparison = compare_current_period(current, historical, current_start=period_start, current_end=period_end)
                anomaly = calculate_anomaly_score(comparison, anomaly_config)
                anomalies.append(anomaly)
                point = ObservatoryTimeSeriesPoint(period_start, period_end, baseline_start, period_start, baseline_count, current_count, True, comparison, anomaly, None)
        if configuration.include_unavailable_periods or point.anomaly is not None:
            points.append(point)
    trend = calculate_temporal_trend(tuple(anomalies), trend_config)
    metadata = {"baseline_lookback_periods": configuration.baseline_lookback_periods, "minimum_baseline_periods": configuration.minimum_baseline_periods, "include_unavailable_periods": configuration.include_unavailable_periods, "first_catalog_timestamp": first, "last_catalog_timestamp": last, "period_boundary_timezone": "UTC", "baseline_excludes_current_period": True, "generated_periods_are_half_open": True}
    result = ObservatoryTimeSeriesResult(configuration.analysis_start or start, configuration.analysis_end or inferred_end, configuration.frequency, len(frame), len(boundaries), len(anomalies), len(boundaries) - len(anomalies), tuple(anomalies), tuple(points), trend, metadata, "")
    return replace(result, summary=_build_summary(result))
