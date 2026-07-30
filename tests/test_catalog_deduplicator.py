from datetime import datetime, timedelta, timezone
from src.catalog import CatalogEvent, merge_events
NOW=datetime(2024,1,1,tzinfo=timezone.utc)
def event(identifier, updated=NOW, magnitude=1): return CatalogEvent(identifier,NOW,18,-66,5,magnitude,source="us",updated_at=updated)

def test_merge_reports_insert_update_and_unchanged():
    result=merge_events((event("changed"),event("same"),event("old",NOW+timedelta(2))), (event("new"),event("changed",NOW+timedelta(1),2),event("same"),event("old",NOW,9)))
    assert (result.inserted_count,result.updated_count,result.unchanged_count)==(1,1,2)
    assert {x.event_id:x.magnitude for x in result.events}["old"] == 1

def test_page_duplicates_are_deterministic():
    first=merge_events((),(event("x",magnitude=1),event("x",magnitude=2)))
    second=merge_events((),reversed((event("x",magnitude=1),event("x",magnitude=2))))
    assert first.events == second.events

def test_ids_are_scoped_by_source():
    other=CatalogEvent("x",NOW,18,-66,5,1,source="pr",updated_at=NOW)
    assert merge_events((event("x"),),(other,)).inserted_count == 1
