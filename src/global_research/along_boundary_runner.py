"""Bundle-stage runner for Athena's along-boundary interaction study."""

from __future__ import annotations

import csv
import json
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any

from src.catalog.storage import events_from_frame, load_catalog
from src.global_research.along_boundary_interaction import (
    ALONG_BOUNDARY_STUDY_ID,
    DEFAULT_ALONG_BOUNDARY_TIME_WINDOWS_DAYS,
    DEFAULT_ALONG_BOUNDARY_WINDOWS_KM,
    AlongBoundaryPair,
    AlongBoundaryWindowObservation,
    along_boundary_pair_to_record,
    along_boundary_window_to_record,
    build_along_boundary_pairs,
    build_along_boundary_windows,
    summarize_along_boundary_study,
)
from src.global_research.interaction import DEFAULT_SOURCE_MAGNITUDE_THRESHOLDS
from src.global_research.plate_boundaries import (
    PlateBoundaryAssociation,
    parse_pb2002_steps,
)
from src.global_research.plate_boundary_network import PlateBoundaryGraph
from src.global_research.sources import research_source_citation


def run_along_boundary_study(
    *,
    bundle_dir: str | Path,
    plate_boundary_steps_path: str | Path,
    max_lag_days: float = 365.0,
    max_along_boundary_distance_km: float = 2000.0,
    max_prepared_boundary_offset_km: float | None = None,
    time_windows_days: tuple[float, ...] = DEFAULT_ALONG_BOUNDARY_TIME_WINDOWS_DAYS,
    distance_windows_km: tuple[float, ...] = DEFAULT_ALONG_BOUNDARY_WINDOWS_KM,
    source_magnitude_thresholds: tuple[float, ...] = (
        DEFAULT_SOURCE_MAGNITUDE_THRESHOLDS
    ),
) -> dict[str, Any]:
    """Generate and attach along-boundary study artifacts to a prepared bundle."""

    destination = Path(bundle_dir)
    metadata_path = destination / "metadata.json"
    catalog_path = destination / "catalog.csv"
    plate_context_path = destination / "event_plate_context.csv"
    for path in (metadata_path, catalog_path, plate_context_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing required prepared artifact: {path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("plate_boundary_context_included") is not True:
        raise ValueError("Along-boundary study requires prepared PB2002 context.")
    if metadata.get("report_is_nonpredictive") is not True:
        raise ValueError("Prepared bundle must retain its nonpredictive marker.")

    frame = load_catalog(catalog_path)
    events = events_from_frame(frame)
    associations = _read_plate_associations(plate_context_path)
    steps = parse_pb2002_steps(
        Path(plate_boundary_steps_path).read_text(encoding="utf-8")
    )
    graph = PlateBoundaryGraph.build(steps)

    prepared_offset = (
        float(max_prepared_boundary_offset_km)
        if max_prepared_boundary_offset_km is not None
        else float(metadata.get("max_plate_boundary_association_distance_km", 500.0))
    )
    minimum_magnitude = float(metadata["minimum_magnitude"])
    profile_start = _parse_utc(metadata["start_utc"])
    profile_end = _parse_utc(metadata["end_utc"])

    pairs = build_along_boundary_pairs(
        events,
        associations,
        graph,
        minimum_magnitude=minimum_magnitude,
        max_lag_days=max_lag_days,
        max_along_boundary_distance_km=max_along_boundary_distance_km,
        max_prepared_boundary_offset_km=prepared_offset,
    )
    observations = build_along_boundary_windows(
        events,
        associations,
        graph,
        pairs,
        profile_start=profile_start,
        profile_end=profile_end,
        minimum_magnitude=minimum_magnitude,
        time_windows_days=time_windows_days,
        distance_windows_km=distance_windows_km,
    )
    summary = summarize_along_boundary_study(
        pairs,
        observations,
        source_magnitude_thresholds=source_magnitude_thresholds,
    )
    bird = research_source_citation("plate_boundaries", "bird_pb2002")
    summary.update(
        profile_id=metadata["profile_id"],
        catalog_minimum_magnitude=minimum_magnitude,
        pair_count=len(pairs),
        window_observation_count=len(observations),
        plate_projection_count=len(associations),
        pb2002_graph_node_count=graph.node_count,
        pb2002_graph_edge_count=graph.edge_count,
        pb2002_graph_component_count=graph.component_count,
        maximum_pair_lag_days=float(max_lag_days),
        maximum_along_boundary_distance_km=float(max_along_boundary_distance_km),
        prepared_boundary_offset_limit_km=prepared_offset,
        candidate_radial_envelope_km=(
            float(max_along_boundary_distance_km) + 2.0 * prepared_offset
        ),
        time_windows_days=[float(value) for value in time_windows_days],
        distance_windows_km=[float(value) for value in distance_windows_km],
        source_citations=[bird],
        limitations=[
            "The frozen cohort contains M6.0+ earthquakes only and does not represent "
            "ordinary lower-magnitude aftershock populations.",
            "Event epicenters are projected to their already-prepared nearest PB2002 "
            "digitization step; the mapped boundary is not the earthquake rupture.",
            "Shortest same-plate-pair PB2002 graph distance is a tectonic geometry "
            "variable, not a stress-transfer, energy-transfer, or rupture path.",
            "PB2002 is a generalized global plate-boundary model published in 2003; "
            "local fault complexity is not resolved by this network.",
            "Pairs with missing plate projections, different plate pairs, or disconnected "
            "same-pair network geometry remain explicitly unavailable rather than being "
            "assigned invented routes.",
            "Along-boundary and radial comparisons use route-available pairs, but source "
            "windows overlap and remain statistically dependent.",
            "V1 is descriptive only. A dependence-aware randomized/null model must be "
            "validated before Athena reports statistical significance.",
            "The study is retrospective and nonpredictive; no future-earthquake "
            "probability is produced.",
        ],
    )

    _write_pairs(destination / "along_boundary_pairs.csv", pairs)
    _write_windows(destination / "along_boundary_windows.csv", observations)
    _write_json(destination / "along_boundary_summary.json", summary)

    metadata.update(
        bundle_schema_version=5,
        along_boundary_study_included=True,
        along_boundary_study_id=ALONG_BOUNDARY_STUDY_ID,
        along_boundary_analysis_schema_version=summary["schema_version"],
        along_boundary_pair_count=len(pairs),
        along_boundary_window_observation_count=len(observations),
        along_boundary_source_magnitude_statistic_count=summary[
            "source_magnitude_statistic_count"
        ],
        along_boundary_annular_statistic_count=summary["annular_statistic_count"],
        along_boundary_route_available_pair_count=summary["coverage"][
            "route_available_pair_count"
        ],
        along_boundary_within_limit_pair_count=summary["coverage"][
            "within_along_boundary_limit_pair_count"
        ],
        along_boundary_missing_projection_pair_count=summary["coverage"][
            "missing_projection_pair_count"
        ],
        along_boundary_different_plate_pair_count=summary["coverage"][
            "different_plate_pair_count"
        ],
        along_boundary_disconnected_same_pair_count=summary["coverage"][
            "disconnected_same_plate_pair_count"
        ],
        along_boundary_graph_node_count=graph.node_count,
        along_boundary_graph_edge_count=graph.edge_count,
        along_boundary_graph_component_count=graph.component_count,
        along_boundary_routing_scope="same_plate_pair",
        along_boundary_max_pair_lag_days=float(max_lag_days),
        along_boundary_max_distance_km=float(max_along_boundary_distance_km),
        along_boundary_candidate_radial_envelope_km=(
            float(max_along_boundary_distance_km) + 2.0 * prepared_offset
        ),
        along_boundary_time_windows_days=[float(value) for value in time_windows_days],
        along_boundary_distance_windows_km=[
            float(value) for value in distance_windows_km
        ],
        along_boundary_source_magnitude_thresholds=[
            float(value) for value in source_magnitude_thresholds
        ],
        along_boundary_inference_status=summary["inference_status"],
        along_boundary_semantics=(
            "Retrospective descriptive comparison of shortest mapped same-plate-pair "
            "PB2002 graph distance with epicentral great-circle distance on the same "
            "route-available event pairs. Mapped routes are tectonic geometry context "
            "only; no causal triggering, stress transfer, energy transfer, rupture "
            "propagation, or future-earthquake probability is inferred."
        ),
    )
    _write_json(metadata_path, metadata)
    return summary


def _read_plate_associations(path: Path) -> tuple[PlateBoundaryAssociation, ...]:
    rows: list[PlateBoundaryAssociation] = []
    with path.open("r", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            rows.append(
                PlateBoundaryAssociation(
                    event_id=row["event_id"],
                    step_id=row["step_id"],
                    boundary_id=row["boundary_id"],
                    left_plate=row["left_plate"],
                    right_plate=row["right_plate"],
                    boundary_class=row["boundary_class"],
                    polarity=row["polarity"],
                    distance_km=float(row["distance_km"]),
                    source=row["source"],
                )
            )
    return tuple(rows)


def _write_pairs(path: Path, pairs: tuple[AlongBoundaryPair, ...]) -> None:
    fieldnames = tuple(field.name for field in fields(AlongBoundaryPair))
    _write_records(
        path,
        fieldnames,
        (along_boundary_pair_to_record(item) for item in pairs),
    )


def _write_windows(
    path: Path,
    observations: tuple[AlongBoundaryWindowObservation, ...],
) -> None:
    fieldnames = tuple(
        field.name for field in fields(AlongBoundaryWindowObservation)
    ) + ("edge_eligible",)
    _write_records(
        path,
        fieldnames,
        (along_boundary_window_to_record(item) for item in observations),
    )


def _write_records(
    path: Path,
    fieldnames: tuple[str, ...],
    records: Any,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Prepared metadata timestamps must be timezone-aware.")
    return parsed
