# RUN.md — SENTINEL Oil Spill Detection System

Complete guide to what was built and how to run it.

---

## 1. What This System Does

Implements the SIH problem statement end-to-end:

> *"Leveraging satellite imagery to determine oil spills at sea along with AIS data correlations to identify the vessel responsible for the spill."*

The full chain, executable via one API call or one button in the UI:

```
SAR satellite image
   → OIL SPILL DETECTION          (trained classifier, real model output)
   → SPILL CHARACTERIZATION        (slick geometry: centroid, area, length, width, orientation)
   → SPILL LOCATION / TIME        (real coords if provided; labelled synthetic anchor in demo)
   → OCEAN + WEATHER DATA          (real Open-Meteo OR clearly-labelled synthetic provider)
   → HINDCAST DRIFT                (backward simulation → estimated origin + release time + uncertainty)
   → FORWARD FORECAST              (future slick movement, 6–72h)
   → AIS HISTORICAL TRAFFIC        (52,943 real records, 347 vessels, Gulf of Mexico)
   → VESSEL FILTERING              (explainable: distance, data sufficiency, physical reachability)
   → TRAJECTORY ANALYSIS           (closest approach, dwell, course/speed changes, route deviation)
   → BEHAVIOUR ANOMALY ANALYSIS    (interpretable rules + the notebook's SVR model)
   → SUSPECT SCORING               (transparent, configurable weights)
   → RANKED CANDIDATE VESSELS      (investigation priorities — NOT proof of guilt)
   → FRONTEND DASHBOARD            (map layers, dossier, evidence panel, timeline)
```

---

## 2. What Existed vs. What Was Built

### Already existed (reused, nothing deleted)
| Component | Status |
|---|---|
| AIS dataset — 52,943 records, 347 vessels, Gulf of Mexico, Dec 2020–Mar 2021 | Reused as-is |
| SAR dataset — 5,630 images (3,725 clean / 1,905 spill, 400×400 JPG) | Reused to train the classifier + served to UI |
| Notebook SVR anomaly model (`SVR(gamma='scale', C=100000, epsilon=1, degree=3)`, features `[LAT, hour, Cargo, COG] → SOG`, threshold \|Δ\| ≥ 6 kn) | Reused as a service AND inside attribution scoring |
| Next.js frontend (7 pages, Leaflet map, Recharts, 14 GET API functions) | Preserved in full, only extended |

### Did NOT exist (claims vs. reality — verified by inspection)
- ❌ The README claimed a **TensorFlow/Keras CNN** — no CNN code or weights ever existed in the repo
- ❌ The README claimed **DBSCAN** anomaly detection — never implemented (notebook uses SVR)
- ❌ No trained model files of any kind (`.h5`, `.pb`, `.pt`, `.pkl`, `.onnx`)
- ❌ No drift/hindcast, no origin estimation, no AIS-SAR correlation, no attribution, no tests

### Newly built
| Module | File(s) |
|---|---|
| Geographic math (haversine, bearing, great-circle destination) | `backend/app/core/geo.py` |
| Pydantic API contracts (incl. all legacy frontend contracts) | `backend/app/schemas.py` |
| SAR feature extraction + classifier persistence | `backend/app/ml/features.py` |
| Model training script (reproducible, honest CV metrics) | `backend/train_sar_classifier.py` |
| **Trained model artifact** (89.5% holdout / 87.5% 5-fold CV) | `backend/models/sar_spill_classifier.pkl` |
| Spill detection + weak slick segmentation + characterization | `backend/app/services/detection.py` |
| Environmental providers (real Open-Meteo + labelled synthetic demo) | `backend/app/services/environment.py` |
| Drift engine: forward forecast + backward hindcast + Monte-Carlo uncertainty | `backend/app/services/drift.py` |
| AIS cleaning, spatio-temporal search, trajectory features, anomaly rules, scoring | `backend/app/services/ais.py` |
| Attribution orchestrator (search → filter → analyze → score → rank) | `backend/app/services/attribution.py` |
| End-to-end pipeline orchestrator | `backend/app/services/pipeline.py` |
| JSON run persistence (no DB required) | `backend/app/db/store.py` |
| Legacy API (all 14 original frontend endpoints, contracts preserved) | `backend/app/api/legacy.py` |
| New pipeline API (POST endpoints) | `backend/app/api/pipeline_api.py` |
| FastAPI app wiring + logging | `backend/main.py` |
| Test suite — 76 tests, all passing | `backend/tests/` |
| Frontend: pipeline API client + types | `frontend/src/lib/api.ts`, `types.ts` |
| Frontend: map layers (hindcast/forecast paths, origin + uncertainty circle, candidate tracks) | `frontend/src/components/MaritimeMapInner.tsx` |
| Frontend: Investigations page = live pipeline dashboard (Run button, image upload, ranked candidates, score bars, evidence) | `frontend/src/app/investigations/page.tsx` |
| Honest status copy on Detection + Pipeline pages | `frontend/src/app/detection/page.tsx`, `pipeline/page.tsx` |
| Configuration template | `.env.example` |

---

## 3. Prerequisites

- **Python 3.11** (the machine already has it; other 3.10+ should work)
- **Node.js 20+** and npm
- No API keys needed. No database needed. Runs fully offline in demo mode.

---

## 4. Quick Start (Windows)

**Option A — one script:**

```
double-click  start-all.bat
```

This launches:
- Backend on http://localhost:8000
- Frontend on http://localhost:3000

**Option B — manual:**

Terminal 1 (backend):
```bat
cd backend
py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Terminal 2 (frontend):
```bat
cd frontend
npm run dev
```

Then open **http://localhost:3000**

> On first launch the backend prints:
> - `AIS dataset: 52,9xx records, 347 vessels`
> - `SAR classifier loaded: holdout acc=0.895, 5-fold CV=0.8746`
>
> If the classifier is NOT trained you'll see a warning instead — see §5.

---

## 5. Training the SAR Classifier (required once)

The repo shipped no model. The trained artifact (`backend/models/sar_spill_classifier.pkl`) is already included from my training run, but to retrain from scratch:

```bat
cd backend
py -3.11 train_sar_classifier.py
```

- Trains on all 5,630 images (~2–3 min on a typical laptop)
- Runs 5-fold stratified cross-validation at the end
- Saves model + honest metadata (accuracies, feature names, timestamps)

Variants:
```bat
python train_sar_classifier.py --quick      :: 800-image smoke train (~30s)
python train_sar_classifier.py --skip-cv    :: skip cross-validation
```

**Measured performance (real, from the training log — nothing fabricated):**

| Metric | Value |
|---|---|
| Holdout accuracy (20% split, 1,126 images) | **89.5%** |
| 5-fold CV mean | **87.5%** (folds 0.858 – 0.893) |
| Class 1 (spill) precision / recall / F1 | 0.888 / 0.790 / 0.836 |
| Class 0 (clean) precision / recall / F1 | 0.898 / 0.949 / 0.923 |

**Honesty note:** the original README claimed a "Customized CNN" — that model never existed. This system ships a real, reproducible classifier (native-resolution GLCM texture + multi-scale statistics + HistGradientBoosting) instead of pretending. If the model file is missing, detection falls back to a clearly-labelled heuristic and tells you to run training.

---

## 6. Running the Demo Pipeline

### From the UI
1. Open http://localhost:3000/investigations
2. The pipeline **auto-runs on page load** using a spill-class SAR image from the dataset
3. Click **Run pipeline** to re-run, or **Select SAR image** to upload your own JPG/PNG/TIFF first
4. Explore:
   - **Map** — amber dot = observed spill (synthetic anchor), purple = estimated origin with uncertainty circle, purple dashed line = hindcast path, cyan line = forecast path, blue dots = candidate vessels, orange track = selected candidate's AIS track. Layers are toggleable (top-right)
   - **Tabs (right panel)** — Summary (timeline + disclaimers), Spill (detection + geometry + hindcast details), AIS (ranked candidates), Evidence (score bars + evidence + trajectory stats for the selected vessel)

### From the API
```bash
# Full pipeline with defaults (uses a dataset spill image):
curl -X POST http://localhost:8000/api/pipeline/run

# With your own image and parameters:
curl -X POST http://localhost:8000/api/pipeline/run \
  -F "file=@my_sar_image.jpg" \
  -F "hindcast_hours=48" \
  -F "forecast_hours=72" \
  -F "windage=0.03" \
  -F "search_radius_km=15" \
  -F "window_hours=12"
```

Interactive API docs: **http://localhost:8000/docs**

### What a pipeline response contains
```jsonc
{
  "run_id": "run-3eff630b",
  "status": "completed",
  "detection": { "detected": true, "confidence": 0.965, "detection_method": "...(trained)", "source_label": { "dataClass": "model" } },
  "characterization": { "geometry": { "area_px": 448, "length_px": 34.2, "aspect_ratio": 4.28, "geometry_type": "elongated" } },
  "environment": { "provider": "demo-synthetic", "dataClass": "synthetic" },
  "hindcast": { "origin_location": {...}, "origin_time": "...", "uncertainty_radius_km": 3.61, "confidence": 0.55 },
  "forecast":  { "track": {...}, "total_displacement_km": 39.2 },
  "attribution": { "candidates": [ { "rank": 1, "mmsi": 477430900, "score": 95.3, "score_components": {...}, "evidence": [...] } ] },
  "timeline": [...],
  "disclaimers": [...]
}
```

Every result carries `source_label.dataClass` so nothing synthetic is mistaken for real:
- `model` — real trained-model output / real AIS records / real provider data
- `heuristic` — rule-based fallback (e.g., untrained detection)
- `synthetic` — demo data (demo environment, synthetic geo anchor)
- `unavailable` — missing data, reported honestly

---

## 7. API Reference

### Preserved frontend endpoints (all GET — the existing UI keeps working)
| Endpoint | Purpose |
|---|---|
| `/api/health` | Service + model + data status |
| `/api/vessels` | Paginated/searchable/sortable vessel list (PascalCase contract) |
| `/api/vessels/types` | Unique vessel types |
| `/api/vessels/{mmsi}` | Full vessel track + info (camelCase contract) |
| `/api/vessels/{mmsi}/anomalies` | SVR anomaly detection (snake_case `model_info` contract) |
| `/api/anomalies` | Fleet-wide anomalies (top vessels) |
| `/api/analytics` | Notebook EDA replication (correlations, distributions) |
| `/api/overview` | Dashboard stats |
| `/api/sar/summary` | SAR dataset summary + model status |
| `/api/sar/images` | Paginated image listing |
| `/api/sar/image/{cls}/{filename}` | Serve SAR image bytes (traversal-protected) |
| `/api/sar/regions` | Region codes from filenames |
| `/api/sar/detections` | REAL classifier inference on sample images |
| `/api/pipeline/status` | Honest stage-by-stage system status |
| `/api/investigations` | Now backed by real pipeline runs |

### New pipeline endpoints
| Endpoint | Purpose |
|---|---|
| `POST /api/spill/detect` | Upload SAR image → detection + characterization |
| `POST /api/spill/analyze` | Same, for a dataset image by filename |
| `POST /api/drift/hindcast` | Backward drift → origin estimate + uncertainty + confidence |
| `POST /api/drift/forecast` | Forward drift → predicted trajectory + uncertainty |
| `POST /api/ais/search` | Spatio-temporal AIS search around a point+time |
| `POST /api/vessels/analyze` | Full attribution around an origin (form body) |
| `POST /api/attribution/rank` | Same (JSON body) |
| `POST /api/pipeline/run` | **Complete end-to-end pipeline** (optional image upload) |
| `GET /api/pipeline/runs` | List persisted runs |
| `GET /api/pipeline/runs/{run_id}` | Fetch one persisted run |

---

## 8. How the Pieces Work

### Detection
`app/services/detection.py` — loads the trained classifier, runs inference (`dataClass: model`). If untrained, falls back to a texture-homogeneity heuristic, labelled as such, with a message telling you to train.

### Weak segmentation (slick region)
Explainable image processing: 8×8 block std map → adaptive threshold (blocks smoother AND darker than image medians) → largest connected region → geometry (centroid, bbox, area, perimeter, length/width via PCA, orientation, aspect ratio). **Explicitly labelled "weak"** — the dataset has no pixel masks, so this is a visual aid, not ground truth.

### Characterization & geographic honesty
The SAR images are plain JPGs with no georeferencing. Pixel-space geometry is always real. Geographic coordinates are only present when user-supplied; otherwise the demo anchors the spill inside the AIS dataset's coverage area and labels it `synthetic`. Spill **age is never invented** — only the observation time is reported, with "age estimation unavailable."

### Environmental data (provider abstraction)
`app/services/environment.py` — adapter chain:
1. **Open-Meteo Marine + Forecast APIs** (real, keyless, requires internet) — verified working
2. **Demo provider** — deterministic synthetic current/wind field, labelled `synthetic`

`DEMO_MODE=true` (default) forces the demo provider so everything runs offline. `DEMO_MODE=false` tries real data first.

### Drift & hindcast
`app/services/drift.py` — `drift_velocity = ocean_current + windage × wind` (windage default 3%, +20° deflection). All displacement uses great-circle destination math — never naive lat/lon addition. Hindcast = time-reversed advection from the observed slick backward over `hindcast_hours`. Both run a Monte-Carlo ensemble (windage/magnitude/direction perturbed) to produce an uncertainty radius. The hindcast also reports a confidence derived from ensemble spread vs. total travel.

### AIS correlation & attribution
1. **Search** — candidates = vessels with AIS pings within `radius_km + hindcast_uncertainty` of the **ESTIMATED ORIGIN** within ±`window_hours` of the **ESTIMATED RELEASE TIME** (not around the observed slick — that's the whole point of hindcasting)
2. **Filter** — explainable exclusions: never came close, <3 observations, physically couldn't reach origin at required speed given max SOG. Every exclusion records its reason.
3. **Trajectory features** — closest approach distance/time, distance at release, dwell minutes near origin, Σ\|ΔCOG\|, Σ\|ΔSOG\|, approach/departure bearings, route deviation score
4. **Behaviour anomaly** (0–100) — interpretable rules: dwell >60 min, sudden speed changes, erratic course, route deviation, near-stop at closest approach, + notebook SVR anomalies in window
5. **Scoring** — see §9

### Scoring (transparent, configurable)
| Component | Default weight | Signal |
|---|---|---|
| Spatial | 30% | closest-approach distance vs. search radius |
| Temporal | 25% | \|Δt\| of closest approach vs. release window |
| Trajectory | 20% | pass-through, dwell, route deviation |
| Behaviour | 15% | anomaly score |
| Data quality | 10% | AIS observation density |

Weights are env-configurable (`SCORE_WEIGHT_*` in `.env`) and echoed back in `weights_used`. Each candidate gets: overall score, rank, component scores, evidence bullets, filter reasons, confidence, its AIS track, and this disclaimer:

> *"This is an investigation-priority score, not proof of responsibility."*

### Persistence
Each run saved as JSON in `backend/data/runs/` (no DB required). Listed via `GET /api/pipeline/runs`, browsable in the Investigations page and `/api/investigations`.

---

## 9. Configuration

Copy `.env.example` → `.env` if you want to change anything. All variables are optional; sensible defaults are compiled in:

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_MODE` | `true` | `true` = labelled synthetic environment; `false` = try real Open-Meteo first |
| `DEMO_SPILL_LAT/LON` | `28.52 / -94.95` | Synthetic anchor (inside real AIS coverage) |
| `DEMO_OBSERVATION_TIME` | `2021-02-01T12:00:00Z` | Demo observation timestamp |
| `DEFAULT_WINDAGE` | `0.03` | 3% windage |
| `DEFAULT_HINDCAST_HOURS` | `48` | Backward simulation duration |
| `DEFAULT_FORECAST_HOURS` | `48` | Forward simulation duration |
| `AIS_SEARCH_RADIUS_KM` | `15` | Candidate search radius |
| `AIS_TIME_WINDOW_HOURS` | `12` | ± release-time window |
| `SCORE_WEIGHT_*` | 30/25/20/15/10 | Attribution weights |
| `MAX_UPLOAD_BYTES` | `15 MB` | Upload cap |

Relative paths resolve against the repo root — no hardcoded Windows paths.

---

## 10. Running Tests

```bat
cd backend
py -3.11 -m pytest tests -q
```

**Result: 76 passed.** Coverage includes:

- Geographic math (known distances, cardinal bearings, roundtrips, non-naive displacement, antipodal)
- Drift physics (pure current/wind, orthogonal sums, displacement magnitudes, **hindcast→forecast roundtrip returns to source**)
- AIS cleaning (invalid coords, duplicates, time sorting), search (finds vessels, empty windows), trajectory features (passing vessel, loitering vessel), filter exclusions
- Anomaly flags (loitering detection) and scoring (high vs. distant candidate, weight sensitivity)
- Detection (spill/clean image classification, response format, georef honesty, invalid images)
- Environment providers (synthetic labelling, determinism, nearest-sample lookup)
- API: every legacy contract (PascalCase/camelCase/snake_case preserved), every new endpoint, upload validation, filename traversal protection, **full end-to-end pipeline run via TestClient**

---

## 11. Frontend Pages

| Route | What it shows |
|---|---|
| `/` | Overview: stats, live map with vessels + anomalies, system status |
| `/detection` | SAR viewer — now backed by **real classifier inference** (honest metrics shown) |
| `/vessels` | AIS analysis: table + map + per-vessel drawer with SVR anomalies |
| `/investigations` | **Live pipeline dashboard** — Run/Upload buttons, hindcast/forecast/origin map layers, ranked candidates, evidence panel, disclaimers |
| `/analytics` | Notebook EDA replication (histograms, correlations, hourly activity) |
| `/explorer` | Raw data tables (AIS records, SAR catalog, detections, anomalies) |
| `/pipeline` | Honest stage-by-stage system status |

---

## 12. Docker (optional)

```bash
docker-compose up --build
```

Builds both services (backend :8000, frontend :3000) with the dataset mounted at `/data`.

---

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| Backend log: "SAR classifier NOT trained" | Run `python train_sar_classifier.py` (§5) |
| Map tiles don't load | CARTO key in `frontend/.env.local` — internet required for basemap only; all data layers work offline |
| "Open-Meteo unreachable" | Expected offline or for 2021 dates (free tier has no historical currents) — system falls back to the labelled synthetic provider automatically |
| 404 on `/api/...` | Backend not running or wrong port — check `http://localhost:8000/api/health` |
| `npm run dev` port conflict | `npm run dev -- -p 3001` and update `NEXT_PUBLIC_API_URL` if needed |
| Pipeline status "partial" | Response `errors[]` explains which stage failed; UI shows it too |
| Upload rejected | Only jpg/jpeg/png/tif/tiff/bmp/webp, ≤15 MB, filenames sanitized |
| Windows `py` not found | Use full interpreter path: `C:\Users\ibrah\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn main:app --port 8000` |

---

## 14. Known Limitations (stated honestly)

1. **SAR images are not georeferenced** → geographic spill coordinates in demo runs are synthetic anchors (always labelled as such)
2. **No pixel masks in the dataset** → slick "segmentation" is a labelled weak heuristic, not a trained segmentation model
3. **Simple advection drift** — no oil weathering/spreading/dissipation; ensemble uncertainty is a rough estimate
4. **Open-Meteo free tier** has no historical ocean currents for the 2021 AIS period → demo environment is synthetic by design
5. **AIS coverage** is one Gulf of Mexico zone over ~3 months — attribution resolution is bounded by that
6. **DBSCAN**: the README claimed it but never implemented it; this system uses interpretable behaviour rules + the notebook's SVR, which suit the small per-vessel samples better
7. **Attribution is probabilistic evidence**, never proof — every response and the UI repeat this

---

## 15. Quick Command Cheat Sheet

```bat
:: train the classifier (once)
cd backend && py -3.11 train_sar_classifier.py

:: run backend
cd backend && py -3.11 -m uvicorn main:app --host 0.0.0.0 --port 8000

:: run frontend
cd frontend && npm run dev

:: run tests
cd backend && py -3.11 -m pytest tests -q

:: build frontend for production
cd frontend && npm run build && npm run start

:: API docs (when backend is running)
http://localhost:8000/docs
```
