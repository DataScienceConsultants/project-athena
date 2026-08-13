"""PB2002 plate-boundary parsing, normalization, and proximity context."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from src.catalog.models import CatalogEvent
from src.global_research.faults import great_circle_segment_distance_km
from src.spatial.distance import validate_latitude, validate_longitude

PB2002_SOURCE = "Bird PB2002 plate boundary model"
PB2002_CITATION_KEY = "bird_pb2002"
PB2002_BOUNDARY_CLASSES = frozenset({"CCB", "CTF", "CRB", "OSR", "OTF", "OCB", "SUB"})
KM_PER_LATITUDE_DEGREE = 110.574
KM_PER_LONGITUDE_DEGREE_EQUATOR = 111.320


@dataclass(frozen=True, slots=True)
class PlateBoundaryStep:
    """One PB2002 digitization step with source-provided tectonic attributes."""

    step_id: str
    sequence_number: int
    boundary_id: str
    left_plate: str
    right_plate: str
    polarity: str
    boundary_class: str
    start: tuple[float, float]
    end: tuple[float, float]
    length_km: float
    azimuth_deg: float
    relative_velocity_mm_per_year: float
    relative_velocity_azimuth_deg: float
    divergent_velocity_mm_per_year: float
    right_lateral_velocity_mm_per_year: float
    elevation_m: float
    seafloor_age_ma: float | None
    in_orogen: bool
    source: str = PB2002_SOURCE

    def __post_init__(self) -> None:
        if not isinstance(self.step_id, str) or not self.step_id.strip():
            raise ValueError("step_id must be a nonempty string.")
        if isinstance(self.sequence_number, bool) or not isinstance(self.sequence_number, int):
            raise TypeError("sequence_number must be an integer.")
        if self.sequence_number <= 0:
            raise ValueError("sequence_number must be positive.")
        if not isinstance(self.boundary_id, str) or len(self.boundary_id) != 5:
            raise ValueError("boundary_id must contain the five-character PB2002 identifier.")
        if self.polarity not in {"-", "/", "\\"}:
            raise ValueError("polarity must be '-', '/', or '\\'.")
        if self.boundary_class not in PB2002_BOUNDARY_CLASSES:
            raise ValueError(f"Unknown PB2002 boundary class: {self.boundary_class!r}.")
        for name, value in (("left_plate", self.left_plate), ("right_plate", self.right_plate)):
            if not isinstance(value, str) or len(value) != 2:
                raise ValueError(f"{name} must be a two-character PB2002 plate identifier.")

        object.__setattr__(self, "step_id", self.step_id.strip())
        object.__setattr__(self, "start", _coordinate(self.start, "start"))
        object.__setattr__(self, "end", _coordinate(self.end, "end"))
        for name in (
            "length_km",
            "azimuth_deg",
            "relative_velocity_mm_per_year",
            "relative_velocity_azimuth_deg",
            "divergent_velocity_mm_per_year",
            "right_lateral_velocity_mm_per_year",
            "elevation_m",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.length_km <= 0:
            raise ValueError("length_km must be positive.")
        if self.seafloor_age_ma is not None:
            age = _finite(self.seafloor_age_ma, "seafloor_age_ma")
            if age < 0:
                raise ValueError("seafloor_age_ma cannot be negative.")
            object.__setattr__(self, "seafloor_age_ma", age)
        if not isinstance(self.in_orogen, bool):
            raise TypeError("in_orogen must be bool.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a nonempty string.")


@dataclass(frozen=True, slots=True)
class PlateBoundaryAssociation:
    """Nearest mapped PB2002 boundary context for one historical earthquake."""

    event_id: str
    step_id: str
    boundary_id: str
    left_plate: str
    right_plate: str
    boundary_class: str
    polarity: str
    distance_km: float
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a nonempty string.")
        object.__setattr__(self, "distance_km", _nonnegative(self.distance_km, "distance_km"))


@dataclass(frozen=True, slots=True)
class PlateBoundaryGridIndex:
    """Conservative grid index for exact event-to-boundary distance calculations."""

    steps: tuple[PlateBoundaryStep, ...]
    search_radius_km: float
    cell_size_degrees: float
    _buckets: dict[tuple[int, int], tuple[int, ...]]
    _latitude_cells: int
    _longitude_cells: int

    @classmethod
    def build(
        cls,
        steps: Iterable[PlateBoundaryStep],
        *,
        search_radius_km: float,
        cell_size_degrees: float = 2.0,
    ) -> "PlateBoundaryGridIndex":
        step_tuple = tuple(steps)
        if not all(isinstance(step, PlateBoundaryStep) for step in step_tuple):
            raise TypeError("steps must contain PlateBoundaryStep objects.")
        radius = _nonnegative(search_radius_km, "search_radius_km")
        cell_size = _finite(cell_size_degrees, "cell_size_degrees")
        if cell_size <= 0 or cell_size > 30:
            raise ValueError("cell_size_degrees must be greater than 0 and at most 30.")

        latitude_cells = math.ceil(180.0 / cell_size)
        longitude_cells = math.ceil(360.0 / cell_size)
        mutable: dict[tuple[int, int], set[int]] = {}

        for step_index, step in enumerate(step_tuple):
            latitudes = [step.start[0], step.end[0]]
            longitudes = [step.start[1], step.end[1]]
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
                    mutable.setdefault((latitude_index, longitude_index), set()).add(step_index)

        return cls(
            steps=step_tuple,
            search_radius_km=radius,
            cell_size_degrees=cell_size,
            _buckets={key: tuple(sorted(value)) for key, value in mutable.items()},
            _latitude_cells=latitude_cells,
            _longitude_cells=longitude_cells,
        )

    def candidates(self, latitude: float, longitude: float) -> tuple[PlateBoundaryStep, ...]:
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
        return tuple(self.steps[index] for index in indexes)


def parse_pb2002_steps(text: str) -> tuple[PlateBoundaryStep, ...]:
    """Parse Bird's PB2002_steps.dat text into immutable source-preserving steps."""
    if not isinstance(text, str):
        raise TypeError("text must be a string.")

    steps: list[PlateBoundaryStep] = []
    seen: set[int] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        tokens = line.split()
        if len(tokens) != 15:
            raise ValueError(
                f"PB2002 step line {line_number} has {len(tokens)} fields; expected 15."
            )
        sequence_number = int(tokens[0])
        if sequence_number in seen:
            raise ValueError(f"Duplicate PB2002 sequence number: {sequence_number}.")
        seen.add(sequence_number)

        boundary_id = tokens[1].lstrip(":")
        if len(boundary_id) != 5:
            raise ValueError(f"Invalid PB2002 boundary identifier: {boundary_id!r}.")
        boundary_class_token = tokens[14].lstrip(":")
        in_orogen = boundary_class_token.endswith("*")
        boundary_class = boundary_class_token.rstrip("*")
        raw_age = float(tokens[13])

        steps.append(
            PlateBoundaryStep(
                step_id=f"pb2002-step-{sequence_number:04d}",
                sequence_number=sequence_number,
                boundary_id=boundary_id,
                left_plate=boundary_id[:2],
                right_plate=boundary_id[3:],
                polarity=boundary_id[2],
                boundary_class=boundary_class,
                start=(float(tokens[3]), _normalize_longitude(float(tokens[2]))),
                end=(float(tokens[5]), _normalize_longitude(float(tokens[4]))),
                length_km=float(tokens[6]),
                azimuth_deg=float(tokens[7]),
                relative_velocity_mm_per_year=float(tokens[8]),
                relative_velocity_azimuth_deg=float(tokens[9]),
                divergent_velocity_mm_per_year=float(tokens[10]),
                right_lateral_velocity_mm_per_year=float(tokens[11]),
                elevation_m=float(tokens[12]),
                seafloor_age_ma=None if raw_age > 180 else raw_age,
                in_orogen=in_orogen,
            )
        )
    return tuple(sorted(steps, key=lambda step: step.sequence_number))


def plate_boundary_feature_collection(
    steps: Iterable[PlateBoundaryStep],
) -> dict[str, Any]:
    """Return GeoJSON suitable for visualization while preserving PB2002 attributes."""
    features = []
    for step in steps:
        if not isinstance(step, PlateBoundaryStep):
            raise TypeError("steps must contain PlateBoundaryStep objects.")
        features.append(
            {
                "type": "Feature",
                "id": step.step_id,
                "properties": {
                    "step_id": step.step_id,
                    "sequence_number": step.sequence_number,
                    "boundary_id": step.boundary_id,
                    "left_plate": step.left_plate,
                    "right_plate": step.right_plate,
                    "polarity": step.polarity,
                    "boundary_class": step.boundary_class,
                    "length_km": step.length_km,
                    "azimuth_deg": step.azimuth_deg,
                    "relative_velocity_mm_per_year": step.relative_velocity_mm_per_year,
                    "relative_velocity_azimuth_deg": step.relative_velocity_azimuth_deg,
                    "divergent_velocity_mm_per_year": step.divergent_velocity_mm_per_year,
                    "right_lateral_velocity_mm_per_year": step.right_lateral_velocity_mm_per_year,
                    "elevation_m": step.elevation_m,
                    "seafloor_age_ma": step.seafloor_age_ma,
                    "in_orogen": step.in_orogen,
                    "source": step.source,
                    "citation_key": PB2002_CITATION_KEY,
                    "relationship_semantics": (
                        "Plate-boundary geographic and kinematic context from PB2002; "
                        "not earthquake causality or prediction."
                    ),
                },
                "geometry": _display_geometry(step.start, step.end),
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "PB2002 plate boundary steps",
        "features": features,
        "athena": {
            "source": PB2002_SOURCE,
            "citation_key": PB2002_CITATION_KEY,
            "report_is_nonpredictive": True,
        },
    }


def distance_to_plate_boundary_step_km(
    latitude: float,
    longitude: float,
    step: PlateBoundaryStep,
) -> float:
    if not isinstance(step, PlateBoundaryStep):
        raise TypeError("step must be PlateBoundaryStep.")
    return great_circle_segment_distance_km(latitude, longitude, step.start, step.end)


def nearest_plate_boundary(
    *,
    event_id: str,
    latitude: float,
    longitude: float,
    steps: Iterable[PlateBoundaryStep],
    max_distance_km: float | None = None,
) -> PlateBoundaryAssociation | None:
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id must be a nonempty string.")
    latitude = validate_latitude(latitude)
    longitude = validate_longitude(longitude)
    limit = None if max_distance_km is None else _nonnegative(max_distance_km, "max_distance_km")

    measured = [
        (distance_to_plate_boundary_step_km(latitude, longitude, step), step)
        for step in steps
    ]
    if not measured:
        return None
    distance, step = min(measured, key=lambda item: (item[0], item[1].step_id))
    if limit is not None and distance > limit:
        return None
    return PlateBoundaryAssociation(
        event_id=event_id.strip(),
        step_id=step.step_id,
        boundary_id=step.boundary_id,
        left_plate=step.left_plate,
        right_plate=step.right_plate,
        boundary_class=step.boundary_class,
        polarity=step.polarity,
        distance_km=distance,
        source=step.source,
    )


def associate_catalog_events_with_plate_boundaries(
    events: Iterable[CatalogEvent],
    index: PlateBoundaryGridIndex,
) -> tuple[PlateBoundaryAssociation, ...]:
    """Attach nearest PB2002 boundary context within the configured radius."""
    if not isinstance(index, PlateBoundaryGridIndex):
        raise TypeError("index must be PlateBoundaryGridIndex.")
    associations: list[PlateBoundaryAssociation] = []
    for event in events:
        if not isinstance(event, CatalogEvent):
            raise TypeError("events must contain CatalogEvent objects.")
        association = nearest_plate_boundary(
            event_id=event.event_id,
            latitude=event.latitude,
            longitude=event.longitude,
            steps=index.candidates(event.latitude, event.longitude),
            max_distance_km=index.search_radius_km,
        )
        if association is not None:
            associations.append(association)
    return tuple(associations)


def _coordinate(value: tuple[float, float], name: str) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"{name} must be a latitude/longitude pair.")
    return validate_latitude(value[0]), validate_longitude(value[1])


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be nonnegative.")
    return result


def _normalize_longitude(value: float) -> float:
    value = _finite(value, "longitude")
    if -180.0 <= value <= 180.0:
        return validate_longitude(value)
    normalized = ((value + 180.0) % 360.0) - 180.0
    return validate_longitude(normalized)


def _display_geometry(
    start: tuple[float, float],
    end: tuple[float, float],
) -> dict[str, Any]:
    start_lat, start_lon = start
    end_lat, end_lon = end
    if abs(end_lon - start_lon) <= 180.0:
        return {
            "type": "LineString",
            "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
        }

    if start_lon >= 0 and end_lon < 0:
        adjusted_end_lon = end_lon + 360.0
        crossing_lon = 180.0
        opposite_lon = -180.0
    else:
        adjusted_end_lon = end_lon - 360.0
        crossing_lon = -180.0
        opposite_lon = 180.0
    fraction = (crossing_lon - start_lon) / (adjusted_end_lon - start_lon)
    crossing_lat = start_lat + fraction * (end_lat - start_lat)
    return {
        "type": "MultiLineString",
        "coordinates": [
            [[start_lon, start_lat], [crossing_lon, crossing_lat]],
            [[opposite_lon, crossing_lat], [end_lon, end_lat]],
        ],
    }


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
