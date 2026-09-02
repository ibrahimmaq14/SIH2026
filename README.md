# SENTINEL — Oil Spill Detection, Spill Tracking & Vessel Attribution

End-to-end maritime intelligence system implementing the SIH problem statement:

> *"Leveraging satellite imagery to determine oil spills at sea along with AIS data correlations to identify the vessel responsible for the spill."*

SAR image → spill detection → slick characterization → ocean/weather data →
hindcast drift → estimated origin → AIS historical traffic → vessel filtering →
trajectory analysis → behaviour anomalies → suspect scoring → ranked candidate
vessels → dashboard.

---

## 1. Project overview

| Layer | Technology | Location |
|---|---|---|
| Frontend | Next.js 16, React 19, Leaflet, Recharts | `frontend/` |
| Backend | FastAPI, pandas, scikit-learn, Pillow | `backend/` |
| ML | Texture-feature classifier (HistGradientBoosting) + notebook SVR anomaly model | `backend/app/ml/`, `backend/train_sar_classifier.py` |
| Data | 52,943-record AIS CSV (347 vessels, Gulf of Mexico, Dec 2020–Mar 2021), 5,630 SAR images (400×400, class 0/1) | `Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data/` |
| Persistence | JSON file store per pipeline run (no mandatory DB) | `backend/data/runs/` |

## 2. Architecture

```
┌────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (Next.js :3000)  │  GET   │  Backend (FastAPI :8000)             │
│  Leaflet map · dossier UI  │ ─────▶ │  app/api/legacy.py   (14 endpoints) │
│  Recharts analytics        │  POST  │  app/api/pipeline_api.py (new)       │
└────────────────────────────┘        │  app/services/*                      │
                                      │   detection → environment → drift   │
                                      │   → ais → attribution → pipeline    │
                                      │  app/ml/features.py (classifier)    │
                                      │  app/db/store.py (JSON runs)        │
                                      └──────────────┬───────────────────────┘
                                                     │
                                     real AIS CSV + SAR images + Open-Meteo
                                     (falls back to labelled synthetic env)
```

## 3. What was reused vs. newly implemented

**Reused from the original repository (nothing deleted):**
- AIS dataset + notebook SVR anomaly methodology (`SVR(gamma='scale', C=100000, epsilon=1, degree=3)`, features `[LAT, hour, Cargo, COG] → SOG`, threshold |Δ| ≥ 6 kn) — now a service (`app/services/ais.py::svr_anomalies_for_vessel`) reused inside the attribution behaviour scoring.
- SAR image dataset (5,630 JPGs) — used to TRAIN the spill classifier and served to the UI.
- The separately-built frontend — preserved in full; only extended (new optional map layers, one page converted to live pipeline mode, honest status texts).

**Newly implemented (the missing SIH functionality):**
- Honest, trained SAR spill classifier (see §7) — the README's claimed CNN **never existed** in the repo (no code, no weights).
- Weak, explainable slick segmentation + geometric characterization (centroid, bbox, area, perimeter, length/width, aspect, orientation).
- Environmental provider abstraction: real Open-Meteo Marine + clearly-labelled synthetic demo provider.
- Great-circle drift engine: forward forecast + backward hindcast with configurable windage, timestep, Monte-Carlo ensemble uncertainty.
- AIS spatio-temporal candidate search around the ESTIMATED ORIGIN (not the observed slick), explainable filtering (distance, data sufficiency, physical reachability), trajectory feature extraction, behaviour anomaly rules.
- Transparent configurable suspect scoring + ranked candidates with per-vessel evidence.
- Full pipeline orchestration + JSON persistence + 76-test pytest suite.

## 4. Installation

```bash
# Backend (Python 3.11)
cd backend
pip install -r requirements.txt

# Frontend (Node 20+)
cd frontend
npm install
```

## 5. Environment setup

Copy `.env.example` → adjust if needed. Defaults run fully offline in demo
mode. No API keys are required. Never commit real secrets.

## 6. Dataset setup

Already present in the repository at
`Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data/`
(AIS CSV + SAR classes 0/1). Paths are configurable via `DATA_DIR`,
`AIS_CSV`, `SAR_DIR` (see `.env.example`).

## 7. Model setup / training

The original project had **no trained model**. Train the real classifier:

```bash
cd backend
python train_sar_classifier.py            # full: ~3 min, incl. 5-fold CV
python train_sar_classifier.py --quick    # 800-image smoke train
```

Measured performance (honest, from the training log):
- Holdout accuracy: **89.5%** (1,126 test images)
- 5-fold stratified CV: **87.5% mean** (folds 0.858–0.893)
- Class 1 (spill) F1: 0.836 · Class 0 F1: 0.923

If the model file is absent, detection endpoints fall back to a clearly
labelled heuristic and tell you to run training. **No accuracy is fabricated.**

## 8. Run the backend

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
# or: python main.py        (Windows: start-backend.bat)
```

## 9. Run the frontend

```bash
cd frontend
npm run dev        # dev server on :3000
# or production: npm run build && npm run start
# Windows: start-frontend.bat / start-all.bat
```

## 10. Demo mode

`DEMO_MODE=true` (default) forces the labelled synthetic environmental
provider so the whole pipeline runs offline. The SAR images are NOT
georeferenced — in demo runs the spill location is anchored SYNTHETICALLY
inside the real AIS dataset's coverage area (Gulf of Mexico) and every
affected response carries a `synthetic` data-class label plus disclaimers.

Set `DEMO_MODE=false` to use real Open-Meteo ocean/wind data (free, no key;
requires internet; only covers recent dates).

## 11. API documentation

Interactive docs: `http://localhost:8000/docs`

**Preserved frontend endpoints (all GET):**
`/api/health`, `/api/vessels`, `/api/vessels/types`, `/api/vessels/{mmsi}`,
`/api/vessels/{mmsi}/anomalies`, `/api/anomalies`, `/api/analytics`,
`/api/overview`, `/api/sar/summary`, `/api/sar/images`, `/api/sar/image/{cls}/{filename}`,
`/api/sar/regions`, `/api/sar/detections`, `/api/pipeline/status`, `/api/investigations`

**New pipeline endpoints:**
| Endpoint | Purpose |
|---|---|
| `POST /api/spill/detect` | Upload SAR image → detection + characterization |
| `POST /api/spill/analyze` | Same for a dataset image by filename |
| `POST /api/drift/hindcast` | Backward drift → estimated origin + uncertainty + confidence |
| `POST /api/drift/forecast` | Forward drift → predicted trajectory + uncertainty |
| `POST /api/ais/search` | Spatio-temporal AIS search around a point+time |
| `POST /api/vessels/analyze` | Full attribution around an origin (form) |
| `POST /api/attribution/rank` | Same, JSON body |
| `POST /api/pipeline/run` | **Complete pipeline** (optional image upload) |
| `GET /api/pipeline/runs` | List persisted runs |
| `GET /api/pipeline/runs/{run_id}` | Fetch a persisted run |

## 12. Pipeline explanation

`POST /api/pipeline/run` executes:

1. **Detection** — trained classifier on the SAR image (`dataClass: model`), or labelled heuristic if untrained.
2. **Characterization** — weak adaptive-threshold segmentation of the suspected slick (labelled `weak` — the dataset has no pixel masks); pixel-space geometry only.
3. **Anchor** — real coordinates if user-supplied; otherwise a clearly-labelled synthetic anchor inside the AIS coverage area.
4. **Environment** — provider chain: Open-Meteo (real, if enabled/available) → synthetic demo provider.
5. **Hindcast** — time-reversed advection `drift = current + windage × wind` with great-circle displacement; Monte-Carlo ensemble for an uncertainty radius; returns estimated origin location + time + confidence.
6. **Forecast** — forward drift for configurable horizon (6–72 h typical).
7. **AIS correlation** — candidate vessels with pings around the ESTIMATED ORIGIN within the release window (not around the observed slick).
8. **Filtering** — explainable exclusions (too far, insufficient data, physically implausible trajectories).
9. **Trajectory analysis** — closest approach, dwell, approach/departure bearings, course/speed changes, route deviation.
10. **Behaviour anomaly** — interpretable rules (dwell, speed changes, erratic course, near-stop at closest approach, route deviation) + the notebook's SVR anomalies inside the window.
11. **Scoring** — weighted, configurable (see below).
12. **Persistence** — run saved to JSON; frontend renders it.

## 13. Attribution methodology & scoring

Investigation-priority score ∈ [0, 100]:

| Component | Default weight | Signal |
|---|---|---|
| Spatial | 30% | closest-approach distance vs. search radius |
| Temporal | 25% | |Δt| of closest approach vs. release window |
| Trajectory | 20% | pass-through, dwell, route deviation |
| Behaviour | 15% | anomaly score (rules + SVR) |
| Data quality | 10% | AIS observation density |

Weights are env-configurable (`SCORE_WEIGHT_*`) and returned in every
response (`weights_used`). Each candidate carries component scores, evidence
bullets, filter reasons, its AIS track, and a disclaimer.

**This is an investigation-priority score, NOT proof of responsibility.** The
UI and API repeat this everywhere. Scores can be wrong when the hindcast
origin estimate is wrong; the origin itself is a model estimate with an
explicit uncertainty radius.

## 14. Data-provenance labels

Every result carries `source_label.dataClass`:
- `model` — real trained-model output (or real AIS records / real provider data)
- `heuristic` — explainable rule-based fallback (e.g. untrained detection)
- `synthetic` — demo data (e.g. demo environment provider, synthetic geo anchor)
- `unavailable` — missing data, reported honestly (never fabricated)

Spill **age** is explicitly reported as unavailable: only observation time is
returned; nothing is invented.

## 15. Limitations

- SAR dataset images are NOT georeferenced → geographic spill coordinates in
  demo runs are synthetic anchors (labelled as such).
- No pixel-level ground truth → slick "segmentation" is a labelled weak
  heuristic, not a trained segmentation model.
- Drift model is simple advection (current + windage wind); no oil
  weathering, spreading, or dissipation.
- Open-Meteo free tier provides no historical ocean currents for 2021 demo
  dates → demo environment is synthetic by design.
- AIS dataset covers one small Gulf of Mexico zone over ~3 months; attribution
  resolution is limited by that coverage.
- Behaviour DBSCAN: the README claimed DBSCAN but the repo never implemented
  it; this system uses interpretable behaviour rules + the notebook's SVR
  instead, which suits the small per-vessel samples better.

## 16. Future improvements

- Train a real segmentation model (e.g. U-Net) if pixel masks are obtained.
- Integrate Sentinel-1 GRD via Copernicus with real geolocation (SNAP/pyroSAR).
- Higher-fidelity drift (OpenDrift-style leeway classes, oil weathering).
- Live AIS ingestion (AISHub/NOAA ERMA) instead of static CSV.
- MongoDB/PostgreSQL persistence for multi-user case management.

## 17. Tests

```bash
cd backend
python -m pytest tests -q
# 76 passed — geo math, drift physics, hindcast round-trip, AIS cleaning,
# trajectory features, anomaly flags, scoring, all API endpoints,
# full end-to-end pipeline run, upload validation, traversal protection
```
