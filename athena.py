"""Command-line interface for Project Athena."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.ingestion.provider import RegionBounds
from src.ingestion.usgs_client import UsgsApiError, UsgsClient

PROJECT_ROOT = Path(__file__).resolve().parent
REGIONS_CONFIG_PATH = PROJECT_ROOT / "config" / "regions.json"

LOGGER = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure console logging for Project Athena."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def load_region_configuration() -> dict[str, Any]:
    """Load and validate the global region configuration file."""

    if not REGIONS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Region configuration was not found at "
            f"{REGIONS_CONFIG_PATH}."
        )

    try:
        with REGIONS_CONFIG_PATH.open(
            "r",
            encoding="utf-8",
        ) as config_file:
            configuration = json.load(config_file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Region configuration contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(configuration, dict):
        raise ValueError(
            "Region configuration must contain a JSON object."
        )

    regions = configuration.get("regions")
    default_region = configuration.get("default_region")

    if not isinstance(regions, dict) or not regions:
        raise ValueError(
            "Region configuration does not contain any regions."
        )

    if not isinstance(default_region, str):
        raise ValueError(
            "Region configuration does not define default_region."
        )

    if default_region not in regions:
        raise ValueError(
            f'Default region "{default_region}" is not configured.'
        )

    return configuration


def build_region_bounds(
    region_configuration: dict[str, Any],
) -> RegionBounds:
    """Convert a configured region into validated RegionBounds."""

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
            "The selected region has incomplete or invalid coordinates."
        ) from exc

    region_bounds.validate()
    return region_bounds


def print_header() -> None:
    """Print the Project Athena command-line header."""

    print()
    print("=" * 58)
    print("PROJECT ATHENA")
    print("Experimental Seismic Intelligence Platform")
    print("=" * 58)


def print_menu(
    region_name: str,
) -> None:
    """Display the available command-line options."""

    print()
    print(f"Current region: {region_name}")
    print()
    print("1. Test USGS connection and preview recent events")
    print("2. Show configured regions")
    print("3. Download historical catalog — coming next")
    print("4. Analyze catalog — future sprint")
    print("5. Generate activity report — future sprint")
    print("0. Exit")
    print()


def preview_recent_events(
    region_key: str,
    region_configuration: dict[str, Any],
) -> None:
    """Download and display a seven-day USGS event preview."""

    region_name = str(
        region_configuration.get("name", region_key)
    )
    bounds = build_region_bounds(region_configuration)

    configured_minimum_magnitude = region_configuration.get(
        "default_minimum_magnitude",
        1.0,
    )

    try:
        minimum_magnitude = float(
            configured_minimum_magnitude
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'Region "{region_key}" has an invalid '
            "default minimum magnitude."
        ) from exc

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)

    print()
    print(f"Connecting to USGS for {region_name}...")
    print(
        f"Period: {start_time:%Y-%m-%d %H:%M UTC} "
        f"through {end_time:%Y-%m-%d %H:%M UTC}"
    )
    print(f"Minimum magnitude: {minimum_magnitude:.1f}")
    print()

    client = UsgsClient()

    events = client.fetch_events(
        start_time=start_time,
        end_time=end_time,
        bounds=bounds,
        minimum_magnitude=minimum_magnitude,
    )

    print("-" * 58)
    print(f"USGS connection successful.")
    print(f"Events received: {len(events)}")
    print("-" * 58)

    if not events:
        print("No matching earthquakes were returned.")
        return

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

    largest_event = max(
        events,
        key=lambda event: (
            event.magnitude
            if event.magnitude is not None
            else float("-inf")
        ),
    )

    if magnitudes:
        print(f"Largest magnitude: M{max(magnitudes):.1f}")

    if depths:
        average_depth = sum(depths) / len(depths)
        print(f"Average depth: {average_depth:.1f} km")

    print()
    print("Most recent events:")
    print()

    recent_events = sorted(
        events,
        key=lambda event: event.event_time_utc,
        reverse=True,
    )[:10]

    for event in recent_events:
        magnitude_text = (
            f"M{event.magnitude:.1f}"
            if event.magnitude is not None
            else "Magnitude unavailable"
        )

        depth_text = (
            f"{event.depth_km:.1f} km deep"
            if event.depth_km is not None
            else "depth unavailable"
        )

        place_text = event.place or "Location unavailable"

        print(
            f"{event.event_time_utc:%Y-%m-%d %H:%M UTC} | "
            f"{magnitude_text} | "
            f"{depth_text} | "
            f"{place_text}"
        )

    print()
    print("Largest event in this period:")
    print(
        f"{largest_event.event_time_utc:%Y-%m-%d %H:%M UTC} | "
        f"M{largest_event.magnitude:.1f} | "
        f"{largest_event.place or 'Location unavailable'}"
        if largest_event.magnitude is not None
        else (
            f"{largest_event.event_time_utc:%Y-%m-%d %H:%M UTC} | "
            f"Magnitude unavailable | "
            f"{largest_event.place or 'Location unavailable'}"
        )
    )


def show_configured_regions(
    configuration: dict[str, Any],
) -> None:
    """Display every region currently registered in Athena."""

    default_region = configuration["default_region"]
    regions = configuration["regions"]

    print()
    print("Configured regions")
    print("-" * 58)

    for region_key, region in regions.items():
        if not isinstance(region, dict):
            continue

        name = region.get("name", region_key)
        enabled = bool(region.get("enabled", False))
        default_marker = (
            " — default"
            if region_key == default_region
            else ""
        )

        status = "enabled" if enabled else "disabled"

        print(
            f"{region_key}: {name} "
            f"({status}){default_marker}"
        )


def run_application() -> int:
    """Run the interactive Project Athena command-line interface."""

    try:
        configuration = load_region_configuration()
    except (FileNotFoundError, ValueError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        return 1

    default_region_key = configuration["default_region"]
    default_region = configuration["regions"][default_region_key]
    default_region_name = default_region.get(
        "name",
        default_region_key,
    )

    while True:
        print_header()
        print_menu(str(default_region_name))

        selection = input("Choose an option: ").strip()

        if selection == "0":
            print()
            print("Project Athena closed.")
            return 0

        if selection == "1":
            try:
                preview_recent_events(
                    default_region_key,
                    default_region,
                )
            except (
                UsgsApiError,
                ValueError,
                requests_exception_types(),
            ) as exc:
                print()
                print(f"Unable to retrieve USGS data: {exc}")

            wait_for_user()
            continue

        if selection == "2":
            show_configured_regions(configuration)
            wait_for_user()
            continue

        if selection == "3":
            print()
            print(
                "Historical catalog ingestion will be "
                "implemented in the next step."
            )
            wait_for_user()
            continue

        if selection in {"4", "5"}:
            print()
            print(
                "This feature belongs to a future "
                "Project Athena sprint."
            )
            wait_for_user()
            continue

        print()
        print("Please enter a valid menu option.")
        wait_for_user()


def requests_exception_types() -> tuple[type[Exception], ...]:
    """Return optional request-related exceptions safely.

    The USGS client normally converts request failures into UsgsApiError.
    This helper keeps the CLI resilient if a lower-level connection error
    reaches the entry point.
    """

    try:
        import requests
    except ImportError:
        return ()

    return (requests.RequestException,)


def wait_for_user() -> None:
    """Pause before returning to the main menu."""

    print()
    input("Press Enter to return to the menu...")


def main() -> None:
    """Launch Project Athena."""

    configure_logging()
    raise SystemExit(run_application())


if __name__ == "__main__":
    main()