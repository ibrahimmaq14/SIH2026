"""Tests for geographic math — the foundation of drift/hindcast correctness."""

from __future__ import annotations

import math

import pytest

from app.core.geo import (
    angle_difference_deg,
    bearing_deg,
    clamp_lat,
    clamp_lon,
    destination_point,
    haversine_km,
    knots_to_kmh,
    kmh_to_knots,
)


def test_haversine_known_distance():
    # Gulf of Mexico pair from the AIS dataset region
    d = haversine_km(28.619, -94.969, 28.4329, -95.14812)
    assert 15 < d < 35  # roughly 23 km


def test_haversine_zero_distance():
    assert haversine_km(28.5, -94.9, 28.5, -94.9) == 0.0


def test_haversine_symmetry():
    assert haversine_km(10, 20, 30, 40) == haversine_km(30, 40, 10, 20)


def test_haversine_antipodal():
    d = haversine_km(0, 0, 0, 180)
    assert d == pytest.approx(math.pi * 6371.0088, rel=1e-3)


def test_bearing_cardinals():
    assert bearing_deg(0, 0, 10, 0) == pytest.approx(0.0)     # north
    assert bearing_deg(0, 0, 0, 10) == pytest.approx(90.0)    # east
    assert bearing_deg(10, 0, 0, 0) == pytest.approx(180.0)   # south
    assert bearing_deg(0, 10, 0, 0) == pytest.approx(270.0)   # west


def test_destination_point_roundtrip():
    lat, lon = 28.5, -94.9
    brg = 45.0
    d = 10.0
    la, lo = destination_point(lat, lon, brg, d)
    assert haversine_km(lat, lon, la, lo) == pytest.approx(d, rel=1e-3)
    assert bearing_deg(lat, lon, la, lo) == pytest.approx(brg, abs=0.5)


def test_destination_point_zero():
    assert destination_point(28.5, -94.9, 90.0, 0.0) == (28.5, -94.9)


def test_destination_point_is_not_naive_addition():
    # 100 km east at high latitude must change lon by ~2 degrees, lat ~unchanged
    la, lo = destination_point(60.0, 20.0, 90.0, 100.0)
    assert abs(la - 60.0) < 0.05  # great-circle path dips slightly; must be tiny
    expected_dlon = 100.0 / (111.32 * math.cos(math.radians(60.0)))
    assert (lo - 20.0) == pytest.approx(expected_dlon, rel=5e-3)


def test_angle_difference():
    assert angle_difference_deg(350, 10) == pytest.approx(20.0)
    assert angle_difference_deg(10, 350) == pytest.approx(20.0)
    assert angle_difference_deg(90, 270) == pytest.approx(180.0)
    assert angle_difference_deg(45, 45) == 0.0


def test_speed_conversions():
    assert knots_to_kmh(10) == pytest.approx(18.52)
    assert kmh_to_knots(18.52) == pytest.approx(10.0, rel=1e-3)


def test_clamps():
    assert clamp_lat(120) == 90
    assert clamp_lat(-120) == -90
    assert clamp_lon(190) == -170
    assert clamp_lon(-190) == 170
