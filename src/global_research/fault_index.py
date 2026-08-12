"""Conservative spatial indexing for scalable mapped-fault proximity research."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from src.catalog.models import CatalogEvent
from src.global_research.faults import nearest_fault
from src.global_research.models import FaultAssociation, FaultTrace
from src.spatial.distance import validate_latitude, validate_longitude

KM_PER_LATITUDE_DEGREE = 110.574
KM_PER_LONGITUDE_DEGREE_EQUATOR = 111.320


@dataclass(frozen=True, slots=True)
class FaultGridIndex:
    """Bucket fault traces using a conservative search-radius-expanded envelope.

    Candidate lookup never replaces the exact great-circle point-to-segment distance.
    Each trace envelope is expanded by the configured association radius before being
    indexed, so an event only needs to query its own grid cell. Dateline-spanning or
    polar envelopes deliberately over-index rather than risk excluding a valid fault.
    """

    faults: tuple[FaultTrace, ...]
    search_radius_km: float
    cell_size_degrees: float
    _buckets: dict[tuple[int, int], tuple[int, ...]]
    _latitude_cells: int
    _longitude_cells: int

    @classmethod
    def build(
        cls,
        faults: Iterable[FaultTrace],
        *,
        search_radius_km: float,
        cell_size_degrees: float = 2.0,
    ) -> "FaultGridIndex":
        fault_tuple = tuple(faults)
        if not all(isinstance(fault, FaultTrace) for fault in fault_tuple):
            raise TypeError("faults must contain FaultTrace objects.")
        radius = _positive_finite(search_radius_km, "search_radius_km", allow_zero=True)
        cell_size = _positive_finite(cell_size_degrees, "cell_size_degrees")
        if cell_size > 30:
            raise ValueError("cell_size_degrees cannot exceed 30 degrees.")

        latitude_cells = math.ceil(180.0 / cell_size)
        longitude_cells = math.ceil(360.0 / cell_size)
        mutable: dict[tuple[int, int], set[int]] = {}

        for fault_index, fault in enumerate(fault_tuple):
            latitudes = [coordinate[0] for coordinate in fault.coordinates]
            longitudes = [coordinate[1] for coordinate in fault.coordinates]
            min_latitude = max(-90.0, min(latitudes) - radius / KM_PER_LATITUDE_DEGREE)
            max_latitude = min(90.0, max(latitudes) + radius / KM_PER_LATITUDE_DEGREE)
            latitude_indexes = _index_range(
                min_latitude,
                max_latitude,
                minimum=-90.0,
                cell_size=cell_size,
                cell_count=latitude_cells,
            )

            longitude_indexes = _expanded_longitude_indexes(
                longitudes,
                min_latitude=min_latitude,
                max_latitude=max_latitude,
                radius_km=radius,
                cell_size=cell_size,
                cell_count=longitude_cells,
            )
            for latitude_index in latitude_indexes:
                for longitude_index in longitude_indexes:
                    mutable.setdefault((latitude_index, longitude_index), set()).add(
                        fault_index
                    )

        buckets = {
            key: tuple(sorted(indexes))
            for key, indexes in mutable.items()
        }
        return cls(
            faults=fault_tuple,
            search_radius_km=radius,
            cell_size_degrees=cell_size,
            _buckets=buckets,
            _latitude_cells=latitude_cells,
            _longitude_cells=longitude_cells,
        )

    def candidates(self, latitude: float, longitude: float) -> tuple[FaultTrace, ...]:
        """Return fault traces whose expanded envelopes cover the event grid cell."""
        latitude = validate_latitude(latitude)
        longitude = validate_longitude(longitude)
        latitude_index = _cell_index(
            latitude,
            minimum=-90.0,
            cell_size=self.cell_size_degrees,
            cell_count=self._latitude_cells,
        )
        longitude_index = _cell_index(
            longitude,
            minimum=-180.0,
            cell_size=self.cell_size_degrees,
            cell_count=self._longitude_cells,
        )
        indexes = self._buckets.get((latitude_index, longitude_index), ())
        return tuple(self.faults[index] for index in indexes)


def associate_catalog_events_indexed(
    events: Iterable[CatalogEvent],
    index: FaultGridIndex,
) -> tuple[FaultAssociation, ...]:
    """Associate events using indexed candidates and exact final segment distances."""
    if not isinstance(index, FaultGridIndex):
        raise TypeError("index must be FaultGridIndex.")
    associations: list[FaultAssociation] = []
    for event in events:
        if not isinstance(event, CatalogEvent):
            raise TypeError("events must contain CatalogEvent objects.")
        association = nearest_fault(
            event_id=event.event_id,
            latitude=event.latitude,
            longitude=event.longitude,
            faults=index.candidates(event.latitude, event.longitude),
            max_distance_km=index.search_radius_km,
        )
        if association is not None:
            associations.append(association)
    return tuple(associations)


def _positive_finite(
    value: float,
    name: str,
    *,
    allow_zero: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (result == 0 and not allow_zero):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}.")
    return result


def _cell_index(
    value: float,
    *,
    minimum: float,
    cell_size: float,
    cell_count: int,
) -> int:
    raw = int(math.floor((value - minimum) / cell_size))
    return min(max(raw, 0), cell_count - 1)


def _index_range(
    minimum_value: float,
    maximum_value: float,
    *,
    minimum: float,
    cell_size: float,
    cell_count: int,
) -> tuple[int, ...]:
    first = _cell_index(
        minimum_value,
        minimum=minimum,
        cell_size=cell_size,
        cell_count=cell_count,
    )
    last = _cell_index(
        maximum_value,
        minimum=minimum,
        cell_size=cell_size,
        cell_count=cell_count,
    )
    return tuple(range(first, last + 1))


def _expanded_longitude_indexes(
    longitudes: list[float],
    *,
    min_latitude: float,
    max_latitude: float,
    radius_km: float,
    cell_size: float,
    cell_count: int,
) -> tuple[int, ...]:
    longitude_span = max(longitudes) - min(longitudes)
    if longitude_span > 180.0:
        return tuple(range(cell_count))

    extreme_latitude = max(abs(min_latitude), abs(max_latitude))
    cosine = math.cos(math.radians(min(extreme_latitude, 89.999999)))
    if cosine <= 1e-6:
        return tuple(range(cell_count))
    longitude_padding = radius_km / (KM_PER_LONGITUDE_DEGREE_EQUATOR * cosine)
    if longitude_padding >= 180.0:
        return tuple(range(cell_count))

    raw_minimum = min(longitudes) - longitude_padding
    raw_maximum = max(longitudes) + longitude_padding
    if raw_minimum < -180.0:
        western = _index_range(
            -180.0,
            raw_maximum,
            minimum=-180.0,
            cell_size=cell_size,
            cell_count=cell_count,
        )
        eastern = _index_range(
            raw_minimum + 360.0,
            180.0,
            minimum=-180.0,
            cell_size=cell_size,
            cell_count=cell_count,
        )
        return tuple(sorted(set(western + eastern)))
    if raw_maximum > 180.0:
        western = _index_range(
            raw_minimum,
            180.0,
            minimum=-180.0,
            cell_size=cell_size,
            cell_count=cell_count,
        )
        eastern = _index_range(
            -180.0,
            raw_maximum - 360.0,
            minimum=-180.0,
            cell_size=cell_size,
            cell_count=cell_count,
        )
        return tuple(sorted(set(western + eastern)))
    return _index_range(
        raw_minimum,
        raw_maximum,
        minimum=-180.0,
        cell_size=cell_size,
        cell_count=cell_count,
    )
