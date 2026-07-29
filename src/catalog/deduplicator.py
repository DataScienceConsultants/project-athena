"""Deterministic catalog-event deduplication."""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    catalog: pd.DataFrame
    input_count: int
    duplicate_count: int
    output_count: int


def deduplicate_catalog(frame: pd.DataFrame) -> DeduplicationResult:
    """Keep the latest update per source/event ID and sort chronologically."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    required = {"event_id", "time"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Catalog is missing required columns: {', '.join(sorted(missing))}")
    output = frame.copy(deep=True)
    output["time"] = pd.to_datetime(output["time"], utc=True, errors="raise")
    if "updated_time" in output:
        output["updated_time"] = pd.to_datetime(output["updated_time"], utc=True, errors="coerce")
    else:
        output["updated_time"] = pd.NaT
    if "source" not in output:
        output["source"] = "USGS"
    # A serialized row is an order-independent final tie breaker.
    output["__tie"] = output.astype(str).agg("\x1f".join, axis=1)
    output["__updated"] = output["updated_time"].fillna(output["time"])
    output = output.sort_values(
        ["source", "event_id", "__updated", "__tie"], kind="mergesort"
    ).drop_duplicates(["source", "event_id"], keep="last")
    output = output.sort_values(["time", "event_id", "source"], kind="mergesort")
    output = output.drop(columns=["__tie", "__updated"]).reset_index(drop=True)
    return DeduplicationResult(output, len(frame), len(frame) - len(output), len(output))
