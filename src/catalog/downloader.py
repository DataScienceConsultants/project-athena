"""Paginated, retrying USGS historical catalog downloader."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.catalog.deduplicator import merge_events
from src.catalog.models import CatalogEvent, CatalogQuery
from src.catalog.validator import CatalogValidationError, parse_usgs_feature_collection

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

class CatalogDownloadError(RuntimeError):
    """Raised when USGS cannot be reached after configured retries."""

class CatalogResponseError(CatalogDownloadError):
    """Raised when USGS returns malformed catalog data."""

@dataclass(frozen=True, slots=True)
class DownloadConfiguration:
    limit: int = 20_000
    timeout_seconds: float = 60.0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    max_pages: int = 10_000

    def __post_init__(self) -> None:
        for name in ("limit", "max_retries", "max_pages"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer, not boolean.")
        for name in ("timeout_seconds", "backoff_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric, not boolean.")
        if not 1 <= self.limit <= 20_000:
            raise ValueError("limit must be between 1 and the USGS maximum of 20000.")
        if self.timeout_seconds <= 0 or self.max_retries < 0 or self.backoff_seconds < 0:
            raise ValueError("timeout must be positive and retry/backoff values nonnegative.")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be greater than zero.")


class USGSCatalogDownloader:
    def __init__(self, configuration: DownloadConfiguration | None = None, *,
                 base_url: str = USGS_QUERY_URL, opener: Callable[..., Any] = urlopen,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.configuration = configuration or DownloadConfiguration()
        self.base_url = base_url
        self._opener = opener
        self._sleep = sleep

    def download(self, query: CatalogQuery) -> tuple[CatalogEvent, ...]:
        if not isinstance(query, CatalogQuery):
            raise TypeError("query must be CatalogQuery.")
        offset = 1
        collected: tuple[CatalogEvent, ...] = ()
        page_signatures: set[tuple[CatalogEvent, ...]] = set()
        for _ in range(self.configuration.max_pages):
            page = self._page(query, offset)
            if page in page_signatures:
                raise CatalogResponseError(
                    "USGS pagination repeated a page and cannot safely progress."
                )
            page_signatures.add(page)
            collected = merge_events(collected, page).events
            if len(page) < self.configuration.limit:
                return collected
            offset += self.configuration.limit
        raise CatalogResponseError(
            f"USGS pagination exceeded the maximum of {self.configuration.max_pages} pages."
        )

    def _page(self, query: CatalogQuery, offset: int) -> tuple[CatalogEvent, ...]:
        bounds = query.bounds
        params: dict[str, str | float | int] = {
            "format": "geojson", "starttime": query.start_time.isoformat(),
            "endtime": query.end_time.isoformat(), "minlatitude": bounds.min_latitude,
            "maxlatitude": bounds.max_latitude, "minlongitude": bounds.min_longitude,
            "maxlongitude": bounds.max_longitude, "orderby": "time-asc",
            "limit": self.configuration.limit, "offset": offset,
        }
        if query.minimum_magnitude is not None:
            params["minmagnitude"] = query.minimum_magnitude
        request = Request(f"{self.base_url}?{urlencode(params)}", headers={"User-Agent": "project-athena/catalog-v1"})
        for attempt in range(self.configuration.max_retries + 1):
            try:
                response = self._opener(request, timeout=self.configuration.timeout_seconds)
                raw = response.read()
                close = getattr(response, "close", None)
                if close is not None:
                    close()
                payload = json.loads(raw.decode("utf-8"))
                return parse_usgs_feature_collection(payload)
            except HTTPError as exc:
                transient = exc.code == 429 or 500 <= exc.code < 600
                if not transient:
                    raise CatalogDownloadError(f"USGS request permanently failed with HTTP {exc.code}.") from exc
                error: Exception = exc
            except (URLError, TimeoutError, OSError) as exc:
                error = exc
            except (UnicodeError, json.JSONDecodeError, CatalogValidationError) as exc:
                raise CatalogResponseError(f"USGS returned a malformed response: {exc}") from exc
            if attempt == self.configuration.max_retries:
                raise CatalogDownloadError(f"USGS request failed after {attempt + 1} attempt(s): {error}") from error
            self._sleep(self.configuration.backoff_seconds * (2 ** attempt))
        raise AssertionError("unreachable")


# Compatibility aliases/wrapper.
CatalogDownloadResult = tuple[CatalogEvent, ...]
HistoricalCatalogDownloader = USGSCatalogDownloader
