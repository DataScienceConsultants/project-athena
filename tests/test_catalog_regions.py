import pytest
from src.catalog import CARIBBEAN, PUERTO_RICO, REGIONS, Region, get_region

def test_required_regions_are_registered():
    assert {"puerto_rico", "virgin_islands", "mona_passage", "dominican_republic", "lesser_antilles", "caribbean"} <= set(REGIONS)

def test_lookup_is_trimmed_and_case_insensitive():
    assert get_region("  Puerto Rico ") is PUERTO_RICO

def test_containment_is_inclusive():
    assert PUERTO_RICO.contains(17, -69) and CARIBBEAN.contains(18, -66)

def test_unknown_region_fails():
    with pytest.raises(KeyError): get_region("atlantis")

def test_region_is_validated():
    with pytest.raises(TypeError): Region("x", "X", PUERTO_RICO.bounds, True)
