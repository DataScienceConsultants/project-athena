"""Adapters between canonical catalog events and Observatory inputs."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.catalog import CatalogEvent, ParquetCatalogStorage, get_region
from src.observatory.models import ObservatoryReport


OBSERVATORY_CATALOG_COLUMNS = (
    "event_id",
    "event_time_utc",
    "updated_time_utc",
    "latitude",
    "longitude",
    "depth_km",
    "magnitude",
    "place",
    "source",
)


def catalog_events_to_observatory_dataframe(
    events: Iterable[CatalogEvent],
) -> pd.DataFrame:
    """Map validated catalog events to the schema used by Observatory metrics."""

    if isinstance(events, (str, bytes)) or not isinstance(events, Iterable):
        raise TypeError("events must be an iterable of CatalogEvent objects.")

    catalog_events = tuple(events)
    if not all(isinstance(event, CatalogEvent) for event in catalog_events):
        raise TypeError("events must contain only CatalogEvent objects.")

    records = [
        {
            "event_id": event.event_id,
            "event_time_utc": event.time,
            "updated_time_utc": event.updated_at,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "depth_km": event.depth,
            "magnitude": event.magnitude,
            "place": event.place,
            "source": event.source,
        }
        for event in catalog_events
    ]
    frame = pd.DataFrame.from_records(
        records,
        columns=OBSERVATORY_CATALOG_COLUMNS,
    )
    for column in ("event_time_utc", "updated_time_utc"):
        frame[column] = pd.to_datetime(frame[column], utc=True)

    return frame.sort_values(
        ["event_time_utc", "event_id", "source"],
        kind="stable",
    ).reset_index(drop=True)


def build_observatory_report_from_catalog_storage(
    catalog_storage_path: str | Path,
    *,
    region_key: str,
) -> ObservatoryReport:
    """Build an Observatory report from canonical catalog storage.

    ``catalog_storage_path`` is the root directory managed by
    :class:`src.catalog.ParquetCatalogStorage`. The explicitly supplied region
    key is resolved through the catalog registry; filenames are never parsed.
    """

    if not isinstance(catalog_storage_path, (str, Path)):
        raise TypeError("catalog_storage_path must be a string or Path.")

    region = get_region(region_key)
    storage = ParquetCatalogStorage(catalog_storage_path)
    events = storage.load(region)
    frame = catalog_events_to_observatory_dataframe(events)

    # Local import avoids a builder/adapter import cycle while retaining the
    # established DataFrame builder as the single calculation entry point.
    from src.observatory.builder import build_observatory_report_from_dataframe

    return build_observatory_report_from_dataframe(
        frame,
        catalog_path=storage.path_for_region(region),
        region_key=region.key,
        region_name=region.name,
    )
