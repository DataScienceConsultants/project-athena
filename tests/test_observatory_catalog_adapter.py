"""Tests for canonical catalog integration with Observatory v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import src.observatory as observatory
from src.catalog import CatalogEvent, ParquetCatalogStorage, get_region
from src.observatory import (
    ObservatoryReport,
    build_observatory_report_from_catalog_storage,
    catalog_events_to_observatory_dataframe,
)


def event(
    event_id: str,
    hour: int,
    *,
    depth: float = 8.0,
    offset: timezone = timezone.utc,
) -> CatalogEvent:
    event_time = datetime(2024, 1, 1, hour, tzinfo=offset)
    return CatalogEvent(
        event_id=event_id,
        time=event_time,
        updated_time=event_time + timedelta(minutes=5),
        latitude=18.25,
        longitude=-66.4,
        depth=depth,
        magnitude=2.4,
        place="Puerto Rico",
        source="USGS",
    )


def test_event_conversion_maps_schema_values_and_utc_timestamps() -> None:
    offset = timezone(timedelta(hours=-4))
    frame = catalog_events_to_observatory_dataframe(
        [event("mapped", 4, depth=-1.25, offset=offset)]
    )

    assert list(frame.columns) == [
        "event_id",
        "event_time_utc",
        "updated_time_utc",
        "latitude",
        "longitude",
        "depth_km",
        "magnitude",
        "place",
        "source",
    ]
    assert frame.loc[0, "event_id"] == "mapped"
    assert frame.loc[0, "event_time_utc"] == pd.Timestamp("2024-01-01T08:00:00Z")
    assert frame.loc[0, "updated_time_utc"] == pd.Timestamp("2024-01-01T08:05:00Z")
    assert str(frame["event_time_utc"].dtype) == "datetime64[ns, UTC]"
    assert str(frame["updated_time_utc"].dtype) == "datetime64[ns, UTC]"
    assert frame.loc[0, "depth_km"] == -1.25
    assert frame.loc[0, "latitude"] == 18.25
    assert frame.loc[0, "longitude"] == -66.4
    assert frame.loc[0, "magnitude"] == 2.4
    assert frame.loc[0, "place"] == "Puerto Rico"
    assert frame.loc[0, "source"] == "USGS"


def test_event_conversion_orders_deterministically() -> None:
    frame = catalog_events_to_observatory_dataframe(
        [event("later", 2), event("z", 1), event("a", 1)]
    )
    assert frame["event_id"].tolist() == ["a", "z", "later"]


@pytest.mark.parametrize("invalid", [None, "events", [None]])
def test_event_conversion_rejects_invalid_or_missing_values(invalid: object) -> None:
    with pytest.raises(TypeError, match="CatalogEvent"):
        catalog_events_to_observatory_dataframe(invalid)  # type: ignore[arg-type]


def test_unknown_region_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="Unknown catalog region"):
        build_observatory_report_from_catalog_storage(
            tmp_path,
            region_key="not-a-region",
        )


def test_invalid_storage_path_type_is_rejected() -> None:
    with pytest.raises(TypeError, match="catalog_storage_path"):
        build_observatory_report_from_catalog_storage(
            123,  # type: ignore[arg-type]
            region_key="puerto_rico",
        )


def test_empty_canonical_catalog_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty catalog"):
        build_observatory_report_from_catalog_storage(
            tmp_path,
            region_key="puerto_rico",
        )


def test_report_builds_from_canonical_catalog_storage(tmp_path: Path) -> None:
    region = get_region("puerto_rico")
    storage = ParquetCatalogStorage(tmp_path)
    storage.save(region, [event("second", 2), event("first", 1, depth=-0.5)])

    report = build_observatory_report_from_catalog_storage(
        tmp_path,
        region_key="puerto_rico",
    )

    assert isinstance(report, ObservatoryReport)
    assert report.catalog.region_key == region.key
    assert report.catalog.region_name == region.name
    assert report.catalog.event_count == 2
    assert report.catalog.first_event_time_utc == "2024-01-01T01:00:00+00:00"
    assert report.depth.minimum_depth_km == -0.5


def test_existing_public_exports_remain_available() -> None:
    expected = {
        "build_observatory_report",
        "build_observatory_report_from_dataframe",
        "build_observatory_intelligence_report",
        "render_terminal_report",
        "save_report_json",
        "run_report",
    }
    assert expected.issubset(observatory.__all__)
    assert all(hasattr(observatory, name) for name in expected)
