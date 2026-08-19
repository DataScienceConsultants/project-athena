"""Retrospective along-boundary earthquake interaction measurements.

This module compares ordinary epicentral distance with shortest mapped distance
along the exact endpoint-connected Bird PB2002 boundary network. It measures
historical association patterns only. A mapped graph route is not a rupture,
stress-transfer, energy-transfer, or causal path.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Iterable

from src.catalog.models import CatalogEvent
from src.global_research.interaction import DEFAULT_SOURCE_MAGNITUDE_THRESHOLDS
from src.global_research.plate_boundaries import PlateBoundaryAssociation
from src.global_research.plate_boundary_network import (
    PlateBoundaryGraph,
    PlateBoundaryProjection,
    project_catalog_events_to_boundaries,
)
from src.spatial.distance import haversine_distance

ALONG_BOUNDARY_STUDY_ID = "global-m6-1976-2025-along-boundary-v1"
DEFAULT_ALONG_BOUNDARY_WINDOWS_KM = (100.0, 250.0, 500.0, 1000.0, 2000.0)
DEFAULT_ALONG_BOUNDARY_TIME_WINDOWS_DAYS = (1.0, 7.0, 30.0, 90.0, 365.0)
ROUTE_STATUS_AVAILABLE = "available"
ROUTE_STATUS_MISSING_PROJECTION = "missing_projection"
ROUTE_STATUS_DIFFERENT_PLATE_PAIR = "different_plate_pair"
ROUTE_STATUS_DISCONNECTED = "disconnected_same_plate_pair_network"


@dataclass(frozen=True, slots=True)
class AlongBoundaryPair:
    """One chronological M6+ pair prepared for along-boundary comparison."""

    earlier_event_id: str
    later_event_id: str
    earlier_time: datetime
    later_time: datetime
    lag_days: float
    radial_distance_km: float
    earlier_magnitude: float
    later_magnitude: float
    earlier_step_id: str | None
    later_step_id: str | None
    earlier_boundary_id: str | None
    later_boundary_id: str | None
    earlier_left_plate: str | None
    earlier_right_plate: str | None
    later_left_plate: str | None
    later_right_plate: str | None
    earlier_boundary_class: str | None
    later_boundary_class: str | None
    same_plate_pair: bool | None
    same_boundary_id: bool | None
    route_status: str
    along_boundary_distance_km: float | None
    within_along_boundary_limit: bool


@dataclass(frozen=True, slots=True)
class AlongBoundaryWindowObservation:
    """Matched pre/post counts for one source event and one study window."""

    source_event_id: str
    source_time: datetime
    source_magnitude: float
    source_magnitude_type: str | None
    source_step_id: str
    source_boundary_id: str
    source_left_plate: str
    source_right_plate: str
    source_boundary_class: str
    source_distance_to_boundary_km: float
    time_window_days: float
    distance_window_km: float
    full_pre_window: bool
    full_post_window: bool
    pre_count_along_boundary: int
    post_count_along_boundary: int
    pre_count_routed_radial: int
    post_count_routed_radial: int

    @property
    def edge_eligible(self) -> bool:
        return self.full_pre_window and self.full_post_window


def build_along_boundary_pairs(
    events: Iterable[CatalogEvent],
    associations: Iterable[PlateBoundaryAssociation],
    graph: PlateBoundaryGraph,
    *,
    minimum_magnitude: float = 6.0,
    max_lag_days: float = 365.0,
    max_along_boundary_distance_km: float = 2000.0,
    max_prepared_boundary_offset_km: float = 500.0,
) -> tuple[AlongBoundaryPair, ...]:
    """Build chronological candidate pairs and route same-plate-pair pairs.

    Candidate radial distance is conservatively bounded by the requested maximum
    along-boundary distance plus two prepared event-to-boundary offsets. That
    envelope prevents a valid <=max along-boundary route from being pruned only
    because the two epicenters sit away from their mapped boundary projections.
    """

    if not isinstance(graph, PlateBoundaryGraph):
        raise TypeError("graph must be PlateBoundaryGraph.")
    minimum = _finite(minimum_magnitude, "minimum_magnitude")
    lag_limit = _positive(max_lag_days, "max_lag_days")
    along_limit = _positive(
        max_along_boundary_distance_km,
        "max_along_boundary_distance_km",
    )
    offset_limit = _nonnegative(
        max_prepared_boundary_offset_km,
        "max_prepared_boundary_offset_km",
    )
    radial_envelope = along_limit + (2.0 * offset_limit)
    catalog = tuple(
        sorted(
            (
                event
                for event in events
                if isinstance(event, CatalogEvent)
                and event.magnitude is not None
                and float(event.magnitude) >= minimum
            ),
            key=lambda event: (event.time, event.event_id),
        )
    )
    if not all(isinstance(event, CatalogEvent) for event in catalog):
        raise TypeError("events must contain CatalogEvent objects.")

    association_tuple = tuple(associations)
    if not all(
        isinstance(item, PlateBoundaryAssociation) for item in association_tuple
    ):
        raise TypeError(
            "associations must contain PlateBoundaryAssociation objects."
        )
    projections = project_catalog_events_to_boundaries(
        catalog,
        association_tuple,
        graph,
    )
    projection_map = {item.event_id: item for item in projections}
    times = [event.time for event in catalog]
    distance_cache: dict[str, tuple[float, ...]] = {}
    pairs: list[AlongBoundaryPair] = []

    for index, earlier in enumerate(catalog):
        upper = bisect_right(
            times,
            earlier.time + timedelta(days=lag_limit),
            lo=index + 1,
        )
        earlier_projection = projection_map.get(earlier.event_id)
        for later in catalog[index + 1 : upper]:
            lag_days = (later.time - earlier.time).total_seconds() / 86400.0
            if lag_days <= 0:
                continue
            radial_distance = haversine_distance(
                earlier.latitude,
                earlier.longitude,
                later.latitude,
                later.longitude,
            )
            if radial_distance > radial_envelope:
                continue

            later_projection = projection_map.get(later.event_id)
            route_status, along_distance, same_pair = _route_pair(
                earlier_projection,
                later_projection,
                graph,
                distance_cache,
            )
            same_boundary = _same_boundary(
                earlier_projection,
                later_projection,
            )
            pairs.append(
                AlongBoundaryPair(
                    earlier_event_id=earlier.event_id,
                    later_event_id=later.event_id,
                    earlier_time=earlier.time,
                    later_time=later.time,
                    lag_days=lag_days,
                    radial_distance_km=radial_distance,
                    earlier_magnitude=float(earlier.magnitude),
                    later_magnitude=float(later.magnitude),
                    earlier_step_id=_projection_field(
                        earlier_projection, "step_id"
                    ),
                    later_step_id=_projection_field(later_projection, "step_id"),
                    earlier_boundary_id=_projection_field(
                        earlier_projection, "boundary_id"
                    ),
                    later_boundary_id=_projection_field(
                        later_projection, "boundary_id"
                    ),
                    earlier_left_plate=_projection_field(
                        earlier_projection, "left_plate"
                    ),
                    earlier_right_plate=_projection_field(
                        earlier_projection, "right_plate"
                    ),
                    later_left_plate=_projection_field(
                        later_projection, "left_plate"
                    ),
                    later_right_plate=_projection_field(
                        later_projection, "right_plate"
                    ),
                    earlier_boundary_class=_projection_field(
                        earlier_projection, "boundary_class"
                    ),
                    later_boundary_class=_projection_field(
                        later_projection, "boundary_class"
                    ),
                    same_plate_pair=same_pair,
                    same_boundary_id=same_boundary,
                    route_status=route_status,
                    along_boundary_distance_km=along_distance,
                    within_along_boundary_limit=(
                        along_distance is not None and along_distance <= along_limit
                    ),
                )
            )
    return tuple(pairs)


def build_along_boundary_windows(
    events: Iterable[CatalogEvent],
    associations: Iterable[PlateBoundaryAssociation],
    graph: PlateBoundaryGraph,
    pairs: Iterable[AlongBoundaryPair],
    *,
    profile_start: datetime,
    profile_end: datetime,
    minimum_magnitude: float = 6.0,
    time_windows_days: Iterable[float] = DEFAULT_ALONG_BOUNDARY_TIME_WINDOWS_DAYS,
    distance_windows_km: Iterable[float] = DEFAULT_ALONG_BOUNDARY_WINDOWS_KM,
) -> tuple[AlongBoundaryWindowObservation, ...]:
    """Build matched pre/post windows using routed boundary and radial distance."""

    if not isinstance(graph, PlateBoundaryGraph):
        raise TypeError("graph must be PlateBoundaryGraph.")
    minimum = _finite(minimum_magnitude, "minimum_magnitude")
    time_windows = _positive_windows(time_windows_days, "time_windows_days")
    distance_windows = _positive_windows(distance_windows_km, "distance_windows_km")
    _validate_profile_window(profile_start, profile_end)

    catalog = tuple(
        sorted(
            (
                event
                for event in events
                if isinstance(event, CatalogEvent)
                and event.magnitude is not None
                and float(event.magnitude) >= minimum
            ),
            key=lambda event: (event.time, event.event_id),
        )
    )
    association_tuple = tuple(associations)
    projections = project_catalog_events_to_boundaries(
        catalog,
        association_tuple,
        graph,
    )
    projection_map = {item.event_id: item for item in projections}
    pair_tuple = tuple(pairs)
    if not all(isinstance(item, AlongBoundaryPair) for item in pair_tuple):
        raise TypeError("pairs must contain AlongBoundaryPair objects.")

    incident: dict[str, list[AlongBoundaryPair]] = defaultdict(list)
    for pair in pair_tuple:
        if pair.route_status != ROUTE_STATUS_AVAILABLE:
            continue
        if pair.along_boundary_distance_km is None:
            continue
        incident[pair.earlier_event_id].append(pair)
        incident[pair.later_event_id].append(pair)

    max_time = max(time_windows)
    max_distance = max(distance_windows)
    observations: list[AlongBoundaryWindowObservation] = []
    for source in catalog:
        projection = projection_map.get(source.event_id)
        if projection is None:
            continue
        counts = {
            (time_window, distance_window): [0, 0, 0, 0]
            for time_window in time_windows
            for distance_window in distance_windows
        }
        for pair in incident.get(source.event_id, ()):
            if pair.lag_days > max_time:
                continue
            if (
                pair.along_boundary_distance_km is None
                or min(pair.along_boundary_distance_km, pair.radial_distance_km)
                > max_distance
            ):
                continue
            is_post = pair.earlier_event_id == source.event_id
            side_offset = 1 if is_post else 0
            for time_window in time_windows:
                if pair.lag_days > time_window:
                    continue
                for distance_window in distance_windows:
                    bucket = counts[(time_window, distance_window)]
                    if pair.along_boundary_distance_km <= distance_window:
                        bucket[side_offset] += 1
                    if pair.radial_distance_km <= distance_window:
                        bucket[2 + side_offset] += 1

        for time_window in time_windows:
            span = timedelta(days=time_window)
            full_pre = source.time - span >= profile_start
            full_post = source.time + span <= profile_end
            for distance_window in distance_windows:
                bucket = counts[(time_window, distance_window)]
                observations.append(
                    AlongBoundaryWindowObservation(
                        source_event_id=source.event_id,
                        source_time=source.time,
                        source_magnitude=float(source.magnitude),
                        source_magnitude_type=source.magnitude_type,
                        source_step_id=projection.step_id,
                        source_boundary_id=projection.boundary_id,
                        source_left_plate=projection.left_plate,
                        source_right_plate=projection.right_plate,
                        source_boundary_class=projection.boundary_class,
                        source_distance_to_boundary_km=(
                            projection.distance_to_boundary_km
                        ),
                        time_window_days=time_window,
                        distance_window_km=distance_window,
                        full_pre_window=full_pre,
                        full_post_window=full_post,
                        pre_count_along_boundary=bucket[0],
                        post_count_along_boundary=bucket[1],
                        pre_count_routed_radial=bucket[2],
                        post_count_routed_radial=bucket[3],
                    )
                )
    return tuple(observations)


def summarize_along_boundary_study(
    pairs: Iterable[AlongBoundaryPair],
    observations: Iterable[AlongBoundaryWindowObservation],
    *,
    source_magnitude_thresholds: Iterable[float] = (
        DEFAULT_SOURCE_MAGNITUDE_THRESHOLDS
    ),
) -> dict[str, Any]:
    """Return descriptive magnitude-stratified along-vs-radial summaries."""

    pair_rows = tuple(pairs)
    window_rows = tuple(observations)
    if not all(isinstance(item, AlongBoundaryPair) for item in pair_rows):
        raise TypeError("pairs must contain AlongBoundaryPair objects.")
    if not all(
        isinstance(item, AlongBoundaryWindowObservation) for item in window_rows
    ):
        raise TypeError(
            "observations must contain AlongBoundaryWindowObservation objects."
        )
    thresholds = _positive_windows(
        source_magnitude_thresholds,
        "source_magnitude_thresholds",
    )

    cumulative: list[dict[str, Any]] = []
    annular: list[dict[str, Any]] = []
    for threshold in thresholds:
        threshold_rows = tuple(
            row for row in window_rows if row.source_magnitude >= threshold
        )
        statistics = _cumulative_statistics(threshold_rows, threshold)
        cumulative.extend(statistics)
        annular.extend(_annular_statistics(statistics, threshold))

    coverage = _coverage_summary(pair_rows)
    route_distances = [
        item.along_boundary_distance_km
        for item in pair_rows
        if item.route_status == ROUTE_STATUS_AVAILABLE
        and item.along_boundary_distance_km is not None
    ]
    route_ratios = [
        item.along_boundary_distance_km / item.radial_distance_km
        for item in pair_rows
        if item.route_status == ROUTE_STATUS_AVAILABLE
        and item.along_boundary_distance_km is not None
        and item.radial_distance_km > 0
    ]

    return {
        "schema_version": 1,
        "study_id": ALONG_BOUNDARY_STUDY_ID,
        "research_mode": "retrospective_descriptive",
        "routing_scope": "same_plate_pair",
        "inference_status": "descriptive_only_null_model_not_yet_applied",
        "report_is_nonpredictive": True,
        "source_magnitude_thresholds": list(thresholds),
        "source_magnitude_statistic_count": len(cumulative),
        "annular_statistic_count": len(annular),
        "coverage": coverage,
        "route_distance_summary": {
            "count": len(route_distances),
            "median_along_boundary_distance_km": (
                median(route_distances) if route_distances else None
            ),
            "median_along_to_radial_ratio": (
                median(route_ratios) if route_ratios else None
            ),
        },
        "source_magnitude_statistics": cumulative,
        "annular_statistics": annular,
        "interpretation": (
            "Along-boundary and radial counts use the same route-available event-pair "
            "universe. Differences describe how mapped PB2002 network distance "
            "re-bins historical event associations; they do not establish a causal "
            "propagation path."
        ),
    }


def along_boundary_pair_to_record(pair: AlongBoundaryPair) -> dict[str, Any]:
    record = asdict(pair)
    record["earlier_time"] = pair.earlier_time.isoformat()
    record["later_time"] = pair.later_time.isoformat()
    return record


def along_boundary_window_to_record(
    observation: AlongBoundaryWindowObservation,
) -> dict[str, Any]:
    record = asdict(observation)
    record["source_time"] = observation.source_time.isoformat()
    record["edge_eligible"] = observation.edge_eligible
    return record


def _route_pair(
    earlier: PlateBoundaryProjection | None,
    later: PlateBoundaryProjection | None,
    graph: PlateBoundaryGraph,
    distance_cache: dict[str, tuple[float, ...]],
) -> tuple[str, float | None, bool | None]:
    if earlier is None or later is None:
        return ROUTE_STATUS_MISSING_PROJECTION, None, None
    same_pair = _projection_plate_pair(earlier) == _projection_plate_pair(later)
    if not same_pair:
        return ROUTE_STATUS_DIFFERENT_PLATE_PAIR, None, False

    distances = distance_cache.get(earlier.event_id)
    if distances is None:
        distances = graph.distances_from_projection(
            earlier,
            routing_scope="same_plate_pair",
        )
        distance_cache[earlier.event_id] = distances
    target_start, target_end = graph.step_nodes[later.step_id]
    candidates = [
        distances[target_start] + later.distance_from_start_km,
        distances[target_end] + later.distance_to_end_km,
    ]
    if earlier.step_id == later.step_id:
        candidates.append(
            abs(earlier.distance_from_start_km - later.distance_from_start_km)
        )
    best = min(candidates)
    if not math.isfinite(best):
        return ROUTE_STATUS_DISCONNECTED, None, True
    return ROUTE_STATUS_AVAILABLE, best, True


def _cumulative_statistics(
    rows: tuple[AlongBoundaryWindowObservation, ...],
    threshold: float,
) -> list[dict[str, Any]]:
    keys = sorted(
        {(row.time_window_days, row.distance_window_km) for row in rows}
    )
    statistics: list[dict[str, Any]] = []
    for time_window, distance_window in keys:
        eligible = [
            row
            for row in rows
            if row.time_window_days == time_window
            and row.distance_window_km == distance_window
            and row.edge_eligible
        ]
        statistics.append(
            {
                "source_minimum_magnitude": threshold,
                "time_window_days": time_window,
                "distance_window_km": distance_window,
                "eligible_source_count": len(eligible),
                **_metric_summary(eligible, "along_boundary"),
                **_metric_summary(eligible, "routed_radial"),
            }
        )
    return statistics


def _metric_summary(
    rows: list[AlongBoundaryWindowObservation],
    metric: str,
) -> dict[str, Any]:
    pre_name = f"pre_count_{metric}"
    post_name = f"post_count_{metric}"
    pre_values = [int(getattr(row, pre_name)) for row in rows]
    post_values = [int(getattr(row, post_name)) for row in rows]
    differences = [post - pre for pre, post in zip(pre_values, post_values)]
    pre_total = sum(pre_values)
    post_total = sum(post_values)
    return {
        f"pre_{metric}_count": pre_total,
        f"post_{metric}_count": post_total,
        f"post_to_pre_{metric}_ratio": _ratio(post_total, pre_total),
        f"post_minus_pre_{metric}": post_total - pre_total,
        f"sources_{metric}_post_gt_pre": sum(value > 0 for value in differences),
        f"sources_{metric}_post_eq_pre": sum(value == 0 for value in differences),
        f"sources_{metric}_post_lt_pre": sum(value < 0 for value in differences),
        f"mean_source_{metric}_difference": (
            sum(differences) / len(differences) if differences else None
        ),
        f"median_source_{metric}_difference": (
            median(differences) if differences else None
        ),
    }


def _annular_statistics(
    cumulative: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    grouped: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for statistic in cumulative:
        grouped[float(statistic["time_window_days"])].append(statistic)

    result: list[dict[str, Any]] = []
    for time_window, statistics in sorted(grouped.items()):
        ordered = sorted(statistics, key=lambda item: item["distance_window_km"])
        previous = None
        for statistic in ordered:
            lower = 0.0 if previous is None else float(previous["distance_window_km"])
            upper = float(statistic["distance_window_km"])
            record: dict[str, Any] = {
                "source_minimum_magnitude": threshold,
                "time_window_days": time_window,
                "distance_min_km": lower,
                "distance_max_km": upper,
                "eligible_source_count": statistic["eligible_source_count"],
            }
            for metric in ("along_boundary", "routed_radial"):
                for side in ("pre", "post"):
                    key = f"{side}_{metric}_count"
                    value = int(statistic[key])
                    prior = 0 if previous is None else int(previous[key])
                    record[f"{side}_{metric}_count"] = value - prior
                pre = record[f"pre_{metric}_count"]
                post = record[f"post_{metric}_count"]
                record[f"post_to_pre_{metric}_ratio"] = _ratio(post, pre)
                record[f"post_minus_pre_{metric}"] = post - pre
            result.append(record)
            previous = statistic
    return result


def _coverage_summary(pairs: tuple[AlongBoundaryPair, ...]) -> dict[str, int]:
    statuses = defaultdict(int)
    for pair in pairs:
        statuses[pair.route_status] += 1
    return {
        "candidate_pair_count": len(pairs),
        "route_available_pair_count": statuses[ROUTE_STATUS_AVAILABLE],
        "within_along_boundary_limit_pair_count": sum(
            item.within_along_boundary_limit for item in pairs
        ),
        "missing_projection_pair_count": statuses[
            ROUTE_STATUS_MISSING_PROJECTION
        ],
        "different_plate_pair_count": statuses[
            ROUTE_STATUS_DIFFERENT_PLATE_PAIR
        ],
        "disconnected_same_plate_pair_count": statuses[ROUTE_STATUS_DISCONNECTED],
    }


def _same_boundary(
    first: PlateBoundaryProjection | None,
    second: PlateBoundaryProjection | None,
) -> bool | None:
    if first is None or second is None:
        return None
    return first.boundary_id == second.boundary_id


def _projection_plate_pair(
    projection: PlateBoundaryProjection,
) -> tuple[str, str]:
    return tuple(sorted((projection.left_plate, projection.right_plate)))


def _projection_field(
    projection: PlateBoundaryProjection | None,
    name: str,
) -> str | None:
    return None if projection is None else str(getattr(projection, name))


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _validate_profile_window(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("profile_start must be timezone-aware.")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("profile_end must be timezone-aware.")
    if start >= end:
        raise ValueError("profile_start must be earlier than profile_end.")


def _positive_windows(values: Iterable[float], name: str) -> tuple[float, ...]:
    result = tuple(sorted({_positive(value, name) for value in values}))
    if not result:
        raise ValueError(f"{name} must contain at least one value.")
    return result


def _positive(value: float, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive.")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be nonnegative.")
    return result


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result
