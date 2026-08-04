"""Parquet persistence for validated historical catalog events."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import pandas as pd

from src.catalog.models import CatalogEvent
from src.catalog.regions import Region, get_region

EVENT_COLUMNS = ("event_id", "time", "latitude", "longitude", "depth", "magnitude", "magnitude_type", "place", "status", "event_type", "source", "updated_at")


def _utc_filter(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime when provided.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def frame_from_events(events: Iterable[CatalogEvent]) -> pd.DataFrame:
    records = [event.to_dict() for event in events]
    frame = pd.DataFrame.from_records(records, columns=EVENT_COLUMNS)
    for column in ("time", "updated_at"):
        if column in frame:
            frame[column] = pd.to_datetime(
                frame[column], format="mixed", utc=True, errors="raise"
            )
    return frame


def events_from_frame(frame: pd.DataFrame) -> tuple[CatalogEvent, ...]:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    records = frame.to_dict(orient="records")
    cleaned = (
        {key: None if pd.isna(value) else value for key, value in record.items()}
        for record in records
    )
    return tuple(CatalogEvent(**record) for record in cleaned)


class ParquetCatalogStorage:
    """Store one validated Parquet catalog per region."""
    def __init__(self, root: str | Path = "data/processed") -> None:
        self.root = Path(root)

    def path_for_region(self, region: Region | str) -> Path:
        selected = get_region(region) if isinstance(region, str) else region
        if not isinstance(selected, Region):
            raise TypeError("region must be a Region or region key.")
        return self.root / f"{selected.key}.parquet"

    def load(
        self,
        region: Region | str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[CatalogEvent, ...]:
        start = _utc_filter(start, "start")
        end = _utc_filter(end, "end")
        if start is not None and end is not None and start >= end:
            raise ValueError("start must be earlier than end.")
        path = self.path_for_region(region)
        if not path.exists():
            return ()
        events = events_from_frame(pd.read_parquet(path, engine="pyarrow"))
        if start is not None:
            events = tuple(event for event in events if event.time >= start)
        if end is not None:
            events = tuple(event for event in events if event.time < end)
        return tuple(sorted(events, key=lambda event: (event.time, event.event_id, event.source)))

    def save(self, region: Region | str, events: Iterable[CatalogEvent]) -> Path:
        path = self.path_for_region(region)
        validated = tuple(events)
        if not all(isinstance(event, CatalogEvent) for event in validated):
            raise TypeError("events must contain CatalogEvent objects.")
        validated = tuple(
            sorted(validated, key=lambda event: (event.time, event.event_id, event.source))
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp.parquet")
        try:
            frame_from_events(validated).to_parquet(temporary, index=False, engine="pyarrow")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path


def save_catalog(frame: pd.DataFrame, path: str | Path) -> Path:
    """Backward-compatible atomic DataFrame writer."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".csv":
        frame.to_csv(destination, index=False)
    elif destination.suffix.lower() == ".parquet":
        frame.to_parquet(destination, index=False, engine="pyarrow")
    else:
        raise ValueError("Catalog path must end in .csv or .parquet.")
    return destination


def load_catalog(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    elif source.suffix.lower() == ".parquet":
        frame = pd.read_parquet(source, engine="pyarrow")
    else:
        raise ValueError("Catalog path must end in .csv or .parquet.")
    for column in ("time", "updated_at", "event_time_utc", "updated_time_utc"):
        if column in frame:
            frame[column] = pd.to_datetime(
                frame[column], format="mixed", utc=True, errors="raise"
            )
    return frame

write_catalog = save_catalog
read_catalog = load_catalog
