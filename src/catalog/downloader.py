"""Standard-library USGS downloader for reproducible catalog retrieval."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.catalog.models import CatalogQuery

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


class CatalogDownloadError(RuntimeError):
    """Raised when the remote service cannot return a valid catalog."""


@dataclass(frozen=True, slots=True)
class CatalogDownloadResult:
    features: tuple[dict[str, Any], ...]
    request_count: int


class HistoricalCatalogDownloader:
    """Download GeoJSON in deterministic, half-open time chunks."""

    def __init__(self, *, base_url: str = USGS_QUERY_URL, timeout_seconds: float = 60.0,
                 chunk_days: int = 30, opener: Callable[..., Any] = urlopen) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be numeric, not boolean.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if isinstance(chunk_days, bool) or not isinstance(chunk_days, int):
            raise TypeError("chunk_days must be an integer, not boolean.")
        if chunk_days <= 0:
            raise ValueError("chunk_days must be greater than zero.")
        self.base_url = base_url
        self.timeout_seconds = float(timeout_seconds)
        self.chunk_days = chunk_days
        self._opener = opener

    def fetch(self, query: CatalogQuery) -> list[dict[str, Any]]:
        return list(self.download(query).features)

    def download(self, query: CatalogQuery) -> CatalogDownloadResult:
        if not isinstance(query, CatalogQuery):
            raise TypeError("query must be CatalogQuery.")
        features: list[dict[str, Any]] = []
        requests = 0
        start = query.start_time_utc
        while start < query.end_time_utc:
            end = min(start + timedelta(days=self.chunk_days), query.end_time_utc)
            features.extend(self._request(query, start, end))
            requests += 1
            start = end
        return CatalogDownloadResult(tuple(features), requests)

    def _request(self, query: CatalogQuery, start: Any, end: Any) -> list[dict[str, Any]]:
        bounds = query.bounds
        parameters: dict[str, str | float] = {
            "format": "geojson", "starttime": start.isoformat(), "endtime": end.isoformat(),
            "minlatitude": bounds.min_latitude, "maxlatitude": bounds.max_latitude,
            "minlongitude": bounds.min_longitude, "maxlongitude": bounds.max_longitude,
            "orderby": "time-asc",
        }
        if query.minimum_magnitude is not None:
            parameters["minmagnitude"] = query.minimum_magnitude
        request = Request(f"{self.base_url}?{urlencode(parameters)}", headers={"User-Agent": "project-athena/catalog-v1"})
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            with response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CatalogDownloadError(f"Catalog request failed: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise CatalogDownloadError("Catalog response is not a GeoJSON FeatureCollection.")
        if not all(isinstance(item, dict) for item in payload["features"]):
            raise CatalogDownloadError("Catalog response contains a non-object feature.")
        return payload["features"]
