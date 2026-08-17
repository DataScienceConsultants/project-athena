from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.interaction import (
    build_interaction_pairs,
    build_interaction_windows,
    seismic_moment_nm,
    summarize_interaction_windows,
)
from src.global_research.plate_boundaries import PlateBoundaryAssociation


def event(
    event_id: str,
    day: int,
    *,
    longitude: float,
    magnitude: float = 6.2,
    magnitude_type: str = "mww",
) -> CatalogEvent:
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, day, tzinfo=UTC),
        latitude=0.0,
        longitude=longitude,
        depth=10.0,
        magnitude=magnitude,
        magnitude_type=magnitude_type,
        source="USGS",
    )


def context(
    event_id: str,
    *,
    boundary_id: str = "AA-BB",
    left_plate: str = "AA",
    right_plate: str = "BB",
    boundary_class: str = "SUB",
) -> PlateBoundaryAssociation:
    return PlateBoundaryAssociation(
        event_id=event_id,
        step_id=f"step-{event_id}",
        boundary_id=boundary_id,
        left_plate=left_plate,
        right_plate=right_plate,
        boundary_class=boundary_class,
        polarity="-",
        distance_km=10.0,
        source="Bird PB2002 plate boundary model",
    )


def test_seismic_moment_only_converts_mw_family_magnitudes():
    assert seismic_moment_nm(6.0, "Mww") == pytest.approx(10**18.1)
    assert seismic_moment_nm(6.0, "Mw") == pytest.approx(10**18.1)
    assert seismic_moment_nm(6.0, "mb") is None
    assert seismic_moment_nm(None, "mww") is None
    assert seismic_moment_nm(6.0, None) is None


def test_interaction_pairs_preserve_plate_relationships_and_missing_context():
    events = (
        event("source", 10, longitude=0.0, magnitude=7.1),
        event("same", 11, longitude=0.5),
        event("missing", 12, longitude=0.7),
        event("far", 13, longitude=30.0),
    )
    associations = (
        context("source"),
        context("same", boundary_id="BB-AA", left_plate="BB", right_plate="AA"),
    )

    pairs = build_interaction_pairs(
        events,
        associations,
        max_lag_days=7,
        max_distance_km=200,
    )
    source_pairs = {pair.target_event_id: pair for pair in pairs if pair.source_event_id == "source"}

    assert set(source_pairs) == {"same", "missing"}
    assert source_pairs["same"].same_plate_pair is True
    assert source_pairs["same"].same_boundary_id is False
    assert source_pairs["same"].source_moment_nm is not None
    assert source_pairs["missing"].same_plate_pair is None
    assert source_pairs["missing"].target_boundary_id is None


def test_matched_windows_count_pre_and_post_activity_by_plate_context():
    events = (
        event("pre", 9, longitude=-0.4),
        event("source", 10, longitude=0.0, magnitude=7.2),
        event("post", 11, longitude=0.4),
        event("far", 11, longitude=20.0),
    )
    associations = tuple(context(item.event_id) for item in events)

    observations = build_interaction_windows(
        events,
        associations,
        profile_start=datetime(2020, 1, 1, tzinfo=UTC),
        profile_end=datetime(2020, 2, 1, tzinfo=UTC),
        time_windows_days=(2,),
        distance_windows_km=(100,),
    )
    source = next(row for row in observations if row.source_event_id == "source")

    assert source.edge_eligible is True
    assert source.pre_count_all == 1
    assert source.post_count_all == 1
    assert source.pre_count_same_plate_pair == 1
    assert source.post_count_same_plate_pair == 1
    assert source.pre_count_same_boundary == 1
    assert source.post_count_same_boundary == 1


def test_windows_mark_catalog_edges_ineligible_instead_of_using_partial_baselines():
    events = (
        event("edge", 2, longitude=0.0),
        event("post", 3, longitude=0.2),
    )
    observations = build_interaction_windows(
        events,
        (context("edge"), context("post")),
        profile_start=datetime(2020, 1, 1, tzinfo=UTC),
        profile_end=datetime(2020, 1, 10, tzinfo=UTC),
        time_windows_days=(7,),
        distance_windows_km=(100,),
    )
    edge = next(row for row in observations if row.source_event_id == "edge")

    assert edge.full_pre_window is False
    assert edge.full_post_window is True
    assert edge.edge_eligible is False


def test_summary_is_descriptive_and_uses_only_edge_complete_sources():
    events = (
        event("pre", 9, longitude=-0.4),
        event("source", 10, longitude=0.0),
        event("post", 11, longitude=0.4),
    )
    observations = build_interaction_windows(
        events,
        tuple(context(item.event_id) for item in events),
        profile_start=datetime(2020, 1, 1, tzinfo=UTC),
        profile_end=datetime(2020, 2, 1, tzinfo=UTC),
        time_windows_days=(2,),
        distance_windows_km=(100,),
    )

    summary = summarize_interaction_windows(observations)
    statistic = summary["statistics"][0]

    assert summary["report_is_nonpredictive"] is True
    assert summary["inference_status"] == "descriptive_only_no_independence_assumption"
    assert statistic["eligible_source_count"] == 3
    assert statistic["pre_all_count"] == statistic["post_all_count"]
    assert statistic["post_minus_pre_same_plate_pair"] == 0
