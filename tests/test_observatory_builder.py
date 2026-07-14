"""Integration tests for Project Athena Observatory builder."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import pandas as pd

from src.observatory.builder import (
    build_observatory_report,
    build_observatory_report_from_dataframe,
    find_latest_catalog,
)
from src.observatory.report import (
    render_terminal_report,
    save_report_json,
)
from src.observatory.thresholds import ObservatoryStatus


def sample_catalog(days: int = 40) -> pd.DataFrame:
    """Create a deterministic synthetic earthquake catalog."""

    records: list[dict[str, object]] = []

    start_date = pd.Timestamp(
        "2024-01-01T00:00:00Z"
    )

    for day_number in range(days):
        current_date = start_date + timedelta(
            days=day_number
        )

        event_count = 1

        if day_number >= days - 7:
            event_count = 3

        for event_number in range(event_count):
            records.append(
                {
                    "event_id": (
                        f"eq-{day_number}-{event_number}"
                    ),
                    "source": "USGS",
                    "event_time_utc": (
                        current_date
                        + timedelta(hours=event_number)
                    ).isoformat(),
                    "updated_time_utc": (
                        current_date
                        + timedelta(
                            hours=event_number + 1
                        )
                    ).isoformat(),
                    "latitude": 18.1,
                    "longitude": -66.8,
                    "depth_km": 12.0 + event_number,
                    "magnitude": 1.5 + (
                        0.5 * event_number
                    ),
                    "magnitude_type": "md",
                    "place": "Puerto Rico test region",
                    "event_type": "earthquake",
                    "status": "reviewed",
                    "tsunami_flag": False,
                    "felt_reports": 0,
                    "significance": 10,
                    "alert_level": None,
                    "detail_url": None,
                    "source_url": None,
                }
            )

    return pd.DataFrame.from_records(records)


def write_region_configuration(
    path: Path,
) -> None:
    """Write a minimal valid region configuration."""

    configuration = {
        "default_region": "puerto_rico",
        "regions": {
            "puerto_rico": {
                "name": (
                    "Puerto Rico and Surrounding Region"
                ),
                "bounds": {
                    "min_latitude": 17.0,
                    "max_latitude": 20.0,
                    "min_longitude": -69.0,
                    "max_longitude": -63.5,
                },
            }
        },
    }

    path.write_text(
        json.dumps(configuration),
        encoding="utf-8",
    )


def test_build_report_from_dataframe() -> None:
    """Builder should populate every Observatory section."""

    report = build_observatory_report_from_dataframe(
        sample_catalog(),
        catalog_path=(
            "data/processed/"
            "puerto_rico_2024_2024_earthquakes.parquet"
        ),
        region_key="puerto_rico",
        region_name=(
            "Puerto Rico and Surrounding Region"
        ),
    )

    assert report.catalog.region_key == "puerto_rico"
    assert report.catalog.event_count == 54
    assert report.catalog.calendar_days == 40

    assert report.activity.events_last_7_days == 21
    assert report.activity.activity_ratio_7d is not None
    assert report.activity.status in {
        ObservatoryStatus.ELEVATED,
        ObservatoryStatus.EXCEPTIONAL,
    }

    assert report.magnitude.maximum_magnitude == 2.5
    assert report.energy.total_energy_joules > 0
    assert report.depth.average_depth_km is not None

    assert report.status.overall_status in {
        ObservatoryStatus.ELEVATED,
        ObservatoryStatus.EXCEPTIONAL,
    }


def test_builder_uses_catalog_and_configuration_files(
    tmp_path: Path,
) -> None:
    """Builder should load a real Parquet file and region config."""

    catalog_path = (
        tmp_path
        / "puerto_rico_2024_2024_earthquakes.parquet"
    )
    configuration_path = tmp_path / "regions.json"

    sample_catalog().to_parquet(
        catalog_path,
        index=False,
    )
    write_region_configuration(
        configuration_path
    )

    report = build_observatory_report(
        catalog_path,
        configuration_path=configuration_path,
    )

    assert report.catalog.region_key == "puerto_rico"
    assert report.catalog.event_count == 54
    assert report.magnitude.events_with_magnitude == 54


def test_find_latest_catalog(
    tmp_path: Path,
) -> None:
    """The newest processed Parquet catalog should be selected."""

    older = tmp_path / "older_earthquakes.parquet"
    newer = tmp_path / "newer_earthquakes.parquet"

    sample_catalog(10).to_parquet(
        older,
        index=False,
    )
    sample_catalog(12).to_parquet(
        newer,
        index=False,
    )

    older_timestamp = 1_700_000_000
    newer_timestamp = 1_800_000_000

    os.utime(
        older,
        (older_timestamp, older_timestamp),
    )
    os.utime(
        newer,
        (newer_timestamp, newer_timestamp),
    )

    assert find_latest_catalog(tmp_path) == newer


def test_save_report_json(
    tmp_path: Path,
) -> None:
    """Structured reports should save as valid JSON."""

    report = build_observatory_report_from_dataframe(
        sample_catalog(),
        catalog_path="catalog.parquet",
        region_key="puerto_rico",
        region_name="Puerto Rico",
    )

    output_path = tmp_path / "report.json"

    saved_path = save_report_json(
        report,
        output_path,
    )

    result = json.loads(
        saved_path.read_text(encoding="utf-8")
    )

    assert result["catalog"]["region_key"] == "puerto_rico"
    assert result["activity"]["events_last_7_days"] == 21
    assert "overall_status" in result["status"]


def test_terminal_report_contains_core_sections() -> None:
    """Terminal rendering should contain every main report section."""

    report = build_observatory_report_from_dataframe(
        sample_catalog(),
        catalog_path="catalog.parquet",
        region_key="puerto_rico",
        region_name="Puerto Rico",
    )

    output = render_terminal_report(report)

    assert "PROJECT ATHENA SEISMIC OBSERVATORY" in output
    assert "REGION" in output
    assert "ACTIVITY" in output
    assert "MAGNITUDE" in output
    assert "ESTIMATED SEISMIC ENERGY" in output
    assert "DEPTH" in output
    assert "OVERALL OBSERVATORY STATUS" in output
    assert "Puerto Rico" in output