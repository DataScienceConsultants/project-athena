"""Generate Project Athena Observatory terminal and JSON reports."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.observatory.builder import (
    PROJECT_ROOT,
    build_observatory_report,
)
from src.observatory.models import ObservatoryReport
from src.observatory.thresholds import STATUS_DISPLAY_NAMES

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs" / "reports"
REPORT_FILENAME = "latest_observatory_report.json"
LINE_WIDTH = 72


def save_report_json(
    report: ObservatoryReport,
    output_path: str | Path,
) -> Path:
    """Save an Observatory report as formatted JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as output_file:
        json.dump(
            report.to_dict(),
            output_file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )

    return path


def render_terminal_report(
    report: ObservatoryReport,
) -> str:
    """Render a structured Observatory report for the terminal."""

    overall_display = STATUS_DISPLAY_NAMES[
        report.status.overall_status
    ]

    lines = [
        "=" * LINE_WIDTH,
        "PROJECT ATHENA SEISMIC OBSERVATORY",
        "=" * LINE_WIDTH,
        "",
        "REGION",
        "-" * LINE_WIDTH,
        report.catalog.region_name,
        "",
        "CATALOG",
        "-" * LINE_WIDTH,
        _row("Source", report.catalog.catalog_path),
        _row("Events", f"{report.catalog.event_count:,}"),
        _row(
            "First event",
            _format_datetime(report.catalog.first_event_time_utc),
        ),
        _row(
            "Last event",
            _format_datetime(report.catalog.last_event_time_utc),
        ),
        _row(
            "Calendar days",
            f"{report.catalog.calendar_days:,}",
        ),
        "",
        "ACTIVITY",
        "-" * LINE_WIDTH,
        _row(
            "Status",
            STATUS_DISPLAY_NAMES[report.activity.status],
        ),
        _row(
            "Total events",
            f"{report.activity.total_events:,}",
        ),
        _row(
            "Events in last 7 catalog days",
            f"{report.activity.events_last_7_days:,}",
        ),
        _row(
            "Events in last 30 catalog days",
            f"{report.activity.events_last_30_days:,}",
        ),
        _row(
            "7-day daily average",
            f"{report.activity.average_events_last_7_days:.2f}",
        ),
        _row(
            "Historical daily average",
            _format_number(
                report.activity.historical_average_events_per_day,
                decimals=2,
            ),
        ),
        _row(
            "7-day activity ratio",
            _format_ratio(report.activity.activity_ratio_7d),
        ),
        f"Interpretation: {report.activity.explanation}",
        "",
        "MAGNITUDE",
        "-" * LINE_WIDTH,
        _row(
            "Average magnitude",
            _format_magnitude(
                report.magnitude.average_magnitude
            ),
        ),
        _row(
            "Median magnitude",
            _format_magnitude(
                report.magnitude.median_magnitude
            ),
        ),
        _row(
            "Largest magnitude",
            _format_magnitude(
                report.magnitude.maximum_magnitude
            ),
        ),
        _row(
            "M3.0+ events",
            f"{report.magnitude.magnitude_3_plus:,}",
        ),
        _row(
            "M4.0+ events",
            f"{report.magnitude.magnitude_4_plus:,}",
        ),
        _row(
            "M5.0+ events",
            f"{report.magnitude.magnitude_5_plus:,}",
        ),
        _row(
            "Largest-event location",
            report.magnitude.largest_event_place
            or "Unavailable",
        ),
        "",
        "ESTIMATED SEISMIC ENERGY",
        "-" * LINE_WIDTH,
        _row(
            "Status",
            STATUS_DISPLAY_NAMES[report.energy.status],
        ),
        _row(
            "Catalog total",
            _format_scientific(
                report.energy.total_energy_joules,
                suffix=" J",
            ),
        ),
        _row(
            "Last 7 catalog days",
            _format_scientific(
                report.energy.energy_last_7_days_joules,
                suffix=" J",
            ),
        ),
        _row(
            "Equivalent single magnitude",
            _format_magnitude(
                report.energy.equivalent_single_magnitude
            ),
        ),
        _row(
            "7-day energy ratio",
            _format_ratio(report.energy.energy_ratio_7d),
        ),
        f"Interpretation: {report.energy.explanation}",
        "",
        "DEPTH",
        "-" * LINE_WIDTH,
        _row(
            "Status",
            STATUS_DISPLAY_NAMES[report.depth.status],
        ),
        _row(
            "Average depth",
            _format_number(
                report.depth.average_depth_km,
                decimals=2,
                suffix=" km",
            ),
        ),
        _row(
            "Median depth",
            _format_number(
                report.depth.median_depth_km,
                decimals=2,
                suffix=" km",
            ),
        ),
        _row(
            "7-day average depth",
            _format_number(
                report.depth.average_depth_last_7_days_km,
                decimals=2,
                suffix=" km",
            ),
        ),
        _row(
            "Historical average depth",
            _format_number(
                report.depth.historical_average_depth_km,
                decimals=2,
                suffix=" km",
            ),
        ),
        _row(
            "Shallow events",
            f"{report.depth.shallow_events:,}",
        ),
        _row(
            "Intermediate events",
            f"{report.depth.intermediate_events:,}",
        ),
        _row(
            "Deep events",
            f"{report.depth.deep_events:,}",
        ),
        f"Interpretation: {report.depth.explanation}",
        "",
        "OVERALL OBSERVATORY STATUS",
        "-" * LINE_WIDTH,
        _row("Status", overall_display.upper()),
        _row("Confidence", report.status.confidence),
        _row(
            "Methodology",
            report.status.methodology_version,
        ),
        "",
        report.status.disclaimer,
        "=" * LINE_WIDTH,
    ]

    return "\n".join(lines)


def run_report(
    *,
    catalog_path: str | Path | None = None,
    region_key: str | None = None,
    output_path: str | Path | None = None,
) -> tuple[ObservatoryReport, Path]:
    """Build, save, and print the Observatory report."""

    report = build_observatory_report(
        catalog_path,
        region_key=region_key,
    )

    selected_output_path = (
        Path(output_path)
        if output_path is not None
        else DEFAULT_OUTPUT_DIRECTORY / REPORT_FILENAME
    )

    saved_path = save_report_json(
        report,
        selected_output_path,
    )

    print(render_terminal_report(report))
    print()
    print(
        "JSON report saved to: "
        f"{_display_path(saved_path)}"
    )

    return report, saved_path


def parse_arguments() -> argparse.Namespace:
    """Parse Observatory command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build Project Athena's structured seismic "
            "Observatory report."
        )
    )

    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help=(
            "Path to a processed CSV or Parquet catalog. "
            "When omitted, Athena uses the newest processed "
            "Parquet catalog."
        ),
    )

    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help=(
            "Region key from config/regions.json. Athena infers "
            "the region from the catalog filename when omitted."
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "JSON output path. Default: "
            "outputs/reports/latest_observatory_report.json"
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
    """Run the Observatory-report command."""

    configure_logging()
    arguments = parse_arguments()

    try:
        run_report(
            catalog_path=arguments.catalog,
            region_key=arguments.region,
            output_path=arguments.output,
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        LOGGER.error(
            "Observatory report failed: %s",
            exc,
        )
        raise SystemExit(1) from exc


def _row(label: str, value: str) -> str:
    """Format a terminal-report label and value."""

    available_width = max(
        LINE_WIDTH - len(label) - 1,
        1,
    )

    if len(value) > available_width:
        return f"{label}: {value}"

    dots = "." * (
        LINE_WIDTH - len(label) - len(value)
    )

    return f"{label}{dots}{value}"


def _format_number(
    value: float | None,
    *,
    decimals: int = 2,
    suffix: str = "",
) -> str:
    """Format an optional numeric value."""

    if value is None:
        return "Unavailable"

    return f"{value:,.{decimals}f}{suffix}"


def _format_scientific(
    value: float | None,
    *,
    suffix: str = "",
) -> str:
    """Format an optional number using scientific notation."""

    if value is None:
        return "Unavailable"

    return f"{value:.3e}{suffix}"


def _format_magnitude(
    value: float | None,
) -> str:
    """Format an optional earthquake magnitude."""

    if value is None:
        return "Unavailable"

    return f"M{value:.2f}"


def _format_ratio(
    value: float | None,
) -> str:
    """Format a ratio and its percentage difference."""

    if value is None:
        return "Unavailable"

    percentage = (value - 1.0) * 100

    return f"{value:.3f} ({percentage:+.1f}%)"


def _format_datetime(
    value: str | None,
) -> str:
    """Return a compact ISO timestamp."""

    if value is None:
        return "Unavailable"

    return value.replace("T", " ").replace("+00:00", " UTC")


def _display_path(path: str | Path) -> str:
    """Return a project-relative output path when possible."""

    selected_path = Path(path)

    try:
        return str(
            selected_path.resolve().relative_to(
                PROJECT_ROOT.resolve()
            )
        )
    except ValueError:
        return str(selected_path)


if __name__ == "__main__":
    main()