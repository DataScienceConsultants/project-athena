"""Build structured Project Athena Observatory reports.

This module is the integration layer between Athena's earthquake catalog,
metrics engine, status interpretation, and structured report models.

It performs no terminal formatting. Consumers receive an ObservatoryReport
that can be printed, serialized to JSON, exposed through an API, or passed
to Project Seismic.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.metrics.activity import (
    add_rolling_activity_metrics,
    build_daily_activity,
    load_catalog,
    summarize_activity,
)
from src.metrics.depth import (
    add_rolling_depth_metrics,
    build_daily_depth,
    summarize_depth,
)
from src.metrics.energy import (
    add_rolling_energy_metrics,
    build_daily_energy,
    summarize_energy,
)
from src.metrics.magnitude import summarize_magnitude
from src.observatory.models import (
    ActivitySection,
    CatalogSection,
    DepthSection,
    EnergySection,
    MagnitudeSection,
    ObservatoryReport,
    StatusSection,
)
from src.observatory.status import (
    classify_activity,
    classify_depth,
    classify_energy,
    confidence_from_history,
    overall_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGIONS_CONFIG_PATH = PROJECT_ROOT / "config" / "regions.json"
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"

METHODOLOGY_VERSION = "observatory-v0.1"

DISCLAIMER = (
    "Experimental seismic analysis. Not an official earthquake "
    "prediction, warning, or emergency alert."
)


def find_latest_catalog(
    directory: str | Path = PROCESSED_DATA_DIRECTORY,
) -> Path:
    """Return the most recently modified processed Parquet catalog.

    Args:
        directory: Directory containing processed Athena catalogs.

    Raises:
        FileNotFoundError: When the directory or a Parquet catalog does
            not exist.
    """

    catalog_directory = Path(directory)

    if not catalog_directory.exists():
        raise FileNotFoundError(
            f"Processed-data directory was not found: "
            f"{catalog_directory}"
        )

    catalogs = list(
        catalog_directory.glob("*_earthquakes.parquet")
    )

    if not catalogs:
        raise FileNotFoundError(
            "No processed Parquet earthquake catalog was found. "
            "Run the historical catalog builder first."
        )

    return max(
        catalogs,
        key=lambda path: path.stat().st_mtime,
    )


def load_regions_configuration(
    configuration_path: str | Path = REGIONS_CONFIG_PATH,
) -> dict[str, Any]:
    """Load and validate Athena's configured regions."""

    path = Path(configuration_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Region configuration was not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as configuration_file:
            configuration = json.load(configuration_file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Region configuration contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(configuration, dict):
        raise ValueError(
            "Region configuration must contain a JSON object."
        )

    regions = configuration.get("regions")

    if not isinstance(regions, dict) or not regions:
        raise ValueError(
            "Region configuration does not contain any regions."
        )

    return configuration


def infer_region_key(
    catalog_path: str | Path,
    configuration: dict[str, Any],
) -> str:
    """Infer a configured region key from a catalog filename."""

    filename = Path(catalog_path).stem
    regions = configuration["regions"]

    matching_keys = [
        key
        for key in regions
        if filename.startswith(f"{key}_")
    ]

    if matching_keys:
        return max(matching_keys, key=len)

    default_region = configuration.get("default_region")

    if (
        isinstance(default_region, str)
        and default_region in regions
    ):
        return default_region

    raise ValueError(
        "Athena could not infer the catalog region and no valid "
        "default region is configured."
    )


def resolve_region(
    *,
    catalog_path: str | Path,
    region_key: str | None = None,
    configuration_path: str | Path = REGIONS_CONFIG_PATH,
) -> tuple[str, str]:
    """Resolve the region key and display name for a catalog."""

    configuration = load_regions_configuration(
        configuration_path
    )
    regions = configuration["regions"]

    selected_key = region_key or infer_region_key(
        catalog_path,
        configuration,
    )

    region = regions.get(selected_key)

    if not isinstance(region, dict):
        available = ", ".join(sorted(regions))
        raise ValueError(
            f'Region "{selected_key}" was not found. '
            f"Available regions: {available}"
        )

    region_name = str(region.get("name", selected_key))

    return selected_key, region_name


def build_observatory_report(
    catalog_path: str | Path | None = None,
    *,
    region_key: str | None = None,
    configuration_path: str | Path = REGIONS_CONFIG_PATH,
) -> ObservatoryReport:
    """Build a complete Observatory report from an Athena catalog.

    When ``catalog_path`` is omitted, Athena uses the most recently
    modified processed Parquet catalog.
    """

    selected_catalog_path = (
        Path(catalog_path)
        if catalog_path is not None
        else find_latest_catalog()
    )

    catalog = load_catalog(selected_catalog_path)

    selected_region_key, region_name = resolve_region(
        catalog_path=selected_catalog_path,
        region_key=region_key,
        configuration_path=configuration_path,
    )

    return build_observatory_report_from_dataframe(
        catalog,
        catalog_path=selected_catalog_path,
        region_key=selected_region_key,
        region_name=region_name,
    )


def build_observatory_report_from_dataframe(
    catalog: pd.DataFrame,
    *,
    catalog_path: str | Path,
    region_key: str,
    region_name: str,
) -> ObservatoryReport:
    """Build an Observatory report from an in-memory catalog.

    This entry point supports testing, notebooks, APIs, and future
    alternative catalog-storage systems.
    """

    if not isinstance(catalog, pd.DataFrame):
        raise TypeError(
            "Catalog must be provided as a pandas DataFrame."
        )

    if catalog.empty:
        raise ValueError(
            "An Observatory report cannot be built from an empty catalog."
        )

    daily_activity = build_daily_activity(
        catalog,
        include_inactive_days=True,
    )
    activity_metrics = add_rolling_activity_metrics(
        daily_activity
    )
    activity_summary = summarize_activity(daily_activity)

    daily_energy = build_daily_energy(
        catalog,
        include_inactive_days=True,
    )
    energy_metrics = add_rolling_energy_metrics(
        daily_energy
    )
    energy_summary = summarize_energy(catalog)

    daily_depth = build_daily_depth(
        catalog,
        include_inactive_days=True,
    )
    depth_metrics = add_rolling_depth_metrics(
        daily_depth
    )
    depth_summary = summarize_depth(catalog)

    magnitude_summary = summarize_magnitude(catalog)

    latest_activity = activity_metrics.iloc[-1]
    latest_energy = energy_metrics.iloc[-1]
    latest_depth = depth_metrics.iloc[-1]

    activity_ratio = _optional_float(
        latest_activity.get("activity_ratio_7d")
    )
    energy_ratio = _optional_float(
        latest_energy.get("energy_ratio_7d")
    )
    depth_difference = _optional_float(
        latest_depth.get("depth_difference_7d_km")
    )

    activity_status = classify_activity(activity_ratio)
    energy_status = classify_energy(energy_ratio)
    depth_status = classify_depth(depth_difference)

    combined_status = overall_status(
        activity=activity_status,
        energy=energy_status,
        depth=depth_status,
    )

    event_times = pd.to_datetime(
        catalog["event_time_utc"],
        utc=True,
        errors="coerce",
    ).dropna()

    if event_times.empty:
        raise ValueError(
            "Catalog does not contain any valid event timestamps."
        )

    first_event_time = event_times.min()
    last_event_time = event_times.max()

    historical_days = max(
        activity_summary.calendar_days - 7,
        0,
    )

    return ObservatoryReport(
        generated_at_utc=datetime.now(
            timezone.utc
        ).isoformat(),
        catalog=CatalogSection(
            catalog_path=_display_path(catalog_path),
            region_key=region_key,
            region_name=region_name,
            event_count=int(len(catalog)),
            first_event_time_utc=first_event_time.isoformat(),
            last_event_time_utc=last_event_time.isoformat(),
            calendar_days=activity_summary.calendar_days,
        ),
        activity=ActivitySection(
            total_events=activity_summary.total_events,
            active_days=activity_summary.active_days,
            calendar_days=activity_summary.calendar_days,
            average_events_per_day=(
                activity_summary.average_events_per_day
            ),
            maximum_events_in_one_day=(
                activity_summary.maximum_events_in_one_day
            ),
            busiest_day=activity_summary.busiest_day,
            events_last_7_days=int(
                latest_activity["event_count_7d"]
            ),
            events_last_30_days=int(
                latest_activity["event_count_30d"]
            ),
            average_events_last_7_days=float(
                latest_activity["daily_average_7d"]
            ),
            historical_average_events_per_day=_optional_float(
                latest_activity.get(
                    "historical_expanding_average"
                )
            ),
            activity_ratio_7d=activity_ratio,
            status=activity_status.status,
            explanation=activity_status.explanation,
        ),
        magnitude=MagnitudeSection(
            events_with_magnitude=(
                magnitude_summary.events_with_magnitude
            ),
            missing_magnitude_count=(
                magnitude_summary.missing_magnitude_count
            ),
            average_magnitude=(
                magnitude_summary.average_magnitude
            ),
            median_magnitude=(
                magnitude_summary.median_magnitude
            ),
            minimum_magnitude=(
                magnitude_summary.minimum_magnitude
            ),
            maximum_magnitude=(
                magnitude_summary.maximum_magnitude
            ),
            magnitude_3_plus=magnitude_summary.magnitude_3_plus,
            magnitude_4_plus=magnitude_summary.magnitude_4_plus,
            magnitude_5_plus=magnitude_summary.magnitude_5_plus,
            largest_event_id=magnitude_summary.largest_event_id,
            largest_event_time_utc=(
                magnitude_summary.largest_event_time_utc
            ),
            largest_event_place=(
                magnitude_summary.largest_event_place
            ),
        ),
        energy=EnergySection(
            events_with_magnitude=(
                energy_summary.event_count_with_magnitude
            ),
            total_energy_joules=(
                energy_summary.total_energy_joules
            ),
            equivalent_single_magnitude=(
                energy_summary.equivalent_single_magnitude
            ),
            maximum_event_energy_joules=(
                energy_summary.maximum_event_energy_joules
            ),
            maximum_energy_magnitude=(
                energy_summary.maximum_energy_magnitude
            ),
            maximum_energy_event_id=(
                energy_summary.maximum_energy_event_id
            ),
            energy_last_7_days_joules=float(
                latest_energy["total_energy_7d_joules"]
            ),
            historical_average_daily_energy_joules=(
                _optional_float(
                    latest_energy.get(
                        "historical_expanding_energy_average_joules"
                    )
                )
            ),
            energy_ratio_7d=energy_ratio,
            status=energy_status.status,
            explanation=energy_status.explanation,
        ),
        depth=DepthSection(
            events_with_depth=depth_summary.events_with_depth,
            average_depth_km=depth_summary.average_depth_km,
            median_depth_km=depth_summary.median_depth_km,
            minimum_depth_km=depth_summary.minimum_depth_km,
            maximum_depth_km=depth_summary.maximum_depth_km,
            shallow_events=depth_summary.shallow_events,
            intermediate_events=(
                depth_summary.intermediate_events
            ),
            deep_events=depth_summary.deep_events,
            average_depth_last_7_days_km=_optional_float(
                latest_depth.get("average_depth_7d_km")
            ),
            historical_average_depth_km=_optional_float(
                latest_depth.get(
                    "historical_expanding_depth_average_km"
                )
            ),
            depth_difference_7d_km=depth_difference,
            status=depth_status.status,
            explanation=depth_status.explanation,
        ),
        status=StatusSection(
            overall_status=combined_status,
            confidence=confidence_from_history(
                historical_days
            ),
            methodology_version=METHODOLOGY_VERSION,
            disclaimer=DISCLAIMER,
        ),
    )


def _optional_float(value: Any) -> float | None:
    """Return a finite float or None."""

    if value is None or pd.isna(value):
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric_value):
        return None

    return numeric_value


def _display_path(path: str | Path) -> str:
    """Return a readable project-relative path when possible."""

    resolved_path = Path(path)

    try:
        return str(
            resolved_path.resolve().relative_to(
                PROJECT_ROOT.resolve()
            )
        )
    except ValueError:
        return str(resolved_path)