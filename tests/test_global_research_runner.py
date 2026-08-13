import csv
import json
from datetime import UTC, datetime

from src.catalog.models import CatalogEvent
from src.global_research.models import GlobalResearchProfile
from src.global_research.runner import run_global_research


def make_event(event_id, day, latitude=0.5, longitude=1.0):
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, day, tzinfo=UTC),
        latitude=latitude,
        longitude=longitude,
        depth=10.0,
        magnitude=6.2,
        source="USGS",
    )


def test_runner_writes_reproducible_catalog_bundle(tmp_path):
    profile = GlobalResearchProfile(
        profile_id="fixture",
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 1, 3, tzinfo=UTC),
        minimum_magnitude=6.0,
    )

    class FakeDownloader:
        def download(self, query):
            return (make_event("a", 1), make_event("b", 2))

    output = tmp_path / "bundle"
    result = run_global_research(
        profile=profile,
        output_dir=output,
        counter=lambda query: 2,
        downloader=FakeDownloader(),
        generated_at=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
    )

    assert result.output_dir == output
    assert (output / "catalog.csv").is_file()
    assert (output / "catalog_plan.json").is_file()
    assert (output / "metadata.json").is_file()
    assert not (output / "faults.geojson").exists()
    assert not (output / "plate_boundaries.geojson").exists()
    assert not (output / "event_plate_context.csv").exists()
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["bundle_schema_version"] == 2
    assert metadata["catalog_event_count"] == 2
    assert metadata["catalog_query_count"] == 1
    assert metadata["fault_context_included"] is False
    assert metadata["plate_boundary_context_included"] is False
    assert metadata["report_is_nonpredictive"] is True
    assert metadata["generated_at_utc"] == "2026-08-12T12:00:00Z"
    assert metadata["source_citations"][0]["source_key"] == "usgs_comcat"


def test_runner_can_add_fault_context(tmp_path):
    profile = GlobalResearchProfile(
        profile_id="fixture",
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 1, 2, tzinfo=UTC),
        minimum_magnitude=6.0,
    )

    class FakeDownloader:
        def download(self, query):
            return (make_event("a", 1),)

    fault_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "fault-a",
                "properties": {"name": "Fixture Fault"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[0.0, 0.0], [2.0, 0.0]],
                },
            }
        ],
    }
    fault_path = tmp_path / "faults.geojson"
    fault_path.write_text(json.dumps(fault_payload), encoding="utf-8")

    output = tmp_path / "bundle"
    result = run_global_research(
        profile=profile,
        output_dir=output,
        fault_geojson_path=fault_path,
        max_fault_distance_km=100.0,
        counter=lambda query: 1,
        downloader=FakeDownloader(),
        generated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert (output / "fault_associations.csv").is_file()
    assert (output / "faults.geojson").is_file()
    persisted_faults = json.loads((output / "faults.geojson").read_text(encoding="utf-8"))
    assert persisted_faults == fault_payload
    assert result.metadata["fault_context_included"] is True
    assert result.metadata["fault_geojson_included"] is True
    assert result.metadata["fault_geojson_feature_count"] == 1
    assert result.metadata["normalized_fault_trace_count"] == 1
    assert result.metadata["event_fault_association_count"] == 1
    assert "not causal attribution" in result.metadata["fault_association_semantics"]
    assert any(
        item["source_key"] == "gem_global_active_faults"
        for item in result.metadata["source_citations"]
    )


def test_runner_can_add_cited_pb2002_plate_boundary_context(tmp_path):
    profile = GlobalResearchProfile(
        profile_id="fixture",
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 1, 2, tzinfo=UTC),
        minimum_magnitude=6.0,
    )

    class FakeDownloader:
        def download(self, query):
            return (make_event("a", 1),)

    plate_path = tmp_path / "PB2002_steps.dat.txt"
    plate_path.write_text(
        "   1  AA-BB    0.000 0.000    2.000 0.000  222.0 90  10.0 90 "
        "  2.0   8.0 -3000 10  OTF\n",
        encoding="utf-8",
    )

    output = tmp_path / "bundle"
    result = run_global_research(
        profile=profile,
        output_dir=output,
        plate_boundary_steps_path=plate_path,
        max_plate_boundary_distance_km=100.0,
        counter=lambda query: 1,
        downloader=FakeDownloader(),
        generated_at=datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert (output / "plate_boundaries.geojson").is_file()
    assert (output / "event_plate_context.csv").is_file()
    plate_geojson = json.loads(
        (output / "plate_boundaries.geojson").read_text(encoding="utf-8")
    )
    assert plate_geojson["type"] == "FeatureCollection"
    assert len(plate_geojson["features"]) == 1
    assert plate_geojson["features"][0]["properties"]["boundary_class"] == "OTF"

    with (output / "event_plate_context.csv").open(
        "r", encoding="utf-8", newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 1
    assert rows[0]["event_id"] == "a"
    assert rows[0]["boundary_id"] == "AA-BB"
    assert rows[0]["left_plate"] == "AA"
    assert rows[0]["right_plate"] == "BB"

    assert result.metadata["plate_boundary_context_included"] is True
    assert result.metadata["plate_boundary_geojson_included"] is True
    assert result.metadata["plate_boundary_step_count"] == 1
    assert result.metadata["event_plate_boundary_association_count"] == 1
    assert "not causal attribution" in result.metadata[
        "plate_boundary_association_semantics"
    ]
    bird = next(
        item
        for item in result.metadata["source_citations"]
        if item["source_key"] == "bird_pb2002"
    )
    assert bird["citation"]["doi"] == "10.1029/2001GC000252"
    assert bird["distribution_license"] == "ODC-By-1.0"
