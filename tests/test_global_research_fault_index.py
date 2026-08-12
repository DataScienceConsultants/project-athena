from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.fault_index import (
    FaultGridIndex,
    associate_catalog_events_indexed,
)
from src.global_research.models import FaultTrace


def fault(fault_id, coordinates):
    return FaultTrace(
        fault_id=fault_id,
        name=fault_id,
        coordinates=coordinates,
        source="fixture",
    )


def event(longitude=1.0, latitude=0.5):
    return CatalogEvent(
        event_id="event-1",
        time=datetime(2020, 1, 1, tzinfo=UTC),
        latitude=latitude,
        longitude=longitude,
        depth=10.0,
        magnitude=6.0,
        source="USGS",
    )


def test_index_excludes_obviously_distant_faults_but_keeps_near_candidates():
    near = fault("near", ((0.0, 0.0), (0.0, 2.0)))
    far = fault("far", ((30.0, 30.0), (30.0, 32.0)))
    index = FaultGridIndex.build((near, far), search_radius_km=200.0)

    candidates = index.candidates(0.5, 1.0)

    assert [item.fault_id for item in candidates] == ["near"]


def test_indexed_association_still_uses_exact_segment_distance():
    near = fault("near", ((0.0, 0.0), (0.0, 2.0)))
    index = FaultGridIndex.build((near,), search_radius_km=100.0)

    associations = associate_catalog_events_indexed((event(),), index)

    assert len(associations) == 1
    assert associations[0].fault_id == "near"
    assert associations[0].distance_km == pytest.approx(55.6, abs=0.3)


def test_index_returns_no_association_outside_configured_radius():
    near = fault("near", ((0.0, 0.0), (0.0, 2.0)))
    index = FaultGridIndex.build((near,), search_radius_km=25.0)

    assert associate_catalog_events_indexed((event(),), index) == ()


def test_dateline_spanning_fault_is_conservatively_indexed():
    dateline = fault("dateline", ((0.0, 179.0), (0.0, -179.0)))
    index = FaultGridIndex.build((dateline,), search_radius_km=100.0)

    candidates = index.candidates(0.1, 179.5)

    assert [item.fault_id for item in candidates] == ["dateline"]
