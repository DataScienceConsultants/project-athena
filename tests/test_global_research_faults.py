from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.faults import (
    associate_catalog_events,
    distance_to_fault_km,
    great_circle_segment_distance_km,
    load_fault_geojson,
    nearest_fault,
)
from src.global_research.models import FaultTrace


def test_geojson_lines_are_normalized_from_lon_lat_to_lat_lon():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "fault-a",
                "properties": {"name": "Test Fault"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0.0, 0.0], [2.0, 0.0]],
                },
            }
        ],
    }

    faults = load_fault_geojson(payload)

    assert len(faults) == 1
    assert faults[0].fault_id == "fault-a"
    assert faults[0].name == "Test Fault"
    assert faults[0].coordinates == ((0.0, 0.0), (0.0, 2.0))


def test_point_on_fault_segment_has_zero_distance():
    distance = great_circle_segment_distance_km(0.0, 1.0, (0.0, 0.0), (0.0, 2.0))

    assert distance == pytest.approx(0.0, abs=1e-8)


def test_point_one_degree_from_equatorial_segment_is_about_111_km_away():
    distance = great_circle_segment_distance_km(1.0, 1.0, (0.0, 0.0), (0.0, 2.0))

    assert distance == pytest.approx(111.2, abs=0.3)


def test_distance_to_fault_scans_all_adjacent_segments():
    fault = FaultTrace(
        fault_id="bent",
        name="Bent Fault",
        coordinates=((0.0, 0.0), (0.0, 2.0), (2.0, 2.0)),
        source="fixture",
    )

    assert distance_to_fault_km(1.0, 2.0, fault) == pytest.approx(0.0, abs=1e-8)


def test_nearest_fault_is_deterministic_and_can_apply_max_distance():
    near = FaultTrace(
        fault_id="near",
        name="Near Fault",
        coordinates=((0.0, 0.0), (0.0, 2.0)),
        source="fixture",
    )
    far = FaultTrace(
        fault_id="far",
        name="Far Fault",
        coordinates=((10.0, 0.0), (10.0, 2.0)),
        source="fixture",
    )

    association = nearest_fault(
        event_id="event-1",
        latitude=1.0,
        longitude=1.0,
        faults=(far, near),
    )

    assert association is not None
    assert association.fault_id == "near"
    assert association.distance_km == pytest.approx(111.2, abs=0.3)
    assert (
        nearest_fault(
            event_id="event-1",
            latitude=1.0,
            longitude=1.0,
            faults=(near,),
            max_distance_km=100.0,
        )
        is None
    )


def test_catalog_events_receive_nearest_fault_context():
    event = CatalogEvent(
        event_id="us-test",
        time=datetime(2020, 1, 1, tzinfo=UTC),
        latitude=0.5,
        longitude=1.0,
        depth=10.0,
        magnitude=6.5,
        source="USGS",
    )
    fault = FaultTrace(
        fault_id="fault-a",
        name="Test Fault",
        coordinates=((0.0, 0.0), (0.0, 2.0)),
        source="fixture",
    )

    result = associate_catalog_events((event,), (fault,))

    assert len(result) == 1
    assert result[0].event_id == "us-test"
    assert result[0].fault_id == "fault-a"
    assert result[0].distance_km == pytest.approx(55.6, abs=0.3)
