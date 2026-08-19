from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_research_dashboard_data import RAW_FILES, build_research_dashboard_data


def _csv(path: Path, fields: list[str], rows: list[dict[str, object]] = []) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_dashboard_builder_preserves_pb2002_na_plate_code(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    output = tmp_path / "out"
    bundle.mkdir()
    for name in RAW_FILES:
        path = bundle / name
        if name.endswith((".json", ".geojson")):
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("placeholder\n", encoding="utf-8")

    (bundle / "metadata.json").write_text(
        json.dumps({"bundle_schema_version": 5, "profile_id": "test", "generated_at_utc": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    (bundle / "along_boundary_summary.json").write_text("{}", encoding="utf-8")
    (bundle / "interaction_summary.json").write_text("{}", encoding="utf-8")

    _csv(
        bundle / "catalog.csv",
        ["event_id","time","latitude","longitude","depth","magnitude","magnitude_type","place","status","event_type","source","updated_at"],
        [
            {"event_id":"major","time":"2000-01-01 00:00:00+00:00","latitude":10,"longitude":20,"depth":30,"magnitude":8.1,"magnitude_type":"mww","place":"Major","status":"reviewed","event_type":"earthquake","source":"us","updated_at":"2000-01-01 01:00:00+00:00"},
            {"event_id":"target","time":"2000-01-02 00:00:00+00:00","latitude":11,"longitude":21,"depth":20,"magnitude":6.2,"magnitude_type":"mw","place":"Target","status":"reviewed","event_type":"earthquake","source":"us","updated_at":"2000-01-02 01:00:00+00:00"},
        ],
    )
    _csv(bundle / "event_plate_context.csv", ["event_id","step_id","boundary_id","left_plate","right_plate","boundary_class","polarity","distance_km","source"], [{"event_id":"major","step_id":"s1","boundary_id":"NA-PA","left_plate":"NA","right_plate":"PA","boundary_class":"SUB","polarity":"+","distance_km":12.5,"source":"PB2002"}])
    _csv(bundle / "fault_associations.csv", ["event_id","fault_id","fault_name","distance_km","fault_source"])
    _csv(bundle / "along_boundary_pairs.csv", ["earlier_event_id","later_event_id","earlier_time","later_time","lag_days","radial_distance_km","earlier_magnitude","later_magnitude","earlier_step_id","later_step_id","earlier_boundary_id","later_boundary_id","earlier_left_plate","earlier_right_plate","later_left_plate","later_right_plate","earlier_boundary_class","later_boundary_class","same_plate_pair","same_boundary_id","route_status","along_boundary_distance_km","within_along_boundary_limit"])
    _csv(bundle / "along_boundary_windows.csv", ["source_event_id","source_time","source_magnitude","source_magnitude_type","source_step_id","source_boundary_id","source_left_plate","source_right_plate","source_boundary_class","source_distance_to_boundary_km","time_window_days","distance_window_km","full_pre_window","full_post_window","pre_count_along_boundary","post_count_along_boundary","pre_count_routed_radial","post_count_routed_radial","edge_eligible"])

    counts = build_research_dashboard_data(bundle, output)
    events = json.loads((output / "events.json").read_text(encoding="utf-8"))

    assert counts["events"] == 2
    assert counts["major_events"] == 1
    assert events[0]["left_plate"] == "NA"
    assert events[0]["time"] == "2000-01-01T00:00:00+00:00"
    assert (output / "raw" / "along_boundary_pairs.csv").is_file()
