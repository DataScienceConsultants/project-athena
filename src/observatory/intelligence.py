"""Unified, descriptive Observatory intelligence-report integration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.metrics.activity import load_catalog
from src.observatory.builder import (
    METHODOLOGY_VERSION,
    find_latest_catalog,
    build_observatory_report_from_dataframe,
    resolve_region,
)
from src.observatory.models import (
    ObservatoryIntelligenceConfiguration,
    ObservatoryIntelligenceReport,
    ObservatoryIntelligenceSnapshot,
)
from src.observatory.thresholds import STATUS_DISPLAY_NAMES
from src.timeseries import build_observatory_time_series

INTELLIGENCE_DISCLAIMER = (
    "Project Athena reports describe historical seismic observations and analytical "
    "anomaly behavior. They are descriptive and nonpredictive. They do not predict "
    "earthquakes, estimate future earthquake probability, determine imminent danger, "
    "or replace official earthquake, tsunami, or emergency-management information."
)


def build_observatory_intelligence_report(
    catalog_path: str | Path | None = None,
    *,
    region_key: str | None = None,
    configuration: ObservatoryIntelligenceConfiguration | None = None,
) -> ObservatoryIntelligenceReport:
    """Build one deterministic report using one loaded catalog."""
    configuration = configuration or ObservatoryIntelligenceConfiguration()
    if not isinstance(configuration, ObservatoryIntelligenceConfiguration):
        raise TypeError("configuration must be an ObservatoryIntelligenceConfiguration or None.")
    path = Path(catalog_path) if catalog_path is not None else find_latest_catalog()
    catalog = load_catalog(path)
    key, name = resolve_region(catalog_path=path, region_key=region_key)
    observatory = build_observatory_report_from_dataframe(
        catalog, catalog_path=path, region_key=key, region_name=name
    )
    time_series_catalog = _time_series_catalog(catalog)
    series = build_observatory_time_series(
        time_series_catalog, configuration.time_series_configuration
    )
    snapshot = _snapshot(series)
    candidates = series.points
    if not configuration.include_unavailable_periods:
        candidates = tuple(point for point in candidates if point.anomaly is not None)
    recent = candidates[-configuration.recent_period_limit :]
    metadata: dict[str, object] = {
        "frequency": series.frequency.value,
        "baseline_lookback_periods": configuration.time_series_configuration.baseline_lookback_periods,
        "minimum_baseline_periods": configuration.time_series_configuration.minimum_baseline_periods,
        "recent_period_limit": configuration.recent_period_limit,
        "include_time_series_points": configuration.include_time_series_points,
        "include_unavailable_periods": configuration.include_unavailable_periods,
        "include_metric_details": configuration.include_metric_details,
        "source_catalog_path": observatory.catalog.catalog_path,
        "source_event_count": series.source_event_count,
        "available_period_count": series.available_period_count,
        "unavailable_period_count": series.unavailable_period_count,
        "baseline_excludes_current_period": True,
        "generated_periods_are_half_open": True,
        "report_is_nonpredictive": True,
    }
    return ObservatoryIntelligenceReport(
        schema_version="1.0", methodology_version=METHODOLOGY_VERSION,
        observatory=observatory, time_series=series, snapshot=snapshot,
        recent_periods=recent, metadata=metadata,
        executive_summary=_executive_summary(observatory, series, snapshot),
        disclaimer=INTELLIGENCE_DISCLAIMER,
        include_time_series_points=configuration.include_time_series_points,
    )


def _time_series_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    """Adapt the validated Observatory catalog without mutating it."""
    frame = catalog.copy(deep=True)
    frame["time"] = frame["event_time_utc"]
    if "depth" not in frame:
        if "depth_km" in frame:
            frame["depth"] = frame["depth_km"]
        else:
            frame["depth"] = float("nan")
    return frame


def _snapshot(series: Any) -> ObservatoryIntelligenceSnapshot:
    points = tuple(sorted(series.points, key=lambda point: point.period_start))
    available = [point for point in points if point.anomaly is not None]
    point = available[-1] if available else (points[-1] if points else None)
    if point is None:
        return ObservatoryIntelligenceSnapshot(None, None, None, None, None, None, None, None, series.trend, False, None, "No eligible Observatory time-series period was available for intelligence analysis.")
    anomaly = point.anomaly
    if anomaly is None:
        summary = (f"The latest {series.frequency.value} period could not be scored because "
                   "sufficient historical baseline information was unavailable. The available "
                   "anomaly-score history remains descriptive and nonpredictive.")
    else:
        score = "unavailable" if anomaly.score is None else f"{anomaly.score:.1f}"
        strongest = _strongest_contributor(anomaly) or "No metric"
        summary = (f"During the latest {series.frequency.value} period, {point.current_event_count} earthquakes were observed. "
                   f"The anomaly score was {score}, classified as {anomaly.level.value}. {strongest} was the strongest contributor. "
                   f"The anomaly-score trend is {series.trend.direction.value.replace('_', ' ')} with {series.trend.strength.value.replace('_', ' ')} strength.")
    return ObservatoryIntelligenceSnapshot(point.period_start, point.period_end, point.current_event_count, point.baseline_start, point.baseline_end, point.baseline_period_count, point.comparison, anomaly, series.trend, anomaly is not None, point.unavailable_reason, summary)


def _strongest_contributor(anomaly: Any) -> str | None:
    scores = [item for item in anomaly.metric_scores.values() if item.weighted_score is not None]
    if not scores:
        return None
    return max(scores, key=lambda item: item.weighted_score).metric_name.replace("_", " ")


def _executive_summary(observatory: Any, series: Any, snapshot: Any) -> str:
    status = STATUS_DISPLAY_NAMES[observatory.status.overall_status].lower()
    first = f"Project Athena analyzed {series.source_event_count} catalog events for {observatory.catalog.region_name}. The existing Observatory status is {status}."
    if snapshot.latest_anomaly is None:
        latest = " The latest observation period was unavailable for anomaly scoring."
    else:
        anomaly = snapshot.latest_anomaly
        score = "unavailable" if anomaly.score is None else f"{anomaly.score:.1f}"
        contributor = _strongest_contributor(anomaly)
        latest = (f" The latest {series.frequency.value} observation period contained {snapshot.latest_current_event_count} events and received an anomaly score of {score}, classified as {anomaly.level.value}" + (f", with {contributor} as the strongest contributor." if contributor else "."))
    trend = series.trend
    history = (f" Across {series.available_period_count} scored periods and {series.unavailable_period_count} unavailable periods, anomaly behavior is {trend.direction.value.replace('_', ' ')} with {trend.strength.value.replace('_', ' ')} strength.")
    return first + latest + history + " These findings describe historical seismic activity and are nonpredictive; they are not an earthquake forecast, warning, or estimate of future earthquake probability."
