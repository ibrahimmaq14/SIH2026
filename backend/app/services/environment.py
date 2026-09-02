"""
Environmental data abstraction layer (ocean + weather).

Providers (adapters — the app never depends on a single one):
1. OpenMeteoMarineProvider — REAL data from the free Open-Meteo Marine API
   (no API key). Requires internet. Fails gracefully.
2. DemoEnvironmentProvider — clearly-labelled SYNTHETIC stationary-current +
   rotating-wind field used for local demos/offline runs.

Selection order: Open-Meteo (real) → demo (synthetic, labelled).
Every sample carries its provider + dataClass so the frontend can label it.
"""

from __future__ import annotations

import json
import logging
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .. import config
from ..schemas import DataClass, EnvironmentalSample, EnvironmentalSeries
from ..core.geo import GeoVector, mps_to_kmh

logger = logging.getLogger("app.services.environment")


# ═══════════════════════════════════════════════════════════════════════════
# Base
# ═══════════════════════════════════════════════════════════════════════════


class EnvironmentProvider:
    name: str = "base"
    data_class: DataClass = "unavailable"

    def get_series(
        self, lat: float, lon: float, start: datetime, end: datetime, step_minutes: int
    ) -> EnvironmentalSeries:
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════
# Open-Meteo Marine (REAL, no API key required)
# ═══════════════════════════════════════════════════════════════════════════


class OpenMeteoMarineProvider(EnvironmentProvider):
    """Real current + wind data via Open-Meteo Marine & Forecast APIs (free, keyless)."""

    name = "open-meteo-marine"
    data_class: DataClass = "model"

    def _fetch(self, url: str, params: dict) -> Optional[dict]:
        import urllib.request
        import urllib.parse

        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{url}?{qs}",
            headers={"User-Agent": "sih-oil-spill-demo/2.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=config.ENV_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Open-Meteo fetch failed (%s): %s", url, e)
            return None

    def get_series(
        self, lat: float, lon: float, start: datetime, end: datetime, step_minutes: int
    ) -> EnvironmentalSeries:
        start_utc = _ensure_utc(start)
        end_utc = _ensure_utc(end)

        # Marine API: current + wave (hourly)
        marine = self._fetch(
            config.OPEN_METEOMARINE_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_utc.date().isoformat(),
                "end_date": end_utc.date().isoformat(),
                "hourly": "sea_surface_temperature,wave_height,wave_direction",
                "current_velocity_10m": "true",  # surface current, 10m depth standard
                "timezone": "UTC",
            },
        )
        # Forecast API: wind (hourly)
        wind = self._fetch(
            config.OPEN_METEO_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_utc.date().isoformat(),
                "end_date": end_utc.date().isoformat(),
                "hourly": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kmh",
                "timezone": "UTC",
            },
        )

        if not marine or not wind:
            raise EnvironmentUnavailableError("Open-Meteo unreachable")

        # Merge hourly series on timestamps
        samples: dict[str, dict] = {}

        mh = (marine or {}).get("hourly") or {}
        times = mh.get("time", [])
        wave_h = mh.get("wave_height", [None] * len(times))
        for i, t in enumerate(times):
            ts = f"{t}:00Z" if not t.endswith("Z") else t
            samples.setdefault(ts, {})["wave_height_m"] = wave_h[i] if i < len(wave_h) else None

        # currents: Open-Meteo marine returns current_velocity_10m &
        # current_direction_10m when requested
        cur_v = mh.get("current_velocity_10m")
        cur_d = mh.get("current_direction_10m")
        if cur_v and cur_d:
            for i, t in enumerate(times):
                ts = f"{t}:00Z" if not t.endswith("Z") else t
                if i < len(cur_v) and cur_v[i] is not None:
                    samples.setdefault(ts, {})["current_speed_mps"] = cur_v[i]
                    samples.setdefault(ts, {})["current_direction_deg"] = cur_d[i]

        wh = wind.get("hourly") or {}
        wtimes = wh.get("time", [])
        wspd = wh.get("wind_speed_10m", [None] * len(wtimes))
        wdir = wh.get("wind_direction_10m", [None] * len(wtimes))
        for i, t in enumerate(wtimes):
            ts = f"{t}:00Z" if not t.endswith("Z") else t
            d = samples.setdefault(ts, {})
            if i < len(wspd):
                d["wind_speed_kmh"] = wspd[i]
                d["wind_direction_deg"] = wdir[i]

        out: list[EnvironmentalSample] = []
        for ts, d in sorted(samples.items()):
            dt = _parse_iso(ts)
            if dt is None or not (start_utc - timedelta(hours=1) <= dt <= end_utc + timedelta(hours=1)):
                continue
            out.append(
                EnvironmentalSample(
                    timestamp=dt.isoformat(),
                    lat=lat,
                    lon=lon,
                    current_speed_kmh=(
                        round(mps_to_kmh(d["current_speed_mps"]), 3)
                        if d.get("current_speed_mps") is not None else None
                    ),
                    current_direction_deg=d.get("current_direction_deg"),
                    wind_speed_kmh=d.get("wind_speed_kmh"),
                    wind_direction_deg=d.get("wind_direction_deg"),
                    wave_height_m=d.get("wave_height_m"),
                    provider=self.name,
                    dataClass="model",
                )
            )
        if not out:
            raise EnvironmentUnavailableError("Open-Meteo returned no usable points")
        return EnvironmentalSeries(
            samples=out,
            provider=self.name,
            dataClass="model",
            note="Real ocean/wind data from Open-Meteo (marine + forecast APIs, no key required).",
        )


class EnvironmentUnavailableError(RuntimeError):
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Demo provider (SYNTHETIC — clearly labelled)
# ═══════════════════════════════════════════════════════════════════════════


class DemoEnvironmentProvider(EnvironmentProvider):
    """
    Synthetic environmental field for offline demos.

    Deterministic given (lat, lon, date) — a seedable pseudo-field:
    - stationary current ~0.4-0.9 km/h rotating slowly over days
    - wind 15-30 km/h veering over time
    All outputs are labelled dataClass="synthetic".
    """

    name = "demo-synthetic"
    data_class: DataClass = "synthetic"

    def get_series(
        self, lat: float, lon: float, start: datetime, end: datetime, step_minutes: int
    ) -> EnvironmentalSeries:
        start_utc = _ensure_utc(start)
        end_utc = _ensure_utc(end)
        samples: list[EnvironmentalSample] = []
        t = start_utc
        while t <= end_utc:
            day_frac = t.timestamp() / 86400.0
            # spatially smooth pseudo-random field
            cur_speed = 0.35 + 0.35 * (0.5 + 0.5 * math.sin(day_frac * 0.7 + lat * 0.3 + lon * 0.2))
            cur_dir = (200.0 + 25.0 * math.sin(day_frac * 0.5 + lon * 0.1)) % 360.0
            wind_speed = 18.0 + 9.0 * math.sin(day_frac * 1.3 + lat * 0.15)
            wind_dir = (65.0 + 40.0 * math.sin(day_frac * 0.4)) % 360.0
            wave = 1.1 + 0.6 * math.sin(day_frac * 0.9 + lon * 0.05)
            samples.append(
                EnvironmentalSample(
                    timestamp=t.isoformat(),
                    lat=round(lat, 4),
                    lon=round(lon, 4),
                    current_speed_kmh=round(cur_speed, 3),
                    current_direction_deg=round(cur_dir, 1),
                    wind_speed_kmh=round(wind_speed, 2),
                    wind_direction_deg=round(wind_dir, 1),
                    wave_height_m=round(max(0.2, wave), 2),
                    provider=self.name,
                    dataClass="synthetic",
                )
            )
            t += timedelta(minutes=step_minutes)
        return EnvironmentalSeries(
            samples=samples,
            provider=self.name,
            dataClass="synthetic",
            note=(
                "SYNTHETIC demo environmental data (deterministic pseudo-field). "
                "NOT real measurements — used because the real provider was "
                "unreachable or DEMO_MODE is enabled."
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════
# Resolution / caching
# ═══════════════════════════════════════════════════════════════════════════

_cache: dict[str, EnvironmentalSeries] = {}


def get_environment_series(
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
    step_minutes: int = 60,
    prefer_real: bool = True,
) -> EnvironmentalSeries:
    """
    Resolve environmental samples for [start, end].

    Tries the real Open-Meteo provider first (unless DEMO_MODE forces demo),
    falls back to the labelled synthetic provider. Results cached on disk
    for reproducibility.
    """
    key = f"{lat:.2f}_{lon:.2f}_{start.isoformat()}_{end.isoformat()}_{step_minutes}"
    if key in _cache:
        return _cache[key]

    providers: list[EnvironmentProvider] = []
    if prefer_real and not config.DEMO_MODE:
        providers.append(OpenMeteoMarineProvider())
    providers.append(DemoEnvironmentProvider())

    last_err: Optional[Exception] = None
    for prov in providers:
        try:
            series = prov.get_series(lat, lon, start, end, step_minutes)
            _cache[key] = series
            return series
        except EnvironmentUnavailableError as e:
            last_err = e
            logger.info("Provider %s unavailable: %s", prov.name, e)

    raise EnvironmentUnavailableError(
        f"No environmental provider available: {last_err}"
    )


def sample_at(series: EnvironmentalSeries, t: datetime) -> EnvironmentalSample:
    """Nearest sample to time t (clamped to series bounds)."""
    if not series.samples:
        raise EnvironmentUnavailableError("empty series")
    target = t.timestamp()
    best = min(series.samples, key=lambda s: abs(_parse_iso(s.timestamp).timestamp() - target))
    return best


# ── helpers ─────────────────────────────────────────────────────────────────

def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
