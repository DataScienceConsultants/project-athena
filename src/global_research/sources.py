"""Verified acquisition and citation metadata for global Athena research sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_SOURCES_PATH = PROJECT_ROOT / "config" / "research_sources.json"
DEFAULT_GEM_FAULT_PATH = Path("data/sources/gem_active_faults.geojson")
DEFAULT_PB2002_STEPS_PATH = Path("data/sources/PB2002_steps.dat.txt")
GEM_FAULT_RAW_URL = (
    "https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/"
    "master/geojson/gem_active_faults.geojson"
)
GEM_FAULT_GIT_BLOB_SHA = "f7a62707792e2b6d99412108bf1496d45bad51f7"
PB2002_MIRROR_COMMIT = "339b0c56563c118307b1f4542703047f5f698fae"
PB2002_STEPS_RAW_URL = (
    "https://raw.githubusercontent.com/fraxen/tectonicplates/"
    f"{PB2002_MIRROR_COMMIT}/original/PB2002_steps.dat.txt"
)
PB2002_STEPS_GIT_BLOB_SHA = "b48506d79c614b241ce26cf949492ee7c6676d60"

_FALLBACK_CITATIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("catalogs", "usgs_comcat"): {
        "source_key": "usgs_comcat",
        "role": "operational_global_ingestion",
        "citation": {
            "type": "data_service",
            "authoring_organization": "U.S. Geological Survey",
            "title": "USGS Earthquake Catalog (ComCat) FDSN Event Web Service",
            "url": "https://earthquake.usgs.gov/fdsnws/event/1/",
        },
    },
    ("faults", "gem_global_active_faults"): {
        "source_key": "gem_global_active_faults",
        "role": "global_active_fault_context",
        "license": "CC-BY-SA-4.0",
        "version_of_record_path": "geojson/gem_active_faults.geojson",
        "observed_git_blob_sha": GEM_FAULT_GIT_BLOB_SHA,
        "citation": {
            "type": "dataset",
            "authoring_organization": "Global Earthquake Model Foundation",
            "title": "GEM Global Active Faults Database",
            "url": "https://github.com/GEMScienceTools/gem-global-active-faults",
        },
    },
    ("plate_boundaries", "bird_pb2002"): {
        "source_key": "bird_pb2002",
        "role": "global_plate_boundary_context",
        "distribution_license": "ODC-By-1.0",
        "distribution_commit": PB2002_MIRROR_COMMIT,
        "version_of_record_path": "original/PB2002_steps.dat.txt",
        "observed_git_blob_sha": PB2002_STEPS_GIT_BLOB_SHA,
        "citation": {
            "type": "journal_article_and_supplementary_dataset",
            "author": "Peter Bird",
            "year": 2003,
            "title": "An updated digital model of plate boundaries",
            "journal": "Geochemistry, Geophysics, Geosystems",
            "volume": "4",
            "article": "1027",
            "doi": "10.1029/2001GC000252",
            "formatted": (
                "Bird, P. (2003). An updated digital model of plate boundaries. "
                "Geochemistry, Geophysics, Geosystems, 4, 1027. "
                "https://doi.org/10.1029/2001GC000252"
            ),
        },
    },
}


class ResearchSourceError(RuntimeError):
    """Raised when a configured external research source cannot be verified."""


def git_blob_sha(content: bytes) -> str:
    """Return the SHA-1 identifier Git assigns to one blob's exact bytes."""
    if not isinstance(content, bytes):
        raise TypeError("content must be bytes.")
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def load_research_sources(path: str | Path = RESEARCH_SOURCES_PATH) -> dict[str, Any]:
    """Load Athena's checked-in research-source provenance configuration."""
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResearchSourceError("research source configuration must be a JSON object.")
    return payload


def research_source_citation(
    section: str,
    key: str,
    *,
    sources_path: str | Path = RESEARCH_SOURCES_PATH,
) -> dict[str, Any]:
    """Return a compact citation/provenance record safe to embed in artifacts."""
    source_path = Path(sources_path)
    if source_path == RESEARCH_SOURCES_PATH and not source_path.exists():
        fallback = _FALLBACK_CITATIONS.get((section, key))
        if fallback is None:
            raise ResearchSourceError(f"Research source is not configured: {section}.{key}")
        return json.loads(json.dumps(fallback))

    sources = load_research_sources(source_path)
    try:
        config = sources[section][key]
    except (KeyError, TypeError) as exc:
        raise ResearchSourceError(f"Research source is not configured: {section}.{key}") from exc
    if not isinstance(config, dict):
        raise ResearchSourceError(f"Research source must be an object: {section}.{key}")
    citation = config.get("citation")
    if not isinstance(citation, dict):
        raise ResearchSourceError(f"Research source citation is missing: {section}.{key}")

    record: dict[str, Any] = {
        "source_key": key,
        "role": config.get("role"),
        "citation": dict(citation),
    }
    for field in (
        "version",
        "release_date",
        "doi",
        "license",
        "distribution_license",
        "distribution_commit",
        "version_of_record_path",
        "observed_git_blob_sha",
    ):
        value = config.get(field)
        if value not in (None, ""):
            record[field] = value
    return record


def _download_verified_content(
    *,
    url: str,
    expected_git_blob_sha: str,
    timeout_seconds: float,
    session: Any,
) -> bytes:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a nonempty string.")
    if not isinstance(expected_git_blob_sha, str) or len(expected_git_blob_sha) != 40:
        raise ValueError("expected_git_blob_sha must be a 40-character Git blob SHA.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive.")

    client = session or requests.Session()
    response = client.get(
        url,
        timeout=float(timeout_seconds),
        headers={"User-Agent": "project-athena/global-research-source-v1"},
    )
    response.raise_for_status()
    content = bytes(response.content)
    observed_sha = git_blob_sha(content)
    if observed_sha != expected_git_blob_sha.lower():
        raise ResearchSourceError(
            "Downloaded research source does not match the configured Git blob SHA: "
            f"expected {expected_git_blob_sha.lower()}, observed {observed_sha}."
        )
    return content


def download_verified_file(
    *,
    url: str,
    destination: str | Path,
    expected_git_blob_sha: str,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download exact verified bytes and persist them without transformation."""
    content = _download_verified_content(
        url=url,
        expected_git_blob_sha=expected_git_blob_sha,
        timeout_seconds=timeout_seconds,
        session=session,
    )
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def download_verified_geojson(
    *,
    url: str,
    destination: str | Path,
    expected_git_blob_sha: str,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download GeoJSON and refuse to persist bytes that do not match provenance."""
    content = _download_verified_content(
        url=url,
        expected_git_blob_sha=expected_git_blob_sha,
        timeout_seconds=timeout_seconds,
        session=session,
    )
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchSourceError("Downloaded source is not valid UTF-8 GeoJSON.") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ResearchSourceError("Downloaded source is not a GeoJSON FeatureCollection.")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def _configured_source(
    section: str,
    key: str,
    *,
    sources_path: str | Path | None,
    fallback_url: str,
    fallback_sha: str,
) -> tuple[str, str]:
    if sources_path is None:
        if not RESEARCH_SOURCES_PATH.exists():
            return fallback_url, fallback_sha
        sources_path = RESEARCH_SOURCES_PATH
    sources = load_research_sources(sources_path)
    try:
        config = sources[section][key]
        return str(config["raw_url"]), str(config["observed_git_blob_sha"])
    except (KeyError, TypeError) as exc:
        raise ResearchSourceError(f"Research source configuration is incomplete: {key}.") from exc


def download_gem_global_active_faults(
    destination: str | Path = DEFAULT_GEM_FAULT_PATH,
    *,
    sources_path: str | Path | None = None,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download the exact GEM active-fault GeoJSON revision recorded by Athena."""
    url, expected_sha = _configured_source(
        "faults",
        "gem_global_active_faults",
        sources_path=sources_path,
        fallback_url=GEM_FAULT_RAW_URL,
        fallback_sha=GEM_FAULT_GIT_BLOB_SHA,
    )
    return download_verified_geojson(
        url=url,
        destination=destination,
        expected_git_blob_sha=expected_sha,
        timeout_seconds=timeout_seconds,
        session=session,
    )


def download_pb2002_steps(
    destination: str | Path = DEFAULT_PB2002_STEPS_PATH,
    *,
    sources_path: str | Path | None = None,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download the pinned PB2002 step file used for plate-boundary context."""
    url, expected_sha = _configured_source(
        "plate_boundaries",
        "bird_pb2002",
        sources_path=sources_path,
        fallback_url=PB2002_STEPS_RAW_URL,
        fallback_sha=PB2002_STEPS_GIT_BLOB_SHA,
    )
    return download_verified_file(
        url=url,
        destination=destination,
        expected_git_blob_sha=expected_sha,
        timeout_seconds=timeout_seconds,
        session=session,
    )
