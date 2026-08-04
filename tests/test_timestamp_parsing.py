"""Regression tests for mixed ISO-8601 catalog timestamps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from src.catalog import CatalogEvent
from src.catalog.storage import load_catalog
from src.ingestion.provider import EarthquakeEvent
from src.pipelines.build_catalog import events_to_dataframe


def event(event_id: str, event_time: datetime, updated_time: datetime) -> EarthquakeEvent:
    """Build a complete provider event for catalog preparation tests."""
    return EarthquakeEvent(
        event_id=event_id,
        source="USGS",
        event_time_utc=event_time,
        updated_time_utc=updated_time,
        latitude=18.0,
        longitude=-66.0,
        depth_km=-1.25,
        magnitude=2.0,
        magnitude_type="ml",
        place="Puerto Rico",
        event_type="earthquake",
        status="reviewed",
        tsunami_flag=False,
        felt_reports=0,
        significance=1,
        alert_level=None,
        detail_url=None,
        source_url=None,
    )


def test_catalog_preparation_accepts_mixed_iso8601_precision_and_offsets() -> None:
    fractional_utc = datetime(2025, 8, 5, 20, 54, 55, 123000, tzinfo=timezone.utc)
    offset = timezone(timedelta(hours=-4))
    whole_second_offset = datetime(2025, 8, 5, 16, 54, 55, tzinfo=offset)

    fractional_record = event("fractional", fractional_utc, fractional_utc).to_dict()
    fractional_record["event_time_utc"] = "2025-08-05T20:54:55.123Z"
    whole_record = event("whole", fractional_utc, whole_second_offset).to_dict()
    whole_record["event_time_utc"] = "2025-08-05T20:54:55+00:00"

    class StringTimestampEvent:
        def __init__(self, record: dict[str, object]) -> None:
            self.record = record

        def to_dict(self) -> dict[str, object]:
            return self.record

    frame = events_to_dataframe(
        [
            StringTimestampEvent(fractional_record),
            StringTimestampEvent(whole_record),
        ]
    )  # type: ignore[list-item]

    assert frame["event_id"].tolist() == ["whole", "fractional"]
    assert str(frame["event_time_utc"].dtype) == "datetime64[ns, UTC]"
    assert frame.loc[0, "event_time_utc"] == pd.Timestamp("2025-08-05T20:54:55Z")
    assert frame.loc[1, "event_time_utc"] == pd.Timestamp(
        "2025-08-05T20:54:55.123Z"
    )
    assert frame.loc[0, "updated_time_utc"] == pd.Timestamp(
        "2025-08-05T20:54:55Z"
    )
    assert frame["depth_km"].tolist() == [-1.25, -1.25]


def test_catalog_preparation_rejects_malformed_timestamp() -> None:
    valid = datetime(2025, 8, 5, tzinfo=timezone.utc)
    record = event("bad", valid, valid).to_dict()
    record["event_time_utc"] = "not-an-iso-timestamp"

    class MalformedEvent:
        def to_dict(self) -> dict[str, object]:
            return record

    with pytest.raises(ValueError, match="not-an-iso-timestamp"):
        events_to_dataframe([MalformedEvent()])  # type: ignore[list-item]


def test_csv_import_parses_mixed_iso8601_timestamps_as_utc(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    pd.DataFrame(
        {
            "event_id": ["fractional", "whole"],
            "time": [
                "2025-08-05T20:54:55.123Z",
                "2025-08-05T16:54:55-04:00",
            ],
            "updated_at": [
                "2025-08-05T20:55:00Z",
                "2025-08-05T20:55:00+00:00",
            ],
        }
    ).to_csv(path, index=False)

    frame = load_catalog(path)

    assert str(frame["time"].dtype) == "datetime64[ns, UTC]"
    assert frame["time"].tolist() == [
        pd.Timestamp("2025-08-05T20:54:55.123Z"),
        pd.Timestamp("2025-08-05T20:54:55Z"),
    ]


def test_canonical_event_keeps_negative_depth() -> None:
    event_time = datetime(2025, 8, 5, tzinfo=timezone.utc)
    catalog_event = CatalogEvent("negative", event_time, 18.0, -66.0, -2.5, 1.0)
    assert catalog_event.depth == -2.5
