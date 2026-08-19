"""Build browser-friendly Athena research dashboard data from bundle schema v5."""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path
from typing import Any

RAW_FILES = (
    "metadata.json",
    "catalog.csv",
    "catalog_plan.json",
    "fault_associations.csv",
    "faults.geojson",
    "event_plate_context.csv",
    "plate_boundaries.geojson",
    "interaction_pairs.csv",
    "interaction_windows.csv",
    "interaction_summary.json",
    "along_boundary_pairs.csv",
    "along_boundary_windows.csv",
    "along_boundary_summary.json",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return None if number is None else int(number)


def _bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _iso_time(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(" ", "T", 1) if "T" not in value and " " in value else value


def build_research_dashboard_data(bundle_dir: Path, output_dir: Path) -> dict[str, int]:
    for name in RAW_FILES:
        if not (bundle_dir / name).is_file():
            raise FileNotFoundError(f"Missing v5 bundle file: {bundle_dir / name}")

    metadata = _read_json(bundle_dir / "metadata.json")
    if metadata.get("bundle_schema_version") != 5:
        raise ValueError("Research dashboard requires bundle schema v5.")

    catalog = _read_csv(bundle_dir / "catalog.csv")
    plate_rows = _read_csv(bundle_dir / "event_plate_context.csv")
    fault_rows = _read_csv(bundle_dir / "fault_associations.csv")
    pair_rows = _read_csv(bundle_dir / "along_boundary_pairs.csv")
    window_rows = _read_csv(bundle_dir / "along_boundary_windows.csv")
    along_summary = _read_json(bundle_dir / "along_boundary_summary.json")
    radial_summary = _read_json(bundle_dir / "interaction_summary.json")

    plate_by_event = {row["event_id"]: row for row in plate_rows}
    fault_by_event = {row["event_id"]: row for row in fault_rows}
    events: list[dict[str, Any]] = []
    major_ids: set[str] = set()

    for row in catalog:
        event_id = row["event_id"]
        plate = plate_by_event.get(event_id, {})
        fault = fault_by_event.get(event_id, {})
        magnitude = _float(row.get("magnitude"))
        event_type = row.get("event_type") or ""
        if magnitude is not None and magnitude >= 7.0 and event_type == "earthquake":
            major_ids.add(event_id)
        events.append(
            {
                "event_id": event_id,
                "time": _iso_time(row.get("time")),
                "latitude": _float(row.get("latitude")),
                "longitude": _float(row.get("longitude")),
                "depth_km": _float(row.get("depth")),
                "magnitude": magnitude,
                "magnitude_type": row.get("magnitude_type") or None,
                "place": row.get("place") or "Unknown location",
                "status": row.get("status") or None,
                "event_type": event_type,
                "source": row.get("source") or None,
                "updated_at": _iso_time(row.get("updated_at")),
                "step_id": plate.get("step_id") or None,
                "boundary_id": plate.get("boundary_id") or None,
                # PB2002 uses the literal code NA for North America; never treat it as missing.
                "left_plate": plate.get("left_plate") or None,
                "right_plate": plate.get("right_plate") or None,
                "boundary_class": plate.get("boundary_class") or None,
                "boundary_polarity": plate.get("polarity") or None,
                "distance_to_boundary_km": _float(plate.get("distance_km")),
                "fault_id": fault.get("fault_id") or None,
                "fault_name": fault.get("fault_name") or None,
                "distance_to_fault_km": _float(fault.get("distance_km")),
            }
        )

    major_pairs: list[dict[str, Any]] = []
    for row in pair_rows:
        if row.get("route_status") != "available":
            continue
        earlier = row.get("earlier_event_id") or ""
        later = row.get("later_event_id") or ""
        if earlier not in major_ids and later not in major_ids:
            continue
        major_pairs.append(
            {
                "earlier_event_id": earlier,
                "later_event_id": later,
                "earlier_time": _iso_time(row.get("earlier_time")),
                "later_time": _iso_time(row.get("later_time")),
                "lag_days": _float(row.get("lag_days")),
                "radial_distance_km": _float(row.get("radial_distance_km")),
                "along_boundary_distance_km": _float(row.get("along_boundary_distance_km")),
                "earlier_magnitude": _float(row.get("earlier_magnitude")),
                "later_magnitude": _float(row.get("later_magnitude")),
                "earlier_boundary_id": row.get("earlier_boundary_id") or None,
                "later_boundary_id": row.get("later_boundary_id") or None,
                "earlier_boundary_class": row.get("earlier_boundary_class") or None,
                "later_boundary_class": row.get("later_boundary_class") or None,
                "same_plate_pair": _bool(row.get("same_plate_pair")),
                "same_boundary_id": _bool(row.get("same_boundary_id")),
                "within_along_boundary_limit": _bool(row.get("within_along_boundary_limit")),
            }
        )

    major_windows: list[dict[str, Any]] = []
    for row in window_rows:
        source_id = row.get("source_event_id") or ""
        if source_id not in major_ids:
            continue
        major_windows.append(
            {
                "source_event_id": source_id,
                "source_time": _iso_time(row.get("source_time")),
                "source_magnitude": _float(row.get("source_magnitude")),
                "source_boundary_id": row.get("source_boundary_id") or None,
                "source_boundary_class": row.get("source_boundary_class") or None,
                "source_distance_to_boundary_km": _float(row.get("source_distance_to_boundary_km")),
                "time_window_days": _float(row.get("time_window_days")),
                "distance_window_km": _float(row.get("distance_window_km")),
                "pre_count_along_boundary": _int(row.get("pre_count_along_boundary")),
                "post_count_along_boundary": _int(row.get("post_count_along_boundary")),
                "pre_count_routed_radial": _int(row.get("pre_count_routed_radial")),
                "post_count_routed_radial": _int(row.get("post_count_routed_radial")),
                "edge_eligible": _bool(row.get("edge_eligible")),
            }
        )

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in RAW_FILES:
        shutil.copy2(bundle_dir / name, raw_dir / name)

    _write_json(output_dir / "events.json", events)
    _write_json(output_dir / "major_pairs.json", major_pairs)
    _write_json(output_dir / "major_windows.json", major_windows)
    _write_json(
        output_dir / "study.json",
        {"metadata": metadata, "along_boundary": along_summary, "radial": radial_summary},
    )
    manifest = {
        "bundle_schema_version": 5,
        "profile_id": metadata.get("profile_id"),
        "generated_at_utc": metadata.get("generated_at_utc"),
        "catalog_event_count": len(events),
        "major_event_count": len(major_ids),
        "major_route_pair_count": len(major_pairs),
        "major_window_count": len(major_windows),
        "raw_file_count": len(RAW_FILES),
        "release_tag": "research-global-m6-1976-2025-v5",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return {
        "events": len(events),
        "major_events": len(major_ids),
        "major_pairs": len(major_pairs),
        "major_windows": len(major_windows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_research_dashboard_data(args.bundle_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
