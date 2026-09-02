"""
Attribution engine — orchestrates candidate search → filtering → trajectory
analysis → anomaly detection → transparent scoring → ranked vessels.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from .. import config
from ..schemas import (
    AttributionResponse,
    BehaviourAnalysis,
    CandidateVessel,
    ScoreComponents,
    TrackPoint,
)
from . import ais as aissvc

logger = logging.getLogger("app.services.attribution")


def run_attribution(
    origin_lat: float,
    origin_lon: float,
    release_time: datetime,
    radius_km: float = 15.0,
    window_hours: float = 12.0,
    uncertainty_km: float = 0.0,
    max_candidates: int = 8,
    weights: Optional[dict[str, float]] = None,
) -> AttributionResponse:
    weights = weights or config.scoring_weights()
    # widen the search radius by hindcast uncertainty (fuzzy tube)
    search_radius = radius_km + uncertainty_km

    search = aissvc.search_candidates(origin_lat, origin_lon, release_time, search_radius, window_hours)
    included: list[CandidateVessel] = []
    excluded: list[dict[str, Any]] = []

    for cand in search.candidates:
        ok, v, reasons = aissvc.filter_candidate(
            cand.mmsi, origin_lat, origin_lon, release_time,
            search_radius, window_hours, config.MIN_AIS_OBSERVATIONS,
        )
        if not ok:
            excluded.append({
                "mmsi": cand.mmsi,
                "vesselName": cand.vesselName,
                "reason": "; ".join(reasons),
            })
            continue

        feats = aissvc.extract_trajectory_features(v, origin_lat, origin_lon, release_time, search_radius)
        anomaly_score, flags, svr_count = aissvc.behaviour_anomaly(v, feats, origin_lat, origin_lon)
        score, comps, evidence = aissvc.score_candidate(
            feats, anomaly_score, len(v), search_radius, window_hours, weights
        )

        track = [
            TrackPoint(
                lat=float(r["LAT"]),
                lon=float(r["LON"]),
                sog=float(r["SOG"]) if pd.notna(r["SOG"]) else 0.0,
                cog=float(r["COG"]) if pd.notna(r["COG"]) else 0.0,
                heading=float(r["Heading"]) if "Heading" in r and pd.notna(r["Heading"]) else 0.0,
                status=str(r.get("Status", "")),
                timestamp=pd.Timestamp(r["BaseDateTime"]).isoformat(),
            )
            for _, r in v.iterrows()
        ]

        included.append(
            CandidateVessel(
                rank=0,  # assigned after sorting
                mmsi=cand.mmsi,
                vesselName=cand.vesselName,
                vesselType=cand.vesselType,
                score=score,
                score_components=ScoreComponents(**comps),
                min_distance_km=feats.min_distance_to_origin_km,
                time_diff_hours=feats.time_diff_from_release_hours,
                trajectory_features=feats,
                behaviour=BehaviourAnalysis(
                    anomaly_score=anomaly_score,
                    anomaly_flags=flags,
                    svr_anomalies_in_window=svr_count,
                    dbscan_cluster_label=None,
                    dbscan_noise_points=0,
                    methodology=(
                        "Rule-based interpretable anomaly indicators + SVR speed "
                        "anomaly detection (notebook methodology) within the window."
                    ),
                ),
                evidence=evidence,
                filter_reasons=reasons,
                confidence=round(min(1.0, (comps["data_quality"] / 100.0) * (0.6 + 0.4 * score / 100.0)), 2),
                track=track,
                disclaimer=config.ATTRIBUTION_DISCLAIMER,
            )
        )

    included.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(included, start=1):
        c.rank = i
    included = included[:max_candidates]

    return AttributionResponse(
        candidates=included,
        excluded=excluded,
        origin={
            "lat": origin_lat,
            "lon": origin_lon,
            "release_time": release_time.isoformat(),
            "radius_km": radius_km,
            "window_hours": window_hours,
            "uncertainty_km": uncertainty_km,
        },
        search_parameters={
            "radius_km": radius_km,
            "window_hours": window_hours,
            "min_observations": config.MIN_AIS_OBSERVATIONS,
        },
        weights_used=weights,
        methodology=(
            "1) Spatio-temporal candidate search around the ESTIMATED ORIGIN "
            "(not the observed slick position): vessels with AIS pings inside "
            f"radius {search_radius:.0f} km within ±{window_hours:.0f} h of the "
            "estimated release time. 2) Explainable filtering (distance, data "
            "sufficiency, physical reachability). 3) Trajectory feature "
            "extraction (closest approach, dwell, course/speed changes, route "
            "deviation). 4) Behaviour anomaly (interpretable rules + notebook "
            "SVR). 5) Weighted transparent scoring with configurable weights."
        ),
        disclaimer=config.ATTRIBUTION_DISCLAIMER,
        source_label={
            "dataClass": "model",
            "description": (
                "Attribution computed over REAL AIS records in the repository "
                "dataset. The origin itself is a hindcast estimate; treat all "
                "scores as investigation priorities, not proof."
            ),
        },
    )
