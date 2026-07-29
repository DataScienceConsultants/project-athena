"""Historical seismic catalog ingestion public API."""

from src.catalog.export import CATALOG_COLUMNS, export_csv, export_parquet, to_dataframe
from src.catalog.models import (
    CatalogEvent,
    CatalogIngestionResult,
    CatalogQuery,
    GeographicBounds,
    IngestionSummary,
)
from src.catalog.pipeline import HistoricalCatalogIngestor, ingest_historical_catalog
from src.catalog.deduplicator import DeduplicationResult, deduplicate_catalog
from src.catalog.downloader import CatalogDownloadError, CatalogDownloadResult, HistoricalCatalogDownloader
from src.catalog.regions import CatalogRegion, RegionRegistry, get_region, load_regions
from src.catalog.storage import load_catalog, read_catalog, save_catalog, write_catalog
from src.catalog.updater import CatalogUpdateResult, update_catalog
from src.catalog.validator import CatalogValidationError, CatalogValidationResult, ValidationIssue, normalize_catalog, validate_catalog
from src.catalog.usgs import (
    USGSHistoricalCatalogClient,
    UsgsCatalogError,
    UsgsHistoricalCatalogClient,
)

__all__ = [
    "CATALOG_COLUMNS",
    "CatalogEvent",
    "CatalogDownloadError",
    "CatalogDownloadResult",
    "CatalogIngestionResult",
    "CatalogQuery",
    "CatalogRegion",
    "CatalogUpdateResult",
    "CatalogValidationError",
    "CatalogValidationResult",
    "DeduplicationResult",
    "GeographicBounds",
    "HistoricalCatalogIngestor",
    "HistoricalCatalogDownloader",
    "IngestionSummary",
    "RegionRegistry",
    "USGSHistoricalCatalogClient",
    "UsgsCatalogError",
    "UsgsHistoricalCatalogClient",
    "ValidationIssue",
    "deduplicate_catalog",
    "export_csv",
    "export_parquet",
    "ingest_historical_catalog",
    "get_region",
    "load_catalog",
    "load_regions",
    "normalize_catalog",
    "read_catalog",
    "save_catalog",
    "to_dataframe",
    "update_catalog",
    "validate_catalog",
    "write_catalog",
]
