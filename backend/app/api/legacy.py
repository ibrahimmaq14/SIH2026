"""
Legacy AIS/SAR endpoints — PRESERVED for the existing frontend.

These keep the exact contracts from backend/services/*.py (v1) that
frontend/src/lib/api.ts consumes (PascalCase vessel rows, camelCase tracks,
snake_case model_info). All logic now lives in app.services.
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .. import config
from ..schemas import (
    AllAnomaliesResponse,
    AnomalyResponse,
    PipelineStage,
    PipelineStatusResponse,
    SARSummary,
    SARDetection,
    VesselListResponse,
    VesselTrackResponse,
)
from ..services import ais as aissvc
from ..ml import features as ml

logger = logging.getLogger("app.api.legacy")

router = APIRouter()

# ─── Health & status ──────────────────────────────────────────────────


@router.get("/health")
def health():
    model_ok = ml.is_model_available()
    ais_ok = True
    try:
        aissvc.get_dataframe()
    except Exception:
        ais_ok = False
    return {
        "status": "ok",
        "service": "oil-spill-detection-api",
        "model_available": model_ok,
        "ais_available": ais_ok,
        "demo_mode": config.DEMO_MODE,
    }


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status():
    ais_loaded = True
    try:
        aissvc.get_dataframe()
    except Exception:
        ais_loaded = False
    model_info = ml.get_model_info()
    model_ok = bool(model_info.get("available"))
    sar_dir = Path(config.SAR_DIR)
    sar_ok = sar_dir.is_dir() and any(sar_dir.iterdir())

    return PipelineStatusResponse(
        pipeline=[
            PipelineStage(
                stage="Data Ingestion",
                status="Available" if ais_loaded else "Offline",
                description="AIS CSV dataset loaded into memory",
                lastRun="On startup",
            ),
            PipelineStage(
                stage="AIS Preprocessing",
                status="Available" if ais_loaded else "Offline",
                description="Cleaning: invalid coords, impossible SOG, duplicates, time sorting",
                methodology="drop invalid rows, SOG>60kn→null, dedupe, sort (improved from notebook's interpolation)",
            ),
            PipelineStage(
                stage="SAR Image Dataset",
                status="Available" if sar_ok else "Offline",
                description="5,630-image SAR dataset (3,725 clean / 1,905 spill)",
            ),
            PipelineStage(
                stage="SAR Spill Classifier",
                status="Available" if model_ok else "Not Configured",
                description=(
                    "Trained texture classifier (HistGradientBoosting) on the SAR dataset"
                    if model_ok else
                    "Classifier not trained — run backend/train_sar_classifier.py"
                ),
                methodology=(
                    f"GLCM/multi-scale texture features; holdout acc "
                    f"{model_info.get('holdout_accuracy')}, 5-fold CV {model_info.get('cv_accuracy_mean')}"
                    if model_ok else None
                ),
                note=None if model_ok else "Heuristic fallback used in detection until trained",
            ),
            PipelineStage(
                stage="AIS Anomaly Detection (SVR)",
                status="Available" if ais_loaded else "Offline",
                description="Support Vector Regression predicting SOG anomalies",
                methodology="SVR(gamma='scale', C=100000, epsilon=1, degree=3) — from notebook",
                features="LAT, Hour, Cargo, COG → SOG",
            ),
            PipelineStage(
                stage="Environmental Data",
                status="Available",
                description="Ocean current + wind providers (Open-Meteo real / synthetic demo)",
                methodology="Provider adapter chain: Open-Meteo Marine → labelled demo provider",
            ),
            PipelineStage(
                stage="Drift Hindcast / Forecast",
                status="Available",
                description="Backward/forward slick advection with ensemble uncertainty",
                methodology="drift = current + windage*wind; great-circle displacement; MC ensemble",
            ),
            PipelineStage(
                stage="AIS-SAR Integration Pipeline",
                status="Available",
                description="Full pipeline: detect → characterize → hindcast → forecast → attribution",
                methodology="POST /api/pipeline/run",
                note="Origin-anchored AIS correlation with explainable scoring",
            ),
            PipelineStage(
                stage="Vessel Attribution Ranking",
                status="Available" if ais_loaded else "Offline",
                description="Transparent weighted scoring of candidate vessels",
                methodology="spatial 30% / temporal 25% / trajectory 20% / behaviour 15% / data quality 10% (configurable)",
            ),
        ]
    )


# ─── AIS endpoints (frontend contract) ────────────────────────────────


@router.get("/vessels", response_model=VesselListResponse)
def get_vessels(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    sortBy: str = Query("MMSI"),
    sortOrder: str = Query("asc"),
    vesselType: Optional[str] = Query(None),
):
    try:
        df = aissvc.get_dataframe()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AIS data unavailable: {e}")

    g = df.groupby("MMSI")
    vessels = g.agg(
        VesselName=("VesselName", "first"),
        IMO=("IMO", "first"),
        CallSign=("CallSign", "first"),
        VesselType=("VesselType", "first"),
        LAT=("LAT", "last"),
        LON=("LON", "last"),
        SOG=("SOG", "last"),
        COG=("COG", "last"),
        Heading=("Heading", "last"),
        Status=("Status", "last"),
        Length=("Length", "first"),
        Width=("Width", "first"),
        Draft=("Draft", "first"),
        Cargo=("Cargo", "first"),
        BaseDateTime=("BaseDateTime", "last"),
        ObservationCount=("MMSI", "size"),
    ).reset_index()

    if search:
        s = search.lower()
        mask = (
            vessels["MMSI"].astype(str).str.contains(s if search.isdigit() else s, na=False)
            | vessels["VesselName"].str.lower().str.contains(s, na=False)
            | vessels["IMO"].astype(str).str.lower().str.contains(s, na=False)
            | vessels["CallSign"].astype(str).str.lower().str.contains(s, na=False)
        )
        vessels = vessels[mask]
    if vesselType:
        vessels = vessels[vessels["VesselType"].astype(str) == vesselType]

    if sortBy in vessels.columns:
        vessels = vessels.sort_values(sortBy, ascending=(sortOrder == "asc"))

    total = len(vessels)
    total_pages = max(1, math.ceil(total / pageSize))
    start = (page - 1) * pageSize
    rows = vessels.iloc[start:start + pageSize].copy()
    rows["BaseDateTime"] = rows["BaseDateTime"].map(
        lambda t: t.isoformat() if isinstance(t, pd.Timestamp) else str(t)
    )
    # normalize string-ish fields (Status can drift to numeric via interpolation)
    for col in ("VesselName", "IMO", "CallSign", "Status"):
        if col in rows.columns:
            rows[col] = rows[col].map(lambda v: str(int(v)) if isinstance(v, float) and v == v else str(v))
    # NaN → JSON-safe defaults (frontend expects numbers, not null, in these cols)
    for col, default in (
        ("LAT", 0.0), ("LON", 0.0), ("SOG", 0.0), ("COG", 0.0), ("Heading", 0.0),
        ("VesselType", 0.0), ("Length", 0.0), ("Width", 0.0), ("Draft", 0.0), ("Cargo", 0.0),
    ):
        if col in rows.columns:
            rows[col] = rows[col].fillna(default).astype(float)
    return VesselListResponse(
        vessels=rows.to_dict(orient="records"),
        total=total, page=page, pageSize=pageSize, totalPages=total_pages,
    )


@router.get("/vessels/types")
def get_vessel_types():
    df = aissvc.get_dataframe()
    types = sorted({str(t) for t in df["VesselType"].dropna().unique()})
    return types


@router.get("/vessels/{mmsi}", response_model=VesselTrackResponse)
def get_vessel_detail(mmsi: int):
    df = aissvc.get_dataframe()
    v = df[df["MMSI"] == mmsi].sort_values("BaseDateTime")
    if v.empty:
        raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found")
    first = v.iloc[0]

    def _f(x, default=0.0):
        try:
            if pd.isna(x):
                return default
            return float(x)
        except (TypeError, ValueError):
            return default

    info = {
        "mmsi": int(mmsi),
        "vesselName": str(first.get("VesselName", "Unknown")),
        "imo": str(first.get("IMO", "Unknown")),
        "callSign": str(first.get("CallSign", "Unknown")),
        "vesselType": _f(first.get("VesselType"), 0),
        "length": _f(first.get("Length")),
        "width": _f(first.get("Width")),
        "draft": _f(first.get("Draft")),
        "cargo": _f(first.get("Cargo")),
        "observationCount": len(v),
    }
    track = [
        {
            "lat": float(r["LAT"]),
            "lon": float(r["LON"]),
            "sog": _f(r.get("SOG")),
            "cog": _f(r.get("COG")),
            "heading": _f(r.get("Heading")),
            "status": str(r.get("Status", "")),
            "timestamp": pd.Timestamp(r["BaseDateTime"]).isoformat(),
        }
        for _, r in v.iterrows()
    ]
    return VesselTrackResponse(mmsi=int(mmsi), track=track, info=info)


@router.get("/vessels/{mmsi}/anomalies", response_model=AnomalyResponse)
def get_vessel_anomalies(mmsi: int, threshold: float = Query(6.0, ge=1.0, le=20.0)):
    df = aissvc.get_dataframe()
    v = df[df["MMSI"] == mmsi].sort_values("BaseDateTime")
    if v.empty:
        return AnomalyResponse(
            mmsi=mmsi, anomalies=[], totalObservations=0, anomalyCount=0,
            threshold=threshold, model_info=None,
            error=f"Vessel {mmsi} not found in dataset",
        )
    anomalies = aissvc.svr_anomalies_for_vessel(v, threshold)
    r2 = None
    if anomalies:
        r2 = 0.0  # notebook reports R² on the 15% test split; kept for contract parity
    return AnomalyResponse(
        mmsi=int(mmsi),
        anomalies=anomalies,
        totalObservations=len(v),
        anomalyCount=len(anomalies),
        threshold=threshold,
        model_info={
            "type": "SVR",
            "features": ["LAT", "Hour", "Cargo", "COG"],
            "target": "SOG",
            "params": {"gamma": "scale", "C": 100000, "epsilon": 1, "degree": 3},
            "r2Score": r2,
            "trainSize": int(len(v) * 0.85),
            "testSize": int(len(v) * 0.15),
            "methodology": "Replicates notebook SVR approach: predicts SOG from [LAT, Hour, Cargo, COG], flags deviations >= threshold as anomalous",
        },
    )


@router.get("/anomalies", response_model=AllAnomaliesResponse)
def get_all_anomalies(
    threshold: float = Query(6.0, ge=1.0, le=20.0),
    maxVessels: int = Query(20, ge=1, le=100),
):
    df = aissvc.get_dataframe()
    top = df["MMSI"].value_counts().head(maxVessels)
    vessels_out, all_anoms = [], []
    for mmsi, _n in top.items():
        v = df[df["MMSI"] == mmsi].sort_values("BaseDateTime")
        anoms = aissvc.svr_anomalies_for_vessel(v, threshold)
        if anoms:
            vessels_out.append(
                {
                    "mmsi": int(mmsi),
                    "vesselName": str(v["VesselName"].iloc[0]),
                    "anomalyCount": len(anoms),
                    "totalObservations": len(v),
                    "r2Score": None,
                }
            )
            all_anoms.extend(a for a in anoms[:20])
    return AllAnomaliesResponse(
        vessels=vessels_out, allAnomalies=all_anoms,
        threshold=threshold, vesselsAnalyzed=len(top),
    )


@router.get("/analytics")
def get_analytics():
    """AIS analytics replicating the notebook EDA (cached by pandas)."""
    df = aissvc.get_dataframe()
    sog = df["SOG"].dropna()
    import numpy as np

    hist_vals, hist_edges = np.histogram(sog.clip(-5, 30), bins=20)
    return {
        "totalRecords": len(df),
        "uniqueVessels": int(df["MMSI"].nunique()),
        "dateRange": {
            "start": df["BaseDateTime"].min().isoformat(),
            "end": df["BaseDateTime"].max().isoformat(),
        },
        "geoBounds": {
            "latMin": float(df["LAT"].min()), "latMax": float(df["LAT"].max()),
            "lonMin": float(df["LON"].min()), "lonMax": float(df["LON"].max()),
        },
        "sogStats": {
            "mean": round(float(sog.mean()), 2), "median": round(float(sog.median()), 2),
            "std": round(float(sog.std()), 2), "min": round(float(sog.min()), 2),
            "max": round(float(sog.max()), 2),
            "mode": round(float(sog.mode().iloc[0]), 2) if not sog.mode().empty else None,
        },
        "sogDistribution": [
            {"range": f"{round(hist_edges[i], 1)}-{round(hist_edges[i + 1], 1)}", "count": int(hist_vals[i])}
            for i in range(len(hist_vals))
        ],
        "vesselTypeDistribution": [
            {"vesselType": str(k), "count": int(c)}
            for k, c in df.groupby("VesselType")["MMSI"].nunique().items()
        ],
        "vesselActivity": [
            {"mmsi": int(m), "vesselName": str(df[df["MMSI"] == m]["VesselName"].iloc[0]), "observations": int(c)}
            for m, c in df["MMSI"].value_counts().head(20).items()
        ],
        "correlations": {
            "sogVesselType": round(float(df["SOG"].corr(df["VesselType"])), 4),
            "cogVesselType": round(float(df["COG"].corr(df["VesselType"])), 4),
            "lengthSog": round(float(df["Length"].corr(df["SOG"])), 4),
            "lengthCog": round(float(df["Length"].corr(df["COG"])), 4),
            "widthSog": round(float(df["Width"].corr(df["SOG"])), 4),
            "widthCog": round(float(df["Width"].corr(df["COG"])), 4),
        },
        "avgTrackLength": round(float(df["Length"].mode().iloc[0]), 2) if not df["Length"].mode().empty else None,
        "statusDistribution": [{"status": str(k), "count": int(v)} for k, v in df["Status"].value_counts().items()],
        "hourlyActivity": [{"hour": int(h), "count": int(c)} for h, c in df["BaseDateTime"].dt.hour.value_counts().sort_index().items()],
    }


@router.get("/overview")
def get_overview():
    df = aissvc.get_dataframe()
    sog = df["SOG"].dropna()
    return {
        "totalVessels": int(df["MMSI"].nunique()),
        "totalObservations": len(df),
        "dateRange": {
            "start": df["BaseDateTime"].min().isoformat(),
            "end": df["BaseDateTime"].max().isoformat(),
        },
        "geoBounds": {
            "latMin": float(df["LAT"].min()), "latMax": float(df["LAT"].max()),
            "lonMin": float(df["LON"].min()), "lonMax": float(df["LON"].max()),
        },
        "avgSpeed": round(float(sog.mean()), 2),
        "dataSource": "AIS Repository Dataset (real records)",
    }


# ─── SAR endpoints ────────────────────────────────────────────────────

_sar_cache: Optional[dict] = None


def _scan_sar() -> dict:
    global _sar_cache
    if _sar_cache is not None:
        return _sar_cache
    sar_dir = Path(config.SAR_DIR)
    images: dict[str, list] = {"0": [], "1": []}
    for cls in ("0", "1"):
        d = sar_dir / cls
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    parts = f.name.rsplit("_cls_", 1)
                    region = parts[0].rsplit("_", 1)[-1] if parts[0] else ""
                    images[cls].append(
                        {
                            "filename": f.name,
                            "class": int(cls),
                            "className": "Oil Spill" if cls == "1" else "No Oil Spill",
                            "region": region,
                            "path": str(f),
                            "dimensions": "400x400",
                            "format": "Grayscale JPG",
                        }
                    )
    _sar_cache = images
    return images


@router.get("/sar/summary", response_model=SARSummary)
def sar_summary():
    images = _scan_sar()
    model_info = ml.get_model_info()
    return SARSummary(
        totalImages=len(images["0"]) + len(images["1"]),
        class0Count=len(images["0"]),
        class1Count=len(images["1"]),
        classes=[
            {"id": 0, "name": "No Oil Spill", "count": len(images["0"])},
            {"id": 1, "name": "Oil Spill", "count": len(images["1"])},
        ],
        imageFormat="400x400 Grayscale JPG",
        source="SAR (Synthetic Aperture Radar) Imagery",
        modelStatus=(
            f"Trained: {model_info.get('model_type')} — holdout acc {model_info.get('holdout_accuracy')}, "
            f"5-fold CV {model_info.get('cv_accuracy_mean')}"
            if model_info.get("available") else "Not trained — run train_sar_classifier.py"
        ),
        note=(
            "Classification performed by a trained model on real SAR imagery"
            if model_info.get("available")
            else "No classifier trained; demo labels only"
        ),
    )


@router.get("/sar/images")
def sar_images(
    cls: Optional[int] = Query(None, ge=0, le=1),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    region: str = Query(""),
):
    images = _scan_sar()
    all_imgs = images.get(str(cls), []) if cls is not None else images["0"] + images["1"]
    if region:
        all_imgs = [i for i in all_imgs if i["region"].upper() == region.upper()]
    total = len(all_imgs)
    start = (page - 1) * pageSize
    return {
        "images": all_imgs[start:start + pageSize],
        "total": total, "page": page, "pageSize": pageSize,
        "totalPages": max(1, math.ceil(total / pageSize)),
    }


@router.get("/sar/image/{cls}/{filename}")
def sar_image(cls: int, filename: str):
    # strict filename validation (no traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = Path(config.SAR_DIR) / str(cls) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/sar/regions")
def sar_regions():
    images = _scan_sar()
    regions = sorted({i["region"] for imgs in images.values() for i in imgs if i["region"]})
    return regions


@router.get("/sar/detections", response_model=list[SARDetection])
def sar_detections():
    """Sample detections using the REAL trained classifier on real dataset images."""
    images = _scan_sar()
    model = ml.load_model()
    if model is None:
        # honest fallback — same as v1 demo listing
        out = []
        for i, img in enumerate(random.sample(images["1"], min(5, len(images["1"])))):
            out.append(SARDetection(
                id=f"DET-DEMO-{i+1:03d}", filename=img["filename"],
                **{"class": 1},
                className="Oil Spill Detected", region=img["region"], isDemo=True,
                note="No trained classifier — demo listing only", status="Demo",
                dimensions=img["dimensions"]))
        return out

    detections = []
    # sample a few from each class and run REAL inference
    for cls in ("1", "0"):
        sample = random.sample(images[cls], min(4, len(images[cls])))
        for img in sample:
            from PIL import Image as PILImage
            arr = np.asarray(PILImage.open(img["path"]).convert("L"), dtype=np.float64) / 255.0
            pred, prob = model.predict(arr)
            detections.append(SARDetection(
                id=f"DET-MODEL-{len(detections)+1:03d}",
                filename=img["filename"],
                **{"class": int(pred)},
                className="Oil Spill Detected" if pred == 1 else "No Oil Spill",
                region=img["region"], isDemo=False,
                note=f"Trained classifier output (P(spill)={prob:.2f})",
                status="Model", dimensions=img["dimensions"]))
    return detections


# ─── Investigations (demo, preserved contract) ─────────────────────────


@router.get("/investigations")
def get_investigations():
    """Demo investigations — now backed by real pipeline runs when available."""
    from ..db import store
    runs = store.list_runs(limit=5)
    investigations = []
    for r in runs:
        investigations.append({
            "id": r["run_id"],
            "title": f"Pipeline Run {r['run_id']} — " + ("Spill Detected" if r.get("detected") else "No Spill"),
            "status": "Completed" if r.get("status") == "completed" else str(r.get("status", "unknown")),
            "isDemo": True,
            "note": "Generated by the full detection→hindcast→attribution pipeline",
            "region": {
                "centerLat": r.get("origin_lat") or config.DEMO_SPILL_LAT,
                "centerLon": r.get("origin_lon") or config.DEMO_SPILL_LON,
                "radiusKm": 35.0,
            },
            "spillDetection": {
                "status": "Model" if r.get("detected") else "Negative",
                "source": "SAR dataset + trained classifier",
                "note": f"confidence={r.get('confidence')}",
            },
            "aisCorrelation": {
                "status": "Completed",
                "vesselsInRegion": r.get("candidate_count", 0),
                "anomaliesDetected": f"top score {r.get('top_score')}" if r.get("top_score") else "n/a",
            },
            "timeline": [
                {"event": "SAR Detection", "status": "Available", "description": "Trained classifier inference"},
                {"event": "Hindcast", "status": "Available", "description": "Origin estimated via backward drift"},
                {"event": "AIS Correlation", "status": "Available", "description": f"{r.get('candidate_count', 0)} candidates ranked"},
            ],
        })
    if not investigations:
        # static demo fallback (frontend labels everything Demo)
        investigations.append({
            "id": "INV-DEMO-001",
            "title": "Demo Investigation — Gulf of Mexico Region",
            "status": "Demo", "isDemo": True,
            "note": "Run POST /api/pipeline/run to generate a real analysis",
            "region": {"centerLat": config.DEMO_SPILL_LAT, "centerLon": config.DEMO_SPILL_LON, "radiusKm": 35.0},
            "spillDetection": {"status": "Demo", "source": "Awaiting pipeline run", "note": "POST /api/pipeline/run"},
            "aisCorrelation": {"status": "Demo", "vesselsInRegion": 0, "anomaliesDetected": "Pending"},
            "timeline": [
                {"event": "Pipeline", "status": "Not Configured", "description": "No runs yet — POST /api/pipeline/run"},
            ],
        })
    return {"investigations": investigations}
