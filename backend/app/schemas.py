"""Pydantic schemas for API contracts.

IMPORTANT: These schemas deliberately match the existing frontend
(`frontend/src/lib/types.ts`) so the running UI continues to work without
changes. Case conventions per endpoint are preserved:
- Vessel list rows use the AIS CSV PascalCase column names
- Track/anomaly/SAR/pipeline objects use camelCase
- `model_info` stays snake_case (frontend expects exactly that)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════
# Existing frontend contracts (PRESERVED)
# ═══════════════════════════════════════════════════════════════════════════


class VesselRow(BaseModel):
    """Matches frontend `Vessel` — PascalCase CSV columns."""

    MMSI: int
    VesselName: str = "Unknown"
    IMO: str = "Unknown"
    CallSign: str = "Unknown"
    VesselType: Optional[float] = None
    LAT: float
    LON: float
    SOG: float
    COG: float
    Heading: float
    Status: str = ""
    Length: Optional[float] = None
    Width: Optional[float] = None
    Draft: Optional[float] = None
    Cargo: Optional[float] = None
    BaseDateTime: Optional[str] = None
    ObservationCount: int = 0


class VesselListResponse(BaseModel):
    vessels: list[VesselRow]
    total: int
    page: int
    pageSize: int
    totalPages: int


class TrackPoint(BaseModel):
    lat: float
    lon: float
    sog: float
    cog: float
    heading: float
    status: str
    timestamp: str


class VesselInfo(BaseModel):
    mmsi: int
    vesselName: str
    imo: str
    callSign: str
    vesselType: Optional[float] = None
    length: Optional[float] = None
    width: Optional[float] = None
    draft: Optional[float] = None
    cargo: Optional[float] = None
    observationCount: int


class VesselTrackResponse(BaseModel):
    mmsi: int
    track: list[TrackPoint]
    info: Optional[VesselInfo] = None


class Anomaly(BaseModel):
    lat: float
    lon: float
    sog: float
    predictedSog: float
    difference: float
    cog: float
    heading: float
    timestamp: str
    status: str


class ModelInfo(BaseModel):
    type: str
    features: list[str]
    target: str
    params: dict[str, Any]
    r2Score: Optional[float] = None
    trainSize: int
    testSize: int
    methodology: str


class AnomalyResponse(BaseModel):
    mmsi: int
    anomalies: list[Anomaly]
    totalObservations: int
    anomalyCount: int
    threshold: float
    model_info: Optional[ModelInfo] = None
    error: Optional[str] = None


class AllAnomaliesResponse(BaseModel):
    vessels: list[dict[str, Any]]
    allAnomalies: list[Anomaly]
    threshold: float
    vesselsAnalyzed: int


class SARImage(BaseModel):
    filename: str
    img_class: int = Field(alias="class")
    className: str
    region: str
    path: Optional[str] = None
    dimensions: str
    format: str

    model_config = {"populate_by_name": True}


class SARSummary(BaseModel):
    totalImages: int
    class0Count: int
    class1Count: int
    classes: list[dict[str, Any]]
    imageFormat: str
    source: str
    modelStatus: str
    note: str


class SARDetection(BaseModel):
    id: str
    filename: str
    img_class: int = Field(alias="class")
    className: str
    region: str
    isDemo: bool
    note: str
    status: str
    dimensions: str

    model_config = {"populate_by_name": True}


class PipelineStage(BaseModel):
    stage: str
    status: Literal["Available", "Offline", "Demo", "Not Configured"]
    description: str
    methodology: Optional[str] = None
    features: Optional[str] = None
    note: Optional[str] = None
    lastRun: Optional[str] = None


class PipelineStatusResponse(BaseModel):
    pipeline: list[PipelineStage]


class OverviewStats(BaseModel):
    totalVessels: int
    totalObservations: int
    dateRange: dict[str, Optional[str]]
    geoBounds: dict[str, float]
    avgSpeed: float
    dataSource: str


class InvestigationTimelineEvent(BaseModel):
    event: str
    status: str
    description: str


class Investigation(BaseModel):
    id: str
    title: str
    status: str
    isDemo: bool
    note: str
    region: dict[str, float]
    spillDetection: dict[str, str]
    aisCorrelation: dict[str, Any]
    timeline: list[InvestigationTimelineEvent]


# ═══════════════════════════════════════════════════════════════════════════
# New schemas — oil spill detection & characterization
# ═══════════════════════════════════════════════════════════════════════════

DataClass = Literal["model", "heuristic", "synthetic", "unavailable"]


class DataSourceLabel(BaseModel):
    """Every result carries honest provenance labels."""
    dataClass: DataClass
    description: str


class DetectionResult(BaseModel):
    detected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    image_id: str
    acquisition_time: Optional[str] = None
    detection_method: str
    source_label: DataSourceLabel
    model_available: bool
    message: Optional[str] = None


class SlickGeometry(BaseModel):
    """Pixel-domain geometry of the suspected slick region (weak segmentation)."""

    centroid_px: tuple[float, float]
    bounding_box_px: tuple[int, int, int, int]  # x0, y0, x1, y1
    area_px: int
    perimeter_px: float
    width_px: float
    length_px: float
    aspect_ratio: float
    orientation_deg: float  # major-axis angle from horizontal (image space)
    geometry_type: str  # e.g. "elongated", "compact", "irregular"


class SpillCharacterization(BaseModel):
    detection: DetectionResult
    geometry: Optional[SlickGeometry] = None
    segmentation_method: str
    segmentation_note: str
    # Geographic info is only present when the source image is georeferenced.
    # The repository's SAR images are plain JPGs — geographic fields will be
    # null unless a GeoTIFF with real geotransform is supplied.
    geographic: Optional[dict[str, Any]] = None
    acquisition_time: Optional[str] = None
    spill_age_note: str
    source_label: DataSourceLabel


# ═══════════════════════════════════════════════════════════════════════════
# Environmental data
# ═════════════════════════════════════════════════════════════════════════


class EnvironmentalSample(BaseModel):
    timestamp: str
    lat: float
    lon: float
    current_speed_kmh: Optional[float] = None
    current_direction_deg: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    wave_height_m: Optional[float] = None
    provider: str
    dataClass: DataClass


class EnvironmentalSeries(BaseModel):
    samples: list[EnvironmentalSample]
    provider: str
    dataClass: DataClass
    note: str


# ═══════════════════════════════════════════════════════════════════════════
# Drift — forecast & hindcast
# ═══════════════════════════════════════════════════════════════════════════


class DriftRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    start_time: Optional[str] = None  # ISO; default = now (forecast) / obs time (hindcast)
    duration_hours: float = Field(gt=0, le=240)
    timestep_minutes: int = Field(default=30, ge=5, le=360)
    windage: float = Field(default=0.03, ge=0.0, le=0.1)
    use_demo_environment: bool = True
    ensemble_members: int = Field(default=40, ge=1, le=200)


class DriftPoint(BaseModel):
    timestamp: str
    lat: float
    lon: float
    current_speed_kmh: Optional[float] = None
    current_direction_deg: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    drift_speed_kmh: float
    drift_direction_deg: float
    displacement_km: float
    cumulative_km: float


class DriftTrack(BaseModel):
    points: list[DriftPoint]


class ForecastResponse(BaseModel):
    request: DriftRequest
    track: DriftTrack
    end_position: dict[str, float]
    total_displacement_km: float
    uncertainty_radius_km: float
    environment: EnvironmentalSeries
    method: str
    source_label: DataSourceLabel


class HindcastResponse(BaseModel):
    request: DriftRequest
    track: DriftTrack  # backward trajectory (latest → earliest)
    origin_location: dict[str, float]
    origin_time: str
    estimated_release_window_hours: float
    uncertainty_radius_km: float
    confidence: float = Field(ge=0.0, le=1.0)
    environment: EnvironmentalSeries
    method: str
    disclaimer: str
    source_label: DataSourceLabel


# ═══════════════════════════════════════════════════════════════════════════
# AIS correlation & attribution
# ═══════════════════════════════════════════════════════════════════════════


class AISSearchRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    time: str  # ISO timestamp (estimated release / observation time)
    radius_km: float = Field(default=15.0, gt=0, le=500)
    window_hours: float = Field(default=12.0, gt=0, le=720)  # ± hours around `time`


class AISCandidateSummary(BaseModel):
    mmsi: int
    vesselName: str
    vesselType: Optional[float] = None
    observations_in_window: int
    min_distance_km: float
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class AISSearchResponse(BaseModel):
    candidates: list[AISCandidateSummary]
    total_records_searched: int
    dataset_note: str
    time_coverage: dict[str, Optional[str]]
    source_label: DataSourceLabel


class FilterDecision(BaseModel):
    included: bool
    reason: str


class TrajectoryFeatures(BaseModel):
    min_distance_to_origin_km: float
    distance_at_release_km: Optional[float]
    min_distance_time: Optional[str]
    time_diff_from_release_hours: Optional[float]
    mean_speed_knots: Optional[float]
    max_speed_knots: Optional[float]
    course_at_min_distance: Optional[float]
    speed_at_min_distance: Optional[float]
    heading_changes_deg: Optional[float]
    speed_changes_knots: Optional[float]
    dwell_minutes_near_origin: float
    approach_bearing_deg: Optional[float]
    departure_bearing_deg: Optional[float]
    passes_within_radius: bool
    time_near_origin_minutes: float
    route_deviation_score: Optional[float]


class BehaviourAnalysis(BaseModel):
    anomaly_score: float = Field(ge=0.0, le=100.0)
    anomaly_flags: list[str]
    svr_anomalies_in_window: int
    dbscan_cluster_label: Optional[int] = None
    dbscan_noise_points: int = 0
    methodology: str


class ScoreComponents(BaseModel):
    spatial: float
    temporal: float
    trajectory: float
    behaviour: float
    data_quality: float


class CandidateVessel(BaseModel):
    rank: int
    mmsi: int
    vesselName: str
    vesselType: Optional[float] = None
    score: float = Field(ge=0.0, le=100.0)
    score_components: ScoreComponents
    min_distance_km: float
    time_diff_hours: Optional[float]
    trajectory_features: TrajectoryFeatures
    behaviour: BehaviourAnalysis
    evidence: list[str]
    filter_reasons: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    track: list[TrackPoint]  # AIS track within the analysis window
    disclaimer: str


class AttributionResponse(BaseModel):
    candidates: list[CandidateVessel]
    excluded: list[dict[str, Any]]  # mmsi, name, reason
    origin: dict[str, Any]
    search_parameters: dict[str, Any]
    weights_used: dict[str, float]
    methodology: str
    disclaimer: str
    source_label: DataSourceLabel


# ═══════════════════════════════════════════════════════════════════════════
# Full pipeline
# ═══════════════════════════════════════════════════════════════════════════


class PipelineRunRequest(BaseModel):
    # Either upload a SAR image via /api/pipeline/run (multipart) or use a
    # sample image by filename for the demo pipeline.
    filename: Optional[str] = None  # dataset-relative e.g. "1/xxx_cls_1.jpg"
    hindcast_hours: float = Field(default=48, gt=0, le=240)
    forecast_hours: float = Field(default=48, gt=0, le=240)
    windage: float = Field(default=0.03, ge=0, le=0.1)
    search_radius_km: float = Field(default=15, gt=0, le=500)
    window_hours: float = Field(default=12, gt=0, le=168)
    timestep_minutes: int = Field(default=30, ge=5, le=360)
    # Geographic override: the SAR dataset is not georeferenced. For the demo
    # pipeline the spill location anchors to the AIS data region (labelled
    # synthetic). Users may supply a real acquisition location when known.
    spill_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    spill_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    observation_time: Optional[str] = None


class PipelineRunResponse(BaseModel):
    run_id: str
    status: Literal["completed", "partial", "failed"]
    errors: list[str]
    detection: DetectionResult
    characterization: SpillCharacterization
    environment: EnvironmentalSeries
    hindcast: HindcastResponse
    forecast: ForecastResponse
    attribution: AttributionResponse
    timeline: list[dict[str, str]]
    disclaimers: list[str]


class PipelineRunSummary(BaseModel):
    run_id: str
    created_at: str
    status: str
    detected: bool
    confidence: float
    origin_lat: Optional[float]
    origin_lon: Optional[float]
    candidate_count: int
    top_mmsi: Optional[int]
    top_score: Optional[float]


# ═══════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    model_available: bool
    ais_available: bool
    demo_mode: bool
