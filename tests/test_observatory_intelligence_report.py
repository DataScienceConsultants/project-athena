"""Focused integration tests for the unified Observatory intelligence report."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.observatory import (
    ObservatoryIntelligenceConfiguration,
    build_observatory_intelligence_report,
    render_intelligence_terminal_report,
    save_intelligence_report_json,
)
from src.timeseries import TimeSeriesConfiguration


def _catalog(days: int = 14) -> pd.DataFrame:
    rows = []
    for day in range(days):
        rows.append({"event_id": f"event-{day}", "source": "USGS", "event_time_utc": f"2024-01-{day + 1:02d}T12:00:00Z", "magnitude": 2.0, "depth_km": 8.0})
    return pd.DataFrame(rows)


def _build(monkeypatch: pytest.MonkeyPatch, catalog: pd.DataFrame, configuration: ObservatoryIntelligenceConfiguration | None = None):
    import src.observatory.intelligence as intelligence

    monkeypatch.setattr(intelligence, "load_catalog", lambda _: catalog.copy(deep=True))
    monkeypatch.setattr(intelligence, "resolve_region", lambda **_: ("puerto_rico", "Puerto Rico"))
    return build_observatory_intelligence_report("catalog.csv", configuration=configuration)


def _configuration(**changes: object) -> ObservatoryIntelligenceConfiguration:
    values = {"time_series_configuration": TimeSeriesConfiguration(baseline_lookback_periods=3, minimum_baseline_periods=2)}
    values.update(changes)
    return ObservatoryIntelligenceConfiguration(**values)


def test_full_integration_serialization_rendering_and_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _build(monkeypatch, _catalog(), _configuration())
    assert report.observatory.catalog.event_count == 14
    assert report.snapshot.latest_anomaly is not None
    assert report.recent_periods
    first = report.to_dict()
    assert first == report.to_dict()
    assert json.dumps(first, allow_nan=False)
    assert first["metadata"]["catalog_as_of_utc"].endswith("Z")
    output = render_intelligence_terminal_report(report)
    for heading in ("PROJECT ATHENA SEISMIC OBSERVATORY INTELLIGENCE REPORT", "LATEST ANALYTICAL SNAPSHOT", "TEMPORAL ANOMALY TREND", "RECENT PERIODS", "EXECUTIVE SUMMARY", "DISCLAIMER"):
        assert heading in output
    path = save_intelligence_report_json(report, tmp_path / "nested" / "report.json")
    assert json.loads(path.read_text()) == first


def test_configuration_immutability_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(TypeError):
        ObservatoryIntelligenceConfiguration(recent_period_limit=True)
    with pytest.raises(ValueError):
        ObservatoryIntelligenceConfiguration(recent_period_limit=0)
    with pytest.raises(TypeError):
        ObservatoryIntelligenceConfiguration(include_metric_details=1)  # type: ignore[arg-type]
    report = _build(monkeypatch, _catalog(), _configuration())
    with pytest.raises(FrozenInstanceError):
        report.snapshot.summary = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.recent_periods = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        report.metadata["changed"] = True  # type: ignore[index]


def test_serialization_options_and_recent_period_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    full = _build(monkeypatch, _catalog(), _configuration(recent_period_limit=3))
    compact = _build(monkeypatch, _catalog(), _configuration(include_time_series_points=False, include_metric_details=False))
    assert "points" not in compact.to_dict()["time_series"]
    assert "points" in full.to_dict()["time_series"]
    assert "metric_scores" not in json.dumps(compact.to_dict())
    assert compact.time_series.points  # underlying result remains intact
    filtered = _build(monkeypatch, _catalog(4), _configuration(include_unavailable_periods=False))
    unfiltered = _build(monkeypatch, _catalog(4), _configuration(include_unavailable_periods=True))
    assert filtered.time_series.candidate_period_count == unfiltered.time_series.candidate_period_count
    assert all(point.anomaly is not None for point in filtered.recent_periods)
    assert tuple(sorted(full.recent_periods, key=lambda point: point.period_start)) == full.recent_periods


def test_snapshot_prefers_latest_anomaly_but_recent_keeps_latest_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _configuration(time_series_configuration=TimeSeriesConfiguration(baseline_lookback_periods=3, minimum_baseline_periods=2, analysis_end=datetime(2024, 1, 16, tzinfo=timezone.utc)))
    report = _build(monkeypatch, _catalog(14), config)
    assert report.snapshot.latest_anomaly is not None
    assert report.snapshot.latest_period_start <= report.recent_periods[-1].period_start


def test_all_unavailable_and_insufficient_trend_render_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _configuration(time_series_configuration=TimeSeriesConfiguration(baseline_lookback_periods=7, minimum_baseline_periods=7, analysis_start=datetime(2024, 1, 1, tzinfo=timezone.utc), analysis_end=datetime(2024, 1, 4, tzinfo=timezone.utc)))
    report = _build(monkeypatch, _catalog(3), config)
    assert report.snapshot.latest_available is False
    assert report.time_series.available_period_count == 0
    assert "Unavailable" in render_intelligence_terminal_report(report)
    assert "descriptive" in report.disclaimer and "nonpredictive" in report.disclaimer
    assert "do not predict earthquakes" in report.disclaimer
    assert "future earthquake probability" in report.disclaimer and "official" in report.disclaimer


def test_unified_builder_loads_catalog_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.observatory.intelligence as intelligence

    calls = 0
    def load_once(_: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return _catalog()
    monkeypatch.setattr(intelligence, "load_catalog", load_once)
    monkeypatch.setattr(intelligence, "resolve_region", lambda **_: ("puerto_rico", "Puerto Rico"))
    build_observatory_intelligence_report("catalog.csv", configuration=_configuration())
    assert calls == 1
