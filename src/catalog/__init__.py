"""Public API for the deterministic Historical Catalog Engine v1."""
from src.catalog.deduplicator import DeduplicationResult, deduplicate_catalog, merge_events
from src.catalog.downloader import (
    CatalogDownloadError, CatalogResponseError, DownloadConfiguration,
    HistoricalCatalogDownloader, USGSCatalogDownloader,
)
from src.catalog.export import CATALOG_COLUMNS, export_csv, export_parquet, to_dataframe
from src.catalog.models import (
    CatalogEvent, CatalogIngestionResult, CatalogQuery, GeographicBounds,
    IngestionSummary,
)
from src.catalog.pipeline import HistoricalCatalogIngestor, ingest_historical_catalog
from src.catalog.regions import (
    CARIBBEAN, DOMINICAN_REPUBLIC, LESSER_ANTILLES, MONA_PASSAGE,
    PUERTO_RICO, REGIONS, VIRGIN_ISLANDS, CatalogRegion, Region,
    RegionRegistry, get_region, load_regions,
)
from src.catalog.storage import (
    ParquetCatalogStorage, events_from_frame, frame_from_events,
    load_catalog as load_catalog_frame, read_catalog, save_catalog, write_catalog,
)
from src.catalog.updater import CatalogUpdateResult, CatalogUpdater, load_catalog
from src.catalog.usgs import (
    USGSHistoricalCatalogClient, UsgsCatalogError, UsgsHistoricalCatalogClient,
)
from src.catalog.validator import (
    CatalogValidationError, parse_usgs_feature, parse_usgs_feature_collection,
)

__all__ = [
    "CARIBBEAN", "CATALOG_COLUMNS", "DOMINICAN_REPUBLIC", "LESSER_ANTILLES",
    "MONA_PASSAGE", "PUERTO_RICO", "REGIONS", "VIRGIN_ISLANDS",
    "CatalogDownloadError", "CatalogEvent", "CatalogIngestionResult",
    "CatalogQuery", "CatalogRegion", "CatalogResponseError", "CatalogUpdateResult",
    "CatalogUpdater", "CatalogValidationError", "DeduplicationResult",
    "DownloadConfiguration", "GeographicBounds", "HistoricalCatalogDownloader",
    "HistoricalCatalogIngestor", "IngestionSummary", "ParquetCatalogStorage",
    "Region", "RegionRegistry", "USGSCatalogDownloader",
    "USGSHistoricalCatalogClient", "UsgsCatalogError", "UsgsHistoricalCatalogClient",
    "deduplicate_catalog", "events_from_frame", "export_csv", "export_parquet",
    "frame_from_events", "get_region", "ingest_historical_catalog", "load_catalog",
    "load_catalog_frame", "load_regions", "merge_events", "parse_usgs_feature",
    "parse_usgs_feature_collection", "read_catalog", "save_catalog", "to_dataframe",
    "write_catalog",
]
