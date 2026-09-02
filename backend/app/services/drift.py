"""
Oil-slick drift engine.

Baseline model: drift_velocity = ocean_current + windage * wind_velocity
with optional wind deflection angle (default 0 — pure downwind windage, a
standard simple formulation e.g. used by OpenDrift-style leeway models).

All displacement uses great-circle destination-point math (app.core.geo) —
NEVER naive lat/lon addition.

Both FORECAST (forward) and HINDCAST (backward) simulations are supported,
with a small Monte-Carlo ensemble for uncertainty estimation (windage and
vector magnitudes perturbed).
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core.geo import (
    bearing_deg,
    destination_point,
    haversine_km,
    resolve_bearing,
)
from ..schemas import (
    DriftPoint,
    DriftRequest,
    DriftTrack,
    EnvironmentalSeries,
)
from . import environment as envsvc

logger = logging.getLogger("app.services.drift")

WIND_DEFLECTION_DEG = 20.0  # empirical deflection of windage component (right of downwind)


def _label_from_series(series: EnvironmentalSeries, prefix: str):
    from ..schemas import DataSourceLabel
    return DataSourceLabel(
        dataClass="model" if series.dataClass == "model" else "synthetic",
        description=f"{prefix} Environmental forcing: {series.note}",
    )


@dataclass
class Vector:
    speed_kmh: float
    direction_deg: float  # direction the vector points TOWARDS


def combine(current: Optional[Vector], wind: Optional[Vector], windage: float) -> Vector:
    """drift = current + windage * wind (orthogonal component sum)."""
    cn = ce = wn = we = 0.0
    if current and current.speed_kmh > 0:
        th = math.radians(current.direction_deg)
        cn = current.speed_kmh * math.cos(th)
        ce = current.speed_kmh * math.sin(th)
    if wind and wind.speed_kmh > 0:
        wd = resolve_bearing(wind.direction_deg, WIND_DEFLECTION_DEG)
        th = math.radians(wd)
        wn = windage * wind.speed_kmh * math.cos(th)
        we = windage * wind.speed_kmh * math.sin(th)
    n, e = cn + wn, ce + we
    speed = math.hypot(n, e)
    direction = (math.degrees(math.atan2(e, n))) % 360.0 if speed > 1e-9 else 0.0
    return Vector(speed_kmh=speed, direction_deg=direction)


def _interp_vector(series: EnvironmentalSeries, t: datetime) -> tuple[Optional[Vector], Optional[Vector]]:
    """Nearest-neighbour lookup of current/wind at time t."""
    s = envsvc.sample_at(series, t)
    cur = Vector(s.current_speed_kmh, s.current_direction_deg) if s.current_speed_kmh is not None else None
    wind = Vector(s.wind_speed_kmh, s.wind_direction_deg) if s.wind_speed_kmh is not None else None
    return cur, wind


def _simulate(
    lat: float,
    lon: float,
    start: datetime,
    duration_hours: float,
    timestep_minutes: int,
    windage: float,
    series: EnvironmentalSeries,
    direction: int = 1,  # +1 forward, -1 backward
    perturb: Optional[random.Random] = None,
) -> list[DriftPoint]:
    """
    March the drift model. Backward mode negates the drift vector each step
    (time-reversed advection), which is the standard simple hindcast approach.
    """
    step_h = timestep_minutes / 60.0
    n_steps = int(round(duration_hours / step_h))
    points: list[DriftPoint] = []
    t = start
    clat, clon = lat, lon
    cumulative = 0.0

    for _ in range(n_steps + 1):
        cur, wind = _interp_vector(series, t)
        w = windage
        if perturb is not None:
            w *= perturb.uniform(0.5, 1.5)
        drift = combine(cur, wind, w)
        if perturb is not None and drift.speed_kmh > 0:
            drift = Vector(
                speed_kmh=drift.speed_kmh * perturb.uniform(0.8, 1.2),
                direction_deg=(drift.direction_deg + perturb.uniform(-15, 15)) % 360.0,
            )

        points.append(
            DriftPoint(
                timestamp=t.isoformat(),
                lat=round(clat, 5),
                lon=round(clon, 5),
                current_speed_kmh=cur.speed_kmh if cur else None,
                current_direction_deg=cur.direction_deg if cur else None,
                wind_speed_kmh=wind.speed_kmh if wind else None,
                wind_direction_deg=wind.direction_deg if wind else None,
                drift_speed_kmh=round(drift.speed_kmh, 3),
                drift_direction_deg=round(drift.direction_deg, 1),
                displacement_km=0.0,  # filled below
                cumulative_km=round(cumulative, 3),
            )
        )

        if _ >= n_steps:
            break

        # advance one timestep in the requested temporal direction
        move_bearing = drift.direction_deg if direction > 0 else (drift.direction_deg + 180.0) % 360.0
        dist = drift.speed_kmh * step_h
        if dist > 0:
            new_lat, new_lon = destination_point(clat, clon, move_bearing, dist)
            seg = haversine_km(clat, clon, new_lat, new_lon)
            cumulative += seg
            points[-1].displacement_km = round(seg, 3)
            clat, clon = new_lat, new_lon
        t = t + timedelta(minutes=timestep_minutes) * direction

    return points


def _parse_time(ts: Optional[str], default: datetime) -> datetime:
    if not ts:
        return default
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return default


def forecast(req: DriftRequest, series: Optional[EnvironmentalSeries] = None):
    """Forward drift simulation from (lat, lon) at start_time."""
    from ..schemas import ForecastResponse

    start = _parse_time(req.start_time, envsvc.now_utc())
    if series is None:
        series = envsvc.get_environment_series(
            req.lat, req.lon, start, start + timedelta(hours=req.duration_hours),
            step_minutes=max(60, req.timestep_minutes), prefer_real=not req.use_demo_environment,
        )

    points = _simulate(
        req.lat, req.lon, start, req.duration_hours, req.timestep_minutes,
        req.windage, series, direction=+1,
    )

    # Monte-Carlo ensemble for end-point uncertainty
    rng = random.Random(1234)
    end_positions = []
    for _ in range(min(req.ensemble_members, 100)):
        pts = _simulate(
            req.lat, req.lon, start, req.duration_hours, max(req.timestep_minutes, 60),
            req.windage, series, direction=+1, perturb=rng,
        )
        if pts:
            end_positions.append((pts[-1].lat, pts[-1].lon))
    last = points[-1]
    if end_positions:
        spread = max(haversine_km(last.lat, last.lon, la, lo) for la, lo in end_positions)
        uncertainty = round(spread, 2)
    else:
        uncertainty = 0.0

    return ForecastResponse(
        request=req,
        track=DriftTrack(points=points),
        end_position={"lat": last.lat, "lon": last.lon},
        total_displacement_km=round(
            haversine_km(req.lat, req.lon, last.lat, last.lon), 3
        ),
        uncertainty_radius_km=uncertainty,
        environment=series,
        method=(
            "Euler forward advection: drift = current + windage*wind "
            f"(windage={req.windage}, dt={req.timestep_minutes}min, "
            f"{len(end_positions)}-member ensemble)"
        ),
        source_label=_label_from_series(series, "Physically-based drift simulation."),
    )


def hindcast(
    req: DriftRequest,
    series: Optional[EnvironmentalSeries] = None,
    origin_time_hint: Optional[str] = None,
):
    """
    Backward drift simulation: estimates where a spill OBSERVED at
    (lat, lon, start_time) likely ORIGINATED, by time-reversing the drift.
    """
    from ..schemas import HindcastResponse

    start = _parse_time(req.start_time, envsvc.now_utc())
    if series is None:
        series = envsvc.get_environment_series(
            req.lat, req.lon, start - timedelta(hours=req.duration_hours), start,
            step_minutes=max(60, req.timestep_minutes), prefer_real=not req.use_demo_environment,
        )

    points = _simulate(
        req.lat, req.lon, start, req.duration_hours, req.timestep_minutes,
        req.windage, series, direction=-1,
    )
    # points are ordered observation → oldest (that IS the backward path)
    origin = points[-1]

    # Ensemble uncertainty for the origin
    rng = random.Random(4321)
    origins = []
    for _ in range(min(req.ensemble_members, 100)):
        pts = _simulate(
            req.lat, req.lon, start, req.duration_hours, max(req.timestep_minutes, 60),
            req.windage, series, direction=-1, perturb=rng,
        )
        if pts:
            origins.append((pts[-1].lat, pts[-1].lon))
    if origins:
        spread = max(haversine_km(origin.lat, origin.lon, la, lo) for la, lo in origins)
        uncertainty = round(spread, 2)
        # simple confidence: tighter ensemble relative to total travel → higher
        travel = haversine_km(req.lat, req.lon, origin.lat, origin.lon)
        conf = max(0.2, min(0.9, 1.0 - (uncertainty / (travel + uncertainty)) * 1.4))
    else:
        uncertainty, conf = 0.0, 0.5

    origin_time = (start - timedelta(hours=req.duration_hours)).isoformat()

    return HindcastResponse(
        request=req,
        track=DriftTrack(points=points),
        origin_location={"lat": origin.lat, "lon": origin.lon},
        origin_time=origin_time,
        estimated_release_window_hours=req.duration_hours,
        uncertainty_radius_km=uncertainty,
        confidence=round(conf, 2),
        environment=series,
        method=(
            "Time-reversed advection (Euler, backward): the observed slick is "
            "stepped backwards using drift = current + windage*wind with "
            f"{len(origins)}-member perturbed ensemble for uncertainty."
        ),
        disclaimer=(
            "The estimated origin is a MODEL ESTIMATE, not a guaranteed fact. "
            "Real spills spread, weather and dissipate; this simple advection "
            "hindcast carries significant uncertainty."
        ),
        source_label=_label_from_series(series, "Backward drift simulation."),
    )
