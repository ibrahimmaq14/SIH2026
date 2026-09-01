"""
Oil Spill Detection — Maritime Intelligence Backend API

FastAPI backend serving:
- AIS vessel data (paginated, filterable)
- Vessel track retrieval
- SVR-based anomaly detection (replicating notebook methodology)
- SAR image dataset serving
- Analytics and pipeline status

Architecture: FastAPI → pandas/scikit-learn → CSV/Image data
No database needed — the AIS dataset fits comfortably in memory.
"""

import os
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager

from services import ais_service, sar_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load data on startup."""
    print("Loading AIS dataset...")
    try:
        df = ais_service.get_dataframe()
        print(f"AIS dataset loaded: {len(df)} records, {df['MMSI'].nunique()} vessels")
    except Exception as e:
        print(f"Warning: Could not load AIS data: {e}")

    print("Scanning SAR images...")
    try:
        summary = sar_service.get_sar_summary()
        print(f"SAR dataset: {summary['totalImages']} images ({summary['class0Count']} clean, {summary['class1Count']} spill)")
    except Exception as e:
        print(f"Warning: Could not scan SAR images: {e}")

    yield


app = FastAPI(
    title="Oil Spill Detection — Maritime Intelligence API",
    description="Backend API for the Oil Spill Detection system combining AIS analysis and SAR imagery",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health & Status ───────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "oil-spill-detection-api"}


@app.get("/api/pipeline/status")
def pipeline_status():
    """Get honest pipeline status — what's available, what's demo."""
    ais_loaded = ais_service._df is not None
    sar_available = os.path.isdir(os.path.join(
        sar_service._get_sar_dir()
    ))

    return {
        "pipeline": [
            {
                "stage": "Data Ingestion",
                "status": "Available" if ais_loaded else "Offline",
                "description": "AIS CSV dataset loaded into memory",
                "lastRun": "On startup",
            },
            {
                "stage": "AIS Preprocessing",
                "status": "Available" if ais_loaded else "Offline",
                "description": "DateTime extraction, missing value interpolation, sorting",
                "methodology": "Linear interpolation + forward/backward fill (from notebook)",
            },
            {
                "stage": "SAR Image Dataset",
                "status": "Available" if sar_available else "Offline",
                "description": "SAR imagery dataset for oil spill classification",
                "note": "Dataset available, no trained CNN model",
            },
            {
                "stage": "SAR CNN Model",
                "status": "Not Configured",
                "description": "CNN model for oil spill detection from SAR images",
                "note": "No trained model exists in the repository. Architecture supports future integration.",
            },
            {
                "stage": "AIS Anomaly Detection (SVR)",
                "status": "Available" if ais_loaded else "Offline",
                "description": "Support Vector Regression predicting SOG anomalies",
                "methodology": "SVR(gamma='scale', C=100000, epsilon=1, degree=3) — from notebook",
                "features": "LAT, Hour, Cargo, COG → SOG",
            },
            {
                "stage": "AIS-SAR Integration",
                "status": "Not Configured",
                "description": "Correlation of AIS anomalies with SAR detections",
                "note": "Architecture supports future integration",
            },
            {
                "stage": "Drift Analysis",
                "status": "Not Configured",
                "description": "Oceanographic drift modeling and hindcasting",
                "note": "Placeholder for future capability",
            },
            {
                "stage": "Investigation Engine",
                "status": "Demo",
                "description": "Combined analysis linking spills to vessels",
                "note": "Demo workflow — not connected to live inference",
            },
        ],
    }


# ─── AIS Endpoints ────────────────────────────────────────────────────

@app.get("/api/vessels")
def get_vessels(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    search: str = Query(""),
    sortBy: str = Query("MMSI"),
    sortOrder: str = Query("asc"),
    vesselType: Optional[str] = Query(None),
):
    """Get paginated vessel list with search, filter, sort."""
    try:
        return ais_service.get_vessels(page, pageSize, search, sortBy, sortOrder, vesselType)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vessels/types")
def get_vessel_types():
    """Get available vessel types for filtering."""
    try:
        return ais_service.get_vessel_types()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vessels/{mmsi}")
def get_vessel_detail(mmsi: int):
    """Get vessel detail with full track."""
    try:
        result = ais_service.get_vessel_track(mmsi)
        if not result["track"]:
            raise HTTPException(status_code=404, detail=f"Vessel {mmsi} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vessels/{mmsi}/anomalies")
def get_vessel_anomalies(
    mmsi: int,
    threshold: float = Query(6.0, ge=1.0, le=20.0),
):
    """Run SVR anomaly detection on a specific vessel."""
    try:
        return ais_service.run_anomaly_detection(mmsi, threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anomalies")
def get_all_anomalies(
    threshold: float = Query(6.0, ge=1.0, le=20.0),
    maxVessels: int = Query(20, ge=1, le=100),
):
    """Run anomaly detection across top vessels."""
    try:
        return ais_service.get_all_anomalies(threshold, maxVessels)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics")
def get_analytics():
    """Get AIS analytics data (replicating notebook EDA)."""
    try:
        return ais_service.get_analytics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/overview")
def get_overview():
    """Get overview dashboard stats."""
    try:
        return ais_service.get_overview_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── SAR Endpoints ────────────────────────────────────────────────────

@app.get("/api/sar/summary")
def sar_summary():
    """Get SAR dataset summary."""
    try:
        return sar_service.get_sar_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/images")
def sar_images(
    cls: Optional[int] = Query(None, ge=0, le=1),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    region: str = Query(""),
):
    """Get paginated SAR image listing."""
    try:
        return sar_service.get_sar_images(cls, page, pageSize, region)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/image/{cls}/{filename}")
def sar_image(cls: int, filename: str):
    """Serve a specific SAR image file."""
    path = sar_service.get_image_path(cls, filename)
    if not path:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/sar/regions")
def sar_regions():
    """Get available SAR image regions."""
    try:
        return sar_service.get_regions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sar/detections")
def sar_detections():
    """Get demo detection results (clearly labeled as demo)."""
    try:
        return sar_service.get_demo_detections()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Investigation (Demo) ─────────────────────────────────────────────

@app.get("/api/investigations")
def get_investigations():
    """
    Get demo investigation data.
    This is sample data to demonstrate the investigation workflow.
    No real AIS-SAR correlation is implemented.
    """
    try:
        analytics = ais_service.get_analytics()
        geo = analytics["geoBounds"]

        # Create a demo investigation centered on the data region
        center_lat = (geo["latMin"] + geo["latMax"]) / 2
        center_lon = (geo["lonMin"] + geo["lonMax"]) / 2

        return {
            "investigations": [
                {
                    "id": "INV-DEMO-001",
                    "title": "Demo Investigation — Gulf of Mexico Region",
                    "status": "Demo",
                    "isDemo": True,
                    "note": "Sample investigation workflow — not connected to real inference",
                    "region": {
                        "centerLat": center_lat,
                        "centerLon": center_lon,
                        "radiusKm": 50,
                    },
                    "spillDetection": {
                        "status": "Demo",
                        "source": "SAR Dataset Sample",
                        "note": "No CNN model available — demo data only",
                    },
                    "aisCorrelation": {
                        "status": "Demo",
                        "vesselsInRegion": analytics["uniqueVessels"],
                        "anomaliesDetected": "Pending analysis",
                    },
                    "timeline": [
                        {"event": "SAR Image Acquired", "status": "Demo", "description": "Sample SAR imagery from dataset"},
                        {"event": "Oil Spill Classification", "status": "Not configured", "description": "CNN model not trained"},
                        {"event": "AIS Data Analysis", "status": "Available", "description": "SVR anomaly detection ready"},
                        {"event": "Vessel Attribution", "status": "Not configured", "description": "AIS-SAR correlation not implemented"},
                    ],
                }
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
