"""Download a small earthquake catalog for testing Project Athena."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.ingestion.provider import RegionBounds
from src.ingestion.usgs_client import UsgsApiError, UsgsClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGIONS_CONFIG_PATH = PROJECT_ROOT / "config" / "regions.json"

LOGGER = logging.getLogger(__name__)


def load_configuration() -> dict[str, Any]:
    """Load Project Athena's region configuration."""

    if not REGIONS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Could not find {REGIONS_CONFIG_PATH}."
        )

    with REGIONS_CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as configuration_file:
        configuration = json.load(configuration_file)

    if not isinstance(configuration, dict):
        raise ValueError(
            "The region configuration must be a JSON object."
        )

    return configuration


def get_default_region(
    configuration: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return the default region key and configuration."""

    default_region_key = configuration.get("default_region")
    regions = configuration.get("regions")

    if not isinstance(default_region_key, str):
        raise ValueError(
            "The configuration does not define a default region."
        )

    if not isinstance(regions, dict):
        raise ValueError(
            "The configuration does not contain a regions object."
        )

    region = regions.get(default_region_key)

    if not isinstance(region, dict):
        raise ValueError(
            f'Default region "{default_region_key}" was not found.'
        )

    return default_region_key, region


def build_bounds(
    region_configuration: dict[str, Any],
) -> RegionBounds:
    """Create validated geographic bounds from a region configuration."""

    bounds = region_configuration.get("bounds")

    if not isinstance(bounds, dict):
        raise ValueError(
            "The selected region does not contain valid bounds."
        )

    try:
        region_bounds = RegionBounds(
            min_latitude=float(bounds["min_latitude"]),
            max_latitude=float(bounds["max_latitude"]),
            min_longitude=float(bounds["min_longitude"]),
            max_longitude=float(bounds["max_longitude"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "The selected region contains invalid coordinates."
        ) from exc

    region_bounds.validate()
    return region_bounds


def download_recent_events(
    days: int = 7,
) -> None:
    """Download and print recent events for the default region."""

    if days <= 0:
        raise ValueError("days must be greater than zero.")

    configuration = load_configuration()
    region_key, region = get_default_region(configuration)

    region_name = str(
        region.get("name", region_key)
    )

    bounds = build_bounds(region)

    try:
        minimum_magnitude = float(
            region.get(
                "default_minimum_magnitude",
                1.0,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "The configured minimum magnitude is invalid."
        ) from exc

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    print()
    print("=" * 64)
    print("PROJECT ATHENA — USGS DOWNLOAD TEST")
    print("=" * 64)
    print(f"Region: {region_name}")
    print(f"Region key: {region_key}")
    print(f"Start: {start_time:%Y-%m-%d %H:%M UTC}")
    print(f"End: {end_time:%Y-%m-%d %H:%M UTC}")
    print(f"Minimum magnitude: {minimum_magnitude:.1f}")
    print()

    client = UsgsClient()

    events = client.fetch_events(
        start_time=start_time,
        end_time=end_time,
        bounds=bounds,
        minimum_magnitude=minimum_magnitude,
    )

    print(f"Events downloaded: {len(events):,}")

    if not events:
        print("No matching earthquakes were returned.")
        return

    events_by_time = sorted(
        events,
        key=lambda event: event.event_time_utc,
        reverse=True,
    )

    magnitudes = [
        event.magnitude
        for event in events
        if event.magnitude is not None
    ]

    depths = [
        event.depth_km
        for event in events
        if event.depth_km is not None
    ]

    if magnitudes:
        print(f"Largest magnitude: M{max(magnitudes):.1f}")
        print(
            f"Average magnitude: "
            f"M{sum(magnitudes) / len(magnitudes):.2f}"
        )

    if depths:
        print(
            f"Average depth: "
            f"{sum(depths) / len(depths):.1f} km"
        )

    print()
    print("Five most recent earthquakes")
    print("-" * 64)

    for event in events_by_time[:5]:
        magnitude = (
            f"M{event.magnitude:.1f}"
            if event.magnitude is not None
            else "Magnitude unavailable"
        )

        depth = (
            f"{event.depth_km:.1f} km"
            if event.depth_km is not None
            else "Depth unavailable"
        )

        place = event.place or "Location unavailable"

        print(
            f"{event.event_time_utc:%Y-%m-%d %H:%M UTC} | "
            f"{magnitude} | {depth} | {place}"
        )

    print()
    print("Download test completed successfully.")


def configure_logging() -> None:
    """Configure terminal logging."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def main() -> None:
    """Run the standalone download test."""

    configure_logging()

    try:
        download_recent_events(days=7)
    except (
        FileNotFoundError,
        ValueError,
        UsgsApiError,
    ) as exc:
        LOGGER.error("Download failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()