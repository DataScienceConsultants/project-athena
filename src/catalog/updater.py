"""Failure-safe historical catalog updates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.catalog.deduplicator import merge_events
from src.catalog.downloader import USGSCatalogDownloader
from src.catalog.models import CatalogEvent, CatalogQuery
from src.catalog.regions import PUERTO_RICO, Region
from src.catalog.storage import ParquetCatalogStorage


class Downloader(Protocol):
    def download(self, query: CatalogQuery) -> tuple[CatalogEvent, ...]: ...

class Storage(Protocol):
    def load(self, region: Region, *, start=None, end=None) -> tuple[CatalogEvent, ...]: ...
    def save(self, region: Region, events: tuple[CatalogEvent, ...]): ...

@dataclass(frozen=True, slots=True)
class CatalogUpdateResult:
    events: tuple[CatalogEvent, ...]
    downloaded_count: int
    existing_count: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    final_count: int


class CatalogUpdater:
    def __init__(self, region: Region = PUERTO_RICO, *, downloader: Downloader | None = None,
                 storage: Storage | None = None) -> None:
        if not isinstance(region, Region):
            raise TypeError("region must be a Region.")
        self.region = region
        self.downloader = downloader or USGSCatalogDownloader()
        self.storage = storage or ParquetCatalogStorage()

    def update(self, query: CatalogQuery) -> CatalogUpdateResult:
        """Download, defensively filter, merge, then persist the complete catalog."""
        existing = self.storage.load(self.region)
        # Download and validate the entire response before any write is attempted.
        downloaded = self.downloader.download(query)
        filtered = tuple(event for event in downloaded if self.region.contains(event.latitude, event.longitude)
                         and query.start_time <= event.time < query.end_time
                         and (query.minimum_magnitude is None or event.magnitude is not None and event.magnitude >= query.minimum_magnitude))
        merged = merge_events(existing, filtered)
        self.storage.save(self.region, merged.events)
        return CatalogUpdateResult(
            merged.events, len(downloaded), len(existing), merged.inserted_count,
            merged.updated_count, merged.unchanged_count, len(merged.events),
        )


def load_catalog(region: Region = PUERTO_RICO, *, storage: Storage | None = None,
                 start=None, end=None) -> tuple[CatalogEvent, ...]:
    """Convenience loader for a region's stored validated events."""
    return (storage or ParquetCatalogStorage()).load(region, start=start, end=end)
