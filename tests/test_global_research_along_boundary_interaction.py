from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.along_boundary_interaction import (
    ROUTE_STATUS_AVAILABLE,
    ROUTE_STATUS_DIFFERENT_PLATE_PAIR,
    ROUTE_STATUS_MISSING_PROJECTION,
    build_along_boundary_pairs,
    build_along_boundary_windows,
    summarize_along_boundary_study,
)
from src.global_research.plate_boundaries import (
    PlateBoundaryAssociation,
    PlateBoundaryStep,
)
from src.global_research.plate_boundary_network import PlateBoundaryGraph


def event(
    event_id: str,
    day: int,
    *,
    longitude: float,
    magnitude: float = 6.2,
) -> CatalogEvent:
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, day, tzinfo=UTC),
        latitude=0.0,
        longitude=longitude,
        depth=10.0,
        magnitude=magnitude,
        magnitude_type="mww",
        source="USGS",
    )


def step(
    sequence: int,
    boundary_id: str,
    start_lon: float,
    end_lon: float,
    *,
    length_km: float = 100.0,
) -> PlateBoundaryStep:
    return PlateBoundaryStep(
        step_id=f"pb2002-step-{sequence:04d}",
        sequence_number=sequence,
        boundary_id=boundary_id,
        left_plate=boundary_id[:2],
        right_plate=boundary_id[3:],
        polarity=boundary_id[2],
        boundary_class="SUB",
        start=(0.0, start_lon),
        end=(0.0, end_lon),
        length_km=length_km,
        azimuth_deg=90.0,
        relative_velocity_mm_per_year=10.0,
        relative_velocity_azimuth_deg=90.0,
        divergent_velocity_mm_per_year=0.0,
        right_lateral_velocity_mm_per_year=0.0,
        elevation_m=-3000.0,
        seafloor_age_ma=10.0,
        in_orogen=False,
    )


def association(
    event_id: str,
    boundary_step: PlateBoundaryStep,
) -> PlateBoundaryAssociation:
    return PlateBoundaryAssociation(
        event_id=event_id,
        step_id=boundary_step.step_id,
        boundary_id=boundary_step.boundary_id,
        left_plate=boundary_step.left_plate,
        right_plate=boundary_step.right_plate,
        boundary_class=boundary_step.boundary_class,
        polarity=boundary_step.polarity,
        distance_km=0.0,
        source=boundary_step.source,
    )


def test_pairs_preserve_route_availability_and_unavailable_reasons():
    first = step(1, "AA-BB", 0.0, 1.0)
    second = step(2, "AA-BB", 1.0, 2.0)
    other = step(3, "CC-DD", 2.0, 3.0)
    graph = PlateBoundaryGraph.build((first, second, other))
    events = (
        event("source", 10, longitude=0.5, magnitude=7.5),
        event("same", 11, longitude=1.5),
        event("different", 12, longitude=2.5),
        event("missing", 13, longitude=1.6),
    )
    associations = (
        association("source", first),
        association("same", second),
        association("different", other),
    )

    pairs = build_along_boundary_pairs(
        events,
        associations,
        graph,
        max_lag_days=7,
        max_along_boundary_distance_km=500,
        max_prepared_boundary_offset_km=500,
    )
    by_ids = {(item.earlier_event_id, item.later_event_id): item for item in pairs}

    routed = by_ids[("source", "same")]
    assert routed.route_status == ROUTE_STATUS_AVAILABLE
    assert routed.same_plate_pair is True
    assert routed.along_boundary_distance_km == pytest.approx(100.0)
    assert routed.within_along_boundary_limit is True

    different = by_ids[("source", "different")]
    assert different.route_status == ROUTE_STATUS_DIFFERENT_PLATE_PAIR
    assert different.same_plate_pair is False
    assert different.along_boundary_distance_km is None

    missing = by_ids[("source", "missing")]
    assert missing.route_status == ROUTE_STATUS_MISSING_PROJECTION
    assert missing.same_plate_pair is None


def test_windows_compare_along_and_radial_distance_on_same_routed_pairs():
    first = step(1, "AA-BB", 0.0, 1.0)
    second = step(2, "AA-BB", 1.0, 2.0)
    graph = PlateBoundaryGraph.build((first, second))
    events = (
        event("pre", 9, longitude=0.4),
        event("source", 10, longitude=0.5, magnitude=7.2),
        event("post", 11, longitude=1.5),
    )
    associations = (
        association("pre", first),
        association("source", first),
        association("post", second),
    )
    pairs = build_along_boundary_pairs(
        events,
        associations,
        graph,
        max_lag_days=7,
        max_along_boundary_distance_km=500,
        max_prepared_boundary_offset_km=500,
    )
    observations = build_along_boundary_windows(
        events,
        associations,
        graph,
        pairs,
        profile_start=datetime(2020, 1, 1, tzinfo=UTC),
        profile_end=datetime(2020, 2, 1, tzinfo=UTC),
        time_windows_days=(2,),
        distance_windows_km=(105,),
    )
    source = next(item for item in observations if item.source_event_id == "source")

    assert source.edge_eligible is True
    assert source.pre_count_along_boundary == 1
    assert source.post_count_along_boundary == 1
    assert source.pre_count_routed_radial == 1
    assert source.post_count_routed_radial == 0

    summary = summarize_along_boundary_study(
        pairs,
        observations,
        source_magnitude_thresholds=(7.0,),
    )
    statistic = summary["source_magnitude_statistics"][0]
    assert summary["report_is_nonpredictive"] is True
    assert summary["routing_scope"] == "same_plate_pair"
    assert summary["inference_status"] == (
        "descriptive_only_null_model_not_yet_applied"
    )
    assert statistic["eligible_source_count"] == 1
    assert statistic["post_to_pre_along_boundary_ratio"] == pytest.approx(1.0)
    assert statistic["post_to_pre_routed_radial_ratio"] == pytest.approx(0.0)
    assert summary["annular_statistic_count"] == 1


def test_summary_reports_route_coverage_without_inventing_missing_routes():
    first = step(1, "AA-BB", 0.0, 1.0)
    other = step(2, "CC-DD", 1.0, 2.0)
    graph = PlateBoundaryGraph.build((first, other))
    events = (
        event("source", 10, longitude=0.5, magnitude=8.0),
        event("different", 11, longitude=1.5),
        event("missing", 12, longitude=0.6),
    )
    associations = (
        association("source", first),
        association("different", other),
    )
    pairs = build_along_boundary_pairs(events, associations, graph)
    observations = build_along_boundary_windows(
        events,
        associations,
        graph,
        pairs,
        profile_start=datetime(2020, 1, 1, tzinfo=UTC),
        profile_end=datetime(2020, 2, 1, tzinfo=UTC),
        time_windows_days=(1,),
        distance_windows_km=(100,),
    )
    summary = summarize_along_boundary_study(
        pairs,
        observations,
        source_magnitude_thresholds=(8.0,),
    )

    coverage = summary["coverage"]
    assert coverage["candidate_pair_count"] == 3
    assert coverage["route_available_pair_count"] == 0
    assert coverage["different_plate_pair_count"] >= 1
    assert coverage["missing_projection_pair_count"] >= 1
    assert summary["route_distance_summary"]["count"] == 0
    assert summary["route_distance_summary"]["median_along_boundary_distance_km"] is None
