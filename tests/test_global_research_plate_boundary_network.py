from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.plate_boundaries import (
    PlateBoundaryAssociation,
    PlateBoundaryStep,
)
from src.global_research.plate_boundary_network import (
    PlateBoundaryGraph,
    project_catalog_events_to_boundaries,
    project_event_to_boundary_step,
)


def step(
    step_id: str,
    sequence_number: int,
    *,
    boundary_id: str = "AA-BB",
    boundary_class: str = "SUB",
    start: tuple[float, float],
    end: tuple[float, float],
    length_km: float = 100.0,
) -> PlateBoundaryStep:
    return PlateBoundaryStep(
        step_id=step_id,
        sequence_number=sequence_number,
        boundary_id=boundary_id,
        left_plate=boundary_id[:2],
        right_plate=boundary_id[3:],
        polarity=boundary_id[2],
        boundary_class=boundary_class,
        start=start,
        end=end,
        length_km=length_km,
        azimuth_deg=90.0,
        relative_velocity_mm_per_year=10.0,
        relative_velocity_azimuth_deg=90.0,
        divergent_velocity_mm_per_year=1.0,
        right_lateral_velocity_mm_per_year=9.0,
        elevation_m=-1000.0,
        seafloor_age_ma=10.0,
        in_orogen=False,
    )


def event(
    event_id: str,
    *,
    latitude: float,
    longitude: float,
) -> CatalogEvent:
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, 1, tzinfo=UTC),
        latitude=latitude,
        longitude=longitude,
        depth=10.0,
        magnitude=7.0,
        magnitude_type="mww",
        source="USGS",
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
        distance_km=10.0,
        source=boundary_step.source,
    )


def test_graph_uses_exact_pb2002_endpoints_and_preserves_junctions():
    first = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    second = step("s2", 2, start=(0.0, 1.0), end=(0.0, 2.0))
    branch = step(
        "s3",
        3,
        boundary_id="BB-CC",
        start=(0.0, 1.0),
        end=(1.0, 1.0),
        length_km=120.0,
    )

    graph = PlateBoundaryGraph.build((first, second, branch))

    assert graph.edge_count == 3
    assert graph.node_count == 4
    assert graph.component_count == 1
    assert graph.step("s2") is second


def test_projection_uses_minor_great_circle_arc_and_source_step_length():
    boundary_step = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    graph = PlateBoundaryGraph.build((boundary_step,))
    quake = event("source", latitude=1.0, longitude=0.5)

    projection = project_event_to_boundary_step(
        quake,
        association("source", boundary_step),
        graph,
    )

    assert projection.projected_latitude == pytest.approx(0.0, abs=1e-9)
    assert projection.projected_longitude == pytest.approx(0.5, abs=1e-9)
    assert projection.fraction_from_start == pytest.approx(0.5, abs=1e-9)
    assert projection.distance_from_start_km == pytest.approx(50.0)
    assert projection.distance_to_end_km == pytest.approx(50.0)
    assert projection.distance_to_boundary_km == pytest.approx(111.195, rel=1e-3)


def test_projection_handles_dateline_crossing_without_long_way_around():
    boundary_step = step(
        "dateline",
        1,
        start=(0.0, 179.0),
        end=(0.0, -179.0),
        length_km=200.0,
    )
    graph = PlateBoundaryGraph.build((boundary_step,))
    quake = event("source", latitude=1.0, longitude=180.0)

    projection = project_event_to_boundary_step(
        quake,
        association("source", boundary_step),
        graph,
    )

    assert projection.projected_latitude == pytest.approx(0.0, abs=1e-9)
    assert abs(abs(projection.projected_longitude) - 180.0) < 1e-9
    assert projection.fraction_from_start == pytest.approx(0.5, abs=1e-9)
    assert projection.distance_from_start_km == pytest.approx(100.0)


def test_shortest_distance_defaults_to_same_plate_pair_and_can_use_full_network():
    first = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    second = step("s2", 2, start=(0.0, 1.0), end=(0.0, 2.0))
    branch = step(
        "s3",
        3,
        boundary_id="BB-CC",
        start=(0.0, 1.0),
        end=(1.0, 1.0),
        length_km=120.0,
    )
    graph = PlateBoundaryGraph.build((first, second, branch))

    source = project_event_to_boundary_step(
        event("source", latitude=0.5, longitude=0.5),
        association("source", first),
        graph,
    )
    same_pair = project_event_to_boundary_step(
        event("same", latitude=-0.5, longitude=1.5),
        association("same", second),
        graph,
    )
    other_pair = project_event_to_boundary_step(
        event("branch", latitude=0.5, longitude=1.0),
        association("branch", branch),
        graph,
    )

    assert graph.along_boundary_distance_km(source, same_pair) == pytest.approx(100.0)
    assert graph.along_boundary_distance_km(source, other_pair) is None
    assert graph.along_boundary_distance_km(
        source,
        other_pair,
        routing_scope="all",
    ) == pytest.approx(110.0)


def test_same_step_distance_uses_direct_along_step_offset():
    boundary_step = step(
        "s1",
        1,
        start=(0.0, 0.0),
        end=(0.0, 2.0),
        length_km=200.0,
    )
    graph = PlateBoundaryGraph.build((boundary_step,))
    first = project_event_to_boundary_step(
        event("a", latitude=0.2, longitude=0.5),
        association("a", boundary_step),
        graph,
    )
    second = project_event_to_boundary_step(
        event("b", latitude=-0.2, longitude=1.5),
        association("b", boundary_step),
        graph,
    )

    assert graph.along_boundary_distance_km(first, second) == pytest.approx(100.0)


def test_projection_outside_minor_arc_falls_back_to_nearest_endpoint():
    boundary_step = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    graph = PlateBoundaryGraph.build((boundary_step,))
    projection = project_event_to_boundary_step(
        event("outside", latitude=0.0, longitude=2.0),
        association("outside", boundary_step),
        graph,
    )

    assert projection.fraction_from_start == 1.0
    assert projection.projected_longitude == 1.0
    assert projection.distance_to_end_km == 0.0


def test_catalog_projection_skips_events_without_prepared_plate_context():
    boundary_step = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    graph = PlateBoundaryGraph.build((boundary_step,))
    associated = event("associated", latitude=0.1, longitude=0.5)
    unassociated = event("unassociated", latitude=10.0, longitude=10.0)

    projections = project_catalog_events_to_boundaries(
        (associated, unassociated),
        (association("associated", boundary_step),),
        graph,
    )

    assert [item.event_id for item in projections] == ["associated"]


def test_graph_rejects_projection_offsets_inconsistent_with_source_step():
    boundary_step = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    graph = PlateBoundaryGraph.build((boundary_step,))
    projection = project_event_to_boundary_step(
        event("source", latitude=0.1, longitude=0.5),
        association("source", boundary_step),
        graph,
    )
    corrupted = replace(
        projection,
        distance_from_start_km=projection.distance_from_start_km + 5.0,
    )

    with pytest.raises(ValueError, match="do not match step length"):
        graph.distances_from_projection(corrupted)


def test_graph_reports_disconnected_same_pair_routes_as_unavailable():
    first = step("s1", 1, start=(0.0, 0.0), end=(0.0, 1.0))
    isolated = step("s2", 2, start=(10.0, 10.0), end=(10.0, 11.0))
    graph = PlateBoundaryGraph.build((first, isolated))
    source = project_event_to_boundary_step(
        event("source", latitude=0.1, longitude=0.5),
        association("source", first),
        graph,
    )
    target = project_event_to_boundary_step(
        event("target", latitude=10.1, longitude=10.5),
        association("target", isolated),
        graph,
    )

    assert graph.component_count == 2
    assert graph.along_boundary_distance_km(source, target) is None
    with pytest.raises(ValueError, match="routing_scope"):
        graph.along_boundary_distance_km(source, target, routing_scope="invalid")
