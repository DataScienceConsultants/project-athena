from datetime import datetime, timedelta, timezone
import pytest
from src.catalog import CatalogEvent, CatalogQuery, CatalogUpdater, GeographicBounds, PUERTO_RICO, load_catalog
NOW=datetime(2024,1,1,tzinfo=timezone.utc)
def event(i,lat=18,updated=NOW): return CatalogEvent(i,NOW,lat,-66,5,1,updated_at=updated)
class MemoryStorage:
    def __init__(self,events=()): self.events=events; self.saved=0
    def load(self,region,**kwargs): return self.events
    def save(self,region,events): self.events=events; self.saved+=1
class Downloader:
    def __init__(self,events=(),error=None): self.events=events; self.error=error
    def download(self,query):
        if self.error: raise self.error
        return self.events
QUERY=CatalogQuery(NOW-timedelta(1),NOW+timedelta(1),GeographicBounds(17,20,-69,-63))

def test_update_counts_filters_and_saves():
    storage=MemoryStorage((event("same"),event("change"),))
    incoming=(event("same"),event("change",updated=NOW+timedelta(1)),event("new"),event("outside",lat=30))
    result=CatalogUpdater(PUERTO_RICO,downloader=Downloader(incoming),storage=storage).update(QUERY)
    assert (result.downloaded_count,result.existing_count,result.inserted_count,result.updated_count,result.unchanged_count,result.final_count)==(4,2,1,1,1,3)
    assert storage.saved==1

def test_failed_download_never_overwrites():
    storage=MemoryStorage((event("old"),))
    with pytest.raises(RuntimeError): CatalogUpdater(PUERTO_RICO,downloader=Downloader(error=RuntimeError("offline")),storage=storage).update(QUERY)
    assert storage.saved==0 and storage.events[0].event_id=="old"

def test_load_catalog_convenience_uses_injected_storage():
    storage=MemoryStorage((event("x"),))
    assert load_catalog(PUERTO_RICO,storage=storage)[0].event_id=="x"


def test_update_rejects_query_bounds_that_do_not_match_region():
    mismatched = CatalogQuery(
        NOW - timedelta(1),
        NOW + timedelta(1),
        GeographicBounds(10, 11, -69, -63),
    )
    storage = MemoryStorage()
    with pytest.raises(ValueError, match="must match"):
        CatalogUpdater(PUERTO_RICO, downloader=Downloader(), storage=storage).update(
            mismatched
        )
    assert storage.saved == 0
