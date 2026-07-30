"""Built-in Caribbean catalog regions."""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

from src.catalog.models import GeographicBounds


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    name: str
    bounds: GeographicBounds
    default_minimum_magnitude: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key must be a nonempty string.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a nonempty string.")
        if not isinstance(self.bounds, GeographicBounds):
            raise TypeError("bounds must be GeographicBounds.")
        if isinstance(self.default_minimum_magnitude, bool) or not isinstance(self.default_minimum_magnitude, (int, float)):
            raise TypeError("default_minimum_magnitude must be numeric, not boolean.")
        if not math.isfinite(float(self.default_minimum_magnitude)):
            raise ValueError("default_minimum_magnitude must be finite.")
        object.__setattr__(self, "key", self.key.strip().lower())
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "default_minimum_magnitude", float(self.default_minimum_magnitude))

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.bounds.contains(latitude, longitude)


PUERTO_RICO = Region("puerto_rico", "Puerto Rico", GeographicBounds(17.0, 20.0, -69.0, -63.5), 1.0)
VIRGIN_ISLANDS = Region("virgin_islands", "Virgin Islands", GeographicBounds(17.0, 19.5, -65.5, -62.0), 1.0)
MONA_PASSAGE = Region("mona_passage", "Mona Passage", GeographicBounds(17.0, 20.0, -69.5, -66.5), 1.0)
DOMINICAN_REPUBLIC = Region("dominican_republic", "Dominican Republic", GeographicBounds(17.0, 20.5, -72.5, -68.0), 1.5)
LESSER_ANTILLES = Region("lesser_antilles", "Lesser Antilles", GeographicBounds(10.0, 19.5, -64.5, -58.0), 1.5)
CARIBBEAN = Region("caribbean", "Caribbean", GeographicBounds(9.0, 23.0, -89.0, -58.0), 2.0)

REGIONS: Mapping[str, Region] = MappingProxyType({region.key: region for region in (
    PUERTO_RICO, VIRGIN_ISLANDS, MONA_PASSAGE, DOMINICAN_REPUBLIC, LESSER_ANTILLES, CARIBBEAN,
)})


def get_region(key: str = PUERTO_RICO.key) -> Region:
    """Look up a built-in region case-insensitively with whitespace trimmed."""
    if not isinstance(key, str):
        raise TypeError("region key must be a string.")
    normalized = key.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return REGIONS[normalized]
    except KeyError as exc:
        raise KeyError(f"Unknown catalog region: {key!r}") from exc


# Compatibility names retained for the first catalog implementation.
CatalogRegion = Region

@dataclass(frozen=True, slots=True)
class RegionRegistry:
    default_region: str = PUERTO_RICO.key
    regions: Mapping[str, Region] = REGIONS

    def get(self, region_id: str | None = None, *, require_enabled: bool = True) -> Region:
        del require_enabled
        return get_region(region_id or self.default_region)


def load_regions(path=None) -> RegionRegistry:
    """Return built-ins; *path* remains accepted for API compatibility."""
    del path
    return RegionRegistry()
