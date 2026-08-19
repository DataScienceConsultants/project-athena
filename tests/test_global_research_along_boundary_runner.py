import csv
import json
from datetime import UTC, datetime

from src.catalog.models import CatalogEvent
from src.catalog.storage import frame_from_events
from src.global_research.along_boundary_runner import run_along_boundary_study


def test_runner_attaches_cited_along_boundary_artifacts_to_prepared_bundle(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    events = (
        CatalogEvent(
            event_id="pre",
            time=datetime(2020, 1, 9, tzinfo=UTC),
            latitude=0.0,
            longitude=0.4,
            depth=10.0,
            magnitude=6.2,
            magnitude_type="mww",
            source="USGS",
        ),
        CatalogEvent(
            event_id="source",
            time=datetime(2020, 1, 10, tzinfo=UTC),
            latitude=0.0,
            longitude=0.5,
            depth=10.0,
            magnitude=8.1,
            magnitude_type="mww",
            source="USGS",
        ),
        CatalogEvent(
            event_id="post",
            time=datetime(2020, 1, 11, tzinfo=UTC),
            latitude=0.0,
            longitude=1.5,
            depth=10.0,
            magnitude=6.3,
            magnitude_type="mww",
            source="USGS",
        ),
    )
    frame_from_events(events).to_csv(bundle / "catalog.csv", index=False)
    metadata = {
        "bundle_schema_version": 4,
        "profile_id": "global-m6-1976-2025",
        "start_utc": "2020-01-01T00:00:00Z",
        "end_utc": "2020-02-01T00:00:00Z",
        "minimum_magnitude": 6.0,
        "plate_boundary_context_included": True,
        "max_plate_boundary_association_distance_km": 500.0,
        "report_is_nonpredictive": True,
        "source_citations": [],
    }
    (bundle / "metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    with (bundle / "event_plate_context.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(
            target,
            fieldnames=(
                "event_id",
                "step_id",
                "boundary_id",
                "left_plate",
                "right_plate",
                "boundary_class",
                "polarity",
                "distance_km",
                "source",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "event_id": "pre",
                "step_id": "pb2002-step-0001",
                "boundary_id": "AA-BB",
                "left_plate": "AA",
                "right_plate": "BB",
                "boundary_class": "SUB",
                "polarity": "-",
                "distance_km": 0.0,
                "source": "Bird PB2002 plate boundary model",
            }
        )
        writer.writerow(
            {
                "event_id": "source",
                "step_id": "pb2002-step-0001",
                "boundary_id": "AA-BB",
                "left_plate": "AA",
                "right_plate": "BB",
                "boundary_class": "SUB",
                "polarity": "-",
                "distance_km": 0.0,
                "source": "Bird PB2002 plate boundary model",
            }
        )
        writer.writerow(
            {
                "event_id": "post",
                "step_id": "pb2002-step-0002",
                "boundary_id": "AA-BB",
                "left_plate": "AA",
                "right_plate": "BB",
                "boundary_class": "SUB",
                "polarity": "-",
                "distance_km": 0.0,
                "source": "Bird PB2002 plate boundary model",
            }
        )

    plate_path = tmp_path / "PB2002_steps.dat.txt"
    plate_path.write_text(
        "   1  AA-BB    0.000 0.000    1.000 0.000  100.0 90  10.0 90 "
        "  0.0   0.0 -3000 10  SUB\n"
        "   2  AA-BB    1.000 0.000    2.000 0.000  100.0 90  10.0 90 "
        "  0.0   0.0 -3000 10  SUB\n",
        encoding="utf-8",
    )

    summary = run_along_boundary_study(
        bundle_dir=bundle,
        plate_boundary_steps_path=plate_path,
        time_windows_days=(2.0,),
        distance_windows_km=(105.0,),
        source_magnitude_thresholds=(7.0, 7.5, 8.0),
    )

    updated = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    assert updated["bundle_schema_version"] == 5
    assert updated["along_boundary_study_included"] is True
    assert updated["along_boundary_routing_scope"] == "same_plate_pair"
    assert updated["along_boundary_inference_status"] == (
        "descriptive_only_null_model_not_yet_applied"
    )
    assert updated["along_boundary_graph_edge_count"] == 2
    assert updated["along_boundary_pair_count"] == 3
    assert summary["report_is_nonpredictive"] is True
    assert summary["source_magnitude_statistic_count"] == 3
    assert summary["annular_statistic_count"] == 3
    assert summary["source_citations"][0]["source_key"] == "bird_pb2002"

    for name in (
        "along_boundary_pairs.csv",
        "along_boundary_windows.csv",
        "along_boundary_summary.json",
    ):
        assert (bundle / name).is_file()
