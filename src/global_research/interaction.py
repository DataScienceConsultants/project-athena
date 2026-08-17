"""Retrospective earthquake-interaction features for Athena global research.

This module measures temporal and geographic association patterns in the frozen
large-event catalog. It does not calculate Coulomb stress transfer, dynamic
wave stresses, or causal earthquake triggering.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from src.catalog.models import CatalogEvent
from src.global_research.plate_boundaries import PlateBoundaryAssociation
from src.spatial.distance import haversine_distance

MOMENT_MAGNITUDE_TYPES = frozenset({"mw", "mww", "mwc", "mwb", "mwr", "mwp"})
DEFAULT_TIME_WINDOWS_DAYS = (1.0, 7.0, 30.0, 90.0, 365.0)
DEFAULT_DISTANCE_WINDOWS_KM = (100.0, 250.0, 500.0, 1000.0, 2000.0)
INTERACTION_STUDY_ID = "global-m6-1976-2025-interaction-v1"


@dataclass(frozen=True, slots=True)
class InteractionPair:
    """One later M6+ event observed near a source event in space and time."""

    source_event_id: str
    target_event_id: str
    source_time: datetime
    target_time: datetime
    lag_days: float
    distance_km: float
    source_magnitude: float
    target_magnitude: float
    source_magnitude_type: str | None
    target_magnitude_type: str | None
    source_moment_nm: float | None
    target_moment_nm: float | None
    source_boundary_id: str | None
    target_boundary_id: str | None
    source_left_plate: str | None
    source_right_plate: str | None
    target_left_plate: str | None
    target_right_plate: str | None
    source_boundary_class: str | None
    target_boundary_class: str | None
    same_plate_pair: bool | None
    same_boundary_id: bool | None
    same_boundary_class: bool | None


@dataclass(frozen=True, slots=True)
class InteractionWindowObservation:
    """Matched pre/post counts around one source event and one window definition."""

    source_event_id: str
    source_time: datetime
    source_magnitude: float
    source_magnitude_type: str | None
    source_moment_nm: float | None
    source_boundary_id: str | None
    source_left_plate: str | None
    source_right_plate: str | None
    source_boundary_class: str | None
    time_window_days: float
    distance_window_km: float
    full_pre_window: bool
    full_post_window: bool
    pre_count_all: int
    post_count_all: int
    pre_count_same_plate_pair: int
    post_count_same_plate_pair: int
    pre_count_same_boundary: int
    post_count_same_boundary: int

    @property
    def edge_eligible(self) -> bool:
        return self.full_pre_window and self.full_post_window

    @property
    def source_has_plate_context(self) -> bool:
        return self.source_boundary_id is not None


def seismic_moment_nm(
    magnitude: float | None,
    magnitude_type: str | None,
) -> float | None:
    """Return scalar seismic moment for an Mw-family magnitude, in N m.

    Uses the Hanks-Kanamori moment-magnitude relation in SI units. Other
    magnitude scales intentionally return ``None`` rather than being silently
    converted to Mw.
    """
    if magnitude is None or magnitude_type is None:
        return None
    if isinstance(magnitude, bool) or not isinstance(magnitude, (int, float)):
        raise TypeError("magnitude must be numeric or None.")
    value = float(magnitude)
    if not math.isfinite(value):
        raise ValueError("magnitude must be finite.")
    if magnitude_type.strip().lower() not in MOMENT_MAGNITUDE_TYPES:
        return None
    return 10.0 ** (1.5 * value + 9.1)


def plate_pair_key(
    association: PlateBoundaryAssociation | None,
) -> tuple[str, str] | None:
    """Return an orientation-independent PB2002 plate-pair key."""
    if association is None:
        return None
    return tuple(sorted((association.left_plate, association.right_plate)))


def build_interaction_pairs(
    events: Iterable[CatalogEvent],
    plate_associations: Iterable[PlateBoundaryAssociation],
    *,
    minimum_magnitude: float = 6.0,
    max_lag_days: float = 365.0,
    max_distance_km: float = 2000.0,
) -> tuple[InteractionPair, ...]:
    """Build later-event pair features within configured time and distance limits."""
    minimum = _finite(minimum_magnitude, "minimum_magnitude")
    lag_limit = _positive(max_lag_days, "max_lag_days")
    distance_limit = _positive(max_distance_km, "max_distance_km")
    catalog = _eligible_events(events, minimum)
    context = _plate_context_map(plate_associations)
    times = [event.time for event in catalog]
    pairs: list[InteractionPair] = []

    for index, source in enumerate(catalog):
        end_time = source.time + timedelta(days=lag_limit)
        upper = bisect_right(times, end_time, lo=index + 1)
        source_context = context.get(source.event_id)
        source_pair = plate_pair_key(source_context)

        for target in catalog[index + 1 : upper]:
            lag_seconds = (target.time - source.time).total_seconds()
            if lag_seconds <= 0:
                continue
            distance = haversine_distance(
                source.latitude,
                source.longitude,
                target.latitude,
                target.longitude,
            )
            if distance > distance_limit:
                continue
            target_context = context.get(target.event_id)
            target_pair = plate_pair_key(target_context)
            pairs.append(
                InteractionPair(
                    source_event_id=source.event_id,
                    target_event_id=target.event_id,
                    source_time=source.time,
                    target_time=target.time,
                    lag_days=lag_seconds / 86400.0,
                    distance_km=distance,
                    source_magnitude=float(source.magnitude),
                    target_magnitude=float(target.magnitude),
                    source_magnitude_type=source.magnitude_type,
                    target_magnitude_type=target.magnitude_type,
                    source_moment_nm=seismic_moment_nm(
                        source.magnitude, source.magnitude_type
                    ),
                    target_moment_nm=seismic_moment_nm(
                        target.magnitude, target.magnitude_type
                    ),
                    source_boundary_id=_field(source_context, "boundary_id"),
                    target_boundary_id=_field(target_context, "boundary_id"),
                    source_left_plate=_field(source_context, "left_plate"),
                    source_right_plate=_field(source_context, "right_plate"),
                    target_left_plate=_field(target_context, "left_plate"),
                    target_right_plate=_field(target_context, "right_plate"),
                    source_boundary_class=_field(source_context, "boundary_class"),
                    target_boundary_class=_field(target_context, "boundary_class"),
                    same_plate_pair=_same_optional(source_pair, target_pair),
                    same_boundary_id=_same_context_field(
                        source_context, target_context, "boundary_id"
                    ),
                    same_boundary_class=_same_context_field(
                        source_context, target_context, "boundary_class"
                    ),
                )
            )
    return tuple(pairs)


def build_interaction_windows(
    events: Iterable[CatalogEvent],
    plate_associations: Iterable[PlateBoundaryAssociation],
    *,
    profile_start: datetime,
    profile_end: datetime,
    minimum_magnitude: float = 6.0,
    time_windows_days: Iterable[float] = DEFAULT_TIME_WINDOWS_DAYS,
    distance_windows_km: Iterable[float] = DEFAULT_DISTANCE_WINDOWS_KM,
) -> tuple[InteractionWindowObservation, ...]:
    """Build matched pre/post counts without treating overlapping windows as independent."""
    minimum = _finite(minimum_magnitude, "minimum_magnitude")
    time_windows = _positive_windows(time_windows_days, "time_windows_days")
    distance_windows = _positive_windows(distance_windows_km, "distance_windows_km")
    if profile_start.tzinfo is None or profile_start.utcoffset() is None:
        raise ValueError("profile_start must be timezone-aware.")
    if profile_end.tzinfo is None or profile_end.utcoffset() is None:
        raise ValueError("profile_end must be timezone-aware.")
    if profile_start >= profile_end:
        raise ValueError("profile_start must be earlier than profile_end.")

    catalog = _eligible_events(events, minimum)
    context = _plate_context_map(plate_associations)
    times = [event.time for event in catalog]
    max_window = max(time_windows)
    observations: list[InteractionWindowObservation] = []

    for source_index, source in enumerate(catalog):
        lower_time = source.time - timedelta(days=max_window)
        upper_time = source.time + timedelta(days=max_window)
        lower = bisect_left(times, lower_time)
        upper = bisect_right(times, upper_time)
        source_context = context.get(source.event_id)
        source_pair = plate_pair_key(source_context)
        counts = {
            (time_window, distance_window): [0, 0, 0, 0, 0, 0]
            for time_window in time_windows
            for distance_window in distance_windows
        }

        for candidate_index in range(lower, upper):
            if candidate_index == source_index:
                continue
            candidate = catalog[candidate_index]
            lag_days = (candidate.time - source.time).total_seconds() / 86400.0
            if lag_days == 0 or abs(lag_days) > max_window:
                continue
            distance = haversine_distance(
                source.latitude,
                source.longitude,
                candidate.latitude,
                candidate.longitude,
            )
            if distance > max(distance_windows):
                continue

            candidate_context = context.get(candidate.event_id)
            candidate_pair = plate_pair_key(candidate_context)
            same_pair = (
                source_pair is not None
                and candidate_pair is not None
                and source_pair == candidate_pair
            )
            same_boundary = (
                source_context is not None
                and candidate_context is not None
                and source_context.boundary_id == candidate_context.boundary_id
            )
            side_offset = 0 if lag_days < 0 else 1
            for time_window in time_windows:
                if abs(lag_days) > time_window:
                    continue
                for distance_window in distance_windows:
                    if distance > distance_window:
                        continue
                    bucket = counts[(time_window, distance_window)]
                    bucket[side_offset] += 1
                    if same_pair:
                        bucket[2 + side_offset] += 1
                    if same_boundary:
                        bucket[4 + side_offset] += 1

        for time_window in time_windows:
            span = timedelta(days=time_window)
            full_pre = source.time - span >= profile_start
            full_post = source.time + span <= profile_end
            for distance_window in distance_windows:
                bucket = counts[(time_window, distance_window)]
                observations.append(
                    InteractionWindowObservation(
                        source_event_id=source.event_id,
                        source_time=source.time,
                        source_magnitude=float(source.magnitude),
                        source_magnitude_type=source.magnitude_type,
                        source_moment_nm=seismic_moment_nm(
                            source.magnitude, source.magnitude_type
                        ),
                        source_boundary_id=_field(source_context, "boundary_id"),
                        source_left_plate=_field(source_context, "left_plate"),
                        source_right_plate=_field(source_context, "right_plate"),
                        source_boundary_class=_field(source_context, "boundary_class"),
                        time_window_days=time_window,
                        distance_window_km=distance_window,
                        full_pre_window=full_pre,
                        full_post_window=full_post,
                        pre_count_all=bucket[0],
                        post_count_all=bucket[1],
                        pre_count_same_plate_pair=bucket[2],
                        post_count_same_plate_pair=bucket[3],
                        pre_count_same_boundary=bucket[4],
                        post_count_same_boundary=bucket[5],
                    )
                )
    return tuple(observations)


def summarize_interaction_windows(
    observations: Iterable[InteractionWindowObservation],
) -> dict[str, Any]:
    """Aggregate edge-complete pre/post counts as descriptive, noninferential statistics."""
    rows = tuple(observations)
    if not all(isinstance(row, InteractionWindowObservation) for row in rows):
        raise TypeError("observations must contain InteractionWindowObservation objects.")

    keys = sorted({(row.time_window_days, row.distance_window_km) for row in rows})
    statistics = []
    for time_window, distance_window in keys:
        eligible = [
            row
            for row in rows
            if row.time_window_days == time_window
            and row.distance_window_km == distance_window
            and row.edge_eligible
        ]
        plate_eligible = [row for row in eligible if row.source_has_plate_context]
        statistics.append(
            {
                "time_window_days": time_window,
                "distance_window_km": distance_window,
                "eligible_source_count": len(eligible),
                "plate_context_source_count": len(plate_eligible),
                **_count_summary(eligible, "all"),
                **_count_summary(plate_eligible, "same_plate_pair"),
                **_count_summary(plate_eligible, "same_boundary"),
            }
        )

    return {
        "schema_version": 1,
        "study_id": INTERACTION_STUDY_ID,
        "research_mode": "retrospective_descriptive",
        "inference_status": "descriptive_only_no_independence_assumption",
        "report_is_nonpredictive": True,
        "window_statistic_count": len(statistics),
        "statistics": statistics,
    }


def pair_to_record(pair: InteractionPair) -> dict[str, Any]:
    """Return a CSV-safe record for a prepared interaction pair."""
    record = asdict(pair)
    record["source_time"] = pair.source_time.isoformat()
    record["target_time"] = pair.target_time.isoformat()
    return record


def window_to_record(observation: InteractionWindowObservation) -> dict[str, Any]:
    """Return a CSV-safe record for one matched pre/post observation."""
    record = asdict(observation)
    record["source_time"] = observation.source_time.isoformat()
    record["edge_eligible"] = observation.edge_eligible
    record["source_has_plate_context"] = observation.source_has_plate_context
    return record


def _eligible_events(
    events: Iterable[CatalogEvent], minimum_magnitude: float
) -> tuple[CatalogEvent, ...]:
    catalog = tuple(events)
    if not all(isinstance(event, CatalogEvent) for event in catalog):
        raise TypeError("events must contain CatalogEvent objects.")
    selected = [
        event
        for event in catalog
        if event.magnitude is not None and float(event.magnitude) >= minimum_magnitude
    ]
    return tuple(sorted(selected, key=lambda event: (event.time, event.event_id)))


def _plate_context_map(
    associations: Iterable[PlateBoundaryAssociation],
) -> dict[str, PlateBoundaryAssociation]:
    result: dict[str, PlateBoundaryAssociation] = {}
    for association in associations:
        if not isinstance(association, PlateBoundaryAssociation):
            raise TypeError("plate_associations must contain PlateBoundaryAssociation objects.")
        if association.event_id in result:
            raise ValueError(f"Duplicate plate context for event: {association.event_id}")
        result[association.event_id] = association
    return result


def _count_summary(
    rows: Iterable[InteractionWindowObservation], relationship: str
) -> dict[str, Any]:
    data = tuple(rows)
    if relationship == "all":
        pre = sum(row.pre_count_all for row in data)
        post = sum(row.post_count_all for row in data)
        prefix = "all"
    elif relationship == "same_plate_pair":
        pre = sum(row.pre_count_same_plate_pair for row in data)
        post = sum(row.post_count_same_plate_pair for row in data)
        prefix = "same_plate_pair"
    elif relationship == "same_boundary":
        pre = sum(row.pre_count_same_boundary for row in data)
        post = sum(row.post_count_same_boundary for row in data)
        prefix = "same_boundary"
    else:
        raise ValueError(f"Unknown relationship: {relationship}")
    return {
        f"pre_{prefix}_count": pre,
        f"post_{prefix}_count": post,
        f"post_minus_pre_{prefix}": post - pre,
        f"post_pre_{prefix}_ratio": None if pre == 0 else post / pre,
    }


def _same_optional(left: object | None, right: object | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _same_context_field(
    left: PlateBoundaryAssociation | None,
    right: PlateBoundaryAssociation | None,
    field_name: str,
) -> bool | None:
    if left is None or right is None:
        return None
    return getattr(left, field_name) == getattr(right, field_name)


def _field(
    association: PlateBoundaryAssociation | None,
    field_name: str,
) -> str | None:
    return None if association is None else str(getattr(association, field_name))


def _positive_windows(values: Iterable[float], name: str) -> tuple[float, ...]:
    normalized = tuple(sorted({_positive(value, name) for value in values}))
    if not normalized:
        raise ValueError(f"{name} must contain at least one value.")
    return normalized


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} values must be positive.")
    return result


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result
