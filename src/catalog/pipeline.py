"""Reusable end-to-end historical seismic catalog ingestion pipeline."""

from __future__ import annotations

from typing import Any, Protocol

from src.catalog.models import CatalogIngestionResult, CatalogQuery, IngestionSummary
from src.catalog.normalization import deduplicate_events, filter_events, normalize_features
from src.catalog.usgs import UsgsHistoricalCatalogClient


class CatalogClient(Protocol):
    """Protocol implemented by clients supplying raw GeoJSON event features."""

    def fetch(self, query: CatalogQuery) -> list[dict[str, Any]]:
        """Return source features for a query."""


class HistoricalCatalogIngestor:
    """Retrieve, validate, deduplicate, and sort a historical seismic catalog."""

    def __init__(self, client: CatalogClient | None = None, *, source: str = "USGS") -> None:
        self.client = client or UsgsHistoricalCatalogClient()
        self.source = source

    def ingest(self, query: CatalogQuery) -> CatalogIngestionResult:
        """Produce a deterministic immutable catalog suitable for Athena analyses."""
        features = self.client.fetch(query)
        events, requested, incomplete, invalid = normalize_features(features, source=self.source)
        filtered = filter_events(events, query)
        deduplicated, duplicates = deduplicate_events(filtered)
        summary = IngestionSummary(
            requested_count=requested, accepted_count=len(events),
            excluded_incomplete_count=incomplete, excluded_invalid_count=invalid,
            duplicate_count=duplicates, final_count=len(deduplicated),
            start_time=query.start_time_utc, end_time=query.end_time_utc,
            minimum_magnitude=query.minimum_magnitude, bounds=query.bounds, source=self.source,
        )
        return CatalogIngestionResult(events=tuple(deduplicated), summary=summary)


def ingest_historical_catalog(
    query: CatalogQuery, client: CatalogClient | None = None, *, source: str = "USGS"
) -> CatalogIngestionResult:
    """Convenience function for a one-off historical catalog ingestion."""
    return HistoricalCatalogIngestor(client, source=source).ingest(query)
