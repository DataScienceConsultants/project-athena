"""Verified acquisition of external datasets used by global Athena research."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_SOURCES_PATH = PROJECT_ROOT / "config" / "research_sources.json"
DEFAULT_GEM_FAULT_PATH = PROJECT_ROOT / "data" / "sources" / "gem_active_faults.geojson"


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


def download_verified_geojson(
    *,
    url: str,
    destination: str | Path,
    expected_git_blob_sha: str,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download GeoJSON and refuse to persist bytes that do not match provenance."""
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


def download_gem_global_active_faults(
    destination: str | Path = DEFAULT_GEM_FAULT_PATH,
    *,
    sources_path: str | Path = RESEARCH_SOURCES_PATH,
    timeout_seconds: float = 120.0,
    session: Any = None,
) -> Path:
    """Download the exact GEM active-fault GeoJSON revision recorded by Athena."""
    sources = load_research_sources(sources_path)
    try:
        config = sources["faults"]["gem_global_active_faults"]
        url = config["raw_url"]
        expected_sha = config["observed_git_blob_sha"]
    except (KeyError, TypeError) as exc:
        raise ResearchSourceError(
            "GEM active-fault source configuration is incomplete."
        ) from exc
    return download_verified_geojson(
        url=url,
        destination=destination,
        expected_git_blob_sha=expected_sha,
        timeout_seconds=timeout_seconds,
        session=session,
    )
