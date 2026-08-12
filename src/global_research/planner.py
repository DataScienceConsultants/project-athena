"""Adaptive query planning for large, reproducible global USGS catalog runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from src.catalog.models import CatalogQuery, GeographicBounds
from src.global_research.models import (
    GlobalCatalogPlan,
    GlobalResearchProfile,
    PlannedCatalogQuery,
    REFERENCE_50_YEAR_PROFILE,
)

CatalogCounter = Callable[[CatalogQuery], int]


class CatalogPlanningError(RuntimeError):
    """Raised when a query cannot be partitioned below the configured safety cap."""


class AdaptiveGlobalCatalogPlanner:
    """Split dense USGS requests by time, then space, before downloading data.

    USGS currently caps event queries at 20,000 results. Athena uses a lower default
    safety cap and preflights every candidate partition with the service's count
    endpoint. Dense windows are first divided temporally because that preserves a
    simple global cohort. Very dense minimum-duration windows fall back to spatial
    quadrants.
    """

    def __init__(
        self,
        count_events: CatalogCounter,
        *,
        max_events_per_query: int = 18_000,
        min_time_span: timedelta = timedelta(days=1),
        max_depth: int = 40,
    ) -> None:
        if not callable(count_events):
            raise TypeError("count_events must be callable.")
        if isinstance(max_events_per_query, bool) or not isinstance(
            max_events_per_query, int
        ):
            raise TypeError("max_events_per_query must be an integer.")
        if not 1 <= max_events_per_query < 20_000:
            raise ValueError("max_events_per_query must be between 1 and 19999.")
        if not isinstance(min_time_span, timedelta) or min_time_span <= timedelta(0):
            raise ValueError("min_time_span must be a positive timedelta.")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int):
            raise TypeError("max_depth must be an integer.")
        if max_depth <= 0:
            raise ValueError("max_depth must be positive.")
        self._count_events = count_events
        self.max_events_per_query = max_events_per_query
        self.min_time_span = min_time_span
        self.max_depth = max_depth

    def plan(self, profile: GlobalResearchProfile) -> GlobalCatalogPlan:
        if not isinstance(profile, GlobalResearchProfile):
            raise TypeError("profile must be GlobalResearchProfile.")
        root = CatalogQuery(
            start_time=profile.start_time,
            end_time=profile.end_time,
            bounds=profile.bounds,
            minimum_magnitude=profile.minimum_magnitude,
        )
        leaves: list[tuple[CatalogQuery, int]] = []
        self._partition(root, leaves, depth=0)
        leaves.sort(
            key=lambda item: (
                item[0].start_time,
                item[0].end_time,
                item[0].bounds.min_latitude,
                item[0].bounds.min_longitude,
            )
        )
        partitions = tuple(
            PlannedCatalogQuery(
                query_id=f"q{index:05d}",
                expected_event_count=count,
                start_time=query.start_time,
                end_time=query.end_time,
                bounds=query.bounds,
                minimum_magnitude=query.minimum_magnitude,
            )
            for index, (query, count) in enumerate(leaves, start=1)
        )
        return GlobalCatalogPlan(
            profile=profile,
            partitions=partitions,
            expected_event_count=sum(item.expected_event_count for item in partitions),
        )

    def _partition(
        self,
        query: CatalogQuery,
        leaves: list[tuple[CatalogQuery, int]],
        *,
        depth: int,
    ) -> None:
        if depth > self.max_depth:
            raise CatalogPlanningError(
                "Adaptive catalog planning exceeded max_depth before reaching the "
                "configured event cap."
            )
        count = self._validated_count(query)
        if count <= self.max_events_per_query:
            leaves.append((query, count))
            return

        duration = query.end_time - query.start_time
        if duration > self.min_time_span:
            left, right = _split_time(query)
            self._partition(left, leaves, depth=depth + 1)
            self._partition(right, leaves, depth=depth + 1)
            return

        quadrants = _split_space(query)
        if not quadrants:
            raise CatalogPlanningError(
                "A dense minimum-duration query could not be spatially partitioned."
            )
        for quadrant in quadrants:
            self._partition(quadrant, leaves, depth=depth + 1)

    def _validated_count(self, query: CatalogQuery) -> int:
        value = self._count_events(query)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Catalog count must be returned as an integer.")
        if value < 0:
            raise ValueError("Catalog count cannot be negative.")
        return value


def _split_time(query: CatalogQuery) -> tuple[CatalogQuery, CatalogQuery]:
    midpoint = query.start_time + (query.end_time - query.start_time) / 2
    if midpoint <= query.start_time or midpoint >= query.end_time:
        raise CatalogPlanningError("Time partition produced a degenerate interval.")
    common = {
        "bounds": query.bounds,
        "minimum_magnitude": query.minimum_magnitude,
    }
    return (
        CatalogQuery(start_time=query.start_time, end_time=midpoint, **common),
        CatalogQuery(start_time=midpoint, end_time=query.end_time, **common),
    )


def _split_space(query: CatalogQuery) -> tuple[CatalogQuery, ...]:
    bounds = query.bounds
    latitude_midpoint = (bounds.min_latitude + bounds.max_latitude) / 2
    longitude_midpoint = (bounds.min_longitude + bounds.max_longitude) / 2
    if (
        latitude_midpoint <= bounds.min_latitude
        or latitude_midpoint >= bounds.max_latitude
        or longitude_midpoint <= bounds.min_longitude
        or longitude_midpoint >= bounds.max_longitude
    ):
        return ()

    spatial_bounds = (
        GeographicBounds(
            bounds.min_latitude,
            latitude_midpoint,
            bounds.min_longitude,
            longitude_midpoint,
        ),
        GeographicBounds(
            bounds.min_latitude,
            latitude_midpoint,
            longitude_midpoint,
            bounds.max_longitude,
        ),
        GeographicBounds(
            latitude_midpoint,
            bounds.max_latitude,
            bounds.min_longitude,
            longitude_midpoint,
        ),
        GeographicBounds(
            latitude_midpoint,
            bounds.max_latitude,
            longitude_midpoint,
            bounds.max_longitude,
        ),
    )
    return tuple(
        CatalogQuery(
            start_time=query.start_time,
            end_time=query.end_time,
            bounds=child_bounds,
            minimum_magnitude=query.minimum_magnitude,
        )
        for child_bounds in spatial_bounds
    )


def reference_50_year_plan(count_events: CatalogCounter) -> GlobalCatalogPlan:
    """Plan the frozen 1976-2025 global M6+ reference cohort."""
    return AdaptiveGlobalCatalogPlanner(count_events).plan(REFERENCE_50_YEAR_PROFILE)


def planned_query_as_catalog_query(partition: PlannedCatalogQuery) -> CatalogQuery:
    """Convert a persisted plan partition back to the canonical catalog query model."""
    return CatalogQuery(
        start_time=partition.start_time,
        end_time=partition.end_time,
        bounds=partition.bounds,
        minimum_magnitude=partition.minimum_magnitude,
    )
