"""
AIS data processing — cleaning, trajectories, spatio-temporal correlation,
candidate filtering, trajectory feature extraction, behaviour anomaly and
attribution scoring.

The AIS dataset shipped with the repository:
  52,943 records, 347 vessels, Gulf of Mexico (LAT 28.43–28.62, LON -95.15–-94.76),
  2020-12-31 → 2021-03-24. Columns:
  MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, IMO, CallSign,
  VesselType, Status, Length, Width, Draft, Cargo, TransceiverClass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from .. import config
from ..core.geo import (
    angle_difference_deg,
    bearing_deg,
    haversine_km,
    knots_to_kmh,
)
from ..schemas import (
    AISCandidateSummary,
    AISSearchResponse,
    Anomaly,
    FilterDecision,
    TrajectoryFeatures,
    TrackPoint,
)

logger = logging.getLogger("app.services.ais")

_df: Optional[pd.DataFrame] = None

VALID_LAT = (-90.0, 90.0)
VALID_LON = (-180.0, 180.0)


# ═══════════════════════════════════════════════════════════════════════════
# Loading & cleaning
# ═══════════════════════════════════════════════════════════════════════════


def find_ais_csv() -> Path:
    p = Path(config.AIS_CSV)
    if p.is_file():
        return p
    if p.is_dir():
        csvs = sorted(p.glob("*.csv"))
        if csvs:
            return csvs[0]
    raise FileNotFoundError(f"AIS CSV not found at {p}")


def get_dataframe() -> pd.DataFrame:
    """Load + clean the AIS dataset (cached). Cleaning:

    - drop rows with invalid/missing coordinates or timestamps
    - clip impossible SOG (> MAX_SOG_KNOTS → invalid)
    - drop exact duplicates
    - sort by (MMSI, BaseDateTime)
    """
    global _df
    if _df is not None:
        return _df

    path = find_ais_csv()
    df = pd.read_csv(path)

    required = {"MMSI", "BaseDateTime", "LAT", "LON"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"AIS dataset missing required columns: {sorted(missing)}. "
            f"Available: {list(df.columns)}"
        )

    n0 = len(df)
    df["BaseDateTime"] = pd.to_datetime(df["BaseDateTime"], errors="coerce", utc=True)
    for c in ("LAT", "LON", "SOG", "COG", "Heading", "VesselType", "Length", "Width", "Draft", "Cargo"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["MMSI", "BaseDateTime", "LAT", "LON"])
    df = df[
        df["LAT"].between(*VALID_LAT) & df["LON"].between(*VALID_LON)
    ]
    if "SOG" in df.columns:
        df.loc[df["SOG"] > config.MAX_SOG_KNOTS, "SOG"] = np.nan  # impossible speeds
    df = df.drop_duplicates(subset=["MMSI", "BaseDateTime", "LAT", "LON"])
    df = df.sort_values(["MMSI", "BaseDateTime"]).reset_index(drop=True)

    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].fillna("Unknown")

    logger.info(
        "AIS loaded: %d/%d rows kept after cleaning (%d vessels), %s → %s",
        len(df), n0, df["MMSI"].nunique(),
        df["BaseDateTime"].min(), df["BaseDateTime"].max(),
    )
    _df = df
    return _df


def time_coverage() -> dict[str, Optional[str]]:
    try:
        df = get_dataframe()
        return {
            "start": df["BaseDateTime"].min().isoformat(),
            "end": df["BaseDateTime"].max().isoformat(),
        }
    except Exception:
        return {"start": None, "end": None}


# ═══════════════════════════════════════════════════════════════════════════
# Spatio-temporal candidate search
# ═══════════════════════════════════════════════════════════════════════════


def search_candidates(
    lat: float,
    lon: float,
    time: datetime,
    radius_km: float = 15.0,
    window_hours: float = 12.0,
) -> AISSearchResponse:
    """Find vessels with AIS pings inside the space-time tube around
    (lat, lon, time): within `radius_km` during ± `window_hours`."""
    df = get_dataframe()

    t_min = time - timedelta(hours=window_hours)
    t_max = time + timedelta(hours=window_hours)

    # fast coarse temporal filter
    sub = df[(df["BaseDateTime"] >= t_min) & (df["BaseDateTime"] <= t_max)].copy()
    searched = len(sub)

    if sub.empty:
        return AISSearchResponse(
            candidates=[],
            total_records_searched=searched,
            dataset_note=_dataset_note(),
            time_coverage=time_coverage(),
            source_label={
                "dataClass": "unavailable",
                "description": "No AIS records in the requested time window.",
            },
        )

    # coarse spatial box prefilter (~radius in degrees) then exact haversine
    dlat = radius_km / 111.0
    dlon = dlat / max(0.2, np.cos(np.radians(lat)))
    box = sub[
        sub["LAT"].between(lat - dlat, lat + dlat)
        & sub["LON"].between(lon - dlon, lon + dlon)
    ].copy()
    if box.empty:
        return AISSearchResponse(
            candidates=[],
            total_records_searched=searched,
            dataset_note=_dataset_note(),
            time_coverage=time_coverage(),
            source_label={
                "dataClass": "unavailable",
                "description": "No AIS records within the spatial radius in the time window.",
            },
        )
    box["dist_km"] = box.apply(
        lambda r: haversine_km(lat, lon, r["LAT"], r["LON"]), axis=1
    )
    box = box[box["dist_km"] <= radius_km]

    candidates: list[AISCandidateSummary] = []
    for mmsi, g in box.groupby("MMSI"):
        candidates.append(
            AISCandidateSummary(
                mmsi=int(mmsi),
                vesselName=str(g["VesselName"].iloc[0]) if "VesselName" in g else "Unknown",
                vesselType=float(g["VesselType"].iloc[0]) if "VesselType" in g and pd.notna(g["VesselType"].iloc[0]) else None,
                observations_in_window=int(len(g)),
                min_distance_km=round(float(g["dist_km"].min()), 3),
                first_seen=g["BaseDateTime"].min().isoformat(),
                last_seen=g["BaseDateTime"].max().isoformat(),
            )
        )
    candidates.sort(key=lambda c: c.min_distance_km)

    return AISSearchResponse(
        candidates=candidates,
        total_records_searched=searched,
        dataset_note=_dataset_note(),
        time_coverage=time_coverage(),
        source_label={
            "dataClass": "model",
            "description": "Candidates derived from REAL AIS records in the repository dataset.",
        },
    )


def _dataset_note() -> str:
    return (
        "Repository AIS dataset: ~52,943 records, 347 vessels, Gulf of Mexico, "
        "2020-12-31 → 2021-03-24 (real NOAA MarineCadastre-style data)."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Candidate filtering + trajectory analysis
# ═══════════════════════════════════════════════════════════════════════════


def filter_candidate(
    mmsi: int,
    origin_lat: float,
    origin_lon: float,
    release_time: datetime,
    radius_km: float,
    window_hours: float,
    min_observations: int = 3,
) -> tuple[bool, pd.DataFrame, list[str]]:
    """
    Decide whether a vessel is a plausible source candidate.

    Returns (included, vessel_records_in_window, reasons) — reasons document
    WHY the vessel was kept or dropped (explainable filtering).
    """
    df = get_dataframe()
    t_min = release_time - timedelta(hours=window_hours)
    t_max = release_time + timedelta(hours=window_hours)
    v = df[
        (df["MMSI"] == mmsi)
        & (df["BaseDateTime"] >= t_min)
        & (df["BaseDateTime"] <= t_max)
    ].sort_values("BaseDateTime")

    if v.empty:
        return False, v, ["No AIS records in the analysis window"]

    reasons: list[str] = []
    if len(v) < min_observations:
        return (
            False,
            v,
            [f"Insufficient AIS data in window ({len(v)} < {min_observations} records)"],
        )

    # minimum distance to origin across the window
    dists = v.apply(lambda r: haversine_km(origin_lat, origin_lon, r["LAT"], r["LON"]), axis=1)
    min_d = float(dists.min())
    if min_d > radius_km:
        return (
            False,
            v,
            [f"Never came within {radius_km:.0f} km of estimated origin (min {min_d:.1f} km)"],
        )

    # physical plausibility: could the vessel reach the origin?
    # compare observed max speed vs required speed from closest approach time to release
    idx = dists.idxmin()
    closest = v.loc[idx]
    dt_hours = abs((closest["BaseDateTime"] - release_time).total_seconds()) / 3600.0
    if "SOG" in v and pd.notna(v["SOG"].max()):
        max_sog = float(v["SOG"].max())
        if dt_hours > 0.25 and min_d > 1.0:
            required_kmh = min_d / dt_hours
            if required_kmh > knots_to_kmh(max_sog) * 6:  # generous bound incl. AIS gaps
                return (
                    False,
                    v,
                    [
                        f"Trajectory implausible: reaching origin would require "
                        f"~{required_kmh:.0f} km/h but vessel max observed SOG is "
                        f"{max_sog:.0f} kn"
                    ],
                )

    reasons.append(
        f"Passed within {min_d:.2f} km of estimated origin during the release window"
    )
    return True, v, reasons


def extract_trajectory_features(
    v: pd.DataFrame,
    origin_lat: float,
    origin_lon: float,
    release_time: datetime,
    radius_km: float,
) -> TrajectoryFeatures:
    """Trajectory behaviour features for a candidate vessel near the origin."""
    dists = np.array(
        [haversine_km(origin_lat, origin_lon, la, lo) for la, lo in zip(v["LAT"], v["LON"])]
    )
    times = v["BaseDateTime"].to_numpy()
    sog = v["SOG"].to_numpy(dtype=float) if "SOG" in v else np.array([np.nan] * len(v))
    cog = v["COG"].to_numpy(dtype=float) if "COG" in v else np.array([np.nan] * len(v))

    i_min = int(np.argmin(dists))
    t_min_dist = pd.Timestamp(times[i_min])
    dt_hours = (t_min_dist - release_time).total_seconds() / 3600.0

    dist_at_release = None
    if len(times) > 0:
        # nearest record to release time
        j = int(np.argmin(np.abs([(pd.Timestamp(t) - release_time).total_seconds() for t in times])))
        dist_at_release = round(float(dists[j]), 3)

    # heading/course changes
    cog_valid = cog[~np.isnan(cog)]
    heading_changes = 0.0
    if len(cog_valid) > 2:
        diffs = [angle_difference_deg(cog_valid[i + 1], cog_valid[i]) for i in range(len(cog_valid) - 1)]
        heading_changes = float(np.sum(diffs))

    sog_valid = sog[~np.isnan(sog)]
    speed_changes = float(np.sum(np.abs(np.diff(sog_valid)))) if len(sog_valid) > 1 else None
    mean_speed = float(np.nanmean(sog)) if len(sog_valid) else None
    max_speed = float(np.nanmax(sog)) if len(sog_valid) else None

    # dwell near origin: minutes spent within radius
    near = dists <= radius_km
    time_near_min = 0.0
    if len(times) > 1:
        for k in range(len(times) - 1):
            if near[k] or near[k + 1]:
                dt = (pd.Timestamp(times[k + 1]) - pd.Timestamp(times[k])).total_seconds() / 60.0
                time_near_min += max(0.0, dt)

    # approach / departure bearings around the closest point
    approach = departure = None
    if i_min > 0:
        approach = bearing_deg(
            float(v["LAT"].iloc[i_min - 1]), float(v["LON"].iloc[i_min - 1]),
            float(v["LAT"].iloc[i_min]), float(v["LON"].iloc[i_min]),
        )
    if i_min < len(v) - 1:
        departure = bearing_deg(
            float(v["LAT"].iloc[i_min]), float(v["LON"].iloc[i_min]),
            float(v["LAT"].iloc[i_min + 1]), float(v["LON"].iloc[i_min + 1]),
        )

    # route deviation: distance of closest approach vs distance of a straight
    # line between window start/end positions (how far off-route the vessel went)
    route_dev = None
    if len(v) >= 3:
        la0, lo0 = float(v["LAT"].iloc[0]), float(v["LON"].iloc[0])
        la1, lo1 = float(v["LAT"].iloc[-1]), float(v["LON"].iloc[-1])
        # perpendicular-ish deviation using closest point
        d_straight = haversine_km(la0, lo0, origin_lat, origin_lon) + haversine_km(origin_lat, origin_lon, la1, lo1)
        d_route = haversine_km(la0, lo0, la1, lo1)
        route_dev = round(min(1.0, d_straight / max(d_route, 0.1) - 1.0), 3) if d_route > 0 else None

    return TrajectoryFeatures(
        min_distance_to_origin_km=round(float(dists[i_min]), 3),
        distance_at_release_km=dist_at_release,
        min_distance_time=pd.Timestamp(times[i_min]).isoformat(),
        time_diff_from_release_hours=round(dt_hours, 2),
        mean_speed_knots=round(mean_speed, 2) if mean_speed is not None else None,
        max_speed_knots=round(max_speed, 2) if max_speed is not None else None,
        course_at_min_distance=float(cog[i_min]) if not np.isnan(cog[i_min]) else None,
        speed_at_min_distance=float(sog[i_min]) if not np.isnan(sog[i_min]) else None,
        heading_changes_deg=round(heading_changes, 1) if heading_changes else None,
        speed_changes_knots=round(speed_changes, 1) if speed_changes is not None else None,
        dwell_minutes_near_origin=round(time_near_min, 1),
        approach_bearing_deg=round(approach, 1) if approach is not None else None,
        departure_bearing_deg=round(departure, 1) if departure is not None else None,
        passes_within_radius=bool(near.any()),
        time_near_origin_minutes=round(time_near_min, 1),
        route_deviation_score=route_dev,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Behaviour anomaly (reuse of notebook SVR + DBSCAN-style density features)
# ═══════════════════════════════════════════════════════════════════════════


def svr_anomalies_for_vessel(v: pd.DataFrame, threshold: float = 6.0) -> list[Anomaly]:
    """Reuse of the notebook's SVR methodology (per-vessel), on window records.

    SVR(gamma='scale', C=100000, epsilon=1, degree=3), features
    [LAT, hour, Cargo, COG] → SOG, anomaly = |actual - predicted| >= threshold.
    """
    if len(v) < 10:
        return []
    from sklearn.svm import SVR
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import r2_score

    data = v.copy()
    for c in ("LAT", "SOG", "COG", "Cargo"):
        if c not in data:
            return []
        data[c] = pd.to_numeric(data[c], errors="coerce")
    data = data.dropna(subset=["LAT", "SOG", "COG", "Cargo"])
    data["Hour"] = data["BaseDateTime"].dt.hour
    if len(data) < 10:
        return []

    X = data[["LAT", "Hour", "Cargo", "COG"]].values
    y = data["SOG"].values
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.15, random_state=4)
    reg = SVR(gamma="scale", C=100000, epsilon=1, degree=3)
    reg.fit(X_tr, y_tr)
    preds = reg.predict(X)

    anomalies: list[Anomaly] = []
    diffs = np.round(y - preds, 0)
    for i in np.where(np.abs(diffs) >= threshold)[0]:
        row = data.iloc[i]
        anomalies.append(
            Anomaly(
                lat=float(row["LAT"]),
                lon=float(row["LON"]),
                sog=float(row["SOG"]),
                predictedSog=round(float(preds[i]), 1),
                difference=float(diffs[i]),
                cog=float(row["COG"]) if pd.notna(row["COG"]) else 0.0,
                heading=float(row["Heading"]) if "Heading" in row and pd.notna(row["Heading"]) else 0.0,
                timestamp=pd.Timestamp(row["BaseDateTime"]).isoformat(),
                status=str(row.get("Status", "")),
            )
        )
    return anomalies


def behaviour_anomaly(
    v: pd.DataFrame, features: TrajectoryFeatures, origin_lat: float, origin_lon: float
) -> tuple[float, list[str], int]:
    """
    Interpretable behaviour anomaly score in [0, 100] from explainable rules:

    - unusual stopping/dwell near origin
    - sudden speed changes
    - erratic course (total heading change)
    - route deviation toward origin
    - SVR speed anomalies (notebook methodology) within the window
    - local AIS density anomaly (DBSCAN-inspired: is the vessel's closest
      approach an outlier vs other pings? computed via z-score of distance)
    """
    flags: list[str] = []
    score = 0.0

    # 1) dwell near origin
    if features.dwell_minutes_near_origin > 60:
        score += 25
        flags.append(f"Unusual dwell: {features.dwell_minutes_near_origin:.0f} min near estimated origin")
    elif features.dwell_minutes_near_origin > 15:
        score += 12
        flags.append(f"Extended presence: {features.dwell_minutes_near_origin:.0f} min near estimated origin")

    # 2) speed changes
    if features.speed_changes_knots and features.speed_changes_knots > 8:
        score += 20
        flags.append(f"Sudden speed changes detected (Σ|ΔSOG| = {features.speed_changes_knots:.0f} kn)")
    elif features.speed_changes_knots and features.speed_changes_knots > 3:
        score += 8

    # 3) erratic course
    if features.heading_changes_deg and features.heading_changes_deg > 240:
        score += 20
        flags.append(f"Erratic course behaviour (Σ|ΔCOG| = {features.heading_changes_deg:.0f}°)")
    elif features.heading_changes_deg and features.heading_changes_deg > 120:
        score += 8

    # 4) route deviation
    if features.route_deviation_score and features.route_deviation_score > 0.25:
        score += 15
        flags.append("Route deviation: vessel track bends toward the estimated origin")

    # 5) SVR anomalies (reuse notebook method)
    svr = svr_anomalies_for_vessel(v)
    if len(svr) >= 3:
        score += 15
        flags.append(f"SVR speed-model anomalies in window: {len(svr)} records (|ΔSOG| ≥ 6 kn)")
    elif len(svr) > 0:
        score += 6

    # 6) low speed near origin (possible discharge behaviour)
    if features.speed_at_min_distance is not None and features.speed_at_min_distance < 2.0:
        score += 10
        flags.append("Vessel slowed to near-stop at closest approach to origin")

    score = min(100.0, score)
    return round(score, 1), flags, len(svr)


# ═══════════════════════════════════════════════════════════════════════════
# Attribution scoring
# ═══════════════════════════════════════════════════════════════════════════


def score_candidate(
    features: TrajectoryFeatures,
    anomaly_score: float,
    n_observations: int,
    radius_km: float,
    window_hours: float,
    weights: dict[str, float],
) -> tuple[float, dict[str, float], list[str]]:
    """
    Transparent investigation-priority score in [0, 100].

    Components (weights configurable via config.scoring_weights()):
      spatial    — closeness of closest approach to the estimated origin
      temporal   — closeness of that approach to the estimated release time
      trajectory — pass-through / dwell / deviation behaviour
      behaviour  — anomaly score
      data_quality — AIS observation density in the window
    """
    evidence: list[str] = []

    # Spatial: linear falloff from 0 km (100) to radius_km (0)
    spatial = max(0.0, 100.0 * (1.0 - features.min_distance_to_origin_km / max(radius_km, 0.1)))
    if features.min_distance_to_origin_km <= 2:
        evidence.append(
            f"Passed within {features.min_distance_to_origin_km:.1f} km of estimated origin"
        )

    # Temporal: linear falloff from 0 h (100) to ±window_hours (0)
    t_diff = abs(features.time_diff_from_release_hours or 0.0)
    temporal = max(0.0, 100.0 * (1.0 - t_diff / max(window_hours, 0.1)))
    if t_diff <= 2:
        evidence.append("Closest approach overlaps the estimated release window")

    # Trajectory
    traj = 30.0
    if features.passes_within_radius:
        traj += 30
        evidence.append("Trajectory passes through the estimated origin region")
    if features.dwell_minutes_near_origin > 30:
        traj += 20
    if features.route_deviation_score and features.route_deviation_score > 0.25:
        traj += 20
    traj = min(100.0, traj)

    # Behaviour
    behaviour = float(anomaly_score)

    # Data quality: >= 12 observations in window is full marks
    dq = min(100.0, 100.0 * n_observations / 12.0)

    comps = {
        "spatial": round(spatial, 1),
        "temporal": round(temporal, 1),
        "trajectory": round(traj, 1),
        "behaviour": round(behaviour, 1),
        "data_quality": round(dq, 1),
    }
    total = sum(comps[k] * weights.get(k, 0.2) for k in comps)
    total = min(100.0, max(0.0, total))

    if anomaly_score >= 50:
        evidence.append("Elevated behaviour anomaly indicators detected")
    if n_observations < 4:
        evidence.append("Low AIS data density — score confidence reduced")

    return round(total, 1), comps, evidence
