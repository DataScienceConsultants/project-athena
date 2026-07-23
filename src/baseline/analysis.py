"""Deterministic, descriptive UTC historical seismic baseline calculations.

Standard deviations use the population convention (``ddof=0``).  Percentile
ranks are the percentage of historical values less than or equal to a value.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from src.baseline.models import (
    BaselineConfiguration, BaselineMetric, BaselinePeriod, CurrentMetricComparison,
    CurrentPeriodComparison, HistoricalBaselineResult, HistoricalPeriodSummary,
)
from src.metrics.energy import magnitude_to_energy_joules

_METRICS = (
    "event_count", "event_rate_per_day", "mean_magnitude", "median_magnitude",
    "maximum_magnitude", "minimum_magnitude", "magnitude_event_count",
    "mean_depth_km", "median_depth_km", "minimum_depth_km", "maximum_depth_km",
    "depth_event_count", "total_energy_joules", "mean_energy_joules",
    "maximum_energy_joules", "energy_event_count", "rolling_event_count_mean",
)
_PRIMARY = ("event_count", "event_rate_per_day", "mean_magnitude", "maximum_magnitude", "mean_depth_km", "total_energy_joules")


def _normalized_frame(dataframe: pd.DataFrame, timestamp_column: str, magnitude_column: str, depth_column: str) -> tuple[pd.DataFrame, int]:
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame.")
    required = {timestamp_column, magnitude_column, depth_column}
    missing = required.difference(dataframe.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {', '.join(sorted(missing))}")
    frame = dataframe[[timestamp_column, magnitude_column, depth_column]].copy()
    raw_time = frame[timestamp_column]
    missing_time = raw_time.isna()
    parsed = pd.to_datetime(raw_time, utc=True, errors="coerce")
    if (parsed.isna() & ~missing_time).any():
        raise ValueError("Timestamp column contains invalid timestamps.")
    frame["_time"] = parsed
    for source, target in ((magnitude_column, "_magnitude"), (depth_column, "_depth")):
        values = frame[source]
        if values.map(lambda value: isinstance(value, bool)).any():
            raise TypeError(f"{source} values must be numeric, not boolean.")
        numeric = pd.to_numeric(values, errors="coerce")
        invalid = values.notna() & numeric.isna()
        if invalid.any():
            raise ValueError(f"{source} values must be numeric when present.")
        if numeric.dropna().map(lambda value: not math.isfinite(float(value))).any():
            raise ValueError(f"{source} values must be finite when present.")
        frame[target] = numeric
    return frame.loc[~missing_time].copy(), int(missing_time.sum())


def _period_start(value: pd.Timestamp, period: BaselinePeriod) -> pd.Timestamp:
    day = value.normalize()
    if period is BaselinePeriod.DAILY:
        return day
    if period is BaselinePeriod.WEEKLY:
        return day - timedelta(days=int(day.weekday()))
    return day.replace(day=1)


def _next(start: pd.Timestamp, period: BaselinePeriod) -> pd.Timestamp:
    if period is BaselinePeriod.DAILY:
        return start + timedelta(days=1)
    if period is BaselinePeriod.WEEKLY:
        return start + timedelta(days=7)
    return start + pd.DateOffset(months=1)


def _value_stats(values: list[float], name: str, configuration: BaselineConfiguration) -> BaselineMetric:
    if not values:
        return BaselineMetric(name, 0, None, None, None, None, None, None, None)
    series = pd.Series(values, dtype=float)
    return BaselineMetric(name, len(values), float(series.mean()), float(series.median()), float(series.std(ddof=0)), float(series.min()), float(series.max()), float(series.quantile(configuration.lower_percentile / 100)), float(series.quantile(configuration.upper_percentile / 100)))


def _summary(start: pd.Timestamp, period: BaselinePeriod, events: pd.DataFrame) -> HistoricalPeriodSummary:
    end = _next(start, period)
    magnitudes = events["_magnitude"].dropna()
    depths = events["_depth"].dropna()
    energies = magnitudes.map(magnitude_to_energy_joules)
    def stat(series: pd.Series, method: str) -> float | None:
        return None if series.empty else float(getattr(series, method)())
    days = (end - start) / timedelta(days=1)
    return HistoricalPeriodSummary(start.to_pydatetime(), end.to_pydatetime(), period, len(events), len(events) / days,
        stat(magnitudes, "mean"), stat(magnitudes, "median"), stat(magnitudes, "max"), stat(magnitudes, "min"), len(magnitudes),
        stat(depths, "mean"), stat(depths, "median"), stat(depths, "min"), stat(depths, "max"), len(depths),
        stat(energies, "sum"), stat(energies, "mean"), stat(energies, "max"), len(energies), None)


def calculate_historical_baselines(dataframe: pd.DataFrame, configuration: BaselineConfiguration | None = None, *, timestamp_column: str = "time", magnitude_column: str = "magnitude", depth_column: str = "depth") -> HistoricalBaselineResult:
    """Calculate calendar-period baselines, including every zero-event period."""
    configuration = configuration or BaselineConfiguration()
    if not isinstance(configuration, BaselineConfiguration):
        raise TypeError("configuration must be a BaselineConfiguration.")
    if dataframe.empty:
        raise ValueError("Historical input must not be empty.")
    frame, excluded = _normalized_frame(dataframe, timestamp_column, magnitude_column, depth_column)
    if frame.empty:
        raise ValueError("Historical input has no valid timestamps.")
    first, last = frame["_time"].min(), frame["_time"].max()
    start, finish = _period_start(first, configuration.period), _period_start(last, configuration.period)
    starts: list[pd.Timestamp] = []
    cursor = start
    while cursor <= finish:
        starts.append(cursor)
        cursor = _next(cursor, configuration.period)
    frame["_period"] = frame["_time"].map(lambda value: _period_start(value, configuration.period))
    grouped = {key: value for key, value in frame.groupby("_period", sort=True)}
    summaries = [_summary(item, configuration.period, grouped.get(item, frame.iloc[0:0])) for item in starts]
    rolling = pd.Series([item.event_count for item in summaries], dtype=float).rolling(configuration.rolling_window, min_periods=configuration.minimum_periods).mean()
    summaries = [HistoricalPeriodSummary(**{**{key: getattr(item, key) for key in item.__dataclass_fields__}, "rolling_event_count_mean": None if pd.isna(rolling.iloc[index]) else float(rolling.iloc[index])}) for index, item in enumerate(summaries)]
    metrics = OrderedDict((name, _value_stats([float(getattr(item, name)) for item in summaries if getattr(item, name) is not None], name, configuration)) for name in _METRICS)
    return HistoricalBaselineResult(configuration, first.to_pydatetime(), last.to_pydatetime(), len(dataframe), len(frame), excluded, len(summaries), tuple(summaries), metrics)


def _as_utc(value: datetime | str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError("Current interval timestamps must be valid datetimes.")
    return parsed


def compare_current_period(dataframe: pd.DataFrame, baseline: HistoricalBaselineResult, *, current_start: datetime | str, current_end: datetime | str, timestamp_column: str = "time", magnitude_column: str = "magnitude", depth_column: str = "depth") -> CurrentPeriodComparison:
    """Compare an explicit interval descriptively; a zero historical mean has ratio 1 for zero current values and otherwise no ratio."""
    if not isinstance(baseline, HistoricalBaselineResult):
        raise TypeError("baseline must be a HistoricalBaselineResult.")
    start, end = _as_utc(current_start), _as_utc(current_end)
    if end <= start:
        raise ValueError("current_end must be later than current_start.")
    frame, _ = _normalized_frame(dataframe, timestamp_column, magnitude_column, depth_column)
    frame = frame.loc[(frame["_time"] >= start) & (frame["_time"] < end)]
    days = (end - start) / timedelta(days=1)
    current = _summary(start, BaselinePeriod.DAILY, frame)
    values: dict[str, float | None] = {name: getattr(current, name) for name in _PRIMARY}
    values["event_rate_per_day"] = len(frame) / days
    result: OrderedDict[str, CurrentMetricComparison] = OrderedDict()
    for name in _PRIMARY:
        metric, value = baseline.metrics[name], values[name]
        history = [float(getattr(item, name)) for item in baseline.periods if getattr(item, name) is not None]
        if value is None or metric.mean is None or metric.lower_percentile is None:
            result[name] = CurrentMetricComparison(value, metric.mean, metric.median, metric.lower_percentile, metric.upper_percentile, None, None, None, "unavailable")
            continue
        classification = "below_historical_range" if value < metric.lower_percentile else "above_historical_range" if value > metric.upper_percentile else "within_historical_range"
        ratio = value / metric.mean if metric.mean != 0 else (1.0 if value == 0 else None)
        rank = 100 * sum(item <= value for item in history) / len(history)
        result[name] = CurrentMetricComparison(value, metric.mean, metric.median, metric.lower_percentile, metric.upper_percentile, rank, value - metric.mean, ratio, classification)
    return CurrentPeriodComparison(start.to_pydatetime(), end.to_pydatetime(), result)
