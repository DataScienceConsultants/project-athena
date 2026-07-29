"""Tests for the independent descriptive intelligence-v1 layer."""

from dataclasses import FrozenInstanceError

import pytest

from src.intelligence import IntelligenceConfiguration


def test_configuration_is_immutable_and_validated() -> None:
    configuration = IntelligenceConfiguration()
    with pytest.raises(FrozenInstanceError):
        configuration.activity_window = 3  # type: ignore[misc]
    with pytest.raises(TypeError):
        IntelligenceConfiguration(activity_window=True)
    with pytest.raises(ValueError):
        IntelligenceConfiguration(trend_window=0)
    with pytest.raises(ValueError):
        IntelligenceConfiguration(high_completeness_threshold=1.1)
    with pytest.raises(ValueError):
        IntelligenceConfiguration(
            moderate_confidence_periods=30, high_confidence_periods=30
        )
