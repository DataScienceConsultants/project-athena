"""USGS GeoJSON client for historical seismic catalog retrieval."""

from __future__ import annotations

from typing import Any

import requests

from src.catalog.models import CatalogQuery


class UsgsCatalogError(RuntimeError):
    """Raised when USGS cannot provide a valid catalog response."""


class UsgsHistoricalCatalogClient:
    """Retrieve raw historical event features from the USGS FDSN service."""

    DEFAULT_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch(self, query: CatalogQuery) -> list[dict[str, Any]]:
        """Fetch GeoJSON features for *query* without normalizing their content."""
        try:
            response = self.session.get(
                self.base_url,
                params=self._parameters(query),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UsgsCatalogError(f"USGS request failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise UsgsCatalogError("USGS returned invalid JSON.") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise UsgsCatalogError("USGS response is not a GeoJSON FeatureCollection.")
        features = payload.get("features")
        if not isinstance(features, list):
            raise UsgsCatalogError("USGS response does not contain a features list.")
        return features

    @staticmethod
    def _parameters(query: CatalogQuery) -> dict[str, str | float]:
        bounds = query.bounds
        parameters: dict[str, str | float] = {
            "format": "geojson",
            "starttime": query.start_time_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": query.end_time_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            "minlatitude": bounds.min_latitude,
            "maxlatitude": bounds.max_latitude,
            "minlongitude": bounds.min_longitude,
            "maxlongitude": bounds.max_longitude,
            "orderby": "time-asc",
        }
        if query.minimum_magnitude is not None:
            parameters["minmagnitude"] = query.minimum_magnitude
        return parameters


USGSHistoricalCatalogClient = UsgsHistoricalCatalogClient
