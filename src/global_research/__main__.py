"""Command-line entry point for Athena global retrospective research."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src.global_research.runner import run_reference_50_year_research
from src.global_research.sources import (
    download_gem_global_active_faults,
    download_pb2002_steps,
)


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

    plate_group = parser.add_mutually_exclusive_group()
    plate_group.add_argument(
        "--plate-boundary-steps",
        type=Path,
        help="Use an existing Bird PB2002_steps.dat file",
    )
    plate_group.add_argument(
        "--with-pb2002-boundaries",
        action="store_true",
        help="Download and verify Athena's pinned PB2002 boundary-step source",
    )
    parser.add_argument(
        "--max-plate-boundary-distance-km",
        type=float,
        default=500.0,
        help=(
            "Maximum distance for nearest PB2002 boundary context "
            "(default: 500 km)"
        ),
    )
    parser.add_argument(
        "--with-interaction-study",
        action="store_true",
        help=(
            "Generate the retrospective Earthquake Interaction Study v1. "
            "Requires PB2002 plate-boundary context."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    fault_path = args.fault_geojson
    if args.with_gem_faults:
        fault_path = download_gem_global_active_faults()

    plate_path = args.plate_boundary_steps
    if args.with_pb2002_boundaries:
        plate_path = download_pb2002_steps()

    bundle = run_reference_50_year_research(
        output_dir=args.output,
        fault_geojson_path=fault_path,
        max_fault_distance_km=args.max_fault_distance_km,
        plate_boundary_steps_path=plate_path,
        max_plate_boundary_distance_km=args.max_plate_boundary_distance_km,
        interaction_study=args.with_interaction_study,
    )
    print(json.dumps(bundle.metadata, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
