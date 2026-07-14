"""Configurable status thresholds for Project Athena Observatory.

This module defines Athena's initial interpretation vocabulary. The values
are versioned starting points, not permanent scientific conclusions.

Future versions should calibrate these thresholds against long historical
catalogs, regional differences, and empirical percentile distributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class ObservatoryStatus(str, Enum):
    """Human-readable seismic activity classifications."""

    VERY_QUIET = "very_quiet"
    QUIET = "quiet"
    NORMAL = "normal"
    ELEVATED = "elevated"
    EXCEPTIONAL = "exceptional"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RatioThresholds:
    """Thresholds for comparing a metric with its historical baseline.

    Ratios are interpreted as follows:

    - A ratio of 1.0 means the current metric equals its baseline.
    - A ratio of 1.5 means the current metric is 50% above baseline.
    - A ratio of 0.5 means the current metric is 50% below baseline.
    """

    very_quiet_upper: float = 0.50
    quiet_upper: float = 0.80
    normal_upper: float = 1.20
    elevated_upper: float = 1.75

    def validate(self) -> None:
        """Validate that thresholds are positive and strictly increasing."""

        values = (
            self.very_quiet_upper,
            self.quiet_upper,
            self.normal_upper,
            self.elevated_upper,
        )

        if any(value <= 0 for value in values):
            raise ValueError(
                "All ratio thresholds must be greater than zero."
            )

        if not (
            self.very_quiet_upper
            < self.quiet_upper
            < self.normal_upper
            < self.elevated_upper
        ):
            raise ValueError(
                "Ratio thresholds must be strictly increasing."
            )


@dataclass(frozen=True, slots=True)
class DepthDifferenceThresholds:
    """Thresholds for changes in average earthquake depth.

    Depth is interpreted differently from earthquake count or energy.
    A shallower or deeper average is not inherently safer or more dangerous.

    These thresholds describe the absolute difference from the historical
    average and are used only to identify whether depth behavior appears
    typical or substantially changed.
    """

    normal_absolute_difference_km: float = 5.0
    elevated_absolute_difference_km: float = 15.0

    def validate(self) -> None:
        """Validate depth-difference thresholds."""

        if self.normal_absolute_difference_km < 0:
            raise ValueError(
                "Normal depth difference must not be negative."
            )

        if (
            self.elevated_absolute_difference_km
            <= self.normal_absolute_difference_km
        ):
            raise ValueError(
                "Elevated depth difference must be greater than "
                "the normal depth difference."
            )


@dataclass(frozen=True, slots=True)
class ConfidenceThresholds:
    """Minimum historical sample sizes for confidence labels."""

    low_minimum_days: int = 30
    moderate_minimum_days: int = 180
    high_minimum_days: int = 730

    def validate(self) -> None:
        """Validate confidence sample-size thresholds."""

        values = (
            self.low_minimum_days,
            self.moderate_minimum_days,
            self.high_minimum_days,
        )

        if any(value <= 0 for value in values):
            raise ValueError(
                "Confidence thresholds must be positive integers."
            )

        if not (
            self.low_minimum_days
            < self.moderate_minimum_days
            < self.high_minimum_days
        ):
            raise ValueError(
                "Confidence thresholds must be strictly increasing."
            )


DEFAULT_ACTIVITY_THRESHOLDS: Final[RatioThresholds] = (
    RatioThresholds()
)

DEFAULT_ENERGY_THRESHOLDS: Final[RatioThresholds] = (
    RatioThresholds(
        very_quiet_upper=0.40,
        quiet_upper=0.75,
        normal_upper=1.35,
        elevated_upper=2.50,
    )
)

DEFAULT_DEPTH_THRESHOLDS: Final[DepthDifferenceThresholds] = (
    DepthDifferenceThresholds()
)

DEFAULT_CONFIDENCE_THRESHOLDS: Final[ConfidenceThresholds] = (
    ConfidenceThresholds()
)


STATUS_DISPLAY_NAMES: Final[
    dict[ObservatoryStatus, str]
] = {
    ObservatoryStatus.VERY_QUIET: "Very Quiet",
    ObservatoryStatus.QUIET: "Quiet",
    ObservatoryStatus.NORMAL: "Normal",
    ObservatoryStatus.ELEVATED: "Elevated",
    ObservatoryStatus.EXCEPTIONAL: "Exceptional",
    ObservatoryStatus.UNAVAILABLE: "Unavailable",
}


STATUS_SEVERITY: Final[
    dict[ObservatoryStatus, int]
] = {
    ObservatoryStatus.UNAVAILABLE: -1,
    ObservatoryStatus.VERY_QUIET: 0,
    ObservatoryStatus.QUIET: 1,
    ObservatoryStatus.NORMAL: 2,
    ObservatoryStatus.ELEVATED: 3,
    ObservatoryStatus.EXCEPTIONAL: 4,
}


def validate_default_thresholds() -> None:
    """Validate every built-in Athena threshold configuration."""

    DEFAULT_ACTIVITY_THRESHOLDS.validate()
    DEFAULT_ENERGY_THRESHOLDS.validate()
    DEFAULT_DEPTH_THRESHOLDS.validate()
    DEFAULT_CONFIDENCE_THRESHOLDS.validate()


validate_default_thresholds()