"""CSV and Parquet export helpers for normalized catalog results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.catalog.models import CatalogIngestionResult

CATALOG_COLUMNS = (
    "event_id", "time", "latitude", "longitude", "depth", "magnitude",
    "magnitude_type", "place", "event_type", "source", "updated_time",
)


def to_dataframe(result: CatalogIngestionResult) -> pd.DataFrame:
    """Convert an immutable result to a typed DataFrame with Athena columns."""
    dataframe = pd.DataFrame.from_records(result.records(), columns=CATALOG_COLUMNS)
    if dataframe.empty:
        return dataframe
    dataframe["time"] = pd.to_datetime(dataframe["time"], utc=True)
    dataframe["updated_time"] = pd.to_datetime(dataframe["updated_time"], utc=True)
    for column in ("latitude", "longitude", "depth", "magnitude"):
        dataframe[column] = pd.to_numeric(dataframe[column], errors="raise")
    return dataframe


def export_csv(result: CatalogIngestionResult, path: str | Path) -> Path:
    """Write the deterministic normalized catalog to CSV."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    to_dataframe(result).to_csv(output, index=False)
    return output


def export_parquet(result: CatalogIngestionResult, path: str | Path) -> Path:
    """Write the deterministic normalized catalog to Parquet."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    to_dataframe(result).to_parquet(output, index=False, engine="pyarrow")
    return output
