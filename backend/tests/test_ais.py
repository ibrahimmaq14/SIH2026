"""Tests for AIS cleaning, search, trajectory features, anomaly, and scoring."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.services import ais as aissvc


@pytest.fixture(scope="module")
def df():
    try:
        return aissvc.get_dataframe()
    except Exception:
        pytest.skip("AIS dataset not available")


def test_cleaning_removes_invalid_coords(df):
    assert ((df["LAT"] >= -90) & (df["LAT"] <= 90)).all()
    assert ((df["LON"] >= -180) & (df["LON"] <= 180)).all()
    assert df["BaseDateTime"].notna().all()


def test_cleaning_sorts_by_vessel_time(df):
    g = df.groupby("MMSI")["BaseDateTime"]
    for _, times in list(g)[:5]:
        assert times.is_monotonic_increasing


def test_cleaning_drops_duplicates(df):
    dup = df.duplicated(subset=["MMSI", "BaseDateTime", "LAT", "LON"])
    assert int(dup.sum()) == 0


def test_search_candidates_finds_vessels(df):
    time = df["BaseDateTime"].iloc[len(df) // 2].to_pydatetime()
    lat, lon = float(df["LAT"].median()), float(df["LON"].median())
    out = aissvc.search_candidates(lat, lon, time, radius_km=50.0, window_hours=48.0)
    assert out.total_records_searched > 0
    if out.candidates:
        assert out.candidates[0].min_distance_km <= out.candidates[-1].min_distance_km
        for c in out.candidates:
            assert c.observations_in_window >= 1


def test_search_candidates_empty_when_out_of_time(df):
    out = aissvc.search_candidates(
        28.5, -94.9, datetime(1999, 1, 1, tzinfo=timezone.utc),
        radius_km=20.0, window_hours=6.0,
    )
    assert out.candidates == []
    assert out.total_records_searched == 0


def test_search_rejects_impossible_radius():
    out = aissvc.search_candidates(28.5, -94.9, datetime(2021, 2, 1, tzinfo=timezone.utc), radius_km=0.001, window_hours=1)
    # radius so small that only a vessel passing within 1 m would match
    assert all(c.min_distance_km <= 0.001 for c in out.candidates)


# ─── trajectory features ────────────────────────────────────────────────────


def _make_vessel_df(points):
    return pd.DataFrame(
        {
            "MMSI": [123] * len(points),
            "BaseDateTime": pd.to_datetime([p[0] for p in points]),
            "LAT": [p[1] for p in points],
            "LON": [p[2] for p in points],
            "SOG": [p[3] for p in points],
            "COG": [p[4] for p in points],
            "Heading": [p[4] for p in points],
            "Status": ["0"] * len(points),
        }
    )


def test_extract_features_passing_vessel():
    release = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    # vessel passes 2 km north of origin at release time
    pts = [
        ("2021-02-01T08:00:00Z", 28.60, -95.00, 10.0, 180.0),
        ("2021-02-01T10:00:00Z", 28.56, -94.95, 10.0, 180.0),
        ("2021-02-01T12:00:00Z", 28.52, -94.90, 8.0, 180.0),
        ("2021-02-01T14:00:00Z", 28.48, -94.85, 10.0, 180.0),
        ("2021-02-01T16:00:00Z", 28.44, -94.80, 10.0, 180.0),
    ]
    v = _make_vessel_df(pts)
    feats = aissvc.extract_trajectory_features(v, 28.50, -94.90, release, radius_km=10.0)
    assert feats.min_distance_to_origin_km < 5.0
    assert feats.time_diff_from_release_hours == 0.0
    assert feats.passes_within_radius
    assert feats.approach_bearing_deg is not None
    assert feats.departure_bearing_deg is not None


def test_extract_features_dwell():
    release = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    # vessel loiters at the origin for hours
    pts = [(f"2021-02-01T{h:02d}:00:00Z", 28.501, -94.901, 0.5, 30.0) for h in range(6, 18)]
    v = _make_vessel_df(pts)
    feats = aissvc.extract_trajectory_features(v, 28.50, -94.90, release, radius_km=10.0)
    assert feats.dwell_minutes_near_origin > 300


def test_filter_candidate_excludes_far_vessel():
    release = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    ok, v, reasons = aissvc.filter_candidate(
        123456789, 28.50, -94.90, release, radius_km=5.0, window_hours=6.0
    )
    assert not ok
    assert "No AIS records" in reasons[0]


# ─── anomaly + scoring ──────────────────────────────────────────────────────


def test_behaviour_anomaly_flags_loitering():
    release = datetime(2021, 2, 1, 12, 0, tzinfo=timezone.utc)
    pts = [(f"2021-02-01T{h:02d}:00:00Z", 28.501, -94.901, 0.3, 30.0) for h in range(0, 20)]
    v = _make_vessel_df(pts)
    feats = aissvc.extract_trajectory_features(v, 28.50, -94.90, release, radius_km=10.0)
    score, flags, svr_count = aissvc.behaviour_anomaly(v, feats, 28.50, -94.90)
    assert score > 0
    assert any("dwell" in f.lower() for f in flags)


def test_scoring_high_for_ideal_candidate():
    from app.schemas import TrajectoryFeatures

    feats = TrajectoryFeatures(
        min_distance_to_origin_km=0.5,
        distance_at_release_km=0.5,
        min_distance_time="2021-02-01T12:10:00+00:00",
        time_diff_from_release_hours=0.2,
        mean_speed_knots=5.0, max_speed_knots=12.0,
        course_at_min_distance=90.0, speed_at_min_distance=1.0,
        heading_changes_deg=50.0, speed_changes_knots=2.0,
        dwell_minutes_near_origin=90.0,
        approach_bearing_deg=10.0, departure_bearing_deg=190.0,
        passes_within_radius=True, time_near_origin_minutes=90.0,
        route_deviation_score=0.4,
    )
    weights = {"spatial": 0.30, "temporal": 0.25, "trajectory": 0.20,
               "behaviour": 0.15, "data_quality": 0.10}
    total, comps, evidence = aissvc.score_candidate(feats, 40.0, 20, 15.0, 12.0, weights)
    assert 0 <= total <= 100
    assert comps["spatial"] > 90
    assert comps["temporal"] > 90
    assert total > 60
    assert evidence


def test_scoring_low_for_distant_candidate():
    from app.schemas import TrajectoryFeatures

    feats = TrajectoryFeatures(
        min_distance_to_origin_km=14.5,
        distance_at_release_km=14.5,
        min_distance_time="2021-02-01T04:00:00+00:00",
        time_diff_from_release_hours=8.0,
        mean_speed_knots=10.0, max_speed_knots=10.0,
        course_at_min_distance=90.0, speed_at_min_distance=10.0,
        heading_changes_deg=10.0, speed_changes_knots=1.0,
        dwell_minutes_near_origin=0.0,
        approach_bearing_deg=90.0, departure_bearing_deg=90.0,
        passes_within_radius=False, time_near_origin_minutes=0.0,
        route_deviation_score=0.0,
    )
    weights = {"spatial": 0.30, "temporal": 0.25, "trajectory": 0.20,
               "behaviour": 0.15, "data_quality": 0.10}
    total, comps, _ = aissvc.score_candidate(feats, 5.0, 3, 15.0, 12.0, weights)
    assert total < 30
    assert comps["spatial"] < 5


def test_weights_change_score():
    from app.schemas import TrajectoryFeatures

    feats = TrajectoryFeatures(
        min_distance_to_origin_km=1.0, distance_at_release_km=1.0,
        min_distance_time="x", time_diff_from_release_hours=1.0,
        mean_speed_knots=5, max_speed_knots=8,
        course_at_min_distance=90, speed_at_min_distance=2,
        heading_changes_deg=100, speed_changes_knots=3,
        dwell_minutes_near_origin=60,
        approach_bearing_deg=10, departure_bearing_deg=190,
        passes_within_radius=True, time_near_origin_minutes=60,
        route_deviation_score=0.3,
    )
    w1 = {"spatial": 0.3, "temporal": 0.25, "trajectory": 0.2, "behaviour": 0.15, "data_quality": 0.1}
    w2 = {"spatial": 0.1, "temporal": 0.1, "trajectory": 0.2, "behaviour": 0.5, "data_quality": 0.1}
    # anomaly (100) is higher than every other component → behaviour-heavy
    # weighting must boost the vessel's total score
    t1, comps1, _ = aissvc.score_candidate(feats, 100.0, 20, 15.0, 12.0, w1)
    t2, comps2, _ = aissvc.score_candidate(feats, 100.0, 20, 15.0, 12.0, w2)
    assert comps2["behaviour"] == 100.0
    assert t2 > t1
