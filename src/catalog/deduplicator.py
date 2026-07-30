"""Deterministic catalog-event merging."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from src.catalog.models import CatalogEvent


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    events: tuple[CatalogEvent, ...]
    inserted_count: int
    updated_count: int
    unchanged_count: int

    @property
    def output_count(self) -> int:
        return len(self.events)


def _revision_key(event: CatalogEvent) -> tuple[datetime, datetime, tuple[str, ...]]:
    serialized = event.to_dict()
    return (
        event.updated_at or event.time,
        event.time,
        tuple("" if value is None else str(value) for value in serialized.values()),
    )


def merge_events(existing: Iterable[CatalogEvent], incoming: Iterable[CatalogEvent]) -> DeduplicationResult:
    """Merge revisions using update time, event time, then serialized value.

    IDs are scoped by source. Incoming records not already stored are inserted;
    a deterministic winning incoming revision is updated, and older/equal records
    are unchanged. Duplicate records within either input cannot affect the result.
    """
    old: dict[tuple[str, str], CatalogEvent] = {}
    for event in existing:
        if not isinstance(event, CatalogEvent):
            raise TypeError("existing must contain CatalogEvent objects.")
        key = (event.source, event.event_id)
        if key not in old or _revision_key(event) > _revision_key(old[key]):
            old[key] = event
    additions: dict[tuple[str, str], CatalogEvent] = {}
    for event in incoming:
        if not isinstance(event, CatalogEvent):
            raise TypeError("incoming must contain CatalogEvent objects.")
        key = (event.source, event.event_id)
        if key not in additions or _revision_key(event) > _revision_key(additions[key]):
            additions[key] = event
    merged = dict(old)
    inserted = updated = unchanged = 0
    for key in sorted(additions):
        candidate = additions[key]
        current = old.get(key)
        if current is None:
            merged[key] = candidate
            inserted += 1
        elif _revision_key(candidate) > _revision_key(current):
            merged[key] = candidate
            updated += 1
        else:
            unchanged += 1
    events = tuple(sorted(merged.values(), key=lambda item: (item.time, item.event_id, item.source)))
    return DeduplicationResult(events, inserted, updated, unchanged)


def deduplicate_catalog(frame: pd.DataFrame):
    """Backward-compatible DataFrame deduplicator."""
    from src.catalog.storage import events_from_frame, frame_from_events
    result = merge_events((), events_from_frame(frame))

    @dataclass(frozen=True, slots=True)
    class LegacyResult:
        catalog: pd.DataFrame
        input_count: int
        duplicate_count: int
        output_count: int
    return LegacyResult(frame_from_events(result.events), len(frame), len(frame) - len(result.events), len(result.events))
