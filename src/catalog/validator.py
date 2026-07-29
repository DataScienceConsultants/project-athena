"""Deterministic validation and normalization of historical catalog frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.catalog.export import CATALOG_COLUMNS

REQUIRED_COLUMNS = ("event_id", "time", "latitude", "longitude", "depth", "magnitude")
NUMERIC_COLUMNS = ("latitude", "longitude", "depth", "magnitude")


class CatalogValidationError(ValueError):
    """Raised when a catalog cannot be made analysis-ready."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    row: object | None
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class CatalogValidationResult:
    """Immutable validation summary; the normalized frame is returned separately."""

    input_count: int
    valid_count: int
    invalid_count: int
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return self.invalid_count == 0


def validate_catalog(frame: pd.DataFrame) -> CatalogValidationResult:
    """Validate required schema and values without mutating *frame*."""
    normalized, result = normalize_catalog(frame, drop_invalid=True)
    del normalized
    return result


def normalize_catalog(
    frame: pd.DataFrame, *, drop_invalid: bool = False
) -> tuple[pd.DataFrame, CatalogValidationResult]:
    """Return a canonical copy and detailed validation result.

    Rows are never silently removed unless ``drop_invalid=True``. Timestamps are
    normalized to UTC, numeric fields are finite, and geographic/depth ranges
    are enforced.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame.")
    missing = tuple(column for column in REQUIRED_COLUMNS if column not in frame.columns)
    if missing:
        raise CatalogValidationError(f"Catalog is missing required columns: {', '.join(missing)}")
    output = frame.copy(deep=True)
    issues: list[ValidationIssue] = []
    bad_rows: set[object] = set()

    def issue(index: object, field: str, message: str) -> None:
        issues.append(ValidationIssue(index, field, message))
        bad_rows.add(index)

    identifiers = output["event_id"]
    for index, value in identifiers.items():
        if not isinstance(value, str) or not value.strip():
            issue(index, "event_id", "must be a nonempty string")
        else:
            output.at[index, "event_id"] = value.strip()
    parsed_time = pd.to_datetime(output["time"], utc=True, errors="coerce")
    for index in output.index[parsed_time.isna()]:
        issue(index, "time", "must be a valid timestamp")
    output["time"] = parsed_time
    if "updated_time" in output:
        present = output["updated_time"].notna()
        updated = pd.to_datetime(output["updated_time"], utc=True, errors="coerce")
        for index in output.index[present & updated.isna()]:
            issue(index, "updated_time", "must be a valid timestamp when present")
        output["updated_time"] = updated
    for column in NUMERIC_COLUMNS:
        # pandas treats bool as numeric; reject it explicitly.
        bool_mask = output[column].map(lambda value: isinstance(value, bool))
        numeric = pd.to_numeric(output[column], errors="coerce")
        finite = numeric.map(lambda value: pd.notna(value) and float("-inf") < float(value) < float("inf"))
        for index in output.index[bool_mask | ~finite]:
            issue(index, column, "must be a finite number, not boolean")
        output[column] = numeric.astype(float)
    ranges = {
        "latitude": (-90.0, 90.0),
        "longitude": (-180.0, 180.0),
        "depth": (0.0, float("inf")),
    }
    for column, (minimum, maximum) in ranges.items():
        mask = (output[column] < minimum) | (output[column] > maximum)
        for index in output.index[mask.fillna(False)]:
            issue(index, column, f"must be between {minimum:g} and {maximum:g}")
    unique_issues = tuple(dict.fromkeys(issues))
    result = CatalogValidationResult(len(frame), len(frame) - len(bad_rows), len(bad_rows), unique_issues)
    if bad_rows and not drop_invalid:
        first = unique_issues[0]
        raise CatalogValidationError(
            f"Catalog contains {len(bad_rows)} invalid row(s); row {first.row!r} "
            f"field {first.field}: {first.message}."
        )
    if drop_invalid:
        output = output.drop(index=list(bad_rows))
    leading = [column for column in CATALOG_COLUMNS if column in output.columns]
    trailing = [column for column in output.columns if column not in leading]
    output = output.loc[:, leading + trailing].reset_index(drop=True)
    return output, result
