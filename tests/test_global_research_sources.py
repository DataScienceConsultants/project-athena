import json

import pytest

from src.global_research.sources import (
    ResearchSourceError,
    download_verified_geojson,
    git_blob_sha,
)


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def get(self, url, *, timeout, headers):
        self.calls.append({"url": url, "timeout": timeout, "headers": headers})
        return FakeResponse(self.content)


def feature_collection_bytes():
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [],
        },
        separators=(",", ":"),
    ).encode()


def test_verified_geojson_download_writes_exact_matching_bytes(tmp_path):
    content = feature_collection_bytes()
    session = FakeSession(content)
    destination = tmp_path / "faults.geojson"

    result = download_verified_geojson(
        url="https://example.test/faults.geojson",
        destination=destination,
        expected_git_blob_sha=git_blob_sha(content),
        session=session,
    )

    assert result == destination
    assert destination.read_bytes() == content
    assert session.calls[0]["timeout"] == 120.0
    assert "project-athena" in session.calls[0]["headers"]["User-Agent"]


def test_verified_geojson_download_rejects_changed_upstream_bytes(tmp_path):
    content = feature_collection_bytes()
    destination = tmp_path / "faults.geojson"

    with pytest.raises(ResearchSourceError, match="does not match"):
        download_verified_geojson(
            url="https://example.test/faults.geojson",
            destination=destination,
            expected_git_blob_sha="0" * 40,
            session=FakeSession(content),
        )

    assert not destination.exists()


def test_git_blob_sha_depends_on_exact_content():
    assert git_blob_sha(b"one") != git_blob_sha(b"two")
