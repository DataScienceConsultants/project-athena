import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
import pytest
from src.catalog import CatalogDownloadError, CatalogQuery, CatalogResponseError, DownloadConfiguration, GeographicBounds, USGSCatalogDownloader
NOW=datetime(2024,1,1,tzinfo=timezone.utc)
QUERY=CatalogQuery(NOW,NOW+timedelta(1),GeographicBounds(17,20,-69,-63))
def feature(i): return {"id":str(i),"geometry":{"type":"Point","coordinates":[-66,18,5]},"properties":{"time":1704067200000+i,"updated":1704067200000+i,"mag":1,"net":"us"}}
class Response:
    def __init__(self,payload): self.payload=payload
    def read(self): return json.dumps(self.payload).encode()
    def close(self): pass

def test_paginates_with_one_based_offsets_and_deduplicates():
    offsets=[]
    def open_(request,timeout):
        offset=int(parse_qs(urlparse(request.full_url).query)["offset"][0]); offsets.append(offset)
        rows=[feature(1),feature(2)] if offset==1 else [feature(2)]
        return Response({"type":"FeatureCollection","features":rows})
    result=USGSCatalogDownloader(DownloadConfiguration(limit=2),opener=open_).download(QUERY)
    assert offsets == [1,3] and len(result)==2

def test_transient_errors_retry_with_exponential_backoff():
    calls=[]; sleeps=[]
    def open_(*args,**kwargs):
        calls.append(1)
        if len(calls)<3: raise URLError("temporary")
        return Response({"type":"FeatureCollection","features":[]})
    USGSCatalogDownloader(DownloadConfiguration(max_retries=2,backoff_seconds=.5),opener=open_,sleep=sleeps.append).download(QUERY)
    assert sleeps == [.5,1.0]

def test_permanent_4xx_does_not_retry():
    calls=[]
    def open_(*args,**kwargs): calls.append(1); raise HTTPError("x",404,"no",{},None)
    with pytest.raises(CatalogDownloadError): USGSCatalogDownloader(opener=open_).download(QUERY)
    assert len(calls)==1

def test_malformed_response_has_specific_error():
    with pytest.raises(CatalogResponseError): USGSCatalogDownloader(opener=lambda *a,**k:Response({})).download(QUERY)


def test_repeated_full_page_stops_endless_pagination():
    payload = {"type": "FeatureCollection", "features": [feature(1)]}
    downloader = USGSCatalogDownloader(
        DownloadConfiguration(limit=1), opener=lambda *args, **kwargs: Response(payload)
    )
    with pytest.raises(CatalogResponseError, match="repeated"):
        downloader.download(QUERY)


def test_maximum_page_count_stops_endless_pagination():
    counter = iter(range(1, 10))
    downloader = USGSCatalogDownloader(
        DownloadConfiguration(limit=1, max_pages=2),
        opener=lambda *args, **kwargs: Response(
            {"type": "FeatureCollection", "features": [feature(next(counter))]}
        ),
    )
    with pytest.raises(CatalogResponseError, match="maximum"):
        downloader.download(QUERY)
