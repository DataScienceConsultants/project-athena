from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import pytest
from src.catalog import CatalogEvent, CatalogQuery, GeographicBounds

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)

def event(**changes):
    values = dict(event_id=" us1 ", time=NOW + timedelta(hours=1), latitude=18, longitude=-66, depth=5, magnitude=None, magnitude_type=" ml ", place=" PR ", status=" reviewed ", event_type=" earthquake ", source=" us ", updated_at=NOW)
    values.update(changes); return CatalogEvent(**values)

def test_event_normalizes_and_serializes_stably():
    value = event()
    assert value.event_id == "us1" and value.time.tzinfo is timezone.utc
    assert value.magnitude is None and value.magnitude_type == "ml"
    assert list(value.to_dict())[-3:] == ["event_type", "source", "updated_at"]

def test_updated_time_compatibility_alias():
    assert event(updated_at=None, updated_time=NOW).updated_at == NOW

def test_event_is_frozen():
    with pytest.raises(FrozenInstanceError): event().depth = 2

@pytest.mark.parametrize(("field", "value"), [("latitude", True), ("longitude", float("inf")), ("depth", -1), ("magnitude", float("nan")), ("time", datetime(2024, 1, 1)), ("event_id", " ")])
def test_event_rejects_invalid_values(field, value):
    with pytest.raises((TypeError, ValueError)): event(**{field: value})

def test_query_normalizes_utc_and_rejects_boolean_magnitude():
    query = CatalogQuery(NOW, NOW + timedelta(days=1), GeographicBounds(17, 20, -69, -63.5))
    assert query.start_time_utc.tzinfo is timezone.utc
    with pytest.raises(TypeError): CatalogQuery(NOW, NOW + timedelta(1), query.bounds, True)
