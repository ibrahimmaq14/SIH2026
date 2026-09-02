"""Tests for the drift engine: forward forecast, backward hindcast, combine()."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.geo import haversine_km
from app.schemas import DriftRequest
from app.services import drift as driftsvc
from app.services.drift import Vector, combine


def _t(hours: float = 0.0) -> datetime:
    return datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc) + timedelta(hours=hours)


# ─── combine() physics ─────────────────────────────────────────────────────


def test_combine_pure_current():
    v = combine(Vector(2.0, 90.0), None, windage=0.03)
    assert v.speed_kmh == pytest.approx(2.0)
    assert v.direction_deg == pytest.approx(90.0)


def test_combine_pure_wind():
    v = combine(None, Vector(20.0, 0.0), windage=0.03)
    # deflected WIND_DEFLECTION_DEG right of downwind
    assert v.speed_kmh == pytest.approx(0.6, rel=1e-6)
    assert v.direction_deg == pytest.approx(driftsvc.WIND_DEFLECTION_DEG)


def test_combine_sum_orthogonal():
    # current east 2 km/h + wind north 10 km/h with 3% windage (deflected 20°)
    import math as _m
    v = combine(Vector(2.0, 90.0), Vector(10.0, 0.0), windage=0.03)
    # windage component: 0.3 km/h at 20° right of north
    wn = 0.3 * _m.cos(_m.radians(driftsvc.WIND_DEFLECTION_DEG))
    we = 0.3 * _m.sin(_m.radians(driftsvc.WIND_DEFLECTION_DEG))
    expected = _m.hypot(2.0 + we, wn)
    assert v.speed_kmh == pytest.approx(expected, rel=1e-6)


def test_combine_zero_vectors():
    v = combine(None, None, windage=0.03)
    assert v.speed_kmh == 0.0


# ─── forecast ───────────────────────────────────────────────────────────────


class _ConstSeries:
    """Minimal EnvironmentalSeries-like object accepted by _simulate."""

    def __init__(self, cur: float, cur_dir: float, wind: float, wind_dir: float):
        self.cur, self.cur_dir, self.wind, self.wind_dir = cur, cur_dir, wind, wind_dir


def _const_env_series(cur=1.0, cur_dir=0.0, wind=0.0, wind_dir=0.0):
    """Build a real EnvironmentalSeries with constant vectors each hour."""
    from app.schemas import EnvironmentalSample, EnvironmentalSeries

    start = _t(-48)
    samples = []
    for h in range(0, 49):
        samples.append(
            EnvironmentalSample(
                timestamp=(start + timedelta(hours=h)).isoformat(),
                lat=28.5, lon=-94.9,
                current_speed_kmh=cur, current_direction_deg=cur_dir,
                wind_speed_kmh=wind, wind_direction_deg=wind_dir,
                wave_height_m=None, provider="test", dataClass="synthetic",
            )
        )
    return EnvironmentalSeries(
        samples=samples, provider="test", dataClass="synthetic", note="test series"
    )


def test_forecast_displacement_matches_physics():
    # 1 km/h current due north for 6 h → ~6 km north of start
    series = _const_env_series(cur=1.0, cur_dir=0.0)
    req = DriftRequest(
        lat=28.5, lon=-94.9, start_time=_t().isoformat(), duration_hours=6.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=2,
    )
    out = driftsvc.forecast(req, series=series)
    assert out.end_position["lat"] > 28.5
    assert out.total_displacement_km == pytest.approx(6.0, rel=0.02)
    assert len(out.track.points) == 7  # 0..6 hours inclusive


def test_forecast_no_motion_with_no_vectors():
    series = _const_env_series(cur=0.0, wind=0.0)
    req = DriftRequest(
        lat=28.5, lon=-94.9, start_time=_t().isoformat(), duration_hours=6.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=1,
    )
    out = driftsvc.forecast(req, series=series)
    assert out.end_position["lat"] == pytest.approx(28.5)
    assert out.end_position["lon"] == pytest.approx(-94.9)
    assert out.total_displacement_km == pytest.approx(0.0, abs=1e-6)


def test_hindcast_moves_backward():
    # backward from a position with constant northward current → origin is SOUTH
    series = _const_env_series(cur=1.0, cur_dir=0.0)
    req = DriftRequest(
        lat=28.5, lon=-94.9, start_time=_t().isoformat(), duration_hours=12.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=2,
    )
    out = driftsvc.hindcast(req, series=series)
    assert out.origin_location["lat"] < 28.5  # south of observation
    assert haversine_km(28.5, -94.9, out.origin_location["lat"], out.origin_location["lon"]) == pytest.approx(12.0, rel=0.05)
    # track ordered observation → oldest
    assert out.track.points[0].lat == pytest.approx(28.5)
    assert out.track.points[-1].lat == pytest.approx(out.origin_location["lat"])


def test_hindcast_roundtrip_forecast():
    """hindcast then forecast from the origin should approximately return."""
    series = _const_env_series(cur=0.8, cur_dir=45.0, wind=10.0, wind_dir=90.0)
    h_req = DriftRequest(
        lat=28.55, lon=-94.95, start_time=_t().isoformat(), duration_hours=24.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=2,
    )
    h = driftsvc.hindcast(h_req, series=series)
    f_req = DriftRequest(
        lat=h.origin_location["lat"], lon=h.origin_location["lon"],
        start_time=h.origin_time, duration_hours=24.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=1,
    )
    f = driftsvc.forecast(f_req, series=series)
    back = haversine_km(28.55, -94.95, f.end_position["lat"], f.end_position["lon"])
    assert back < 1.0  # close to the original observation point


def test_disclaimer_present():
    series = _const_env_series()
    req = DriftRequest(
        lat=28.5, lon=-94.9, start_time=_t().isoformat(), duration_hours=6.0,
        timestep_minutes=60, windage=0.03, use_demo_environment=True, ensemble_members=1,
    )
    out = driftsvc.hindcast(req, series=series)
    assert "ESTIMATE" in out.disclaimer or "estimate" in out.disclaimer
