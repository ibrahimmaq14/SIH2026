"""Geographic math utilities. All distance/bearing/displacement calculations go through here."""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
KM_PER_NM = 1.852
KNOTS_PER_M_PER_S = 1.943844  # 1 m/s = 1.943844 knots


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees in [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination_point(lat: float, lon: float, bearing: float, distance_km: float) -> tuple[float, float]:
    """
    Move from (lat, lon) along `bearing` (degrees clockwise from north) for
    `distance_km` kilometres. Returns the new (lat, lon).

    Uses the great-circle destination formula — never naively adds deltas to
    lat/lon.
    """
    if distance_km == 0:
        return lat, lon
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing)
    phi1 = math.radians(lat)
    lmb1 = math.radians(lon)

    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    lmb2 = lmb1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * sin_phi2,
    )
    return math.degrees(phi2), math.degrees((lmb2 + math.pi) % (2 * math.pi) - math.pi)


def displacement_components(
    lat: float, lon: float, vector_bearing: float, speed_kmh: float, hours: float
) -> tuple[float, float]:
    """Displacement (dlat, dlon) in degrees caused by a vector over `hours`."""
    if speed_kmh <= 0 or hours == 0:
        return 0.0, 0.0
    dist_km = speed_kmh * hours
    new_lat, new_lon = destination_point(lat, lon, vector_bearing, dist_km)
    return new_lat - lat, new_lon - lon


def resolve_bearing(current_bearing: float, relative_bearing: float) -> float:
    """Add a relative bearing (e.g. wind-driven deflection) to a current bearing."""
    return (current_bearing + relative_bearing) % 360.0


@dataclass(frozen=True)
class GeoVector:
    """A velocity vector at a geographic location, meteorological oceanographic convention.

    direction_deg: direction the vector points TOWARDS (0 = north, 90 = east).
    speed_kmh: magnitude in km/h. (Use knots/kmh converters as needed.)
    """

    direction_deg: float
    speed_kmh: float

    def to_orthogonal(self, lat: float) -> tuple[float, float]:
        """Approximate (north_km, east_km) components at latitude `lat`."""
        # For short steps this is used only for reporting, not displacement.
        north = self.speed_kmh * math.cos(math.radians(self.direction_deg))
        east = self.speed_kmh * math.sin(math.radians(self.direction_deg))
        return north, east


def knots_to_kmh(knots: float) -> float:
    return knots * KM_PER_NM


def kmh_to_knots(kmh: float) -> float:
    return kmh / KM_PER_NM


def mps_to_kmh(mps: float) -> float:
    return mps * 3600.0 / 1000.0


def mps_to_knots(mps: float) -> float:
    return mps * KNOTS_PER_M_PER_S


def angle_difference_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in [0, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return abs(d)


def clamp_lat(lat: float) -> float:
    return max(-90.0, min(90.0, lat))


def clamp_lon(lon: float) -> float:
    # wrap into [-180, 180)
    return (lon + 180.0) % 360.0 - 180.0
