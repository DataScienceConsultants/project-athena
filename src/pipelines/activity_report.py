"""Generate Project Athena activity metrics from a saved catalog."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.metrics.activity import (
    add_rolling_activity_metrics,
    build_daily_activity,
    load_catalog,
    summarize_activity,
)

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DATA_DIRECTORY = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs" / "reports"


def generate_activity_report(
    catalog_path: str | Path,
) -> dict[str, Path]:
    """Generate daily metrics and a summary from a catalog."""

    catalog = load_catalog(catalog_path)

    daily_activity = build_daily_activity(
        catalog,
        include_inactive_days=True,
    )

    daily_metrics = add_rolling_activity_metrics(
        daily_activity
    )

    summary = summarize_activity(daily_activity)

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    catalog_name = Path(catalog_path).stem

    daily_output_path = (
        OUTPUT_DIRECTORY
        / f"{catalog_name}_daily_activity.csv"
    )

    summary_output_path = (
        OUTPUT_DIRECTORY
        / f"{catalog_name}_activity_summary.json"
    )

    daily_metrics.to_csv(
        daily_output_path,
        index=False,
    )

    with summary_output_path.open(
        "w",
        encoding="utf-8",
    ) as summary_file:
        json.dump(
            summary.to_dict(),
            summary_file,
            indent=2,
        )

    print()
    print("=" * 68)
    print("PROJECT ATHENA — ACTIVITY REPORT")
    print("=" * 68)
    print(f"Catalog: {catalog_path}")
    print(f"Total earthquakes: {summary.total_events:,}")
    print(f"Calendar days: {summary.calendar_days:,}")
    print(f"Active days: {summary.active_days:,}")
    print(
        "Average earthquakes per day: "
        f"{summary.average_events_per_day:.3f}"
    )
    print(
        "Maximum earthquakes in one day: "
        f"{summary.maximum_events_in_one_day:,}"
    )
    print(f"Busiest day: {summary.busiest_day}")
    print(f"M3.0+ earthquakes: {summary.magnitude_3_plus:,}")
    print(f"M4.0+ earthquakes: {summary.magnitude_4_plus:,}")
    print()
    print(
        "Daily metrics: "
        f"{daily_output_path.relative_to(PROJECT_ROOT)}"
    )
    print(
        "Summary: "
        f"{summary_output_path.relative_to(PROJECT_ROOT)}"
    )

    return {
        "daily_activity": daily_output_path,
        "summary": summary_output_path,
    }


def find_latest_catalog() -> Path:
    """Find the most recently modified Athena Parquet catalog."""

    catalog_paths = list(
        PROCESSED_DATA_DIRECTORY.glob(
            "*_earthquakes.parquet"
        )
    )

    if not catalog_paths:
        raise FileNotFoundError(
            "No processed Parquet earthquake catalogs were found. "
            "Run the historical catalog builder first."
        )

    return max(
        catalog_paths,
        key=lambda path: path.stat().st_mtime,
    )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate daily seismic activity metrics from a "
            "Project Athena earthquake catalog."
        )
    )

    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help=(
            "Path to a CSV or Parquet catalog. When omitted, "
            "Athena uses the latest processed Parquet catalog."
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
    """Run the activity-report pipeline."""

    configure_logging()
    arguments = parse_arguments()

    try:
        catalog_path = (
            arguments.catalog
            if arguments.catalog is not None
            else find_latest_catalog()
        )

        generate_activity_report(catalog_path)

    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        LOGGER.error(
            "Activity report failed: %s",
            exc,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()