"""USGS earthquake catalog client for Project Athena."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.ingestion.provider import (
    EarthquakeEvent,
    EarthquakeProvider,
    RegionBounds,
)

LOGGER = logging.getLogger(__name__)


class UsgsApiError(RuntimeError):
    """Raised when the USGS earthquake service returns an invalid response."""


class UsgsClient(EarthquakeProvider):
    """Retrieve and normalize earthquake events from the USGS API."""

    provider_name = "USGS"

    DEFAULT_BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_LIMIT = 20_000

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/geo+json, application/json",
                "User-Agent": (
                    "Project-Athena/0.1 "
                    "(experimental seismic research platform)"
                ),
            }
        )

    def fetch_events(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        bounds: RegionBounds,
        minimum_magnitude: float | None = None,
    ) -> list[EarthquakeEvent]:
        """Retrieve normalized earthquake events from the USGS catalog."""

        self.validate_request(
            start_time=start_time,
            end_time=end_time,
            bounds=bounds,
            minimum_magnitude=minimum_magnitude,
        )

        parameters = self._build_query_parameters(
            start_time=start_time,
            end_time=end_time,
            bounds=bounds,
            minimum_magnitude=minimum_magnitude,
        )

        LOGGER.info(
            "Requesting USGS events from %s through %s.",
            start_time.isoformat(),
            end_time.isoformat(),
        )

        try:
            response = self.session.get(
                self.base_url,
                params=parameters,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UsgsApiError(
                f"USGS request failed: {exc}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise UsgsApiError(
                "USGS returned a response that was not valid JSON."
            ) from exc

        self._validate_response(payload)

        events = [
            self._parse_feature(feature)
            for feature in payload.get("features", [])
        ]

        normalized_events = [
            event for event in events if event is not None
        ]

        LOGGER.info(
            "Received %s valid USGS earthquake events.",
            len(normalized_events),
        )

        return self.deduplicate_events(normalized_events)

    def _build_query_parameters(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        bounds: RegionBounds,
        minimum_magnitude: float | None,
    ) -> dict[str, str | int | float]:
        """Build supported USGS query parameters."""

        parameters: dict[str, str | int | float] = {
            "format": "geojson",
            "starttime": self._format_datetime(start_time),
            "endtime": self._format_datetime(end_time),
            "minlatitude": bounds.min_latitude,
            "maxlatitude": bounds.max_latitude,
            "minlongitude": bounds.min_longitude,
            "maxlongitude": bounds.max_longitude,
            "orderby": "time-asc",
            "limit": self.DEFAULT_LIMIT,
            "eventtype": "earthquake",
        }

        if minimum_magnitude is not None:
            parameters["minmagnitude"] = minimum_magnitude

        return parameters

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        """Convert a timezone-aware datetime to a USGS-compatible UTC value."""

        utc_value = value.astimezone(timezone.utc)
        return utc_value.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _validate_response(payload: Any) -> None:
        """Validate the basic structure of a USGS GeoJSON response."""

        if not isinstance(payload, dict):
            raise UsgsApiError(
                "USGS response must be a JSON object."
            )

        if payload.get("type") != "FeatureCollection":
            raise UsgsApiError(
                "USGS response is not a GeoJSON FeatureCollection."
            )

        features = payload.get("features")

        if not isinstance(features, list):
            raise UsgsApiError(
                "USGS response does not contain a valid features list."
            )

    def _parse_feature(
        self,
        feature: Any,
    ) -> EarthquakeEvent | None:
        """Convert one USGS GeoJSON feature into an EarthquakeEvent."""

        if not isinstance(feature, dict):
            LOGGER.warning("Skipping malformed USGS feature.")
            return None

        event_id = feature.get("id")
        properties = feature.get("properties")
        geometry = feature.get("geometry")

        if not isinstance(event_id, str) or not event_id:
            LOGGER.warning("Skipping USGS feature without an event ID.")
            return None

        if not isinstance(properties, dict):
            LOGGER.warning(
                "Skipping USGS event %s because properties are missing.",
                event_id,
            )
            return None

        if not isinstance(geometry, dict):
            LOGGER.warning(
                "Skipping USGS event %s because geometry is missing.",
                event_id,
            )
            return None

        coordinates = geometry.get("coordinates")

        if not isinstance(coordinates, list) or len(coordinates) < 2:
            LOGGER.warning(
                "Skipping USGS event %s because coordinates are invalid.",
                event_id,
            )
            return None

        longitude = self._as_float(coordinates[0])
        latitude = self._as_float(coordinates[1])
        depth_km = (
            self._as_float(coordinates[2])
            if len(coordinates) >= 3
            else None
        )

        event_time = self._milliseconds_to_datetime(
            properties.get("time")
        )

        if latitude is None or longitude is None or event_time is None:
            LOGGER.warning(
                "Skipping USGS event %s because required values are missing.",
                event_id,
            )
            return None

        return EarthquakeEvent(
            event_id=event_id,
            source=self.provider_name,
            event_time_utc=event_time,
            updated_time_utc=self._milliseconds_to_datetime(
                properties.get("updated")
            ),
            latitude=latitude,
            longitude=longitude,
            depth_km=depth_km,
            magnitude=self._as_float(properties.get("mag")),
            magnitude_type=self._as_optional_string(
                properties.get("magType")
            ),
            place=self._as_optional_string(properties.get("place")),
            event_type=self._as_optional_string(properties.get("type")),
            status=self._as_optional_string(properties.get("status")),
            tsunami_flag=self._as_optional_bool(
                properties.get("tsunami")
            ),
            felt_reports=self._as_optional_int(
                properties.get("felt")
            ),
            significance=self._as_optional_int(
                properties.get("sig")
            ),
            alert_level=self._as_optional_string(
                properties.get("alert")
            ),
            detail_url=self._as_optional_string(
                properties.get("detail")
            ),
            source_url=self._as_optional_string(
                properties.get("url")
            ),
        )

    @staticmethod
    def _milliseconds_to_datetime(value: Any) -> datetime | None:
        """Convert Unix milliseconds into a timezone-aware UTC datetime."""

        if value is None or isinstance(value, bool):
            return None

        try:
            milliseconds = float(value)
        except (TypeError, ValueError):
            return None

        return datetime.fromtimestamp(
            milliseconds / 1000,
            tz=timezone.utc,
        )

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_optional_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_optional_bool(value: Any) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        if value in (0, "0"):
            return False

        if value in (1, "1"):
            return True

        return None

    @staticmethod
    def _as_optional_string(value: Any) -> str | None:
        if value is None:
            return None

        text = str(value).strip()
        return text or None