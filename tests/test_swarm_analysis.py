"""Tests for descriptive seismic swarm analysis."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from src.swarm import (
    SeismicSwarm,
    SwarmAnalysisResult,
    SwarmMigration,
    SwarmTrend,
    analyze_swarms,
)


def _events(times: list[str] | None = None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": times or ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
            "latitude": [18.0, 18.0, 18.01, 18.01],
            "longitude": [-66.0, -65.99, -65.99, -65.98],
            "depth": [5.0, 6.0, 7.0, 8.0],
            "magnitude": [1.0, 1.5, 2.0, 2.5],
        },
        index=[10, 11, 12, 13],
    )


def test_characterizes_trends_migration_and_latest_event_reference():
    result = analyze_swarms(_events(), eps_km=3, recent_window_days=2)
    swarm = result.swarms[0]

    assert result.reference_time_utc == "2025-01-04T00:00:00+00:00"
    assert swarm.member_indices == (10, 11, 12, 13)
    assert swarm.duration_days == 3
    assert swarm.event_rate_per_day == pytest.approx(4 / 3)
    assert swarm.magnitude_trend.direction == "increasing"
    assert swarm.depth_trend.direction == "increasing"
    assert swarm.migration.distance_km > 0
    assert swarm.migration.bearing_degrees is not None
    assert swarm.migration.cardinal_direction == "NE"
    assert swarm.activity_status == "active"


@pytest.mark.parametrize(
    ("values", "direction"),
    [
        ([1, 2, 3, 4], "increasing"),
        ([4, 3, 2, 1], "decreasing"),
        ([2, 2, 2, 2], "stable"),
    ],
)
def test_trend_direction_classification(values: list[float], direction: str):
    frame = _events()
    frame["magnitude"] = values
    assert (
        analyze_swarms(frame, eps_km=3).swarms[0].magnitude_trend.direction == direction
    )


def test_zero_duration_has_insufficient_trends_and_stationary_migration():
    frame = _events(["2025-01-01"] * 4)
    frame["latitude"] = 18.0
    frame["longitude"] = -66.0
    swarm = analyze_swarms(frame, eps_km=3).swarms[0]

    assert swarm.duration_days == 0
    assert swarm.magnitude_trend.direction == "insufficient_data"
    assert swarm.depth_trend.direction == "insufficient_data"
    assert swarm.migration.is_stationary is True
    assert swarm.migration.cardinal_direction == "stationary"


@pytest.mark.parametrize(
    ("reference", "status"),
    [
        ("2025-01-04", "active"),
        ("2025-01-08", "recently_active"),
        ("2025-01-20", "inactive"),
    ],
)
def test_activity_status_uses_explicit_reference_time(reference: str, status: str):
    assert (
        analyze_swarms(_events(), eps_km=3, reference_time=reference)
        .swarms[0]
        .activity_status
        == status
    )


def test_single_event_swarm_has_insufficient_activity_data():
    swarm = analyze_swarms(
        _events().iloc[:1], eps_km=3, min_samples=1, minimum_swarm_events=1
    ).swarms[0]
    assert swarm.activity_status == "insufficient_data"


def test_ids_are_deterministic_and_independent_of_input_order():
    frame = _events()
    first = analyze_swarms(frame, eps_km=3).swarms[0].swarm_id
    second = (
        analyze_swarms(frame.sample(frac=1, random_state=5), eps_km=3)
        .swarms[0]
        .swarm_id
    )
    assert first == second


def test_minimum_swarm_events_excludes_small_clusters_and_preserves_noise_indices():
    frame = _events().iloc[:2].copy()
    frame.loc[99] = ["2025-01-02", 10.0, 10.0, 3.0, 1.0]
    result = analyze_swarms(frame, eps_km=3, minimum_swarm_events=3)
    assert result.swarms == ()
    assert result.noise_indices == (99,)


def test_swarms_sort_by_recent_time_then_event_count_then_cluster_id():
    frame = pd.concat(
        [
            _events(),
            _events()
            .assign(
                latitude=lambda data: data.latitude + 10,
                longitude=lambda data: data.longitude + 10,
                time=["2025-02-01", "2025-02-02", "2025-02-03", "2025-02-04"],
            )
            .rename(index=lambda index: index + 100),
        ]
    )
    result = analyze_swarms(frame, eps_km=3)
    assert [swarm.end_time_utc for swarm in result.swarms] == [
        "2025-02-04T00:00:00+00:00",
        "2025-01-04T00:00:00+00:00",
    ]


def test_custom_columns_missing_rows_and_utc_normalization():
    frame = pd.DataFrame(
        {
            "when": ["2025-01-01T01:00:00+01:00", "2025-01-01T02:00:00+01:00", None],
            "lat": [0.0, 0.0, 0.0],
            "lon": [0.0, 0.01, 0.02],
            "z": [1.0, 2.0, 3.0],
            "mag": [1.0, 2.0, 3.0],
        },
        index=[1, 2, 3],
    )
    result = analyze_swarms(
        frame,
        time_column="when",
        latitude_column="lat",
        longitude_column="lon",
        depth_column="z",
        magnitude_column="mag",
        eps_km=3,
    )
    assert result.analyzed_event_count == 2
    assert result.swarms[0].start_time_utc == "2025-01-01T00:00:00+00:00"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("time", "not-a-date"),
        ("latitude", 91.0),
        ("longitude", "east"),
        ("depth", -1.0),
        ("magnitude", float("inf")),
    ],
)
def test_rejects_invalid_present_event_values(column: str, value: object):
    frame = _events().astype({"time": "object", "longitude": "object"})
    frame.at[10, column] = value
    with pytest.raises((TypeError, ValueError)):
        analyze_swarms(frame)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_swarm_events": 0},
        {"active_window_days": 8, "recent_window_days": 7},
        {"trend_stable_tolerance": -1},
        {"stationary_threshold_km": -1},
        {"reference_time": "invalid"},
    ],
)
def test_parameter_validation(kwargs: dict[str, object]):
    with pytest.raises((TypeError, ValueError)):
        analyze_swarms(_events(), **kwargs)


def test_public_models_are_immutable():
    result = analyze_swarms(_events(), eps_km=3)
    for model in (
        result,
        result.swarms[0],
        result.swarms[0].magnitude_trend,
        result.swarms[0].migration,
    ):
        with pytest.raises(FrozenInstanceError):
            model.__setattr__("unused", None)
    assert isinstance(result, SwarmAnalysisResult)
    assert isinstance(result.swarms[0], SeismicSwarm)
    assert isinstance(result.swarms[0].magnitude_trend, SwarmTrend)
    assert isinstance(result.swarms[0].migration, SwarmMigration)
