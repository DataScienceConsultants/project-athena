import pytest
from src.catalog import CatalogValidationError, parse_usgs_feature, parse_usgs_feature_collection

def feature(event_id="a", updated=1704067201000):
    return {"type":"Feature", "id":event_id, "geometry":{"type":"Point","coordinates":[-66,18,5]}, "properties":{"time":1704067200000,"updated":updated,"mag":2.1,"magType":"ml","place":"PR","status":"reviewed","type":"earthquake","net":"pr"}}

def test_parse_feature_maps_all_fields():
    event = parse_usgs_feature(feature())
    assert (event.event_id, event.source, event.status, event.event_type) == ("a", "pr", "reviewed", "earthquake")

def test_nullable_magnitude_is_supported():
    raw=feature(); raw["properties"]["mag"] = None
    assert parse_usgs_feature(raw).magnitude is None

def test_collection_preserves_order():
    assert [x.event_id for x in parse_usgs_feature_collection({"type":"FeatureCollection","features":[feature("b"), feature("a")]})] == ["b", "a"]

@pytest.mark.parametrize("payload", [{}, {"type":"FeatureCollection","features":{}}, {"type":"FeatureCollection","features":[{"id":"x"}]}])
def test_malformed_payload_is_rejected(payload):
    with pytest.raises(CatalogValidationError): parse_usgs_feature_collection(payload)
