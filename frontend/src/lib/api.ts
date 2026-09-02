/**
 * API Service Layer
 * 
 * Clean abstraction over the FastAPI backend.
 * All calls go through this service — easy to swap mock/real endpoints.
 */

import type {
  VesselListResponse,
  VesselTrackResponse,
  AnomalyResponse,
  AllAnomaliesResponse,
  SARSummary,
  SARDetection,
  Analytics,
  PipelineStatusResponse,
  OverviewStats,
  Investigation,
  PaginationParams,
  PipelineRunResponse,
  SpillCharacterization,
  HindcastResponse,
  ForecastResponse,
  AttributionResponse,
  PipelineRunOptions,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchAPI<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const res = await fetch(url.toString(), {
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

// ─── AIS / Vessel Endpoints ──────────────────────────────────────────

export async function getVessels(params?: PaginationParams): Promise<VesselListResponse> {
  return fetchAPI<VesselListResponse>('/api/vessels', params as Record<string, string | number>);
}

export async function getVesselTrack(mmsi: number): Promise<VesselTrackResponse> {
  return fetchAPI<VesselTrackResponse>(`/api/vessels/${mmsi}`);
}

export async function getVesselAnomalies(mmsi: number, threshold?: number): Promise<AnomalyResponse> {
  return fetchAPI<AnomalyResponse>(`/api/vessels/${mmsi}/anomalies`, { threshold });
}

export async function getAllAnomalies(threshold?: number, maxVessels?: number): Promise<AllAnomaliesResponse> {
  return fetchAPI<AllAnomaliesResponse>('/api/anomalies', { threshold, maxVessels });
}

export async function getVesselTypes(): Promise<string[]> {
  return fetchAPI<string[]>('/api/vessels/types');
}

// ─── Analytics ────────────────────────────────────────────────────────

export async function getAnalytics(): Promise<Analytics> {
  return fetchAPI<Analytics>('/api/analytics');
}

export async function getOverview(): Promise<OverviewStats> {
  return fetchAPI<OverviewStats>('/api/overview');
}

// ─── SAR / Detection ─────────────────────────────────────────────────

export async function getSARSummary(): Promise<SARSummary> {
  return fetchAPI<SARSummary>('/api/sar/summary');
}

export async function getSARDetections(): Promise<SARDetection[]> {
  return fetchAPI<SARDetection[]>('/api/sar/detections');
}

export async function getSARRegions(): Promise<string[]> {
  return fetchAPI<string[]>('/api/sar/regions');
}

export function getSARImageURL(cls: number, filename: string): string {
  return `${API_BASE}/api/sar/image/${cls}/${filename}`;
}

// ─── Pipeline ─────────────────────────────────────────────────────────

export async function getPipelineStatus(): Promise<PipelineStatusResponse> {
  return fetchAPI<PipelineStatusResponse>('/api/pipeline/status');
}

// ─── Investigations ───────────────────────────────────────────────────

export async function getInvestigations(): Promise<{ investigations: Investigation[] }> {
  return fetchAPI<{ investigations: Investigation[] }>('/api/investigations');
}

// ─── Health ───────────────────────────────────────────────────────────

export async function checkHealth(): Promise<{ status: string }> {
  return fetchAPI<{ status: string }>('/api/health');
}

// ─── Pipeline v2 (detection → drift → attribution) ────────────────────

export async function runPipeline(
  options: PipelineRunOptions = {},
  imageFile?: File
): Promise<PipelineRunResponse> {
  const form = new FormData();
  const defaults = {
    hindcast_hours: 48,
    forecast_hours: 48,
    windage: 0.03,
    search_radius_km: 15,
    window_hours: 12,
    timestep_minutes: 60,
    ...options,
  };
  Object.entries(defaults).forEach(([key, value]) => {
    if (value !== undefined && value !== null) form.append(key, String(value));
  });
  if (imageFile) form.append('file', imageFile);

  const res = await fetch(`${API_BASE}/api/pipeline/run`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch { /* keep default */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function analyzeSpillImage(
  filename: string,
  acquisitionTime?: string
): Promise<SpillCharacterization> {
  const form = new FormData();
  form.append('filename', filename);
  if (acquisitionTime) form.append('acquisition_time', acquisitionTime);
  const res = await fetch(`${API_BASE}/api/spill/analyze`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function hindcastDrift(body: {
  lat: number;
  lon: number;
  start_time?: string;
  duration_hours: number;
  timestep_minutes?: number;
  windage?: number;
  use_demo_environment?: boolean;
}): Promise<HindcastResponse> {
  const res = await fetch(`${API_BASE}/api/drift/hindcast`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function forecastDrift(body: {
  lat: number;
  lon: number;
  start_time?: string;
  duration_hours: number;
  timestep_minutes?: number;
  windage?: number;
  use_demo_environment?: boolean;
}): Promise<ForecastResponse> {
  const res = await fetch(`${API_BASE}/api/drift/forecast`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function rankAttribution(body: {
  lat: number;
  lon: number;
  time: string;
  radius_km?: number;
  window_hours?: number;
  uncertainty_km?: number;
}): Promise<AttributionResponse> {
  const res = await fetch(`${API_BASE}/api/attribution/rank`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}
