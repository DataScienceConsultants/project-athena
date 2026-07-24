"""Deterministic, descriptive temporal seismic anomaly trend analysis API."""

from src.trends.analysis import calculate_temporal_trend
from src.trends.models import (
    TemporalTrendResult,
    TrendConfiguration,
    TrendDirection,
    TrendPoint,
    TrendStrength,
    TrendWindowSummary,
)

__all__ = [
    "TemporalTrendResult",
    "TrendConfiguration",
    "TrendDirection",
    "TrendPoint",
    "TrendStrength",
    "TrendWindowSummary",
    "calculate_temporal_trend",
]
