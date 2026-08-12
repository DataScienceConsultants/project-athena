"""Command-line entry point for Athena global retrospective research."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.global_research.runner import run_reference_50_year_research
from src.global_research.sources import download_gem_global_active_faults


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build Athena's retrospective global M6.0+ research bundle for the "
            "50 complete calendar years from 1976 through 2025."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: data/global_research/global-m6-1976-2025)",
    )
    fault_group = parser.add_mutually_exclusive_group()
    fault_group.add_argument(
        "--fault-geojson",
        type=Path,
        help="Use an existing GEM Global Active Faults GeoJSON file",
    )
    fault_group.add_argument(
        "--with-gem-faults",
        action="store_true",
        help="Download and verify Athena's configured GEM fault GeoJSON before enrichment",
    )
    parser.add_argument(
        "--max-fault-distance-km",
        type=float,
        default=250.0,
        help="Maximum distance for a mapped-fault association (default: 250 km)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    fault_path = args.fault_geojson
    if args.with_gem_faults:
        fault_path = download_gem_global_active_faults()

    bundle = run_reference_50_year_research(
        output_dir=args.output,
        fault_geojson_path=fault_path,
        max_fault_distance_km=args.max_fault_distance_km,
    )
    print(json.dumps(bundle.metadata, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
