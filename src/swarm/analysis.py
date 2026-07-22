"""Descriptive analysis of spatially clustered seismic event sequences."""

from __future__ import annotations

import hashlib
import math
from numbers import Integral, Real

import numpy as np
import pandas as pd

from src.spatial.centroid import geographic_centroid
from src.spatial.clusters import cluster_frame
from src.spatial.distance import (
    haversine_distance,
    validate_latitude,
    validate_longitude,
)
from src.swarm.models import (
    SeismicSwarm,
    SwarmAnalysisResult,
    SwarmMigration,
    SwarmTrend,
)


def _positive_real(value: Real, *, name: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0 or (numeric == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier}, finite number.")
    return numeric


def _finite_numeric(value: object, *, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a real number.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(f"{name} must be a real number.") from error
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite.")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}.")
    return numeric


def _normalize_events(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Data must be a pandas DataFrame.")
    missing = set(columns).difference(dataframe.columns)
    if missing:
        raise ValueError(
            "DataFrame is missing required columns: " + ", ".join(sorted(missing))
        )

    source = dataframe.loc[:, columns].copy()
    source["_source_index"] = dataframe.index
    complete = source.dropna(subset=columns).copy()
    time_column, latitude_column, longitude_column, depth_column, magnitude_column = (
        columns
    )
    normalized: list[dict[str, object]] = []
    for position, row in complete.iterrows():
        try:
            timestamp = pd.to_datetime(row[time_column], utc=True, errors="raise")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(
                f"Invalid timestamp at DataFrame index {position!r}."
            ) from error
        normalized.append(
            {
                "_source_index": row["_source_index"],
                "_time": timestamp,
                "_latitude": validate_latitude(row[latitude_column]),
                "_longitude": validate_longitude(row[longitude_column]),
                "_depth": _finite_numeric(row[depth_column], name="Depth", minimum=0),
                "_magnitude": _finite_numeric(row[magnitude_column], name="Magnitude"),
            }
        )
    return pd.DataFrame(normalized)


def _trend(times: pd.Series, values: pd.Series, tolerance: float) -> SwarmTrend:
    if len(times) < 2:
        return SwarmTrend(None, "insufficient_data", len(times))
    elapsed_days = (times - times.iloc[0]).dt.total_seconds().to_numpy(
        dtype=float
    ) / 86_400.0
    if np.ptp(elapsed_days) == 0:
        return SwarmTrend(None, "insufficient_data", len(times))
    slope = float(np.polyfit(elapsed_days, values.to_numpy(dtype=float), 1)[0])
    direction = "stable"
    if slope > tolerance:
        direction = "increasing"
    elif slope < -tolerance:
        direction = "decreasing"
    return SwarmTrend(slope, direction, len(times))


def _bearing_degrees(start: tuple[float, float], end: tuple[float, float]) -> float:
    start_latitude, start_longitude = map(math.radians, start)
    end_latitude, end_longitude = map(math.radians, end)
    longitude_delta = end_longitude - start_longitude
    x = math.sin(longitude_delta) * math.cos(end_latitude)
    y = math.cos(start_latitude) * math.sin(end_latitude) - math.sin(
        start_latitude
    ) * math.cos(end_latitude) * math.cos(longitude_delta)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _cardinal_direction(bearing: float) -> str:
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[round(bearing / 45) % len(directions)]


def _migration(
    coordinates: list[tuple[float, float]], stationary_km: float
) -> SwarmMigration:
    if len(coordinates) < 2:
        return SwarmMigration(0.0, None, "stationary", True)
    split = len(coordinates) // 2
    early = geographic_centroid(coordinates[:split]).as_tuple()
    late = geographic_centroid(coordinates[split:]).as_tuple()
    distance = haversine_distance(*early, *late)
    if distance <= stationary_km:
        return SwarmMigration(distance, None, "stationary", True)
    bearing = _bearing_degrees(early, late)
    return SwarmMigration(distance, bearing, _cardinal_direction(bearing), False)


def _swarm_id(member_indices: tuple[object, ...]) -> str:
    """Make an input-order-independent identifier from source event indices."""

    digest_input = "\x1f".join(sorted(map(repr, member_indices))).encode()
    return "swarm-" + hashlib.sha256(digest_input).hexdigest()[:12]


def _activity_status(
    event_count: int,
    end: pd.Timestamp,
    reference: pd.Timestamp,
    active_days: float,
    recent_days: float,
) -> str:
    if event_count < 2:
        return "insufficient_data"
    age_days = (reference - end).total_seconds() / 86_400.0
    if age_days <= active_days:
        return "active"
    if age_days <= recent_days:
        return "recently_active"
    return "inactive"


def analyze_swarms(
    dataframe: pd.DataFrame,
    *,
    time_column: str = "time",
    latitude_column: str = "latitude",
    longitude_column: str = "longitude",
    depth_column: str = "depth",
    magnitude_column: str = "magnitude",
    eps_km: Real = 10.0,
    min_samples: Integral = 2,
    minimum_swarm_events: Integral = 2,
    reference_time: object | None = None,
    active_window_days: Real = 1.0,
    recent_window_days: Real = 7.0,
    trend_stable_tolerance: Real = 1e-9,
    stationary_threshold_km: Real = 0.1,
) -> SwarmAnalysisResult:
    """Characterize qualifying spatial event clusters without predicting earthquakes.

    The reference time defaults to the newest valid event, never wall-clock
    time. Activity is ``active`` within ``active_window_days``,
    ``recently_active`` within ``recent_window_days``, and otherwise inactive.
    """

    if isinstance(minimum_swarm_events, bool) or not isinstance(
        minimum_swarm_events, Integral
    ):
        raise TypeError("minimum_swarm_events must be an integer.")
    if minimum_swarm_events < 1:
        raise ValueError("minimum_swarm_events must be greater than or equal to 1.")
    active_days = _positive_real(
        active_window_days, name="active_window_days", allow_zero=True
    )
    recent_days = _positive_real(
        recent_window_days, name="recent_window_days", allow_zero=True
    )
    if active_days > recent_days:
        raise ValueError("active_window_days must not exceed recent_window_days.")
    tolerance = _positive_real(
        trend_stable_tolerance, name="trend_stable_tolerance", allow_zero=True
    )
    stationary_km = _positive_real(
        stationary_threshold_km, name="stationary_threshold_km", allow_zero=True
    )
    events = _normalize_events(
        dataframe,
        [
            time_column,
            latitude_column,
            longitude_column,
            depth_column,
            magnitude_column,
        ],
    )
    if events.empty:
        parsed_reference: pd.Timestamp | None = None
        if reference_time is not None:
            try:
                parsed_reference = pd.to_datetime(
                    reference_time, utc=True, errors="raise"
                )
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError(
                    "reference_time must be a parseable timestamp."
                ) from error
        return SwarmAnalysisResult(
            (),
            len(dataframe),
            0,
            len(dataframe),
            (),
            parsed_reference.isoformat() if parsed_reference is not None else None,
        )

    if reference_time is None:
        reference = events["_time"].max()
    else:
        try:
            reference = pd.to_datetime(reference_time, utc=True, errors="raise")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("reference_time must be a parseable timestamp.") from error
    if reference < events["_time"].max():
        raise ValueError(
            "reference_time must not be earlier than the latest valid event."
        )

    spatial = cluster_frame(
        events,
        latitude_column="_latitude",
        longitude_column="_longitude",
        eps_km=eps_km,
        min_samples=min_samples,
    )
    noise_indices = tuple(
        events.loc[position, "_source_index"] for position in spatial.noise_indices
    )
    swarms: list[SeismicSwarm] = []
    for cluster in spatial.clusters:
        if cluster.event_count < minimum_swarm_events:
            continue
        sequence = (
            events.iloc[list(cluster.member_indices)]
            .sort_values("_time")
            .reset_index(drop=True)
        )
        start, end = sequence["_time"].iloc[0], sequence["_time"].iloc[-1]
        duration_days = (end - start).total_seconds() / 86_400.0
        rate_days = duration_days if duration_days else 1.0
        coordinates = list(
            sequence[["_latitude", "_longitude"]].itertuples(index=False, name=None)
        )
        members = tuple(sequence["_source_index"])
        area = math.pi * cluster.radius_km**2
        swarms.append(
            SeismicSwarm(
                swarm_id=_swarm_id(members),
                cluster_id=cluster.cluster_id,
                event_count=cluster.event_count,
                start_time_utc=start.isoformat(),
                end_time_utc=end.isoformat(),
                duration_days=duration_days,
                event_rate_per_day=cluster.event_count / rate_days,
                spatial_density_events_per_sq_km=(
                    cluster.event_count / area if area else None
                ),
                centroid_latitude=cluster.centroid_latitude,
                centroid_longitude=cluster.centroid_longitude,
                radius_km=cluster.radius_km,
                mean_magnitude=float(sequence["_magnitude"].mean()),
                magnitude_trend=_trend(
                    sequence["_time"], sequence["_magnitude"], tolerance
                ),
                mean_depth_km=float(sequence["_depth"].mean()),
                depth_trend=_trend(sequence["_time"], sequence["_depth"], tolerance),
                migration=_migration(coordinates, stationary_km),
                activity_status=_activity_status(
                    cluster.event_count, end, reference, active_days, recent_days
                ),
                recent_event_count=int(
                    (
                        sequence["_time"] >= reference - pd.Timedelta(days=recent_days)
                    ).sum()
                ),
                member_indices=members,
            )
        )
    swarms.sort(
        key=lambda swarm: (
            -pd.Timestamp(swarm.end_time_utc).value,
            -swarm.event_count,
            swarm.cluster_id,
        )
    )
    return SwarmAnalysisResult(
        tuple(swarms),
        len(dataframe),
        len(events),
        len(dataframe) - len(events),
        noise_indices,
        reference.isoformat(),
    )
