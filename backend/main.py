"""
Oil Spill Detection — Maritime Intelligence Backend API (v2)

FastAPI backend serving:
- Legacy endpoints (preserved contracts for the existing frontend):
  AIS vessels/tracks/anomalies/analytics, SAR dataset, investigations, status
- New SIH pipeline endpoints:
  POST /api/spill/detect | /api/spill/analyze
  POST /api/drift/hindcast | /api/drift/forecast
  POST /api/ais/search | /api/vessels/analyze | /api/attribution/rank
  POST /api/pipeline/run   (full end-to-end pipeline)
  GET  /api/pipeline/runs[/{run_id}]
  GET  /api/health

Run:  uvicorn main:app --host 0.0.0.0 --port 8000   (from backend/)
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ensure backend/ is importable when started via `python main.py` or uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api import legacy, pipeline_api
from app.ml import features as ml
from app.services import ais as aissvc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Oil Spill Detection API v2")
    try:
        df = aissvc.get_dataframe()
        logger.info("AIS dataset: %d records, %d vessels", len(df), df["MMSI"].nunique())
    except Exception as e:
        logger.warning("AIS data unavailable: %s", e)

    model = ml.load_model()
    if model is not None:
        logger.info(
            "SAR classifier loaded: holdout acc=%s, 5-fold CV=%s",
            model.metadata.get("holdout_accuracy"),
            model.metadata.get("cv_accuracy_mean"),
        )
    else:
        logger.warning(
            "SAR classifier NOT trained — detection falls back to a labelled "
            "heuristic. Run: python train_sar_classifier.py"
        )
    logger.info("Demo mode: %s", config.DEMO_MODE)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Oil Spill Detection — Maritime Intelligence API",
    description=(
        "Backend for the SIH oil-spill detection system: SAR spill detection, "
        "slick characterization, drift hindcast/forecast, AIS correlation "
        "and vessel attribution ranking. All synthetic/demo outputs are "
        "explicitly labelled."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(legacy.router, prefix="/api")
app.include_router(pipeline_api.router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
