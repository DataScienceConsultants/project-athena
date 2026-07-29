"""Incremental historical catalog updates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

from src.catalog.deduplicator import deduplicate_catalog
from src.catalog.export import to_dataframe
from src.catalog.models import CatalogQuery, GeographicBounds
from src.catalog.pipeline import HistoricalCatalogIngestor
from src.catalog.storage import load_catalog, save_catalog
from src.catalog.validator import normalize_catalog


@dataclass(frozen=True, slots=True)
class CatalogUpdateResult:
    path: Path
    previous_count: int
    downloaded_count: int
    duplicate_count: int
    final_count: int
    query_start: datetime
    query_end: datetime


def update_catalog(path: str | Path, *, end_time: datetime, bounds: GeographicBounds,
                   minimum_magnitude: float | None = None, client: object | None = None,
                   overlap: timedelta = timedelta(days=1), start_time: datetime | None = None) -> CatalogUpdateResult:
    """Download new/changed events, merge deterministically, and atomically save.

    ``overlap`` intentionally re-fetches the trailing interval so revised source
    events replace their older versions during deduplication.
    """
    destination = Path(path)
    if not isinstance(end_time, datetime) or end_time.tzinfo is None:
        raise ValueError("end_time must be a timezone-aware datetime.")
    if not isinstance(overlap, timedelta) or overlap < timedelta(0):
        raise ValueError("overlap must be a nonnegative timedelta.")
    if destination.exists():
        existing, _ = normalize_catalog(load_catalog(destination))
        previous_count = len(existing)
        if existing.empty and start_time is None:
            raise ValueError("start_time is required when the existing catalog is empty.")
        latest = existing["time"].max().to_pydatetime() if not existing.empty else start_time
        query_start = latest - overlap  # type: ignore[operator]
    else:
        if start_time is None:
            raise ValueError("start_time is required when creating a catalog.")
        existing = pd.DataFrame()
        previous_count = 0
        query_start = start_time
    if query_start.tzinfo is None:
        raise ValueError("start_time must be timezone-aware.")
    query_start = query_start.astimezone(timezone.utc)
    query_end = end_time.astimezone(timezone.utc)
    query = CatalogQuery(query_start, query_end, bounds, minimum_magnitude)
    ingestion = HistoricalCatalogIngestor(client=client).ingest(query)  # type: ignore[arg-type]
    downloaded = to_dataframe(ingestion)
    combined = downloaded if existing.empty else pd.concat([existing, downloaded], ignore_index=True)
    normalized, _ = normalize_catalog(combined)
    deduplicated = deduplicate_catalog(normalized)
    save_catalog(deduplicated.catalog, destination)
    return CatalogUpdateResult(destination, previous_count, len(downloaded),
                               deduplicated.duplicate_count, deduplicated.output_count,
                               query_start, query_end)
