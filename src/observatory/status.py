"""Interpret Project Athena metrics into Observatory status."""

from __future__ import annotations

from dataclasses import dataclass

from .thresholds import (
    DEFAULT_ACTIVITY_THRESHOLDS,
    DEFAULT_CONFIDENCE_THRESHOLDS,
    DEFAULT_DEPTH_THRESHOLDS,
    DEFAULT_ENERGY_THRESHOLDS,
    ObservatoryStatus,
    RatioThresholds,
)


@dataclass(frozen=True, slots=True)
class MetricStatus:
    """Human-readable interpretation of one metric."""

    status: ObservatoryStatus
    score: float | None
    explanation: str


def classify_ratio(
    ratio: float | None,
    thresholds: RatioThresholds,
) -> MetricStatus:
    """Interpret a ratio compared with its historical baseline."""

    if ratio is None:
        return MetricStatus(
            status=ObservatoryStatus.UNAVAILABLE,
            score=None,
            explanation="Historical comparison unavailable.",
        )

    if ratio < thresholds.very_quiet_upper:
        status = ObservatoryStatus.VERY_QUIET

    elif ratio < thresholds.quiet_upper:
        status = ObservatoryStatus.QUIET

    elif ratio <= thresholds.normal_upper:
        status = ObservatoryStatus.NORMAL

    elif ratio <= thresholds.elevated_upper:
        status = ObservatoryStatus.ELEVATED

    else:
        status = ObservatoryStatus.EXCEPTIONAL

    percent = (ratio - 1.0) * 100

    return MetricStatus(
        status=status,
        score=ratio,
        explanation=(
            f"{percent:+.1f}% relative to historical average."
        ),
    )


def classify_activity(
    activity_ratio: float | None,
) -> MetricStatus:
    """Interpret earthquake activity."""

    return classify_ratio(
        activity_ratio,
        DEFAULT_ACTIVITY_THRESHOLDS,
    )


def classify_energy(
    energy_ratio: float | None,
) -> MetricStatus:
    """Interpret seismic energy."""

    return classify_ratio(
        energy_ratio,
        DEFAULT_ENERGY_THRESHOLDS,
    )


def classify_depth(
    depth_difference_km: float | None,
) -> MetricStatus:
    """Interpret changes in average earthquake depth."""

    if depth_difference_km is None:
        return MetricStatus(
            ObservatoryStatus.UNAVAILABLE,
            None,
            "Historical comparison unavailable.",
        )

    difference = abs(depth_difference_km)

    if (
        difference
        <= DEFAULT_DEPTH_THRESHOLDS.normal_absolute_difference_km
    ):
        status = ObservatoryStatus.NORMAL

    elif (
        difference
        <= DEFAULT_DEPTH_THRESHOLDS.elevated_absolute_difference_km
    ):
        status = ObservatoryStatus.ELEVATED

    else:
        status = ObservatoryStatus.EXCEPTIONAL

    return MetricStatus(
        status=status,
        score=difference,
        explanation=(
            f"Average depth differs by "
            f"{difference:.1f} km from baseline."
        ),
    )


def confidence_from_history(
    historical_days: int,
) -> str:
    """Estimate confidence from catalog length."""

    thresholds = DEFAULT_CONFIDENCE_THRESHOLDS

    if historical_days >= thresholds.high_minimum_days:
        return "High"

    if historical_days >= thresholds.moderate_minimum_days:
        return "Moderate"

    if historical_days >= thresholds.low_minimum_days:
        return "Low"

    return "Very Low"


def overall_status(
    *,
    activity: MetricStatus,
    energy: MetricStatus,
    depth: MetricStatus,
) -> ObservatoryStatus:
    """Return Athena's overall Observatory status.

    Current implementation:

    Highest severity wins.

    Future versions may replace this with the
    Seismic Activity Index (SAI).
    """

    statuses = [
        activity.status,
        energy.status,
        depth.status,
    ]

    severity = {
        ObservatoryStatus.UNAVAILABLE: -1,
        ObservatoryStatus.VERY_QUIET: 0,
        ObservatoryStatus.QUIET: 1,
        ObservatoryStatus.NORMAL: 2,
        ObservatoryStatus.ELEVATED: 3,
        ObservatoryStatus.EXCEPTIONAL: 4,
    }

    return max(
        statuses,
        key=lambda status: severity[status],
    )