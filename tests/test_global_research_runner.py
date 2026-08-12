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
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["catalog_event_count"] == 2
    assert metadata["catalog_query_count"] == 1
    assert metadata["fault_context_included"] is False
    assert metadata["report_is_nonpredictive"] is True
    assert metadata["generated_at_utc"] == "2026-08-12T12:00:00Z"


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

    fault_path = tmp_path / "faults.geojson"
    fault_path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )

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
    assert result.metadata["fault_context_included"] is True
    assert result.metadata["normalized_fault_trace_count"] == 1
    assert result.metadata["event_fault_association_count"] == 1
    assert "not causal attribution" in result.metadata["fault_association_semantics"]
