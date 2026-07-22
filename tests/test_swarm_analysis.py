"""Tests for descriptive seismic swarm analysis."""

from __future__ import annotations

import pandas as pd
import pytest

from src.swarm import analyze_swarms


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
            "latitude": [18.0, 18.0, 18.01, 18.01],
            "longitude": [-66.0, -65.99, -65.99, -65.98],
            "depth": [5.0, 6.0, 7.0, 8.0],
            "magnitude": [1.0, 1.5, 2.0, 2.5],
        },
        index=[10, 11, 12, 13],
    )


def test_analyze_swarms_characterizes_density_trends_and_recent_activity():
    """A compact temporal sequence should expose its measurable behavior."""

    result = analyze_swarms(_events(), eps_km=3, recent_window_days=2)

    assert result.input_event_count == result.analyzed_event_count == 4
    assert result.excluded_event_count == 0
    assert result.swarm_count == 1
    swarm = result.swarms[0]
    assert swarm.member_indices == (10, 11, 12, 13)
    assert swarm.start_time_utc == "2025-01-01T00:00:00+00:00"
    assert swarm.duration_days == 3
    assert swarm.event_rate_per_day == pytest.approx(4 / 3)
    assert swarm.spatial_density_events_per_sq_km is not None
    assert swarm.mean_magnitude == pytest.approx(1.75)
    assert swarm.magnitude_trend_per_day == pytest.approx(0.5)
    assert swarm.depth_trend_km_per_day == pytest.approx(1.0)
    assert swarm.recent_event_count == 3
    assert swarm.recent_activity_fraction == pytest.approx(0.75)
    assert swarm.is_swarm_like is True


def test_analyze_swarms_normalizes_offsets_to_utc_and_supports_custom_columns():
    """Configurable input names and parseable timestamps are supported."""

    frame = pd.DataFrame(
        {"when": ["2025-01-01T01:00:00+01:00", "2025-01-01T02:00:00+01:00"],
         "lat": [0, 0], "lon": [0, 0.01], "z": [1, 2], "mag": [1, 2]}
    )
    result = analyze_swarms(frame, time_column="when", latitude_column="lat",
                            longitude_column="lon", depth_column="z", magnitude_column="mag", eps_km=3)

    assert result.swarms[0].start_time_utc == "2025-01-01T00:00:00+00:00"


def test_analyze_swarms_excludes_missing_rows_and_tracks_noise_indices():
    """Missing required values are excluded while source indices remain traceable."""

    frame = _events()
    frame.loc[11, "depth"] = None
    frame.loc[99] = ["2025-01-02", 10, 10, 3, 1]
    result = analyze_swarms(frame, eps_km=3)

    assert result.analyzed_event_count == 4
    assert result.excluded_event_count == 1
    assert result.noise_indices == (99,)
    assert result.swarms[0].member_indices == (10, 12, 13)


@pytest.mark.parametrize(
    ("column", "value"),
    [("time", "not-a-date"), ("latitude", 91), ("longitude", "east"),
     ("depth", -1), ("magnitude", float("inf"))],
)
def test_analyze_swarms_rejects_non_missing_invalid_event_values(column: str, value: object):
    """Invalid required source values must not be silently discarded."""

    frame = _events()
    frame.loc[10, column] = value
    with pytest.raises((TypeError, ValueError)):
        analyze_swarms(frame)


def test_analyze_swarms_returns_empty_result_when_every_row_is_missing():
    """A valid schema with no complete events should return an empty analysis."""

    frame = pd.DataFrame({name: [None] for name in ["time", "latitude", "longitude", "depth", "magnitude"]})
    result = analyze_swarms(frame)

    assert result.swarms == ()
    assert result.analyzed_event_count == 0
    assert result.excluded_event_count == 1


def test_analyze_swarms_rejects_missing_columns_and_invalid_options():
    """Required schema and descriptive-screening options are validated."""

    with pytest.raises(ValueError, match="missing required columns"):
        analyze_swarms(pd.DataFrame())
    with pytest.raises(ValueError, match="recent_window_days"):
        analyze_swarms(_events(), recent_window_days=0)
    with pytest.raises(ValueError, match="swarm_max_duration_days"):
        analyze_swarms(_events(), swarm_max_duration_days=0)
    with pytest.raises(ValueError, match="swarm_min_rate_per_day"):
        analyze_swarms(_events(), swarm_min_rate_per_day=0)


def test_analyze_swarms_does_not_flag_long_low_rate_sequence_as_swarm_like():
    """The screening flag communicates its configured duration and rate criteria."""

    frame = _events()
    frame["time"] = ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"]
    result = analyze_swarms(frame, eps_km=3)

    assert result.swarms[0].is_swarm_like is False


def test_swarm_result_serializes_to_plain_data():
    """Result models are suitable for APIs and reports."""

    data = analyze_swarms(_events(), eps_km=3).to_dict()

    assert data["swarms"][0]["member_indices"] == (10, 11, 12, 13)
    assert data["recent_window_days"] == 7.0
