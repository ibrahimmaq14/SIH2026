"""
New SIH pipeline endpoints: detection, drift, hindcast, forecast, AIS search,
attribution, full pipeline run.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query
from PIL import Image

from .. import config
from ..schemas import (
    AISSearchRequest,
    AISSearchResponse,
    AttributionResponse,
    DetectionResult,
    DriftRequest,
    ForecastResponse,
    HindcastResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineRunSummary,
    SpillCharacterization,
)
from ..services import ais as aissvc
from ..services import attribution as attrsvc
from ..services import detection as detsvc
from ..services import drift as driftsvc
from ..services import pipeline as pipesvc
from ..ml import features as ml

logger = logging.getLogger("app.api.pipeline")

router = APIRouter()

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-\.]+$")


def _validate_image_upload(upload: UploadFile) -> None:
    name = upload.filename or ""
    if not _SAFE_NAME.match(name) or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    ext = Path(name).suffix.lower()
    if ext not in config.ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(config.ALLOWED_IMAGE_EXTENSIONS)}",
        )


def _save_upload_temp(upload: UploadFile) -> Path:
    """Persist an upload to a temp path with size cap, then return the path."""
    import tempfile
    import shutil

    suffix = Path(upload.filename or "upload.jpg").suffix.lower()
    tmp_dir = Path(tempfile.gettempdir()) / "sih_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    with open(tmp_path, "wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                out.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds {config.MAX_UPLOAD_BYTES // (1024*1024)} MB limit",
                )
            out.write(chunk)
    # verify it's a real image
    try:
        with Image.open(tmp_path) as im:
            im.verify()
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="File is not a valid image")
    return tmp_path


# ─── Detection ─────────────────────────────────────────────────────────


@router.post("/spill/detect", response_model=SpillCharacterization)
async def detect_spill(
    file: UploadFile = File(..., description="SAR image (jpg/png/tif)"),
    acquisition_time: Optional[str] = Form(None),
):
    """Detect + characterize an oil spill from an uploaded SAR image."""
    _validate_image_upload(file)
    tmp = _save_upload_temp(file)
    try:
        arr = ml.load_image_grayscale(tmp)
        det = detsvc.detect_from_array(arr, image_id=file.filename, acquisition_time=acquisition_time)
        return detsvc.characterize(arr, det, tmp, acquisition_time=acquisition_time)
    except ml.InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp.unlink(missing_ok=True)


@router.post("/spill/analyze")
async def analyze_spill(
    filename: str = Form(..., description="Dataset image, e.g. '1/img_xxx_JAV_cls_1.jpg'"),
    acquisition_time: Optional[str] = Form(None),
) -> SpillCharacterization:
    """Run detection + characterization on a dataset image (no upload)."""
    rel = Path(filename)
    if ".." in rel.parts:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = Path(config.SAR_DIR) / rel
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Image not found: {filename}")
    try:
        arr = ml.load_image_grayscale(path)
    except ml.InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    det = detsvc.detect_from_array(arr, image_id=rel.name, acquisition_time=acquisition_time)
    return detsvc.characterize(arr, det, path, acquisition_time=acquisition_time)


# ─── Drift ─────────────────────────────────────────────────────────────


@router.post("/drift/hindcast", response_model=HindcastResponse)
def drift_hindcast(req: DriftRequest):
    """Backward drift: estimate probable spill origin from an observation."""
    try:
        return driftsvc.hindcast(req)
    except Exception as e:
        logger.exception("hindcast failed")
        raise HTTPException(status_code=502, detail=f"Hindcast failed: {e}")


@router.post("/drift/forecast", response_model=ForecastResponse)
def drift_forecast(req: DriftRequest):
    """Forward drift: predict future slick movement."""
    try:
        return driftsvc.forecast(req)
    except Exception as e:
        logger.exception("forecast failed")
        raise HTTPException(status_code=502, detail=f"Forecast failed: {e}")


# ─── AIS & attribution ──────────────────────────────────────────────────


@router.post("/ais/search", response_model=AISSearchResponse)
def ais_search(req: AISSearchRequest):
    """Spatio-temporal AIS search around a point+time."""
    try:
        t = datetime.fromisoformat(req.time.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid `time` — ISO 8601 required")
    try:
        return aissvc.search_candidates(req.lat, req.lon, t, req.radius_km, req.window_hours)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"AIS dataset unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/vessels/analyze", response_model=AttributionResponse)
def vessels_analyze(
    lat: float = Form(...),
    lon: float = Form(...),
    time: str = Form(...),
    radius_km: float = Form(15.0),
    window_hours: float = Form(12.0),
    uncertainty_km: float = Form(0.0),
):
    """Full attribution around a given origin point/time."""
    try:
        t = datetime.fromisoformat(time.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid `time` — ISO 8601 required")
    return attrsvc.run_attribution(
        origin_lat=lat, origin_lon=lon, release_time=t,
        radius_km=radius_km, window_hours=window_hours, uncertainty_km=uncertainty_km,
    )


@router.post("/attribution/rank", response_model=AttributionResponse)
def attribution_rank(payload: dict):
    """Alias of /vessels/analyze accepting a JSON body."""
    required = {"lat", "lon", "time"}
    missing = required - set(payload)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {sorted(missing)}")
    try:
        t = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid `time` — ISO 8601 required")
    return attrsvc.run_attribution(
        origin_lat=float(payload["lat"]),
        origin_lon=float(payload["lon"]),
        release_time=t,
        radius_km=float(payload.get("radius_km", 15.0)),
        window_hours=float(payload.get("window_hours", 12.0)),
        uncertainty_km=float(payload.get("uncertainty_km", 0.0)),
    )


# ─── Full pipeline ──────────────────────────────────────────────────────


@router.post("/pipeline/run", response_model=PipelineRunResponse)
async def pipeline_run(
    file: Optional[UploadFile] = File(None, description="Optional SAR image upload"),
    filename: Optional[str] = Form(None, description="Dataset image path e.g. 1/img_x_JAV_cls_1.jpg"),
    hindcast_hours: float = Form(48.0),
    forecast_hours: float = Form(48.0),
    windage: float = Form(0.03),
    search_radius_km: float = Form(15.0),
    window_hours: float = Form(12.0),
    timestep_minutes: int = Form(30),
    spill_lat: Optional[float] = Form(None),
    spill_lon: Optional[float] = Form(None),
    observation_time: Optional[str] = Form(None),
):
    """
    Full end-to-end pipeline: detect → characterize → environment → hindcast
    → forecast → AIS attribution. Optionally upload a SAR image; otherwise a
    dataset image is used (demo).
    """
    upload_path: Optional[Path] = None
    if file is not None and file.filename:
        _validate_image_upload(file)
        upload_path = _save_upload_temp(file)

    try:
        req = PipelineRunRequest(
            filename=filename,
            hindcast_hours=hindcast_hours,
            forecast_hours=forecast_hours,
            windage=windage,
            search_radius_km=search_radius_km,
            window_hours=window_hours,
            timestep_minutes=timestep_minutes,
            spill_lat=spill_lat,
            spill_lon=spill_lon,
            observation_time=observation_time,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid parameters: {e}")
    try:
        return pipesvc.run_pipeline(req, upload_path=upload_path)
    except ml.InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("pipeline run failed")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")
    finally:
        if upload_path is not None:
            upload_path.unlink(missing_ok=True)


@router.get("/pipeline/runs", response_model=list[PipelineRunSummary])
def pipeline_runs(limit: int = Query(20, ge=1, le=100)):
    from ..db import store
    return [PipelineRunSummary(**r) for r in store.list_runs(limit=limit)]


@router.get("/pipeline/runs/{run_id}")
def pipeline_run_detail(run_id: str):
    from ..db import store
    run = store.load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run
