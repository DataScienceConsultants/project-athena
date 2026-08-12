"""USGS-backed execution helpers for Athena global research catalog plans."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from src.catalog.deduplicator import merge_events
from src.catalog.downloader import USGSCatalogDownloader
from src.catalog.models import CatalogEvent, CatalogQuery
from src.catalog.storage import frame_from_events
from src.global_research.models import GlobalCatalogPlan
from src.global_research.planner import planned_query_as_catalog_query

USGS_COUNT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/count"


class CatalogCountError(RuntimeError):
    """Raised when the USGS count endpoint cannot safely preflight a query."""


class USGSCatalogCounter:
    """Callable USGS event counter with bounded retries for adaptive planning."""

    def __init__(
        self,
        *,
        base_url: str = USGS_COUNT_URL,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        session: Any = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError("max_retries must be an integer.")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative.")
        self.base_url = base_url
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max_retries
        self.backoff_seconds = float(backoff_seconds)
        self.session = session or requests.Session()

    def __call__(self, query: CatalogQuery) -> int:
        if not isinstance(query, CatalogQuery):
            raise TypeError("query must be CatalogQuery.")
        params = _count_parameters(query)
        error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "project-athena/global-research-v1"},
                )
                status_code = int(response.status_code)
                if status_code == 429 or 500 <= status_code < 600:
                    raise requests.HTTPError(
                        f"Transient USGS count response HTTP {status_code}",
                        response=response,
                    )
                response.raise_for_status()
                value = int(response.text.strip())
                if value < 0:
                    raise CatalogCountError("USGS returned a negative event count.")
                return value
            except (requests.RequestException, ValueError) as exc:
                error = exc
                if isinstance(exc, requests.HTTPError):
                    response = exc.response
                    if response is not None:
                        code = int(response.status_code)
                        if code != 429 and not 500 <= code < 600:
                            raise CatalogCountError(
                                f"USGS count request permanently failed with HTTP {code}."
                            ) from exc
                if attempt == self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2**attempt))
        raise CatalogCountError(
            f"USGS count request failed after {self.max_retries + 1} attempt(s): {error}"
        ) from error


def _count_parameters(query: CatalogQuery) -> dict[str, str | float]:
    bounds = query.bounds
    params: dict[str, str | float] = {
        "format": "text",
        "starttime": query.start_time.isoformat(),
        "endtime": query.end_time.isoformat(),
        "minlatitude": bounds.min_latitude,
        "maxlatitude": bounds.max_latitude,
        "minlongitude": bounds.min_longitude,
        "maxlongitude": bounds.max_longitude,
    }
    if query.minimum_magnitude is not None:
        params["minmagnitude"] = query.minimum_magnitude
    return params


@dataclass(frozen=True, slots=True)
class GlobalCatalogDownload:
    """Deduplicated event cohort produced from one adaptive query plan."""

    plan: GlobalCatalogPlan
    events: tuple[CatalogEvent, ...]

    @property
    def event_count(self) -> int:
        return len(self.events)


def download_global_catalog(
    plan: GlobalCatalogPlan,
    *,
    downloader: USGSCatalogDownloader | None = None,
) -> GlobalCatalogDownload:
    """Execute every planned partition and merge boundary duplicates by event id."""
    if not isinstance(plan, GlobalCatalogPlan):
        raise TypeError("plan must be GlobalCatalogPlan.")
    client = downloader or USGSCatalogDownloader()
    collected: tuple[CatalogEvent, ...] = ()
    for partition in plan.partitions:
        query = planned_query_as_catalog_query(partition)
        downloaded = client.download(query)
        collected = merge_events(collected, downloaded).events
    ordered = tuple(
        sorted(collected, key=lambda event: (event.time, event.event_id, event.source))
    )
    return GlobalCatalogDownload(plan=plan, events=ordered)


def export_global_catalog_csv(result: GlobalCatalogDownload, path: str | Path) -> Path:
    """Persist the normalized global cohort without requiring the parquet extra."""
    if not isinstance(result, GlobalCatalogDownload):
        raise TypeError("result must be GlobalCatalogDownload.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame_from_events(result.events).to_csv(destination, index=False)
    return destination
