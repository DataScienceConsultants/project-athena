"""Tests for Project Athena Observatory report models."""

from __future__ import annotations

from src.observatory.models import (
    ActivitySection,
    CatalogSection,
    DepthSection,
    EnergySection,
    MagnitudeSection,
    ObservatoryReport,
    StatusSection,
)
from src.observatory.thresholds import ObservatoryStatus


def sample_report() -> ObservatoryReport:
    """Create a complete synthetic Observatory report."""

    return ObservatoryReport(
        generated_at_utc="2026-07-14T12:00:00+00:00",
        catalog=CatalogSection(
            catalog_path=(
                "data/processed/"
                "puerto_rico_2024_2024_earthquakes.parquet"
            ),
            region_key="puerto_rico",
            region_name="Puerto Rico and Surrounding Region",
            event_count=100,
            first_event_time_utc="2024-01-01T01:00:00+00:00",
            last_event_time_utc="2024-12-31T22:00:00+00:00",
            calendar_days=366,
        ),
        activity=ActivitySection(
            total_events=100,
            active_days=80,
            calendar_days=366,
            average_events_per_day=0.273,
            maximum_events_in_one_day=5,
            busiest_day="2024-06-10",
            events_last_7_days=10,
            events_last_30_days=34,
            average_events_last_7_days=1.429,
            historical_average_events_per_day=0.25,
            activity_ratio_7d=5.716,
            status=ObservatoryStatus.EXCEPTIONAL,
            explanation="+471.6% relative to historical average.",
        ),
        magnitude=MagnitudeSection(
            events_with_magnitude=99,
            missing_magnitude_count=1,
            average_magnitude=1.82,
            median_magnitude=1.7,
            minimum_magnitude=1.0,
            maximum_magnitude=4.2,
            magnitude_3_plus=6,
            magnitude_4_plus=1,
            magnitude_5_plus=0,
            largest_event_id="eq100",
            largest_event_time_utc=(
                "2024-08-05T10:00:00+00:00"
            ),
            largest_event_place="Southwest Puerto Rico",
        ),
        energy=EnergySection(
            events_with_magnitude=99,
            total_energy_joules=1.2e11,
            equivalent_single_magnitude=4.19,
            maximum_event_energy_joules=1.1e11,
            maximum_energy_magnitude=4.2,
            maximum_energy_event_id="eq100",
            energy_last_7_days_joules=8.5e9,
            historical_average_daily_energy_joules=2.0e8,
            energy_ratio_7d=6.071,
            status=ObservatoryStatus.EXCEPTIONAL,
            explanation="+507.1% relative to historical average.",
        ),
        depth=DepthSection(
            events_with_depth=100,
            average_depth_km=18.2,
            median_depth_km=16.4,
            minimum_depth_km=2.0,
            maximum_depth_km=125.0,
            shallow_events=97,
            intermediate_events=3,
            deep_events=0,
            average_depth_last_7_days_km=17.0,
            historical_average_depth_km=18.2,
            depth_difference_7d_km=-1.2,
            status=ObservatoryStatus.NORMAL,
            explanation=(
                "Average depth differs by 1.2 km from baseline."
            ),
        ),
        status=StatusSection(
            overall_status=ObservatoryStatus.EXCEPTIONAL,
            confidence="Moderate",
            methodology_version="observatory-v0.1",
            disclaimer=(
                "Experimental analysis. Not an official earthquake "
                "prediction, warning, or emergency alert."
            ),
        ),
    )


def test_report_to_dict_contains_all_sections() -> None:
    """The serialized report should contain every Observatory section."""

    result = sample_report().to_dict()

    assert result["generated_at_utc"] == (
        "2026-07-14T12:00:00+00:00"
    )
    assert "catalog" in result
    assert "activity" in result
    assert "magnitude" in result
    assert "energy" in result
    assert "depth" in result
    assert "status" in result


def test_status_values_are_json_compatible_strings() -> None:
    """Enum values should serialize as readable strings."""

    result = sample_report().to_dict()

    assert result["activity"]["status"] == "exceptional"
    assert result["activity"]["status_display"] == "Exceptional"

    assert result["depth"]["status"] == "normal"
    assert result["depth"]["status_display"] == "Normal"

    assert result["status"]["overall_status"] == "exceptional"
    assert (
        result["status"]["overall_status_display"]
        == "Exceptional"
    )


def test_catalog_section_serialization() -> None:
    """Catalog metadata should remain intact."""

    result = sample_report().to_dict()

    catalog = result["catalog"]

    assert catalog["region_key"] == "puerto_rico"
    assert catalog["event_count"] == 100
    assert catalog["calendar_days"] == 366


def test_magnitude_section_serialization() -> None:
    """Magnitude details should serialize correctly."""

    result = sample_report().to_dict()

    magnitude = result["magnitude"]

    assert magnitude["maximum_magnitude"] == 4.2
    assert magnitude["largest_event_id"] == "eq100"
    assert magnitude["magnitude_4_plus"] == 1


def test_report_dictionary_is_independent() -> None:
    """Changing a returned dictionary must not mutate the report."""

    report = sample_report()
    result = report.to_dict()

    result["catalog"]["event_count"] = 999

    assert report.catalog.event_count == 100