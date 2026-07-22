"""Descriptive analysis of spatially clustered seismic event sequences."""

from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np
import pandas as pd

from src.spatial.centroid import geographic_centroid
from src.spatial.clusters import cluster_frame
from src.spatial.distance import haversine_distance, validate_latitude, validate_longitude
from src.swarm.models import SwarmAnalysisResult, SwarmCluster


def _finite_numeric(value: object, *, name: str, minimum: float | None = None) -> float:
    """Validate a finite numeric event field."""

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


def _positive_real(value: Real, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number.")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{name} must be a positive, finite number.")
    return numeric


def _trend_per_day(times: pd.Series, values: pd.Series) -> float | None:
    """Return a least-squares linear trend, or ``None`` without time spread."""

    elapsed_days = (times - times.iloc[0]).dt.total_seconds().to_numpy() / 86400
    if len(elapsed_days) < 2 or np.ptp(elapsed_days) == 0:
        return None
    return float(np.polyfit(elapsed_days, values.to_numpy(dtype=float), 1)[0])


def _normalized_events(
    dataframe: pd.DataFrame,
    *,
    time_column: str,
    latitude_column: str,
    longitude_column: str,
    depth_column: str,
    magnitude_column: str,
) -> pd.DataFrame:
    """Exclude missing rows and reject non-missing invalid source values."""

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Data must be a pandas DataFrame.")
    columns = [time_column, latitude_column, longitude_column, depth_column, magnitude_column]
    missing = set(columns).difference(dataframe.columns)
    if missing:
        raise ValueError("DataFrame is missing required columns: " + ", ".join(sorted(missing)))

    source = dataframe.loc[:, columns].copy()
    source["_source_index"] = dataframe.index
    complete = source.dropna(subset=columns).copy()
    for position, row in complete.iterrows():
        try:
            timestamp = pd.to_datetime(row[time_column], utc=True, errors="raise")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Invalid timestamp at DataFrame index {position!r}.") from error
        complete.loc[position, "_time"] = timestamp
        complete.loc[position, "_latitude"] = validate_latitude(row[latitude_column])
        complete.loc[position, "_longitude"] = validate_longitude(row[longitude_column])
        complete.loc[position, "_magnitude"] = _finite_numeric(row[magnitude_column], name="Magnitude")
        complete.loc[position, "_depth"] = _finite_numeric(row[depth_column], name="Depth", minimum=0)

    return complete.reset_index(drop=True)


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
    recent_window_days: Real = 7.0,
    swarm_max_duration_days: Real = 30.0,
    swarm_min_rate_per_day: Real = 0.5,
) -> SwarmAnalysisResult:
    """Characterize DBSCAN spatial clusters as possible seismic swarms.

    Complete events are clustered using Athena's existing Haversine DBSCAN
    implementation.  A cluster is descriptively flagged ``is_swarm_like`` when
    it meets the supplied duration and event-rate thresholds.  The flag does
    not predict future earthquakes and does not distinguish swarms from other
    physical sequence types.
    """

    recent_days = _positive_real(recent_window_days, name="recent_window_days")
    max_duration = _positive_real(swarm_max_duration_days, name="swarm_max_duration_days")
    min_rate = _positive_real(swarm_min_rate_per_day, name="swarm_min_rate_per_day")
    events = _normalized_events(dataframe, time_column=time_column, latitude_column=latitude_column,
                                longitude_column=longitude_column, depth_column=depth_column,
                                magnitude_column=magnitude_column)
    if events.empty:
        return SwarmAnalysisResult((), len(dataframe), 0, len(dataframe), (), recent_days)

    spatial = cluster_frame(events, latitude_column="_latitude", longitude_column="_longitude",
                            eps_km=eps_km, min_samples=min_samples)
    noise_indices = tuple(events.loc[position, "_source_index"] for position in spatial.noise_indices)
    swarms: list[SwarmCluster] = []
    for cluster in spatial.clusters:
        sequence = events.iloc[list(cluster.member_indices)].sort_values("_time").reset_index(drop=True)
        start, end = sequence["_time"].iloc[0], sequence["_time"].iloc[-1]
        duration_days = (end - start).total_seconds() / 86400
        rate_days = duration_days if duration_days > 0 else 1.0
        coordinates = list(sequence[["_latitude", "_longitude"]].itertuples(index=False, name=None))
        if len(sequence) == 1:
            migration = 0.0
        else:
            midpoint = len(sequence) // 2
            early = geographic_centroid(coordinates[:midpoint])
            late = geographic_centroid(coordinates[midpoint:])
            migration = haversine_distance(*early.as_tuple(), *late.as_tuple())
        area = math.pi * cluster.radius_km**2
        recent_count = int((sequence["_time"] >= end - pd.Timedelta(days=recent_days)).sum())
        swarms.append(SwarmCluster(
            cluster_id=cluster.cluster_id, event_count=cluster.event_count,
            start_time_utc=start.isoformat(), end_time_utc=end.isoformat(), duration_days=duration_days,
            event_rate_per_day=cluster.event_count / rate_days,
            spatial_density_events_per_sq_km=(cluster.event_count / area if area else None),
            centroid_latitude=cluster.centroid_latitude, centroid_longitude=cluster.centroid_longitude,
            radius_km=cluster.radius_km, mean_magnitude=float(sequence["_magnitude"].mean()),
            magnitude_trend_per_day=_trend_per_day(sequence["_time"], sequence["_magnitude"]),
            mean_depth_km=float(sequence["_depth"].mean()),
            depth_trend_km_per_day=_trend_per_day(sequence["_time"], sequence["_depth"]),
            migration_distance_km=migration,
            migration_rate_km_per_day=(migration / duration_days if duration_days else None),
            recent_event_count=recent_count, recent_activity_fraction=recent_count / cluster.event_count,
            is_swarm_like=duration_days <= max_duration and cluster.event_count / rate_days >= min_rate,
            member_indices=tuple(sequence["_source_index"]),
        ))
    return SwarmAnalysisResult(tuple(swarms), len(dataframe), len(events), len(dataframe) - len(events),
                               noise_indices, recent_days)
