from datetime import UTC, datetime, timedelta

import pytest

from src.catalog.models import GeographicBounds
from src.global_research.models import GlobalResearchProfile, REFERENCE_50_YEAR_PROFILE
from src.global_research.planner import AdaptiveGlobalCatalogPlanner


def profile(*, start=None, end=None):
    return GlobalResearchProfile(
        profile_id="test-global",
        start_time=start or datetime(2020, 1, 1, tzinfo=UTC),
        end_time=end or datetime(2020, 1, 5, tzinfo=UTC),
        minimum_magnitude=6.0,
    )


def test_reference_profile_is_exactly_50_complete_calendar_years():
    assert REFERENCE_50_YEAR_PROFILE.start_time == datetime(1976, 1, 1, tzinfo=UTC)
    assert REFERENCE_50_YEAR_PROFILE.end_time == datetime(2026, 1, 1, tzinfo=UTC)
    assert REFERENCE_50_YEAR_PROFILE.minimum_magnitude == 6.0


def test_under_cap_query_remains_single_partition():
    planner = AdaptiveGlobalCatalogPlanner(lambda query: 321)

    result = planner.plan(profile())

    assert result.query_count == 1
    assert result.expected_event_count == 321
    assert result.partitions[0].query_id == "q00001"
    assert result.partitions[0].bounds == REFERENCE_50_YEAR_PROFILE.bounds


def test_dense_query_splits_by_time_until_each_partition_is_safe():
    def counter(query):
        days = (query.end_time - query.start_time).total_seconds() / 86400
        return 20_000 if days > 1 else 100

    planner = AdaptiveGlobalCatalogPlanner(
        counter,
        max_events_per_query=1_000,
        min_time_span=timedelta(days=1),
    )

    result = planner.plan(profile())

    assert result.query_count == 4
    assert result.expected_event_count == 400
    assert all(item.expected_event_count <= 1_000 for item in result.partitions)
    assert result.partitions[0].start_time == datetime(2020, 1, 1, tzinfo=UTC)
    assert result.partitions[-1].end_time == datetime(2020, 1, 5, tzinfo=UTC)


def test_minimum_duration_dense_query_falls_back_to_spatial_quadrants():
    global_bounds = REFERENCE_50_YEAR_PROFILE.bounds

    def counter(query):
        if query.bounds == global_bounds:
            return 30_000
        return 100

    one_day = profile(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2020, 1, 2, tzinfo=UTC),
    )
    planner = AdaptiveGlobalCatalogPlanner(
        counter,
        max_events_per_query=1_000,
        min_time_span=timedelta(days=1),
    )

    result = planner.plan(one_day)

    assert result.query_count == 4
    assert result.expected_event_count == 400
    assert {item.bounds for item in result.partitions} == {
        GeographicBounds(-90, 0, -180, 0),
        GeographicBounds(-90, 0, 0, 180),
        GeographicBounds(0, 90, -180, 0),
        GeographicBounds(0, 90, 0, 180),
    }


def test_invalid_catalog_count_is_rejected():
    planner = AdaptiveGlobalCatalogPlanner(lambda query: -1)

    with pytest.raises(ValueError, match="cannot be negative"):
        planner.plan(profile())
