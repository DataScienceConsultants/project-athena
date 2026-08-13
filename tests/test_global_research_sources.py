import json

import pytest

from src.global_research.sources import (
    ResearchSourceError,
    download_pb2002_steps,
    download_verified_file,
    download_verified_geojson,
    git_blob_sha,
    research_source_citation,
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


def test_verified_file_download_preserves_exact_non_geojson_bytes(tmp_path):
    content = b"PB2002 fixture bytes\n"
    destination = tmp_path / "PB2002_steps.dat.txt"

    result = download_verified_file(
        url="https://example.test/PB2002_steps.dat.txt",
        destination=destination,
        expected_git_blob_sha=git_blob_sha(content),
        session=FakeSession(content),
    )

    assert result == destination
    assert destination.read_bytes() == content


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


def test_download_pb2002_steps_uses_pinned_configured_source(tmp_path):
    content = b"   1  AF-AN   -0.438 -54.852   -0.039 -54.677  32.1  53  13.2  48    1.2   13.1  -1584   2  OTF\n"
    source_config = {
        "plate_boundaries": {
            "bird_pb2002": {
                "raw_url": "https://example.test/PB2002_steps.dat.txt",
                "observed_git_blob_sha": git_blob_sha(content),
                "citation": {"doi": "10.1029/2001GC000252"},
            }
        }
    }
    config_path = tmp_path / "sources.json"
    config_path.write_text(json.dumps(source_config), encoding="utf-8")
    destination = tmp_path / "steps.dat"
    session = FakeSession(content)

    result = download_pb2002_steps(
        destination=destination,
        sources_path=config_path,
        session=session,
    )

    assert result == destination
    assert destination.read_bytes() == content
    assert session.calls[0]["url"].endswith("PB2002_steps.dat.txt")


def test_research_source_citation_preserves_doi_license_and_revision(tmp_path):
    config = {
        "plate_boundaries": {
            "bird_pb2002": {
                "role": "global_plate_boundary_context",
                "distribution_license": "ODC-By-1.0",
                "distribution_commit": "abc123",
                "version_of_record_path": "PB2002_steps.dat.txt",
                "observed_git_blob_sha": "b" * 40,
                "citation": {
                    "author": "Peter Bird",
                    "year": 2003,
                    "doi": "10.1029/2001GC000252",
                },
            }
        }
    }
    config_path = tmp_path / "sources.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    citation = research_source_citation(
        "plate_boundaries",
        "bird_pb2002",
        sources_path=config_path,
    )

    assert citation["source_key"] == "bird_pb2002"
    assert citation["distribution_license"] == "ODC-By-1.0"
    assert citation["distribution_commit"] == "abc123"
    assert citation["observed_git_blob_sha"] == "b" * 40
    assert citation["citation"]["doi"] == "10.1029/2001GC000252"


def test_git_blob_sha_depends_on_exact_content():
    assert git_blob_sha(b"one") != git_blob_sha(b"two")
