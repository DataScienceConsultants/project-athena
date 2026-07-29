"""Atomic CSV and Parquet persistence for historical catalogs."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4
import pandas as pd

_SUPPORTED_SUFFIXES = {".csv", ".parquet"}


def save_catalog(frame: pd.DataFrame, path: str | Path) -> Path:
    """Atomically persist *frame*, selecting format from the path suffix."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    destination = Path(path)
    suffix = destination.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError("Catalog path must end in .csv or .parquet.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp{suffix}")
    try:
        if suffix == ".csv":
            frame.to_csv(temporary, index=False)
        else:
            frame.to_parquet(temporary, index=False, engine="pyarrow")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_catalog(path: str | Path) -> pd.DataFrame:
    """Load a CSV or Parquet catalog and normalize timestamp columns to UTC."""
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(source)
    elif suffix == ".parquet":
        frame = pd.read_parquet(source, engine="pyarrow")
    else:
        raise ValueError("Catalog path must end in .csv or .parquet.")
    for column in ("time", "updated_time"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    return frame


write_catalog = save_catalog
read_catalog = load_catalog
