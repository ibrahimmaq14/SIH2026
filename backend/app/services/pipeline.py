"""
End-to-end pipeline orchestrator.

    SAR image → detection → characterization → (location/time anchor)
    → environment → hindcast (origin estimate) → forecast
    → AIS search around ORIGIN → filter → trajectory analysis
    → behaviour anomaly → attribution scoring → ranked candidates

Geographic honesty: the repository's SAR images are plain 400x400 JPGs
with NO georeferencing. Unless the caller supplies a real acquisition
location/time, the demo anchors the spill to the AIS dataset's coverage
area (Gulf of Mexico) and labels that anchor SYNTHETIC.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

from .. import config
from ..schemas import (
    DetectionResult,
    DriftRequest,
    EnvironmentalSeries,
    ForecastResponse,
    HindcastResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    SpillCharacterization,
)
from . import attribution as attrsvc
from . import detection as detsvc
from . import drift as driftsvc
from . import environment as envsvc

logger = logging.getLogger("app.services.pipeline")


def _parse_time(ts: Optional[str], default: datetime) -> datetime:
    if not ts:
        return default
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return default


def pick_sample_spill_image() -> Optional[Path]:
    """Pick a class-1 SAR image from the dataset for the demo pipeline."""
    sar_dir = Path(config.SAR_DIR) / "1"
    if not sar_dir.is_dir():
        return None
    imgs = sorted(p for p in sar_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    return imgs[0] if imgs else None


def resolve_image(filename: Optional[str], upload_path: Optional[Path]) -> Path:
    if upload_path is not None:
        return upload_path
    if filename:
        p = Path(config.SAR_DIR) / filename  # e.g. "1/foo_cls_1.jpg"
        if not p.is_file():
            raise FileNotFoundError(f"Image not found in dataset: {filename}")
        return p
    sample = pick_sample_spill_image()
    if sample is None:
        raise FileNotFoundError("SAR dataset unavailable and no image supplied")
    return sample


def run_pipeline(
    req: PipelineRunRequest, upload_path: Optional[Path] = None
) -> PipelineRunResponse:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    errors: list[str] = []
    created_at = datetime.now(timezone.utc).isoformat()

    # 1-2) Detection + characterization
    image_path = resolve_image(req.filename, upload_path)
    arr = np.asarray(Image.open(image_path).convert("L"), dtype=np.float64) / 255.0

    obs_time = _parse_time(req.observation_time, _demo_obs_time())
    detection = detsvc.detect_from_array(arr, image_id=Path(image_path).name, acquisition_time=obs_time.isoformat())

    # Geographic anchor: real if user-provided; else SYNTHETIC demo anchor
    geographic: dict[str, Any] | None = None
    if req.spill_lat is not None and req.spill_lon is not None:
        geographic = {
            "lat": req.spill_lat,
            "lon": req.spill_lon,
            "source": "user-supplied acquisition coordinates",
        }
        geo_class = "model"
        geo_note = "Spill location anchored to user-supplied acquisition coordinates."
    else:
        geographic = {
            "lat": config.DEMO_SPILL_LAT,
            "lon": config.DEMO_SPILL_LON,
            "source": "synthetic-demo-anchor",
        }
        geo_class = "synthetic"
        geo_note = (
            "SAR image is not georeferenced; spill location anchored "
            "SYNTHETICALLY inside the real AIS dataset coverage area "
            "(Gulf of Mexico) for demonstration."
        )

    characterization = detsvc.characterize(
        arr, detection, image_path, acquisition_time=obs_time.isoformat(),
        geographic=geographic,
    )
    if geographic["source"] == "synthetic-demo-anchor":
        from ..schemas import DataSourceLabel
        characterization.source_label = DataSourceLabel(
            dataClass="synthetic", description=geo_note,
        )

    if not detection.detected:
        # No spill: stop the pipeline with a clean response
        empty_env = EnvironmentalSeries(samples=[], provider="n/a", dataClass="unavailable", note="No spill detected — environmental data not fetched.")
        return PipelineRunResponse(
            run_id=run_id,
            status="completed",
            errors=[],
            detection=detection,
            characterization=characterization,
            environment=empty_env,
            hindcast=None,  # type: ignore[arg-type]
            forecast=None,  # type: ignore[arg-type]
            attribution=None,  # type: ignore[arg-type]
            timeline=[
                {"event": "Detection", "status": "completed", "description": "No oil spill detected — pipeline stopped."},
            ],
            disclaimers=[geo_note],
        )

    lat, lon = geographic["lat"], geographic["lon"]

    # 3) Environmental data
    try:
        env_series = envsvc.get_environment_series(
            lat, lon,
            obs_time - timedelta(hours=req.hindcast_hours),
            obs_time + timedelta(hours=req.forecast_hours),
            step_minutes=max(60, req.timestep_minutes),
        )
    except envsvc.EnvironmentUnavailableError as e:
        errors.append(f"Environmental data unavailable: {e}")
        env_series = EnvironmentalSeries(
            samples=[], provider="unavailable", dataClass="unavailable",
            note="Environmental data could not be fetched; drift modelling halted.",
        )

    # 4) Hindcast → origin
    hind: Optional[HindcastResponse] = None
    fore: Optional[ForecastResponse] = None
    if env_series.samples:
        h_req = DriftRequest(
            lat=lat, lon=lon, start_time=obs_time.isoformat(),
            duration_hours=req.hindcast_hours, timestep_minutes=req.timestep_minutes,
            windage=req.windage, use_demo_environment=True,
        )
        hind = driftsvc.hindcast(h_req, series=env_series)
        f_req = DriftRequest(
            lat=lat, lon=lon, start_time=obs_time.isoformat(),
            duration_hours=req.forecast_hours, timestep_minutes=req.timestep_minutes,
            windage=req.windage, use_demo_environment=True,
        )
        fore = driftsvc.forecast(f_req, series=env_series)
    else:
        errors.append("Drift modelling skipped: no environmental data.")

    # 5) Attribution around the ESTIMATED ORIGIN (not the observed slick)
    attribution = None
    if hind is not None:
        o = hind.origin_location
        rel_time = _parse_time(hind.origin_time, obs_time)
        try:
            attribution = attrsvc.run_attribution(
                origin_lat=o["lat"],
                origin_lon=o["lon"],
                release_time=rel_time,
                radius_km=req.search_radius_km,
                window_hours=req.window_hours,
                uncertainty_km=hind.uncertainty_radius_km,
            )
        except Exception as e:
            logger.exception("Attribution failed")
            errors.append(f"Attribution failed: {e}")

    status = "completed" if not errors else "partial"

    timeline = [
        {"event": "SAR Detection", "status": "completed",
         "description": f"detected={detection.detected}, confidence={detection.confidence} ({detection.detection_method})"},
        {"event": "Slick Characterization", "status": "completed" if characterization.geometry else "skipped",
         "description": characterization.segmentation_note[:120]},
        {"event": "Environmental Data", "status": "completed" if env_series.samples else "failed",
         "description": f"provider={env_series.provider} ({env_series.dataClass}), {len(env_series.samples)} samples"},
        {"event": "Hindcast", "status": "completed" if hind else "skipped",
         "description": (f"origin=({hind.origin_location['lat']:.4f},{hind.origin_location['lon']:.4f}) ±{hind.uncertainty_radius_km} km" if hind else "not run")},
        {"event": "Forecast", "status": "completed" if fore else "skipped",
         "description": (f"{fore.total_displacement_km} km over {req.forecast_hours} h" if fore else "not run")},
        {"event": "AIS Attribution", "status": "completed" if attribution else "skipped",
         "description": (f"{len(attribution.candidates)} candidates, top score {attribution.candidates[0].score if attribution.candidates else 'n/a'}" if attribution else "not run")},
    ]

    disclaimers = [
        geo_note,
        "Hindcast origin is an ESTIMATE; the spill age cannot be determined from the image.",
        config.ATTRIBUTION_DISCLAIMER,
    ]
    if env_series.dataClass == "synthetic":
        disclaimers.append("Environmental forcing is SYNTHETIC (demo mode) — drift results are illustrative only.")

    resp = PipelineRunResponse(
        run_id=run_id,
        status=status,
        errors=errors,
        detection=detection,
        characterization=characterization,
        environment=env_series,
        hindcast=hind,
        forecast=fore,
        attribution=attribution,
        timeline=timeline,
        disclaimers=disclaimers,
    )

    # persist
    try:
        from ..db import store
        store.save_run(run_id, {"created_at": created_at, **resp.model_dump()})
    except Exception as e:
        logger.warning("Could not persist run %s: %s", run_id, e)

    return resp


def _demo_obs_time() -> datetime:
    return _parse_time(config.DEMO_OBSERVATION_TIME, datetime.now(timezone.utc))
