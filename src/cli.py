"""Command-line interface for Project Athena."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from src.observatory.report import run_report

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build Athena's command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="athena",
        description=(
            "Project Athena experimental seismic intelligence platform."
        ),
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Display additional logging information.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    observatory_parser = subparsers.add_parser(
        "observatory",
        help="Generate a seismic Observatory report.",
        description=(
            "Build a structured Observatory report using an Athena "
            "earthquake catalog."
        ),
    )

    observatory_parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help=(
            "Processed CSV or Parquet catalog. Athena uses the newest "
            "processed Parquet catalog when omitted."
        ),
    )

    observatory_parser.add_argument(
        "--region",
        type=str,
        default=None,
        help=(
            "Region key from config/regions.json. Athena attempts to "
            "infer the region from the catalog filename when omitted."
        ),
    )

    observatory_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "JSON output path. Default: "
            "outputs/reports/latest_observatory_report.json"
        ),
    )

    return parser


def configure_logging(*, verbose: bool) -> None:
    """Configure Athena's terminal logging."""

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def execute_command(
    arguments: argparse.Namespace,
) -> int:
    """Execute the selected Athena command."""

    if arguments.command == "observatory":
        run_report(
            catalog_path=arguments.catalog,
            region_key=arguments.region,
            output_path=arguments.output,
        )
        return 0

    raise ValueError(
        f'Unsupported Athena command: "{arguments.command}"'
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Run the Project Athena CLI."""

    parser = build_parser()
    arguments = parser.parse_args(argv)

    configure_logging(
        verbose=bool(arguments.verbose),
    )

    try:
        return execute_command(arguments)
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        LOGGER.error("%s", exc)
        return 1