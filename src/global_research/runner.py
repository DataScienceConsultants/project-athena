"""Orchestration for reproducible global Athena research bundles."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.catalog.downloader import USGSCatalogDownloader
from src.global_research.catalog import (
    USGSCatalogCounter,
    download_global_catalog,
    export_global_catalog_csv,
)
from src.global_research.fault_index import (
    FaultGridIndex,
    associate_catalog_events_indexed,
)
from src.global_research.faults import load_fault_geojson
from src.global_research.models import (
    FaultAssociation,
    GlobalCatalogPlan,
    GlobalResearchProfile,
    REFERENCE_50_YEAR_PROFILE,
)
from src.global_research.plate_boundaries import (
    PB2002_SOURCE,
    PlateBoundaryAssociation,
    PlateBoundaryGridIndex,
    associate_catalog_events_with_plate_boundaries,
    parse_pb2002_steps,
    plate_boundary_feature_collection,
)
from src.global_research.planner import AdaptiveGlobalCatalogPlanner
from src.global_research.sources import research_source_citation

DEFAULT_OUTPUT_ROOT = Path("data/global_research")


@dataclass(frozen=True, slots=True)
class GlobalResearchBundle:
    output_dir: Path
    metadata: dict[str, Any]


def run_global_research(
    *,
    profile: GlobalResearchProfile = REFERENCE_50_YEAR_PROFILE,
    output_dir: str | Path | None = None,
    fault_geojson_path: str | Path | None = None,
    max_fault_distance_km: float = 250.0,
    plate_boundary_steps_path: str | Path | None = None,
    max_plate_boundary_distance_km: float = 500.0,
    counter: Any = None,
    downloader: Any = None,
    generated_at: datetime | None = None,
) -> GlobalResearchBundle:
    """Plan, download, context-enrich, and persist one retrospective cohort."""
    if not isinstance(profile, GlobalResearchProfile):
        raise TypeError("profile must be GlobalResearchProfile.")
    destination = Path(output_dir or DEFAULT_OUTPUT_ROOT / profile.profile_id)
    destination.mkdir(parents=True, exist_ok=True)

    generated = _generated_at(generated_at)
    count_client = counter or USGSCatalogCounter()
    plan = AdaptiveGlobalCatalogPlanner(count_client).plan(profile)
    catalog = download_global_catalog(
        plan,
        downloader=downloader or USGSCatalogDownloader(),
    )

    export_global_catalog_csv(catalog, destination / "catalog.csv")
    _write_json(destination / "catalog_plan.json", _plan_payload(plan))

    source_citations = [research_source_citation("catalogs", "usgs_comcat")]
    metadata: dict[str, Any] = {
        "bundle_schema_version": 2,
        "profile_id": profile.profile_id,
        "start_utc": _utc_string(profile.start_time),
        "end_utc": _utc_string(profile.end_time),
        "minimum_magnitude": profile.minimum_magnitude,
        "generated_at_utc": _utc_string(generated),
        "catalog_source": "USGS ComCat",
        "catalog_event_count": catalog.event_count,
        "catalog_query_count": plan.query_count,
        "catalog_preflight_expected_event_count": plan.expected_event_count,
        "fault_context_included": fault_geojson_path is not None,
        "plate_boundary_context_included": plate_boundary_steps_path is not None,
        "research_mode": "retrospective_global",
        "report_is_nonpredictive": True,
        "source_citations": source_citations,
    }

    if fault_geojson_path is not None:
        with Path(fault_geojson_path).open("r", encoding="utf-8") as source:
            fault_payload = json.load(source)
        faults = load_fault_geojson(fault_payload)
        _write_geojson(destination / "faults.geojson", fault_payload)

        fault_index = FaultGridIndex.build(
            faults,
            search_radius_km=max_fault_distance_km,
        )
        associations = associate_catalog_events_indexed(catalog.events, fault_index)
        _write_associations(destination / "fault_associations.csv", associations)
        source_citations.append(
            research_source_citation("faults", "gem_global_active_faults")
        )
        metadata.update(
            fault_source="GEM Global Active Faults Database",
            fault_geojson_included=True,
            fault_geojson_feature_count=len(fault_payload["features"]),
            normalized_fault_trace_count=len(faults),
            event_fault_association_count=len(associations),
            max_fault_association_distance_km=float(max_fault_distance_km),
            fault_candidate_index="2-degree conservative expanded-envelope grid",
            fault_distance_method="exact great-circle point-to-segment distance",
            fault_association_semantics=(
                "Nearest mapped active-fault geographic context within the configured "
                "distance; not causal attribution."
            ),
        )

    if plate_boundary_steps_path is not None:
        steps_text = Path(plate_boundary_steps_path).read_text(encoding="utf-8")
        plate_steps = parse_pb2002_steps(steps_text)
        plate_geojson = plate_boundary_feature_collection(plate_steps)
        _write_geojson(destination / "plate_boundaries.geojson", plate_geojson)

        plate_index = PlateBoundaryGridIndex.build(
            plate_steps,
            search_radius_km=max_plate_boundary_distance_km,
        )
        plate_associations = associate_catalog_events_with_plate_boundaries(
            catalog.events,
            plate_index,
        )
        _write_plate_boundary_associations(
            destination / "event_plate_context.csv",
            plate_associations,
        )
        source_citations.append(
            research_source_citation("plate_boundaries", "bird_pb2002")
        )
        metadata.update(
            plate_boundary_source=PB2002_SOURCE,
            plate_boundary_geojson_included=True,
            plate_boundary_step_count=len(plate_steps),
            plate_boundary_geojson_feature_count=len(plate_geojson["features"]),
            event_plate_boundary_association_count=len(plate_associations),
            max_plate_boundary_association_distance_km=float(
                max_plate_boundary_distance_km
            ),
            plate_boundary_candidate_index=(
                "2-degree conservative expanded-envelope grid"
            ),
            plate_boundary_distance_method=(
                "exact great-circle point-to-segment distance"
            ),
            plate_boundary_association_semantics=(
                "Nearest mapped PB2002 digitization step within the configured "
                "distance. Adjacent plates and boundary class are source-defined "
                "tectonic context, not causal attribution or future-earthquake "
                "probability."
            ),
        )

    _write_json(destination / "metadata.json", metadata)
    return GlobalResearchBundle(output_dir=destination, metadata=metadata)


def run_reference_50_year_research(**kwargs: Any) -> GlobalResearchBundle:
    """Run the frozen global M6+ cohort from 1976-01-01 through 2026-01-01."""
    return run_global_research(profile=REFERENCE_50_YEAR_PROFILE, **kwargs)


def _generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if not isinstance(value, datetime):
        raise TypeError("generated_at must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware.")
    return value.astimezone(UTC)


def _utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _plan_payload(plan: GlobalCatalogPlan) -> dict[str, Any]:
    return {
        "profile": {
            "profile_id": plan.profile.profile_id,
            "start_utc": _utc_string(plan.profile.start_time),
            "end_utc": _utc_string(plan.profile.end_time),
            "minimum_magnitude": plan.profile.minimum_magnitude,
            "description": plan.profile.description,
        },
        "expected_event_count": plan.expected_event_count,
        "query_count": plan.query_count,
        "partitions": [
            {
                "query_id": item.query_id,
                "expected_event_count": item.expected_event_count,
                "start_utc": _utc_string(item.start_time),
                "end_utc": _utc_string(item.end_time),
                "minimum_magnitude": item.minimum_magnitude,
                "bounds": {
                    "min_latitude": item.bounds.min_latitude,
                    "max_latitude": item.bounds.max_latitude,
                    "min_longitude": item.bounds.min_longitude,
                    "max_longitude": item.bounds.max_longitude,
                },
            }
            for item in plan.partitions
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_geojson(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _write_associations(path: Path, associations: tuple[FaultAssociation, ...]) -> None:
    fields = ("event_id", "fault_id", "fault_name", "distance_km", "fault_source")
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for item in associations:
            writer.writerow(
                {
                    "event_id": item.event_id,
                    "fault_id": item.fault_id,
                    "fault_name": item.fault_name,
                    "distance_km": item.distance_km,
                    "fault_source": item.fault_source,
                }
            )


def _write_plate_boundary_associations(
    path: Path,
    associations: tuple[PlateBoundaryAssociation, ...],
) -> None:
    fields = (
        "event_id",
        "step_id",
        "boundary_id",
        "left_plate",
        "right_plate",
        "boundary_class",
        "polarity",
        "distance_km",
        "source",
    )
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for item in associations:
            writer.writerow(
                {
                    "event_id": item.event_id,
                    "step_id": item.step_id,
                    "boundary_id": item.boundary_id,
                    "left_plate": item.left_plate,
                    "right_plate": item.right_plate,
                    "boundary_class": item.boundary_class,
                    "polarity": item.polarity,
                    "distance_km": item.distance_km,
                    "source": item.source,
                }
            )
