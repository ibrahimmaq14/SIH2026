/* TypeScript types matching the actual AIS dataset schema and API responses */

// AIS Dataset Schema (17 columns from repository CSV)
export interface AISRecord {
  MMSI: number;
  BaseDateTime: string;
  LAT: number;
  LON: number;
  SOG: number; // Speed Over Ground
  COG: number; // Course Over Ground
  Heading: number;
  VesselName: string;
  IMO: string;
  CallSign: string;
  VesselType: number;
  Status: string;
  Length: number;
  Width: number;
  Draft: number;
  Cargo: number;
  TransceiverClass?: string;
}

// Vessel summary (aggregated from AIS records)
export interface Vessel {
  MMSI: number;
  VesselName: string;
  IMO: string;
  CallSign: string;
  VesselType: number;
  LAT: number; // Latest position
  LON: number;
  SOG: number;
  COG: number;
  Heading: number;
  Status: string;
  Length: number;
  Width: number;
  Draft: number;
  Cargo: number;
  BaseDateTime: string;
  ObservationCount: number;
}

export interface VesselListResponse {
  vessels: Vessel[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// Vessel track
export interface TrackPoint {
  lat: number;
  lon: number;
  sog: number;
  cog: number;
  heading: number;
  status: string;
  timestamp: string;
}

export interface VesselInfo {
  mmsi: number;
  vesselName: string;
  imo: string;
  callSign: string;
  vesselType: number;
  length: number;
  width: number;
  draft: number;
  cargo: number;
  observationCount: number;
}

export interface VesselTrackResponse {
  mmsi: number;
  track: TrackPoint[];
  info: VesselInfo | null;
}

// Anomaly detection (SVR methodology from notebook)
export interface Anomaly {
  lat: number;
  lon: number;
  sog: number;
  predictedSog: number;
  difference: number;
  cog: number;
  heading: number;
  timestamp: string;
  status: string;
}

export interface ModelInfo {
  type: string;
  features: string[];
  target: string;
  params: { gamma: string; C: number; epsilon: number; degree: number };
  r2Score: number;
  trainSize: number;
  testSize: number;
  methodology: string;
}

export interface AnomalyResponse {
  mmsi: number;
  anomalies: Anomaly[];
  totalObservations: number;
  anomalyCount: number;
  threshold: number;
  model_info: ModelInfo | null;
  error?: string;
}

export interface AllAnomaliesResponse {
  vessels: {
    mmsi: number;
    vesselName: string;
    anomalyCount: number;
    totalObservations: number;
    r2Score: number | null;
  }[];
  allAnomalies: Anomaly[];
  threshold: number;
  vesselsAnalyzed: number;
}

// SAR imagery
export interface SARImage {
  filename: string;
  class: number;
  className: string;
  region: string;
  path?: string;
  dimensions: string;
  format: string;
}

export interface SARSummary {
  totalImages: number;
  class0Count: number;
  class1Count: number;
  classes: { id: number; name: string; count: number }[];
  imageFormat: string;
  source: string;
  modelStatus: string;
  note: string;
}

export interface SARDetection {
  id: string;
  filename: string;
  class: number;
  className: string;
  region: string;
  isDemo: boolean;
  note: string;
  status: string;
  dimensions: string;
}

// Analytics (replicating notebook EDA)
export interface Analytics {
  totalRecords: number;
  uniqueVessels: number;
  dateRange: { start: string | null; end: string | null };
  geoBounds: { latMin: number; latMax: number; lonMin: number; lonMax: number };
  sogStats: {
    mean: number; median: number; std: number;
    min: number; max: number; mode: number | null;
  };
  sogDistribution: { range: string; count: number }[];
  vesselTypeDistribution: { vesselType: number; count: number }[];
  vesselActivity: { mmsi: number; vesselName: string; observations: number }[];
  correlations: {
    sogVesselType: number; cogVesselType: number;
    lengthSog: number; lengthCog: number;
    widthSog: number; widthCog: number;
  };
  avgTrackLength: number | null;
  statusDistribution: { status: string; count: number }[];
  hourlyActivity: { hour: number; count: number }[];
}

// Pipeline status
export interface PipelineStage {
  stage: string;
  status: 'Available' | 'Offline' | 'Demo' | 'Not Configured';
  description: string;
  methodology?: string;
  features?: string;
  note?: string;
  lastRun?: string;
}

export interface PipelineStatusResponse {
  pipeline: PipelineStage[];
}

// Overview
export interface OverviewStats {
  totalVessels: number;
  totalObservations: number;
  dateRange: { start: string | null; end: string | null };
  geoBounds: { latMin: number; latMax: number; lonMin: number; lonMax: number };
  avgSpeed: number;
  dataSource: string;
}

// Investigation
export interface Investigation {
  id: string;
  title: string;
  status: string;
  isDemo: boolean;
  note: string;
  region: { centerLat: number; centerLon: number; radiusKm: number };
  spillDetection: { status: string; source: string; note: string };
  aisCorrelation: { status: string; vesselsInRegion: number; anomaliesDetected: string };
  timeline: { event: string; status: string; description: string }[];
}

// Pagination params
export interface PaginationParams {
  page?: number;
  pageSize?: number;
  search?: string;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
  vesselType?: string;
}

// ═════════════════════════════════════════════════════════════════════════
// Pipeline v2 types — oil spill detection, drift, attribution
// (backend/app/schemas.py is the source of truth)
// ═════════════════════════════════════════════════════════════════════════

export type DataClass = 'model' | 'heuristic' | 'synthetic' | 'unavailable';

export interface DataSourceLabel {
  dataClass: DataClass;
  description: string;
}

export interface DetectionResult {
  detected: boolean;
  confidence: number;
  image_id: string;
  acquisition_time: string | null;
  detection_method: string;
  source_label: DataSourceLabel;
  model_available: boolean;
  message?: string | null;
}

export interface SlickGeometry {
  centroid_px: [number, number];
  bounding_box_px: [number, number, number, number];
  area_px: number;
  perimeter_px: number;
  width_px: number;
  length_px: number;
  aspect_ratio: number;
  orientation_deg: number;
  geometry_type: string;
}

export interface SpillCharacterization {
  detection: DetectionResult;
  geometry: SlickGeometry | null;
  segmentation_method: string;
  segmentation_note: string;
  geographic: { lat: number; lon: number; source: string } | null;
  acquisition_time: string | null;
  spill_age_note: string;
  source_label: DataSourceLabel;
}

export interface EnvironmentalSample {
  timestamp: string;
  lat: number;
  lon: number;
  current_speed_kmh: number | null;
  current_direction_deg: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  wave_height_m: number | null;
  provider: string;
  dataClass: DataClass;
}

export interface EnvironmentalSeries {
  samples: EnvironmentalSample[];
  provider: string;
  dataClass: DataClass;
  note: string;
}

export interface DriftPoint {
  timestamp: string;
  lat: number;
  lon: number;
  current_speed_kmh: number | null;
  current_direction_deg: number | null;
  wind_speed_kmh: number | null;
  wind_direction_deg: number | null;
  drift_speed_kmh: number;
  drift_direction_deg: number;
  displacement_km: number;
  cumulative_km: number;
}

export interface ForecastResponse {
  request: unknown;
  track: { points: DriftPoint[] };
  end_position: { lat: number; lon: number };
  total_displacement_km: number;
  uncertainty_radius_km: number;
  environment: EnvironmentalSeries;
  method: string;
  source_label: DataSourceLabel;
}

export interface HindcastResponse {
  request: unknown;
  track: { points: DriftPoint[] };
  origin_location: { lat: number; lon: number };
  origin_time: string;
  estimated_release_window_hours: number;
  uncertainty_radius_km: number;
  confidence: number;
  environment: EnvironmentalSeries;
  method: string;
  disclaimer: string;
  source_label: DataSourceLabel;
}

export interface TrajectoryFeatures {
  min_distance_to_origin_km: number;
  distance_at_release_km: number | null;
  min_distance_time: string | null;
  time_diff_from_release_hours: number | null;
  mean_speed_knots: number | null;
  max_speed_knots: number | null;
  course_at_min_distance: number | null;
  speed_at_min_distance: number | null;
  heading_changes_deg: number | null;
  speed_changes_knots: number | null;
  dwell_minutes_near_origin: number;
  approach_bearing_deg: number | null;
  departure_bearing_deg: number | null;
  passes_within_radius: boolean;
  time_near_origin_minutes: number;
  route_deviation_score: number | null;
}

export interface BehaviourAnalysis {
  anomaly_score: number;
  anomaly_flags: string[];
  svr_anomalies_in_window: number;
  dbscan_cluster_label: number | null;
  dbscan_noise_points: number;
  methodology: string;
}

export interface ScoreComponents {
  spatial: number;
  temporal: number;
  trajectory: number;
  behaviour: number;
  data_quality: number;
}

export interface CandidateVessel {
  rank: number;
  mmsi: number;
  vesselName: string;
  vesselType: number | null;
  score: number;
  score_components: ScoreComponents;
  min_distance_km: number;
  time_diff_hours: number | null;
  trajectory_features: TrajectoryFeatures;
  behaviour: BehaviourAnalysis;
  evidence: string[];
  filter_reasons: string[];
  confidence: number;
  track: TrackPoint[];
  disclaimer: string;
}

export interface AttributionResponse {
  candidates: CandidateVessel[];
  excluded: { mmsi: number; vesselName: string; reason: string }[];
  origin: Record<string, unknown>;
  search_parameters: Record<string, unknown>;
  weights_used: Record<string, number>;
  methodology: string;
  disclaimer: string;
  source_label: DataSourceLabel;
}

export interface PipelineRunResponse {
  run_id: string;
  status: 'completed' | 'partial' | 'failed';
  errors: string[];
  detection: DetectionResult;
  characterization: SpillCharacterization;
  environment: EnvironmentalSeries;
  hindcast: HindcastResponse | null;
  forecast: ForecastResponse | null;
  attribution: AttributionResponse | null;
  timeline: { event: string; status: string; description: string }[];
  disclaimers: string[];
}

export interface PipelineRunOptions {
  filename?: string;
  hindcast_hours?: number;
  forecast_hours?: number;
  windage?: number;
  search_radius_km?: number;
  window_hours?: number;
  timestep_minutes?: number;
  spill_lat?: number;
  spill_lon?: number;
  observation_time?: string;
}
