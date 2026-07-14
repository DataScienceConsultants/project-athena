"""Build a historical earthquake catalog for Project Athena.

This pipeline downloads earthquake events month by month for Athena's
default configured region, removes duplicates, and saves analysis-ready
CSV and Parquet files plus a catalog summary.
"""

from __future__ import annotations

import argparse
import json
import logging
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.ingestion.provider import EarthquakeEvent, RegionBounds
from src.ingestion.usgs_client import UsgsApiError, UsgsClient

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGIONS_CONFIG_PATH = PROJECT_ROOT / "config" / "regions.json"
RAW_DATA_DIRECTORY = PROJECT_ROOT / "data" / "raw"
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"


def load_configuration() -> dict[str, Any]:
    """Load and validate Athena's region configuration."""

    if not REGIONS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Region configuration not found: {REGIONS_CONFIG_PATH}"
        )

    try:
        with REGIONS_CONFIG_PATH.open("r", encoding="utf-8") as file:
            configuration = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Region configuration contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(configuration, dict):
        raise ValueError("Region configuration must be a JSON object.")

    regions = configuration.get("regions")
    default_region = configuration.get("default_region")

    if not isinstance(regions, dict) or not regions:
        raise ValueError("No regions are defined in regions.json.")

    if not isinstance(default_region, str):
        raise ValueError("default_region is missing from regions.json.")

    if default_region not in regions:
        raise ValueError(
            f'Default region "{default_region}" is not configured.'
        )

    return configuration


def get_region(
    configuration: dict[str, Any],
    region_key: str | None,
) -> tuple[str, dict[str, Any]]:
    """Return the requested region or Athena's default region."""

    selected_key = region_key or configuration["default_region"]
    regions = configuration["regions"]
    selected_region = regions.get(selected_key)

    if not isinstance(selected_region, dict):
        available = ", ".join(sorted(regions))
        raise ValueError(
            f'Region "{selected_key}" was not found. '
            f"Available regions: {available}"
        )

    return selected_key, selected_region


def build_region_bounds(
    region_configuration: dict[str, Any],
) -> RegionBounds:
    """Create validated geographic bounds from configuration."""

    bounds = region_configuration.get("bounds")

    if not isinstance(bounds, dict):
        raise ValueError("The selected region does not contain bounds.")

    try:
        region_bounds = RegionBounds(
            min_latitude=float(bounds["min_latitude"]),
            max_latitude=float(bounds["max_latitude"]),
            min_longitude=float(bounds["min_longitude"]),
            max_longitude=float(bounds["max_longitude"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "The selected region contains invalid geographic bounds."
        ) from exc

    region_bounds.validate()
    return region_bounds


def get_minimum_magnitude(
    region_configuration: dict[str, Any],
) -> float:
    """Read the region's configured minimum magnitude."""

    value = region_configuration.get(
        "default_minimum_magnitude",
        1.0,
    )

    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "The configured minimum magnitude is invalid."
        ) from exc


def validate_year_range(
    start_year: int,
    end_year: int,
) -> None:
    """Validate the requested catalog year range."""

    current_year = datetime.now(timezone.utc).year

    if start_year < 1900:
        raise ValueError("Start year cannot be earlier than 1900.")

    if end_year > current_year:
        raise ValueError(
            f"End year cannot be later than {current_year}."
        )

    if start_year > end_year:
        raise ValueError(
            "Start year must be less than or equal to end year."
        )


def iter_months(
    start_year: int,
    end_year: int,
) -> list[tuple[datetime, datetime]]:
    """Create monthly UTC intervals for an inclusive year range."""

    intervals: list[tuple[datetime, datetime]] = []

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            start_time = datetime(
                year,
                month,
                1,
                tzinfo=timezone.utc,
            )

            if month == 12:
                end_time = datetime(
                    year + 1,
                    1,
                    1,
                    tzinfo=timezone.utc,
                )
            else:
                end_time = datetime(
                    year,
                    month + 1,
                    1,
                    tzinfo=timezone.utc,
                )

            intervals.append((start_time, end_time))

    return intervals


def download_catalog_events(
    *,
    client: UsgsClient,
    bounds: RegionBounds,
    minimum_magnitude: float,
    start_year: int,
    end_year: int,
) -> list[EarthquakeEvent]:
    """Download all monthly events for the requested period."""

    all_events: list[EarthquakeEvent] = []
    intervals = iter_months(start_year, end_year)
    total_months = len(intervals)

    for index, (start_time, end_time) in enumerate(
        intervals,
        start=1,
    ):
        LOGGER.info(
            "Downloading %s-%02d (%s of %s)...",
            start_time.year,
            start_time.month,
            index,
            total_months,
        )

        monthly_events = client.fetch_events(
            start_time=start_time,
            end_time=end_time,
            bounds=bounds,
            minimum_magnitude=minimum_magnitude,
        )

        if len(monthly_events) >= client.DEFAULT_LIMIT:
            raise RuntimeError(
                f"USGS returned its maximum result limit for "
                f"{start_time:%Y-%m}. The interval must be divided "
                "into smaller requests before catalog completeness "
                "can be guaranteed."
            )

        LOGGER.info(
            "%s-%02d returned %s events.",
            start_time.year,
            start_time.month,
            len(monthly_events),
        )

        all_events.extend(monthly_events)

    return client.deduplicate_events(all_events)


def events_to_dataframe(
    events: list[EarthquakeEvent],
) -> pd.DataFrame:
    """Convert normalized earthquake events into a typed DataFrame."""

    columns = [
        "event_id",
        "source",
        "event_time_utc",
        "updated_time_utc",
        "latitude",
        "longitude",
        "depth_km",
        "magnitude",
        "magnitude_type",
        "place",
        "event_type",
        "status",
        "tsunami_flag",
        "felt_reports",
        "significance",
        "alert_level",
        "detail_url",
        "source_url",
    ]

    dataframe = pd.DataFrame.from_records(
        [event.to_dict() for event in events],
        columns=columns,
    )

    if dataframe.empty:
        return dataframe

    dataframe["event_time_utc"] = pd.to_datetime(
        dataframe["event_time_utc"],
        utc=True,
        errors="coerce",
    )

    dataframe["updated_time_utc"] = pd.to_datetime(
        dataframe["updated_time_utc"],
        utc=True,
        errors="coerce",
    )

    numeric_columns = [
        "latitude",
        "longitude",
        "depth_km",
        "magnitude",
        "felt_reports",
        "significance",
    ]

    for column in numeric_columns:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

    dataframe = dataframe.dropna(
        subset=[
            "event_id",
            "event_time_utc",
            "latitude",
            "longitude",
        ]
    )

    dataframe = dataframe.drop_duplicates(
        subset=["source", "event_id"],
        keep="last",
    )

    return dataframe.sort_values(
        ["event_time_utc", "event_id"],
    ).reset_index(drop=True)


def build_summary(
    *,
    dataframe: pd.DataFrame,
    region_key: str,
    region_name: str,
    start_year: int,
    end_year: int,
    minimum_magnitude: float,
) -> dict[str, Any]:
    """Build a descriptive and quality-control catalog summary."""

    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "region_key": region_key,
        "region_name": region_name,
        "requested_start_year": start_year,
        "requested_end_year": end_year,
        "minimum_magnitude": minimum_magnitude,
        "event_count": int(len(dataframe)),
        "duplicate_count_after_processing": int(
            dataframe.duplicated(
                subset=["source", "event_id"]
            ).sum()
        ),
    }

    if dataframe.empty:
        summary.update(
            {
                "first_event_time_utc": None,
                "last_event_time_utc": None,
                "minimum_magnitude_found": None,
                "maximum_magnitude_found": None,
                "average_magnitude": None,
                "average_depth_km": None,
                "missing_magnitude_count": 0,
                "missing_depth_count": 0,
                "events_by_year": {},
            }
        )
        return summary

    magnitudes = dataframe["magnitude"].dropna()
    depths = dataframe["depth_km"].dropna()

    events_by_year = (
        dataframe.groupby(
            dataframe["event_time_utc"].dt.year
        )
        .size()
        .to_dict()
    )

    summary.update(
        {
            "first_event_time_utc": dataframe[
                "event_time_utc"
            ].min().isoformat(),
            "last_event_time_utc": dataframe[
                "event_time_utc"
            ].max().isoformat(),
            "minimum_magnitude_found": (
                float(magnitudes.min())
                if not magnitudes.empty
                else None
            ),
            "maximum_magnitude_found": (
                float(magnitudes.max())
                if not magnitudes.empty
                else None
            ),
            "average_magnitude": (
                round(float(magnitudes.mean()), 3)
                if not magnitudes.empty
                else None
            ),
            "average_depth_km": (
                round(float(depths.mean()), 3)
                if not depths.empty
                else None
            ),
            "missing_magnitude_count": int(
                dataframe["magnitude"].isna().sum()
            ),
            "missing_depth_count": int(
                dataframe["depth_km"].isna().sum()
            ),
            "events_by_year": {
                str(year): int(count)
                for year, count in events_by_year.items()
            },
        }
    )

    return summary


def save_catalog(
    *,
    dataframe: pd.DataFrame,
    summary: dict[str, Any],
    region_key: str,
    start_year: int,
    end_year: int,
) -> dict[str, Path]:
    """Save processed catalog and summary files."""

    RAW_DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_stem = (
        f"{region_key}_{start_year}_{end_year}_earthquakes"
    )

    raw_path = RAW_DATA_DIRECTORY / f"{file_stem}.json"
    csv_path = PROCESSED_DATA_DIRECTORY / f"{file_stem}.csv"
    parquet_path = (
        PROCESSED_DATA_DIRECTORY / f"{file_stem}.parquet"
    )
    summary_path = (
        PROCESSED_DATA_DIRECTORY
        / f"{file_stem}_summary.json"
    )

    raw_records = dataframe.copy()

    if not raw_records.empty:
        raw_records["event_time_utc"] = raw_records[
            "event_time_utc"
        ].astype(str)
        raw_records["updated_time_utc"] = raw_records[
            "updated_time_utc"
        ].astype(str)

    with raw_path.open("w", encoding="utf-8") as file:
        json.dump(
            raw_records.to_dict(orient="records"),
            file,
            indent=2,
            ensure_ascii=False,
        )

    dataframe.to_csv(csv_path, index=False)

    dataframe.to_parquet(
        parquet_path,
        index=False,
        engine="pyarrow",
    )

    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(
            summary,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "raw": raw_path,
        "csv": csv_path,
        "parquet": parquet_path,
        "summary": summary_path,
    }


def build_catalog(
    *,
    start_year: int,
    end_year: int,
    region_key: str | None = None,
) -> dict[str, Path]:
    """Run the complete Athena historical catalog pipeline."""

    validate_year_range(start_year, end_year)

    configuration = load_configuration()
    selected_key, region = get_region(
        configuration,
        region_key,
    )

    region_name = str(region.get("name", selected_key))
    bounds = build_region_bounds(region)
    minimum_magnitude = get_minimum_magnitude(region)

    print()
    print("=" * 68)
    print("PROJECT ATHENA — HISTORICAL CATALOG BUILDER")
    print("=" * 68)
    print(f"Region: {region_name}")
    print(f"Period: {start_year} through {end_year}")
    print(f"Minimum magnitude: {minimum_magnitude:.1f}")
    print("Download interval: monthly")
    print()

    client = UsgsClient()

    events = download_catalog_events(
        client=client,
        bounds=bounds,
        minimum_magnitude=minimum_magnitude,
        start_year=start_year,
        end_year=end_year,
    )

    dataframe = events_to_dataframe(events)

    summary = build_summary(
        dataframe=dataframe,
        region_key=selected_key,
        region_name=region_name,
        start_year=start_year,
        end_year=end_year,
        minimum_magnitude=minimum_magnitude,
    )

    paths = save_catalog(
        dataframe=dataframe,
        summary=summary,
        region_key=selected_key,
        start_year=start_year,
        end_year=end_year,
    )

    print()
    print("=" * 68)
    print("CATALOG BUILD COMPLETE")
    print("=" * 68)
    print(f"Events saved: {len(dataframe):,}")
    print(f"Raw JSON: {paths['raw'].relative_to(PROJECT_ROOT)}")
    print(f"CSV: {paths['csv'].relative_to(PROJECT_ROOT)}")
    print(
        f"Parquet: "
        f"{paths['parquet'].relative_to(PROJECT_ROOT)}"
    )
    print(
        f"Summary: "
        f"{paths['summary'].relative_to(PROJECT_ROOT)}"
    )

    return paths


def parse_arguments() -> argparse.Namespace:
    """Parse command-line catalog options."""

    current_year = datetime.now(timezone.utc).year

    parser = argparse.ArgumentParser(
        description=(
            "Download and save a historical earthquake catalog "
            "for a configured Project Athena region."
        )
    )

    parser.add_argument(
        "--start-year",
        type=int,
        default=2024,
        help="First year to download. Default: 2024.",
    )

    parser.add_argument(
        "--end-year",
        type=int,
        default=current_year,
        help=f"Final inclusive year. Default: {current_year}.",
    )

    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help=(
            "Region key from config/regions.json. "
            "The configured default region is used when omitted."
        ),
    )

    return parser.parse_args()


def configure_logging() -> None:
    """Configure terminal logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def main() -> None:
    """Run the historical catalog builder."""

    configure_logging()
    arguments = parse_arguments()

    try:
        build_catalog(
            start_year=arguments.start_year,
            end_year=arguments.end_year,
            region_key=arguments.region,
        )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        UsgsApiError,
        ValueError,
    ) as exc:
        LOGGER.error("Catalog build failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()