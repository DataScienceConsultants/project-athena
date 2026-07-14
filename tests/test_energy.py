"""Tests for Project Athena seismic-energy metrics."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.metrics.energy import (
    add_event_energy,
    add_rolling_energy_metrics,
    build_daily_energy,
    energy_joules_to_equivalent_magnitude,
    magnitude_to_energy_joules,
    summarize_energy,
    sum_event_energy,
)


def sample_energy_catalog() -> pd.DataFrame:
    """Return a small synthetic earthquake catalog."""

    return pd.DataFrame(
        {
            "event_id": [
                "eq1",
                "eq2",
                "eq3",
                "eq4",
            ],
            "event_time_utc": [
                "2024-01-01T01:00:00Z",
                "2024-01-01T12:00:00Z",
                "2024-01-03T06:00:00Z",
                "2024-01-04T08:00:00Z",
            ],
            "magnitude": [
                1.0,
                2.0,
                3.0,
                None,
            ],
        }
    )


def test_magnitude_to_energy_known_value():
    """M3 energy should match the configured estimation formula."""

    energy = magnitude_to_energy_joules(3.0)

    assert energy == pytest.approx(
        10 ** (1.5 * 3.0 + 4.8)
    )


def test_one_magnitude_unit_is_about_32_times_energy():
    """A one-unit magnitude increase should be about 31.6 times."""

    magnitude_2_energy = magnitude_to_energy_joules(2.0)
    magnitude_3_energy = magnitude_to_energy_joules(3.0)

    assert magnitude_2_energy is not None
    assert magnitude_3_energy is not None

    ratio = magnitude_3_energy / magnitude_2_energy

    assert ratio == pytest.approx(
        10 ** 1.5,
        rel=1e-12,
    )


def test_energy_round_trip():
    """Energy converted back to magnitude should reproduce the input."""

    original_magnitude = 4.2

    energy = magnitude_to_energy_joules(
        original_magnitude
    )

    equivalent_magnitude = (
        energy_joules_to_equivalent_magnitude(
            energy
        )
    )

    assert equivalent_magnitude == pytest.approx(
        original_magnitude
    )


def test_invalid_boolean_magnitude():
    """Boolean values should not be treated as magnitudes."""

    with pytest.raises(TypeError):
        magnitude_to_energy_joules(True)


def test_add_event_energy():
    """Event-level energy should be added without losing rows."""

    catalog = sample_energy_catalog()
    result = add_event_energy(catalog)

    assert len(result) == len(catalog)
    assert "estimated_energy_joules" in result.columns
    assert pd.isna(
        result.loc[
            result["event_id"] == "eq4",
            "estimated_energy_joules",
        ].iloc[0]
    )


def test_daily_energy_contains_inactive_day():
    """Inactive dates should be included with zero total energy."""

    daily = build_daily_energy(
        sample_energy_catalog(),
        include_inactive_days=True,
    )

    jan2 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-02")
    ].iloc[0]

    assert jan2["event_count"] == 0
    assert jan2["events_with_magnitude"] == 0
    assert jan2["total_energy_joules"] == 0.0


def test_daily_energy_total():
    """Daily total should equal the sum of event energies."""

    daily = build_daily_energy(
        sample_energy_catalog(),
        include_inactive_days=True,
    )

    jan1 = daily.loc[
        daily["date"] == pd.Timestamp("2024-01-01")
    ].iloc[0]

    expected = sum_event_energy([1.0, 2.0])

    assert jan1["total_energy_joules"] == pytest.approx(
        expected
    )


def test_energy_summary():
    """Period energy summary should identify the largest event."""

    summary = summarize_energy(
        sample_energy_catalog()
    )

    assert summary.event_count_with_magnitude == 3
    assert summary.maximum_energy_magnitude == 3.0
    assert summary.maximum_energy_event_id == "eq3"
    assert summary.total_energy_joules > 0


def test_rolling_energy_has_no_future_leakage():
    """First historical comparison should be unavailable."""

    daily = build_daily_energy(
        sample_energy_catalog(),
        include_inactive_days=True,
    )

    metrics = add_rolling_energy_metrics(daily)

    first_day = metrics.iloc[0]

    assert pd.isna(
        first_day[
            "historical_expanding_energy_average_joules"
        ]
    )


def test_total_energy_is_dominated_by_largest_event():
    """A larger event should contribute most of the sample energy."""

    energy_1 = magnitude_to_energy_joules(1.0)
    energy_2 = magnitude_to_energy_joules(2.0)
    energy_3 = magnitude_to_energy_joules(3.0)

    assert energy_1 is not None
    assert energy_2 is not None
    assert energy_3 is not None

    total = energy_1 + energy_2 + energy_3

    assert energy_3 / total > 0.96