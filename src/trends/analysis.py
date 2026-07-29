"""Auditable calculations for descriptive temporal anomaly-score trends."""

from __future__ import annotations

import math
from collections import OrderedDict
from datetime import datetime

from src.anomaly import SeismicAnomalyResult
from src.trends.models import (
    TemporalTrendResult,
    TrendConfiguration,
    TrendDirection,
    TrendPoint,
    TrendStrength,
    TrendWindowSummary,
)


def _validate_score(score: object) -> float | None:
    if score is None:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise TypeError("score must be numeric, not boolean.")
    value = float(score)
    if not math.isfinite(value):
        raise ValueError("score must be finite.")
    if not 0 <= value <= 100:
        raise ValueError("score must be between 0 and 100.")
    return value


def _ordinary_least_squares_slope(scores: list[float]) -> float | None:
    if len(scores) < 2:
        return None
    mean_x = (len(scores) - 1) / 2
    mean_y = sum(scores) / len(scores)
    numerator = sum((index - mean_x) * (score - mean_y) for index, score in enumerate(scores))
    denominator = sum((index - mean_x) ** 2 for index in range(len(scores)))
    return numerator / denominator


def _percent_change(first_score: float | None, latest_score: float | None) -> float | None:
    if first_score is None or latest_score is None:
        return None
    if first_score == 0:
        return 0.0 if latest_score == 0 else None
    return ((latest_score - first_score) / abs(first_score)) * 100


def _window_summary(scores: list[float], window_size: int) -> TrendWindowSummary:
    values = scores[-window_size:]
    if not values:
        return TrendWindowSummary(window_size, 0, None, None, None, None, None)
    first_score, latest_score = values[0], values[-1]
    return TrendWindowSummary(
        window_size,
        len(values),
        _ordinary_least_squares_slope(values),
        first_score,
        latest_score,
        latest_score - first_score,
        _percent_change(first_score, latest_score),
    )


def _consecutive_movement(scores: list[float]) -> tuple[int, int]:
    if len(scores) < 2 or scores[-1] == scores[-2]:
        return 0, 0
    increasing = scores[-1] > scores[-2]
    count = 0
    for prior, current in zip(reversed(scores[:-1]), reversed(scores[1:])):
        if (current > prior) != increasing or current == prior:
            break
        count += 1
    return (count, 0) if increasing else (0, count)


def _direction(
    count: int, slope: float | None, configuration: TrendConfiguration
) -> TrendDirection:
    if count < configuration.minimum_points or slope is None:
        return TrendDirection.INSUFFICIENT_DATA
    if slope > configuration.rapid_slope_threshold:
        return TrendDirection.RAPIDLY_INCREASING
    if slope > configuration.stable_slope_threshold:
        return TrendDirection.INCREASING
    if slope >= -configuration.stable_slope_threshold:
        return TrendDirection.STABLE
    if slope >= -configuration.rapid_slope_threshold:
        return TrendDirection.DECREASING
    return TrendDirection.RAPIDLY_DECREASING


def _strength(
    direction: TrendDirection,
    current_slope: float | None,
    increases: int,
    decreases: int,
    percent_change: float | None,
    configuration: TrendConfiguration,
) -> TrendStrength:
    if direction is TrendDirection.INSUFFICIENT_DATA:
        return TrendStrength.INSUFFICIENT_DATA
    if direction is TrendDirection.STABLE:
        return TrendStrength.WEAK
    assert current_slope is not None
    consecutive = increases if "increasing" in direction.value else decreases
    slope_component = min(abs(current_slope) / configuration.rapid_slope_threshold, 1.0) * 50.0
    persistence = min(consecutive / max(configuration.minimum_points - 1, 1), 1.0) * 30.0
    change = 0.0 if percent_change is None else min(abs(percent_change) / 100.0, 1.0) * 20.0
    score = slope_component + persistence + change
    if score < configuration.moderate_strength_threshold:
        return TrendStrength.WEAK
    if score < configuration.strong_strength_threshold:
        return TrendStrength.MODERATE
    return TrendStrength.STRONG


def _summary(
    scores: list[float], direction: TrendDirection, strength: TrendStrength,
    current_slope: float | None, momentum: float | None, short_window: int,
) -> str:
    disclaimer = "This trend analysis is descriptive and is not an earthquake prediction or warning."
    count = len(scores)
    if direction is TrendDirection.INSUFFICIENT_DATA:
        noun = "score was" if count == 1 else "scores were"
        return f"A temporal trend could not be classified because only {count} available anomaly {noun} provided. This trend analysis is descriptive and nonpredictive."
    movement = ""
    if scores[0] != scores[-1]:
        verb = "increased" if scores[-1] > scores[0] else "decreased"
        movement = f" the score {verb} from {scores[0]:.1f} to {scores[-1]:.1f}."
    sentence = f"Across {count} available anomaly-score periods,"
    sentence += movement if movement else ""
    sentence += f" the current trend is {direction.value} with {strength.value} strength"
    if current_slope is not None:
        sentence += f" at {current_slope:.1f} score points per period."
    else:
        sentence += "."
    if momentum is not None and momentum != 0:
        relation = "above" if momentum > 0 else "below"
        sentence += f" The latest score is {abs(momentum):.1f} points {relation} its {short_window}-period moving average."
    return f"{sentence} {disclaimer}"


def calculate_temporal_trend(
    anomaly_results: tuple[SeismicAnomalyResult, ...],
    configuration: TrendConfiguration | None = None,
) -> TemporalTrendResult:
    """Describe observed movement in existing anomaly scores without prediction."""
    if not isinstance(anomaly_results, tuple):
        raise TypeError("anomaly_results must be a tuple of SeismicAnomalyResult values.")
    if not all(isinstance(result, SeismicAnomalyResult) for result in anomaly_results):
        raise TypeError("anomaly_results must contain SeismicAnomalyResult values.")
    configuration = configuration or TrendConfiguration()
    if not isinstance(configuration, TrendConfiguration):
        raise TypeError("configuration must be a TrendConfiguration or None.")
    starts: set[datetime] = set()
    for result in anomaly_results:
        if not isinstance(result.current_start, datetime) or not isinstance(result.current_end, datetime):
            raise TypeError("current_start and current_end must be datetime values.")
        if result.current_start in starts:
            raise ValueError("duplicate current_start timestamps are invalid.")
        starts.add(result.current_start)
        if result.current_end <= result.current_start:
            raise ValueError("current_end must be later than current_start.")
        _validate_score(result.score)
    ordered = tuple(sorted(anomaly_results, key=lambda result: result.current_start))
    available_scores: list[float] = []
    scored_points: list[tuple[SeismicAnomalyResult, float | None]] = []
    for result in ordered:
        score = _validate_score(result.score)
        scored_points.append((result, score))
        if score is not None:
            available_scores.append(score)
    points: list[TrendPoint] = []
    observed: list[float] = []
    for result, score in scored_points:
        if score is not None:
            observed.append(score)
        points.append(TrendPoint(
            result.current_start, result.current_end, score, score is not None,
            sum(observed[-configuration.short_window:]) / len(observed[-configuration.short_window:]) if observed else None,
            sum(observed[-configuration.medium_window:]) / len(observed[-configuration.medium_window:]) if observed else None,
            sum(observed[-configuration.long_window:]) / len(observed[-configuration.long_window:]) if observed else None,
        ))
    current_values = available_scores[-configuration.slope_window:]
    previous_values = available_scores[: -len(current_values)][-configuration.previous_slope_window:]
    current_slope = _ordinary_least_squares_slope(current_values)
    previous_slope = _ordinary_least_squares_slope(previous_values)
    acceleration = None if current_slope is None or previous_slope is None else current_slope - previous_slope
    increases, decreases = _consecutive_movement(available_scores)
    latest_score = available_scores[-1] if available_scores else None
    short_average = points[-1].short_moving_average if points else None
    momentum = None if latest_score is None or short_average is None else latest_score - short_average
    percent_change = _percent_change(available_scores[0] if available_scores else None, latest_score)
    maxima = minima = None
    if available_scores:
        available_entries = [(point.current_start, point.score) for point in points if point.score is not None]
        maxima = max(available_entries, key=lambda item: item[1])
        minima = min(available_entries, key=lambda item: item[1])
    windows = OrderedDict((name, _window_summary(available_scores, size)) for name, size in (
        ("short", configuration.short_window), ("medium", configuration.medium_window), ("long", configuration.long_window),
    ))
    direction = _direction(len(available_scores), current_slope, configuration)
    strength = _strength(direction, current_slope, increases, decreases, percent_change, configuration)
    return TemporalTrendResult(
        ordered[0].current_start if ordered else None, ordered[-1].current_end if ordered else None,
        len(ordered), len(available_scores), len(ordered) - len(available_scores), direction, strength,
        latest_score, short_average, points[-1].medium_moving_average if points else None,
        points[-1].long_moving_average if points else None, current_slope, previous_slope, acceleration,
        momentum, increases, decreases, None if maxima is None else maxima[1], None if maxima is None else maxima[0],
        None if minima is None else minima[1], None if minima is None else minima[0], percent_change,
        tuple(points), windows, _summary(available_scores, direction, strength, current_slope, momentum, configuration.short_window),
    )
