from datetime import UTC, datetime

from src.catalog.models import CatalogEvent, CatalogQuery, GeographicBounds
from src.global_research.catalog import USGSCatalogCounter, download_global_catalog
from src.global_research.models import (
    GlobalCatalogPlan,
    GlobalResearchProfile,
    PlannedCatalogQuery,
)


class FakeResponse:
    status_code = 200
    text = "1234\n"

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, *, params, timeout, headers):
        self.calls.append(
            {"url": url, "params": params, "timeout": timeout, "headers": headers}
        )
        return FakeResponse()


def event(event_id, day, *, updated_day=None):
    return CatalogEvent(
        event_id=event_id,
        time=datetime(2020, 1, day, tzinfo=UTC),
        latitude=10.0,
        longitude=-60.0,
        depth=20.0,
        magnitude=6.2,
        source="USGS",
        updated_at=datetime(2020, 2, updated_day or day, tzinfo=UTC),
    )


def test_usgs_counter_uses_count_endpoint_parameters():
    session = FakeSession()
    counter = USGSCatalogCounter(session=session, timeout_seconds=12.0)
    query = CatalogQuery(
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 2, 1, tzinfo=UTC),
        bounds=GeographicBounds(-10, 10, -20, 20),
        minimum_magnitude=6.0,
    )

    count = counter(query)

    assert count == 1234
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["params"]["format"] == "text"
    assert call["params"]["minmagnitude"] == 6.0
    assert call["params"]["minlatitude"] == -10.0
    assert call["params"]["maxlongitude"] == 20.0
    assert call["timeout"] == 12.0


def test_global_download_merges_duplicate_boundary_events_and_keeps_newest_revision():
    profile = GlobalResearchProfile(
        profile_id="fixture",
        start_time=datetime(2020, 1, 1, tzinfo=UTC),
        end_time=datetime(2020, 1, 5, tzinfo=UTC),
        minimum_magnitude=6.0,
    )
    bounds = profile.bounds
    partitions = (
        PlannedCatalogQuery(
            query_id="q00001",
            expected_event_count=2,
            start_time=datetime(2020, 1, 1, tzinfo=UTC),
            end_time=datetime(2020, 1, 3, tzinfo=UTC),
            bounds=bounds,
            minimum_magnitude=6.0,
        ),
        PlannedCatalogQuery(
            query_id="q00002",
            expected_event_count=2,
            start_time=datetime(2020, 1, 3, tzinfo=UTC),
            end_time=datetime(2020, 1, 5, tzinfo=UTC),
            bounds=bounds,
            minimum_magnitude=6.0,
        ),
    )
    plan = GlobalCatalogPlan(profile=profile, partitions=partitions, expected_event_count=4)

    older_boundary = event("boundary", 3, updated_day=3)
    newer_boundary = CatalogEvent(
        event_id="boundary",
        time=older_boundary.time,
        latitude=older_boundary.latitude,
        longitude=older_boundary.longitude,
        depth=older_boundary.depth,
        magnitude=6.4,
        source="USGS",
        updated_at=datetime(2020, 2, 4, tzinfo=UTC),
    )

    class FakeDownloader:
        def download(self, query):
            if query.start_time.day == 1:
                return (event("first", 1), older_boundary)
            return (newer_boundary, event("last", 4))

    result = download_global_catalog(plan, downloader=FakeDownloader())

    assert result.event_count == 3
    assert [item.event_id for item in result.events] == ["first", "boundary", "last"]
    assert result.events[1].magnitude == 6.4
