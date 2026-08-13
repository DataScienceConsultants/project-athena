from datetime import UTC, datetime

import pytest

from src.catalog.models import CatalogEvent
from src.global_research.plate_boundaries import (
    PB2002_SOURCE,
    PlateBoundaryGridIndex,
    associate_catalog_events_with_plate_boundaries,
    nearest_plate_boundary,
    parse_pb2002_steps,
    plate_boundary_feature_collection,
)


SAMPLE_STEPS = """\
   1  AF-AN   -0.438 -54.852   -0.039 -54.677  32.1  53  13.2  48    1.2   13.1  -1584   2  OTF
   2 :AF-AN   -0.039 -54.677    0.443 -54.451  40.0  51  13.2  47    0.9   13.1  -1639   5 :OTF
"""


def make_event(event_id, latitude, longitude):
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, 1, tzinfo=UTC),
        latitude=latitude,
        longitude=longitude,
        depth=10.0,
        magnitude=6.5,
        source="USGS",
    )


def test_parse_pb2002_steps_preserves_source_defined_tectonic_fields():
    steps = parse_pb2002_steps(SAMPLE_STEPS)

    assert len(steps) == 2
    first = steps[0]
    assert first.step_id == "pb2002-step-0001"
    assert first.boundary_id == "AF-AN"
    assert first.left_plate == "AF"
    assert first.right_plate == "AN"
    assert first.polarity == "-"
    assert first.boundary_class == "OTF"
    assert first.relative_velocity_mm_per_year == 13.2
    assert first.divergent_velocity_mm_per_year == 1.2
    assert first.right_lateral_velocity_mm_per_year == 13.1
    assert first.seafloor_age_ma == 2.0
    assert first.source == PB2002_SOURCE


def test_parse_normalizes_wrapped_longitudes_and_unknown_seafloor_age():
    text = (
        "  10  PA-NA  190.000 10.000  191.000 11.000  50.0 45  10.0 90 "
        "  5.0   8.0 -1000 181  CTF\n"
    )

    step = parse_pb2002_steps(text)[0]

    assert step.start == (10.0, -170.0)
    assert step.end == (11.0, -169.0)
    assert step.seafloor_age_ma is None


def test_geojson_splits_dateline_crossing_for_display():
    text = (
        "  11  PA-AN  179.500 5.000  180.500 5.500  80.0 90  20.0 90 "
        "  1.0  19.0 -3000 10  OTF\n"
    )
    step = parse_pb2002_steps(text)[0]

    payload = plate_boundary_feature_collection((step,))

    feature = payload["features"][0]
    assert feature["geometry"]["type"] == "MultiLineString"
    assert feature["properties"]["left_plate"] == "PA"
    assert feature["properties"]["right_plate"] == "AN"
    assert feature["properties"]["citation_key"] == "bird_pb2002"
    assert payload["athena"]["report_is_nonpredictive"] is True


def test_indexed_association_uses_exact_distance_and_source_plate_pair():
    text = (
        "   1  AA-BB    0.000 0.000    2.000 0.000  222.0 90  10.0 90 "
        "  2.0   8.0 -3000 10  OTF\n"
    )
    step = parse_pb2002_steps(text)[0]
    index = PlateBoundaryGridIndex.build((step,), search_radius_km=100.0)

    associations = associate_catalog_events_with_plate_boundaries(
        (make_event("event-a", 0.2, 1.0),),
        index,
    )

    assert len(associations) == 1
    result = associations[0]
    assert result.event_id == "event-a"
    assert result.boundary_id == "AA-BB"
    assert result.left_plate == "AA"
    assert result.right_plate == "BB"
    assert result.boundary_class == "OTF"
    assert result.distance_km == pytest.approx(22.24, rel=0.02)


def test_association_radius_prevents_misleading_distant_plate_context():
    text = (
        "   1  AA-BB    0.000 0.000    2.000 0.000  222.0 90  10.0 90 "
        "  2.0   8.0 -3000 10  OTF\n"
    )
    step = parse_pb2002_steps(text)[0]

    result = nearest_plate_boundary(
        event_id="event-far",
        latitude=10.0,
        longitude=1.0,
        steps=(step,),
        max_distance_km=500.0,
    )

    assert result is None


def test_parser_rejects_unknown_boundary_class():
    text = (
        "   1  AA-BB    0.000 0.000    2.000 0.000  222.0 90  10.0 90 "
        "  2.0   8.0 -3000 10  XYZ\n"
    )

    with pytest.raises(ValueError, match="Unknown PB2002 boundary class"):
        parse_pb2002_steps(text)
