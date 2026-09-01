# Oil Spill Detection — Maritime Intelligence Web Application

## Technical Assessment

### A. What the Repository Actually Implements

| Component | Status | Details |
|-----------|--------|---------|
| **AIS EDA** | ✅ Implemented | Full exploratory analysis on `AIS_2017_01_Zone01.csv` (~10,224 records). Includes geographic plotting (geopandas + folium), correlation analysis, speed/track/vessel-type analysis |
| **AIS Data Cleaning** | ✅ Implemented | Missing value detection across columns (VesselName, IMO, CallSign, VesselType, Width, Draft, Cargo), linear interpolation with forward/backward fill |
| **AIS Vessel Tracking** | ✅ Implemented | Per-MMSI vessel track extraction. Top 3 vessels tracked: 367390380, 366940480, 352844000 |
| **AIS Anomaly Detection (SVR)** | ✅ Implemented | Support Vector Regression predicting SOG from [LAT, hour, Cargo, COG]. Anomalies = records where `|predicted - actual| >= 6`. Applied to single vessel (track1 = MMSI 367390380) |
| **SAR Image Dataset** | ✅ Available | Binary classification dataset: Class 0 (no spill, 3725 images) / Class 1 (oil spill, 1905 images). 400×400 grayscale JPG SAR imagery |
| **SAR CNN Model** | ❌ **Not implemented** | README mentions "Customized CNN" and TensorFlow/Keras, but **no trained model file, training script, or CNN code exists** in the repository |

### B. What the Repository Does NOT Implement

- ❌ No trained CNN model (no `.h5`, `.keras`, `.pb`, or SavedModel)
- ❌ No CNN training or inference code
- ❌ No DBSCAN implementation (README mentions it, notebook uses SVR instead)
- ❌ No MongoDB integration
- ❌ No API/backend service
- ❌ No web interface
- ❌ No spill-age estimation
- ❌ No drift modeling or hindcasting
- ❌ No spill origin estimation
- ❌ No real-time AIS ingestion
- ❌ No AIS-SAR integration pipeline
- ❌ No segmentation model (the dataset is for classification)

### C. How the AIS Pipeline Works

```
AIS CSV (AIS_2017_01_Zone01.csv, ~10,224 rows, 16 columns)
    │
    ├── Columns: MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading,
    │            VesselName, IMO, CallSign, VesselType, Status,
    │            Length, Width, Draft, Cargo
    │
    ▼
PREPROCESSING
    ├── Convert BaseDateTime to datetime
    ├── Extract time features: year, month, day, hour, minute
    ├── Identify missing values (VesselName, IMO, CallSign, VesselType, Width, Draft, Cargo)
    ├── Linear interpolation + forward/backward fill
    │
    ▼
EDA / ANALYSIS
    ├── Geographic plotting (geopandas map + folium markers)
    ├── Average track length (mode of Length column = 89.92)
    ├── SOG/COG correlation with VesselType (weak: 0.01, -0.01)
    ├── SOG/COG correlation with Length/Width (~0.10-0.16)
    ├── Average speed (mode of SOG)
    │
    ▼
VESSEL TRACKING
    ├── Group by MMSI → separate per-vessel DataFrames
    ├── Plot scatter of LON vs LAT per vessel
    │
    ▼
ANOMALY DETECTION (SVR on vessel 367390380 only)
    ├── Features: X = [LAT, hour, Cargo, COG]
    ├── Target: y = SOG
    ├── Train/test split: 85/15
    ├── SVR(gamma='scale', C=100000, epsilon=1, degree=3)
    ├── R² score evaluation
    ├── Anomaly threshold: |Actual - Predicted| >= 6 (rounded)
    ├── Output: list of anomalous AIS observations
```

### D. How the SAR/CNN Pipeline Works

**Current state: Classification dataset only — no model exists.**

- **Dataset**: 5,630 SAR images (400×400 grayscale JPG)
  - Class 0 (no oil spill): 3,725 images
  - Class 1 (oil spill): 1,905 images
- **Naming**: `{augmentation}_{id}_{region}_cls_{class}.jpg` — region codes include SFr, GBR, BAH, JAV, EGY, JAP, PHI, ISR, GGu
- **No model file exists** — no `.h5`, `.keras`, `.pb`, `.pt`, `.onnx`
- **No training script exists**
- The README claims TensorFlow/Keras CNN but the code is absent

### E. Integration Between AIS and SAR

**Not implemented.** The README describes integration conceptually ("AIS anomaly detection results validated by satellite image analysis") but no code connects the two pipelines. The existing project is two independent datasets with analysis only on AIS data.

### F. What Can Be Directly Reused

| Asset | Reuse Strategy |
|-------|---------------|
| AIS CSV schema (17 columns) | Define TypeScript types matching exactly |
| AIS preprocessing logic | Port to Python backend service |
| SVR anomaly detection | Wrap in API endpoint |
| Vessel tracking by MMSI | Implement as API with per-vessel querying |
| SAR image dataset | Serve sample images for detection UI |
| Geographic coordinates (LAT/LON ranges) | Center map on actual data region |

### G. What Needs an API/Backend Wrapper

1. **AIS data querying** — paginated, filterable endpoint for ~52K records (actual CSV in repo)
2. **Vessel tracking** — endpoint returning per-MMSI trajectory data
3. **Anomaly detection** — endpoint running SVR prediction + anomaly flagging
4. **SAR image serving** — endpoint to list/serve SAR images by class
5. **Analytics** — pre-computed statistical summaries

### H. What Needs to Remain Mocked/Demo-Only

- CNN inference results (model doesn't exist)
- Spill polygon geometry (no real geo-registered spill data)
- AIS-SAR correlation (no integration code exists)
- Investigation workflow (conceptual, not implemented)
- Pipeline status (no running pipeline exists)
- Drift analysis, hindcasting, origin estimation

### I. Dependencies Required

**Backend (Python/FastAPI)**:
- pandas, numpy, scikit-learn (SVR), geopandas
- fastapi, uvicorn
- Pillow (SAR image handling)

**Frontend (Next.js)**:
- next, react, typescript
- tailwindcss, shadcn/ui
- leaflet / react-leaflet (mapping)
- recharts (charting)

### J. Recommended Architecture

```
┌──────────────────────────┐     ┌──────────────────────────┐
│   Frontend (Next.js)     │────▶│   Backend (FastAPI)      │
│   - TypeScript           │     │   - Python 3.11          │
│   - Tailwind CSS         │     │   - AIS data service     │
│   - Leaflet maps         │     │   - SVR anomaly model    │
│   - Recharts             │     │   - SAR image serving    │
│   Port: 3000             │     │   Port: 8000             │
└──────────────────────────┘     └──────────────────────────┘
                                          │
                                          ▼
                                 ┌────────────────────┐
                                 │   Data Layer        │
                                 │   - AIS CSV files   │
                                 │   - SAR images      │
                                 │   - No DB needed    │
                                 └────────────────────┘
```

> [!IMPORTANT]
> **No MongoDB is needed.** The project doesn't actually use MongoDB — the README mentions it but no database code exists. The AIS dataset is ~52K rows in CSV, easily handled in-memory by pandas. Adding MongoDB would be unnecessary complexity.

---

## Proposed Implementation

### 1. Backend Service (FastAPI)

#### [NEW] `backend/main.py`
FastAPI application with CORS, serving endpoints for all data

#### [NEW] `backend/services/ais_service.py`
- Load AIS CSV into pandas DataFrame on startup
- Paginated vessel listing with search/filter
- Per-MMSI track retrieval
- SVR-based anomaly detection (replicating notebook logic)
- Analytics endpoints (statistics, distributions)

#### [NEW] `backend/services/sar_service.py`
- List available SAR images by class
- Serve individual images
- Mock detection results (clearly labeled as demo)

#### [NEW] `backend/services/investigation_service.py`
- Demo investigation data combining AIS anomalies + SAR detections
- Clearly labeled as demo/sample data

#### [NEW] `backend/requirements.txt`
pandas, numpy, scikit-learn, fastapi, uvicorn, geopandas, shapely, pillow

---

### 2. Frontend Application (Next.js + TypeScript)

#### Pages

| Page | Purpose |
|------|---------|
| **Overview** | Command-center dashboard with map, key metrics, system status |
| **Oil Spill Detection** | SAR image viewer with sample detection results |
| **AIS Vessel Analysis** | Interactive map + data table + vessel detail panel |
| **Investigations** | Connected workflow: spill → region → AIS → anomalies → vessels |
| **AIS Analytics** | Charts replicating notebook analysis (speed distribution, correlations, vessel types) |
| **Data Explorer** | Tabular view with search/filter/pagination for AIS, SAR, anomalies |
| **Pipeline Status** | Pipeline visualization with honest status labels |

#### Key Components

- **MaritimeMap**: Leaflet-based map with vessel markers, tracks, spill regions, anomaly markers, layer controls
- **VesselTable**: Paginated, sortable, filterable table using actual AIS schema
- **VesselDetail**: Drawer showing vessel info, trajectory, anomaly status
- **SARViewer**: Image viewer with zoom/pan for SAR imagery
- **AnalyticsCharts**: Recharts-based visualizations of actual notebook analytics
- **PipelineStatus**: Honest status display with demo/offline labels
- **InvestigationPanel**: Side panel with spill detection, AIS correlation, evidence timeline

#### Data/API Architecture

```typescript
// Clean service abstraction - mock data swappable with real API
interface APIService {
  getVessels(params: PaginationParams): Promise<VesselListResponse>
  getVesselTrack(mmsi: string): Promise<TrackResponse>
  getAISAnomalies(): Promise<AnomalyResponse>
  getSARImages(params: FilterParams): Promise<SARImageListResponse>
  getDetections(): Promise<DetectionResponse>
  getAnalytics(): Promise<AnalyticsResponse>
  getInvestigation(id: string): Promise<InvestigationResponse>
  getPipelineStatus(): Promise<PipelineStatusResponse>
}
```

---

### 3. Docker Setup

#### [NEW] `docker-compose.yml`
Two services: `frontend` and `backend`

#### [NEW] `backend/Dockerfile`
Python 3.11 slim, install requirements, run uvicorn

#### [NEW] `frontend/Dockerfile`
Node 20, install deps, build Next.js, serve

#### [NEW] `.dockerignore`
Exclude node_modules, .git, __pycache__, large dataset files (mounted as volume)

---

## Open Questions

> [!IMPORTANT]
> **AIS Dataset Discrepancy**: The notebook references `AIS_2017_01_Zone01.csv` (~10,224 rows) but the repository contains a different file `AIS_172433991588466433_2317-1724339916028.csv` (~52,943 rows) with the same schema but different geographic region (Gulf of Mexico, ~28°N, -94°W vs the notebook's Alaska region ~52°N, -176°W). The backend will use the **actual CSV in the repository** since it has the same schema. The anomaly detection methodology remains the same.

> [!NOTE]
> **No CNN Model**: The SAR detection page will be functional with the image dataset but will honestly display "Model not trained — demo classification" for any detection results. The architecture supports plugging in a real model later.

---

## Verification Plan

### Automated Tests
- Backend: FastAPI endpoint testing with `pytest`
- Frontend: TypeScript compilation check, `npm run build`

### Manual Verification
- Start both services (or via Docker)
- Navigate all 7 pages
- Test map interactions (zoom, pan, vessel click, layer controls)
- Test vessel table (search, sort, filter, pagination)
- Test vessel selection → map sync
- Test SAR image viewer
- Verify all "demo" labels are present where applicable
- Check browser console for errors
- Test responsive layout at different viewport sizes
