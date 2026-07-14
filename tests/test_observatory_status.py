"""Tests for Project Athena Observatory status interpretation."""

from __future__ import annotations

import pytest

from src.observatory.status import (
    MetricStatus,
    classify_activity,
    classify_depth,
    classify_energy,
    classify_ratio,
    confidence_from_history,
    overall_status,
)
from src.observatory.thresholds import (
    ObservatoryStatus,
    RatioThresholds,
)


@pytest.mark.parametrize(
    ("ratio", "expected_status"),
    [
        (0.20, ObservatoryStatus.VERY_QUIET),
        (0.49, ObservatoryStatus.VERY_QUIET),
        (0.50, ObservatoryStatus.QUIET),
        (0.79, ObservatoryStatus.QUIET),
        (0.80, ObservatoryStatus.NORMAL),
        (1.00, ObservatoryStatus.NORMAL),
        (1.20, ObservatoryStatus.NORMAL),
        (1.21, ObservatoryStatus.ELEVATED),
        (1.75, ObservatoryStatus.ELEVATED),
        (1.76, ObservatoryStatus.EXCEPTIONAL),
    ],
)
def test_classify_ratio_boundaries(
    ratio: float,
    expected_status: ObservatoryStatus,
) -> None:
    """Ratios should follow Athena's configured status boundaries."""

    thresholds = RatioThresholds()

    result = classify_ratio(
        ratio,
        thresholds,
    )

    assert result.status == expected_status
    assert result.score == ratio


def test_classify_ratio_unavailable() -> None:
    """Missing ratios should produce an unavailable status."""

    result = classify_ratio(
        None,
        RatioThresholds(),
    )

    assert result.status == ObservatoryStatus.UNAVAILABLE
    assert result.score is None
    assert "unavailable" in result.explanation.lower()


def test_activity_uses_activity_thresholds() -> None:
    """Activity ratios should use Athena's activity vocabulary."""

    result = classify_activity(1.40)

    assert result.status == ObservatoryStatus.ELEVATED
    assert result.score == pytest.approx(1.40)


def test_energy_uses_energy_thresholds() -> None:
    """Energy should use its wider normal range."""

    result = classify_energy(1.30)

    assert result.status == ObservatoryStatus.NORMAL

    elevated = classify_energy(2.00)

    assert elevated.status == ObservatoryStatus.ELEVATED


@pytest.mark.parametrize(
    ("difference_km", "expected_status"),
    [
        (0.0, ObservatoryStatus.NORMAL),
        (5.0, ObservatoryStatus.NORMAL),
        (-5.0, ObservatoryStatus.NORMAL),
        (5.1, ObservatoryStatus.ELEVATED),
        (-10.0, ObservatoryStatus.ELEVATED),
        (15.0, ObservatoryStatus.ELEVATED),
        (15.1, ObservatoryStatus.EXCEPTIONAL),
        (-25.0, ObservatoryStatus.EXCEPTIONAL),
    ],
)
def test_classify_depth(
    difference_km: float,
    expected_status: ObservatoryStatus,
) -> None:
    """Depth differences should be classified using absolute distance."""

    result = classify_depth(difference_km)

    assert result.status == expected_status
    assert result.score == pytest.approx(abs(difference_km))


def test_classify_depth_unavailable() -> None:
    """Missing depth comparison should be unavailable."""

    result = classify_depth(None)

    assert result.status == ObservatoryStatus.UNAVAILABLE
    assert result.score is None


@pytest.mark.parametrize(
    ("historical_days", "expected_confidence"),
    [
        (0, "Very Low"),
        (29, "Very Low"),
        (30, "Low"),
        (179, "Low"),
        (180, "Moderate"),
        (729, "Moderate"),
        (730, "High"),
        (2000, "High"),
    ],
)
def test_confidence_from_history(
    historical_days: int,
    expected_confidence: str,
) -> None:
    """Confidence labels should reflect available historical days."""

    assert (
        confidence_from_history(historical_days)
        == expected_confidence
    )


def make_metric_status(
    status: ObservatoryStatus,
) -> MetricStatus:
    """Create a test MetricStatus value."""

    return MetricStatus(
        status=status,
        score=1.0,
        explanation="Test metric.",
    )


def test_overall_status_uses_highest_severity() -> None:
    """The most severe available metric should determine overall status."""

    result = overall_status(
        activity=make_metric_status(
            ObservatoryStatus.NORMAL
        ),
        energy=make_metric_status(
            ObservatoryStatus.EXCEPTIONAL
        ),
        depth=make_metric_status(
            ObservatoryStatus.ELEVATED
        ),
    )

    assert result == ObservatoryStatus.EXCEPTIONAL


def test_overall_status_can_be_normal() -> None:
    """All-normal inputs should produce a normal overall status."""

    result = overall_status(
        activity=make_metric_status(
            ObservatoryStatus.NORMAL
        ),
        energy=make_metric_status(
            ObservatoryStatus.NORMAL
        ),
        depth=make_metric_status(
            ObservatoryStatus.NORMAL
        ),
    )

    assert result == ObservatoryStatus.NORMAL


def test_unavailable_does_not_override_available_status() -> None:
    """Unavailable metrics should not outrank valid classifications."""

    result = overall_status(
        activity=make_metric_status(
            ObservatoryStatus.NORMAL
        ),
        energy=make_metric_status(
            ObservatoryStatus.UNAVAILABLE
        ),
        depth=make_metric_status(
            ObservatoryStatus.ELEVATED
        ),
    )

    assert result == ObservatoryStatus.ELEVATED


def test_ratio_explanation_above_baseline() -> None:
    """Explanations should describe positive baseline differences."""

    result = classify_activity(1.25)

    assert "+25.0%" in result.explanation


def test_ratio_explanation_below_baseline() -> None:
    """Explanations should describe negative baseline differences."""

    result = classify_activity(0.75)

    assert "-25.0%" in result.explanation