"""Central configuration. All paths relative to repo root or via environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# backend/ directory (this file: backend/app/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent
# repository root (backend/..)
REPO_ROOT = BACKEND_DIR.parent


def _repo_rel_env(env_key: str, default: Path | str) -> Path:
    """Resolve a path from env var; relative paths are resolved against the repo root."""
    val = os.environ.get(env_key)
    if val is None:
        p = Path(default)
    else:
        p = Path(val)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    return p


# ── Data locations ────────────────────────────────────────────────────────
DATA_DIR = _repo_rel_env("DATA_DIR", "Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data")
AIS_CSV = _repo_rel_env("AIS_CSV", DATA_DIR / "AIS Dataset")
SAR_DIR = _repo_rel_env("SAR_DIR", DATA_DIR / "SAR Image Dataset")

# Auto-detect AIS CSV if the env var points at a directory
if AIS_CSV.is_dir():
    _csvs = sorted(AIS_CSV.glob("*.csv"))
    AIS_CSV = _csvs[0] if _csvs else AIS_CSV

# ── Model artifacts ───────────────────────────────────────────────────────
MODELS_DIR = _repo_rel_env("MODELS_DIR", BACKEND_DIR / "models")
SPILL_CLASSIFIER_PATH = _repo_rel_env("SPILL_CLASSIFIER_PATH", MODELS_DIR / "sar_spill_classifier.pkl")
CNN_MODEL_PATH = _repo_rel_env("CNN_MODEL_PATH", MODELS_DIR / "sar_spill_cnn.keras")  # optional TF CNN

# ── Persistence (JSON file store — demo-friendly; no mandatory database) ──
RUNS_DIR = _repo_rel_env("RUNS_DIR", BACKEND_DIR / "data" / "runs")

# ── Demo mode ─────────────────────────────────────────────────────────────
# When true (or when real providers are unavailable), synthetic environmental
# data is used and clearly labelled as such in every response.
DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() in ("1", "true", "yes")

# Demo scenario coordinates (Gulf of Mexico — inside the real AIS dataset area).
# The SAR images are NOT georeferenced; any geographic spill location shown in
# demo mode is SYNTHETIC and labelled as such.
DEMO_SPILL_LAT = float(os.environ.get("DEMO_SPILL_LAT", "28.52"))
DEMO_SPILL_LON = float(os.environ.get("DEMO_SPILL_LON", "-94.95"))
DEMO_OBSERVATION_TIME = os.environ.get(
    "DEMO_OBSERVATION_TIME", "2021-02-01T12:00:00Z"
)

# ── Environmental providers ───────────────────────────────────────────────
# Open-Meteo Marine API (no key required, free tier). If unreachable the
# system falls back to the clearly-labelled demo provider.
OPEN_METEOMARINE_URL = os.environ.get(
    "OPEN_METEOMARINE_URL", "https://marine-api.open-meteo.com/v1/marine"
)
OPEN_METEO_URL = os.environ.get(
    "OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"
)
ENV_CACHE_DIR = _repo_rel_env("ENV_CACHE_DIR", BACKEND_DIR / "data" / "env_cache")
ENV_TIMEOUT_SECONDS = float(os.environ.get("ENV_TIMEOUT_SECONDS", "6"))

# ── Drift model defaults ──────────────────────────────────────────────────
DEFAULT_WINDAGE = float(os.environ.get("DEFAULT_WINDAGE", "0.03"))  # 3% of wind speed
DEFAULT_TIMESTEP_MIN = int(os.environ.get("DEFAULT_TIMESTEP_MIN", "30"))
DEFAULT_HINDCAST_HOURS = int(os.environ.get("DEFAULT_HINDCAST_HOURS", "48"))
DEFAULT_FORECAST_HOURS = int(os.environ.get("DEFAULT_FORECAST_HOURS", "48"))
# Uncertainty growth (fraction of displacement per hour, applied per component)
UNCERTAINTY_GROWTH_RATE = float(os.environ.get("UNCERTAINTY_GROWTH_RATE", "0.15"))
MONTE_CARLO_MEMBERS = int(os.environ.get("MONTE_CARLO_MEMBERS", "40"))

# ── AIS search defaults ───────────────────────────────────────────────────
AIS_SEARCH_RADIUS_KM = float(os.environ.get("AIS_SEARCH_RADIUS_KM", "15"))
AIS_TIME_WINDOW_HOURS = float(os.environ.get("AIS_TIME_WINDOW_HOURS", "12"))
MIN_AIS_OBSERVATIONS = int(os.environ.get("MIN_AIS_OBSERVATIONS", "3"))
MAX_SOG_KNOTS = float(os.environ.get("MAX_SOG_KNOTS", "60"))  # physical speed cap

# ── Attribution scoring weights (configurable; must sum to ~1.0) ──────────
def scoring_weights() -> dict[str, float]:
    """Weights are read from env so they can be tuned without code changes."""
    default = {
        "spatial": 0.30,
        "temporal": 0.25,
        "trajectory": 0.20,
        "behaviour": 0.15,
        "data_quality": 0.10,
    }
    out = {}
    for key, val in default.items():
        out[key] = float(os.environ.get(f"SCORE_WEIGHT_{key.upper()}", str(val)))
    return out


ATTRIBUTION_DISCLAIMER = (
    "This is an investigation-priority score, not proof of responsibility. "
    "It ranks vessels by spatio-temporal and behavioural evidence only."
)

# ── Upload constraints ─────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
