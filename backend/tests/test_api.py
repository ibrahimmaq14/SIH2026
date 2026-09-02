"""API contract tests — every endpoint the frontend + new pipeline uses."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config


@pytest.fixture(scope="module")
def client():
    from main import app
    with TestClient(app) as c:
        yield c


# ─── health ──────────────────────────────────────────────────────────────


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


# ─── legacy frontend contracts ────────────────────────────────────────────


def test_vessels_pagination_contract(client):
    r = client.get("/api/vessels", params={"page": 1, "pageSize": 5})
    assert r.status_code == 200
    body = r.json()
    for key in ("vessels", "total", "page", "pageSize", "totalPages"):
        assert key in body
    if body["vessels"]:
        v = body["vessels"][0]
        # PascalCase fields exactly as the frontend expects
        for key in ("MMSI", "VesselName", "LAT", "LON", "SOG", "COG", "ObservationCount"):
            assert key in v


def test_vessels_search_and_sort(client):
    r = client.get("/api/vessels", params={"search": "36", "sortBy": "SOG", "sortOrder": "desc"})
    assert r.status_code == 200
    body = r.json()
    sogs = [v["SOG"] for v in body["vessels"] if v["SOG"] is not None]
    assert sogs == sorted(sogs, reverse=True)


def test_vessel_types(client):
    r = client.get("/api/vessels/types")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_vessel_track_contract(client):
    # first get a valid mmsi
    mmsi = client.get("/api/vessels", params={"pageSize": 1}).json()["vessels"][0]["MMSI"]
    r = client.get(f"/api/vessels/{mmsi}")
    assert r.status_code == 200
    body = r.json()
    assert body["mmsi"] == mmsi
    assert isinstance(body["track"], list)
    assert body["info"] is not None
    if body["track"]:
        tp = body["track"][0]
        for key in ("lat", "lon", "sog", "cog", "heading", "status", "timestamp"):
            assert key in tp


def test_vessel_not_found(client):
    r = client.get("/api/vessels/999999999")
    assert r.status_code == 404


def test_vessel_anomalies_contract(client):
    mmsi = client.get("/api/vessels", params={"pageSize": 1}).json()["vessels"][0]["MMSI"]
    r = client.get(f"/api/vessels/{mmsi}/anomalies")
    assert r.status_code == 200
    body = r.json()
    assert "model_info" in body  # snake_case contract
    assert "anomalies" in body
    if body["anomalies"]:
        a = body["anomalies"][0]
        for key in ("lat", "lon", "sog", "predictedSog", "difference", "timestamp"):
            assert key in a


def test_all_anomalies(client):
    r = client.get("/api/anomalies", params={"threshold": 6.0, "maxVessels": 5})
    assert r.status_code == 200
    body = r.json()
    for key in ("vessels", "allAnomalies", "threshold", "vesselsAnalyzed"):
        assert key in body


def test_analytics(client):
    r = client.get("/api/analytics")
    assert r.status_code == 200
    body = r.json()
    for key in ("totalRecords", "uniqueVessels", "sogStats", "correlations", "hourlyActivity"):
        assert key in body


def test_overview(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["totalVessels"] > 0


def test_sar_summary(client):
    r = client.get("/api/sar/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["totalImages"] > 5000


def test_sar_images(client):
    r = client.get("/api/sar/images", params={"cls": 1, "pageSize": 5})
    assert r.status_code == 200
    body = r.json()
    assert len(body["images"]) <= 5


def test_sar_image_serving_and_traversal_protection(client):
    imgs = client.get("/api/sar/images", params={"cls": 1, "pageSize": 1}).json()["images"]
    if imgs:
        r = client.get(f"/api/sar/image/1/{imgs[0]['filename']}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
    # traversal blocked
    r = client.get("/api/sar/image/1/..%5C..%5Cmain.py")
    assert r.status_code in (400, 404)


def test_sar_regions(client):
    r = client.get("/api/sar/regions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sar_detections_model_backed(client):
    r = client.get("/api/sar/detections")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        # with the trained model, detections carry model output
        assert any(not d["isDemo"] for d in body) or all(d["isDemo"] for d in body)


def test_investigations(client):
    r = client.get("/api/investigations")
    assert r.status_code == 200
    body = r.json()
    assert "investigations" in body
    inv = body["investigations"][0]
    for key in ("id", "title", "status", "isDemo", "region", "timeline"):
        assert key in inv


def test_pipeline_status(client):
    r = client.get("/api/pipeline/status")
    assert r.status_code == 200
    body = r.json()
    stages = {s["stage"] for s in body["pipeline"]}
    assert "SAR Spill Classifier" in stages
    assert "Drift Hindcast / Forecast" in stages
    assert "Vessel Attribution Ranking" in stages
    for s in body["pipeline"]:
        assert s["status"] in ("Available", "Offline", "Demo", "Not Configured")


# ─── new pipeline endpoints ──────────────────────────────────────────────


def test_spill_analyze_dataset_image(client):
    imgs = client.get("/api/sar/images", params={"cls": 1, "pageSize": 1}).json()["images"]
    if not imgs:
        pytest.skip("no SAR dataset")
    r = client.post(
        "/api/spill/analyze",
        data={"filename": f"1/{imgs[0]['filename']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["detection"]["detected"] is True
    assert body["source_label"]["dataClass"] == "model"


def test_spill_analyze_missing_image(client):
    r = client.post("/api/spill/analyze", data={"filename": "1/missing_image.jpg"})
    assert r.status_code == 404


def test_spill_detect_upload(client):
    # upload one of the dataset images as a file
    imgs = client.get("/api/sar/images", params={"cls": 1, "pageSize": 1}).json()["images"]
    if not imgs:
        pytest.skip("no SAR dataset")
    path = Path(config.SAR_DIR) / "1" / imgs[0]["filename"]
    with open(path, "rb") as f:
        r = client.post(
            "/api/spill/detect",
            files={"file": (imgs[0]["filename"], f, "image/jpeg")},
        )
    assert r.status_code == 200
    body = r.json()
    assert "detection" in body
    assert body["detection"]["confidence"] >= 0


def test_spill_detect_rejects_non_image(client):
    r = client.post(
        "/api/spill/detect",
        files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 400


def test_hindcast_endpoint(client):
    r = client.post("/api/drift/hindcast", json={
        "lat": 28.5, "lon": -94.9,
        "start_time": "2021-02-01T12:00:00Z",
        "duration_hours": 24.0, "timestep_minutes": 60,
        "windage": 0.03, "use_demo_environment": True, "ensemble_members": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert "origin_location" in body
    assert "uncertainty_radius_km" in body
    assert "confidence" in body
    assert "environment" in body
    assert len(body["track"]["points"]) == 25


def test_forecast_endpoint(client):
    r = client.post("/api/drift/forecast", json={
        "lat": 28.5, "lon": -94.9,
        "start_time": "2021-02-01T12:00:00Z",
        "duration_hours": 12.0, "timestep_minutes": 60,
        "windage": 0.03, "use_demo_environment": True, "ensemble_members": 3,
    })
    assert r.status_code == 200
    body = r.json()
    assert "end_position" in body
    assert "uncertainty_radius_km" in body


def test_ais_search_endpoint(client):
    r = client.post("/api/ais/search", json={
        "lat": 28.52, "lon": -94.95,
        "time": "2021-02-01T12:00:00Z",
        "radius_km": 50.0, "window_hours": 48.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert "candidates" in body
    assert "time_coverage" in body


def test_ais_search_bad_time(client):
    r = client.post("/api/ais/search", json={
        "lat": 28.5, "lon": -94.9, "time": "not-a-date",
    })
    assert r.status_code == 400


def test_attribution_rank_endpoint(client):
    r = client.post("/api/attribution/rank", json={
        "lat": 28.52, "lon": -94.95,
        "time": "2021-02-01T12:00:00Z",
        "radius_km": 20.0, "window_hours": 24.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert "candidates" in body
    assert "disclaimer" in body
    assert "investigation-priority" in body["disclaimer"]
    if body["candidates"]:
        c = body["candidates"][0]
        for key in ("rank", "mmsi", "score", "score_components", "evidence", "track"):
            assert key in c
        assert c["rank"] == 1
    # ranking is descending
    scores = [c["score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_full_pipeline_run(client):
    """THE end-to-end test: SAR image → detection → drift → AIS → ranked vessels."""
    r = client.post("/api/pipeline/run", data={
        "hindcast_hours": "24", "forecast_hours": "12",
        "windage": "0.03", "search_radius_km": "15",
        "window_hours": "12", "timestep_minutes": "60",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("completed", "partial")
    assert body["detection"]["detected"] is True
    assert body["hindcast"]["origin_location"]["lat"] != 0
    assert len(body["forecast"]["track"]["points"]) == 13
    assert "candidates" in body["attribution"]
    assert len(body["timeline"]) == 6
    assert any("SYNTHETIC" in d or "synthetic" in d for d in body["disclaimers"])

    # the run must be listed
    runs = client.get("/api/pipeline/runs").json()
    assert any(x["run_id"] == body["run_id"] for x in runs)
    detail = client.get(f"/api/pipeline/runs/{body['run_id']}")
    assert detail.status_code == 200


def test_pipeline_run_with_specific_image(client):
    imgs = client.get("/api/sar/images", params={"cls": 1, "pageSize": 1}).json()["images"]
    if not imgs:
        pytest.skip("no SAR dataset")
    r = client.post("/api/pipeline/run", data={
        "filename": f"1/{imgs[0]['filename']}",
        "hindcast_hours": "12", "forecast_hours": "6",
        "timestep_minutes": "60",
    })
    assert r.status_code == 200
    assert r.json()["detection"]["detected"] is True


def test_pipeline_run_bad_filename(client):
    r = client.post("/api/pipeline/run", data={"filename": "999/nope.jpg"})
    assert r.status_code == 404


def test_pipeline_run_invalid_geo(client):
    r = client.post("/api/pipeline/run", data={"spill_lat": "120.0"})
    assert r.status_code == 422  # pydantic validation
