from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from src.catalog import CatalogEvent, ParquetCatalogStorage, PUERTO_RICO
NOW=datetime(2024,1,1,tzinfo=timezone.utc)
def events(): return tuple(CatalogEvent(str(i),NOW+timedelta(days=i),18,-66,5,1,updated_at=NOW) for i in range(3))

def test_nonexistent_load_is_empty_and_path_is_region_scoped(tmp_path):
    storage=ParquetCatalogStorage(tmp_path)
    assert storage.load(PUERTO_RICO) == ()
    assert storage.path_for_region("puerto_rico") == tmp_path/"puerto_rico.parquet"

def test_round_trip_reconstructs_events(tmp_path):
    storage=ParquetCatalogStorage(tmp_path); storage.save(PUERTO_RICO,events())
    assert storage.load(PUERTO_RICO) == events()

def test_filter_is_inclusive_start_exclusive_end(tmp_path):
    storage=ParquetCatalogStorage(tmp_path); storage.save(PUERTO_RICO,events())
    assert [x.event_id for x in storage.load(PUERTO_RICO,start=NOW+timedelta(1),end=NOW+timedelta(2))] == ["1"]


def test_filter_rejects_naive_datetimes_and_invalid_interval(tmp_path):
    storage = ParquetCatalogStorage(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        storage.load(PUERTO_RICO, start=datetime(2024, 1, 1))
    with pytest.raises(ValueError, match="earlier"):
        storage.load(PUERTO_RICO, start=NOW, end=NOW)


def test_filter_datetimes_are_normalized_to_utc(tmp_path):
    storage = ParquetCatalogStorage(tmp_path)
    storage.save(PUERTO_RICO, events())
    offset = timezone(timedelta(hours=-4))
    start = datetime(2023, 12, 31, 20, tzinfo=offset)
    end = datetime(2024, 1, 1, 20, tzinfo=offset)
    assert [event.event_id for event in storage.load(PUERTO_RICO, start=start, end=end)] == ["0"]


def test_save_order_is_deterministic(tmp_path):
    storage = ParquetCatalogStorage(tmp_path)
    storage.save(PUERTO_RICO, reversed(events()))
    assert [event.event_id for event in storage.load(PUERTO_RICO)] == ["0", "1", "2"]
