"""Tests for deterministic historical catalog ingestion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.catalog import (
    CatalogQuery,
    GeographicBounds,
    HistoricalCatalogIngestor,
    UsgsCatalogError,
    UsgsHistoricalCatalogClient,
    export_csv,
    export_parquet,
    to_dataframe,
)

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_catalog.json"


class FixtureClient:
    def fetch(self, query: CatalogQuery) -> list[dict[str, object]]:
        del query
        return json.loads(FIXTURE.read_text(encoding="utf-8"))["features"]


def query() -> CatalogQuery:
    return CatalogQuery(
        start_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        end_time=datetime(2020, 1, 3, tzinfo=timezone.utc),
        bounds=GeographicBounds(17, 20, -69, -63.5),
        minimum_magnitude=0,
    )


def test_ingestion_normalizes_filters_and_deduplicates() -> None:
    result = HistoricalCatalogIngestor(FixtureClient()).ingest(query())
    assert [event.event_id for event in result.events] == ["same", "later"]
    assert result.events[0].magnitude == 1.5
    assert result.events[0].time.tzinfo == timezone.utc
    assert result.summary.excluded_incomplete_count == 1
    assert result.summary.excluded_invalid_count == 1
    assert result.summary.duplicate_count == 1
    assert result.summary.final_count == 2
    with pytest.raises(AttributeError):
        result.events += ()  # type: ignore[misc]


def test_exports_have_required_columns_and_round_trip(tmp_path: Path) -> None:
    result = HistoricalCatalogIngestor(FixtureClient()).ingest(query())
    dataframe = to_dataframe(result)
    assert list(dataframe.columns) == [
        "event_id", "time", "latitude", "longitude", "depth", "magnitude",
        "magnitude_type", "place", "event_type", "source", "updated_time",
    ]
    csv_path = export_csv(result, tmp_path / "catalog.csv")
    parquet_path = export_parquet(result, tmp_path / "catalog.parquet")
    assert len(pd.read_csv(csv_path)) == 2
    assert len(pd.read_parquet(parquet_path)) == 2


def test_client_builds_filtered_request_with_mocked_session() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"type": "FeatureCollection", "features": []}

    class Session:
        def get(self, *args: object, **kwargs: object) -> Response:
            self.args, self.kwargs = args, kwargs
            return Response()

    session = Session()
    assert UsgsHistoricalCatalogClient(session=session).fetch(query()) == []  # type: ignore[arg-type]
    assert session.kwargs["params"]["minmagnitude"] == 0  # type: ignore[index]
    assert session.kwargs["params"]["minlatitude"] == 17  # type: ignore[index]


def test_client_wraps_network_failure() -> None:
    class Session:
        def get(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise requests.ConnectionError("offline")

    with pytest.raises(UsgsCatalogError, match="USGS request failed"):
        UsgsHistoricalCatalogClient(session=Session()).fetch(query())  # type: ignore[arg-type]


def test_query_rejects_invalid_bounds_and_naive_time() -> None:
    with pytest.raises(ValueError, match="Latitude"):
        GeographicBounds(-91, 20, -69, -63)
    with pytest.raises(ValueError, match="timezone-aware"):
        CatalogQuery(
            start_time=datetime(2020, 1, 1), end_time=datetime(2020, 1, 2),
            bounds=GeographicBounds(17, 20, -69, -63),
        )
