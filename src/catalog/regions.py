"""Version-controlled geographic region definitions for catalog operations."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from src.catalog.models import GeographicBounds

DEFAULT_REGIONS_PATH = Path(__file__).parents[2] / "config" / "regions.json"


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric, not boolean.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


@dataclass(frozen=True, slots=True)
class CatalogRegion:
    """Immutable named catalog region loaded from ``config/regions.json``."""

    region_id: str
    name: str
    description: str
    bounds: GeographicBounds
    default_minimum_magnitude: float
    timezone: str
    enabled: bool = True

    def __post_init__(self) -> None:
        for field_name in ("region_id", "name", "timezone"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a nonempty string.")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string.")
        if not isinstance(self.bounds, GeographicBounds):
            raise TypeError("bounds must be GeographicBounds.")
        object.__setattr__(
            self,
            "default_minimum_magnitude",
            _finite_number(self.default_minimum_magnitude, "default_minimum_magnitude"),
        )
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be boolean.")


@dataclass(frozen=True, slots=True)
class RegionRegistry:
    """Immutable collection of configured regions and its default region ID."""

    default_region: str
    regions: Mapping[str, CatalogRegion]

    def __post_init__(self) -> None:
        if not isinstance(self.default_region, str) or not self.default_region:
            raise ValueError("default_region must be a nonempty string.")
        copied = dict(self.regions)
        if self.default_region not in copied:
            raise ValueError("default_region must identify a configured region.")
        if any(key != region.region_id for key, region in copied.items()):
            raise ValueError("Region keys must match their region_id values.")
        object.__setattr__(self, "regions", MappingProxyType(copied))

    def get(self, region_id: str | None = None, *, require_enabled: bool = True) -> CatalogRegion:
        """Return a configured region, optionally allowing disabled definitions."""
        selected = self.default_region if region_id is None else region_id
        try:
            region = self.regions[selected]
        except KeyError as exc:
            raise KeyError(f"Unknown catalog region: {selected}") from exc
        if require_enabled and not region.enabled:
            raise ValueError(f"Catalog region is disabled: {selected}")
        return region


def load_regions(path: str | Path = DEFAULT_REGIONS_PATH) -> RegionRegistry:
    """Load and strictly validate a region registry from JSON."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load catalog regions from {source}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("regions"), dict):
        raise ValueError("Region configuration must contain a regions object.")
    default = payload.get("default_region")
    if not isinstance(default, str):
        raise ValueError("Region configuration must contain default_region.")
    regions: dict[str, CatalogRegion] = {}
    for region_id, raw in payload["regions"].items():
        if not isinstance(region_id, str) or not isinstance(raw, dict):
            raise ValueError("Each region must be a named object.")
        bounds = raw.get("bounds")
        if not isinstance(bounds, dict):
            raise ValueError(f"Region {region_id} must contain bounds.")
        try:
            regions[region_id] = CatalogRegion(
                region_id=region_id,
                name=raw["name"],
                description=raw.get("description", ""),
                bounds=GeographicBounds(
                    bounds["min_latitude"], bounds["max_latitude"],
                    bounds["min_longitude"], bounds["max_longitude"],
                ),
                default_minimum_magnitude=raw["default_minimum_magnitude"],
                timezone=raw["timezone"],
                enabled=raw.get("enabled", True),
            )
        except KeyError as exc:
            raise ValueError(f"Region {region_id} is missing {exc.args[0]}.") from exc
    return RegionRegistry(default, regions)


def get_region(region_id: str | None = None, path: str | Path = DEFAULT_REGIONS_PATH) -> CatalogRegion:
    """Convenience lookup using the repository region configuration."""
    return load_regions(path).get(region_id)
