'use client';

import { useEffect, useState, useCallback, Fragment } from 'react';
import dynamic from 'next/dynamic';
import {
  Search, Satellite, Ship, AlertTriangle, ShieldAlert,
  Clock, MapPin, CheckCircle2, ChevronRight, FileText, Download,
  Layers, ArrowRight, ExternalLink, Play, Loader2, Upload, Info,
} from 'lucide-react';
import { runPipeline, getInvestigations } from '@/lib/api';
import type {
  PipelineRunResponse,
  CandidateVessel,
  Investigation,
} from '@/lib/types';
import type { DriftLayer, PointMarker } from '@/components/MaritimeMapInner';

const MaritimeMap = dynamic(() => import('@/components/MaritimeMap'), { ssr: false });

const FALLBACK_CENTER: [number, number] = [28.52, -94.95];

export default function InvestigationsPage() {
  const [run, setRun] = useState<PipelineRunResponse | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateVessel | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'summary' | 'spill' | 'ais' | 'evidence'>('summary');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [priorRuns, setPriorRuns] = useState<Investigation[]>([]);

  const execute = useCallback(async (file?: File | null) => {
    setRunning(true);
    setError(null);
    try {
      const result = await runPipeline(
        {
          hindcast_hours: 48,
          forecast_hours: 48,
          timestep_minutes: 60,
          windage: 0.03,
          search_radius_km: 15,
          window_hours: 12,
        },
        file ?? undefined
      );
      setRun(result);
      setSelectedCandidate(result.attribution?.candidates?.[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pipeline failed');
      setRun(null);
    } finally {
      setRunning(false);
    }
  }, []);

  useEffect(() => {
    // Auto-run the demo pipeline on first load (uses a dataset SAR image)
    execute(null);
    getInvestigations()
      .then((r) => setPriorRuns(r.investigations))
      .catch(() => setPriorRuns([]));
  }, [execute]);

  // ── Map layers derived from the pipeline result ──────────────────────
  const spill = run?.characterization?.geographic ?? null;
  const hindcast = run?.hindcast ?? null;
  const forecast = run?.forecast ?? null;

  const driftLayers: DriftLayer[] = [];
  if (hindcast?.track?.points?.length) {
    driftLayers.push({
      id: 'hindcast',
      label: 'Hindcast Path (backward)',
      points: hindcast.track.points.map((p) => ({ lat: p.lat, lon: p.lon, timestamp: p.timestamp })),
      color: '#a78bfa',
      dashed: true,
    });
  }
  if (forecast?.track?.points?.length) {
    driftLayers.push({
      id: 'forecast',
      label: 'Forecast Path (forward)',
      points: forecast.track.points.map((p) => ({ lat: p.lat, lon: p.lon, timestamp: p.timestamp })),
      color: '#22d3ee',
    });
  }

  const pointMarkers: PointMarker[] = [];
  if (spill) {
    pointMarkers.push({
      id: 'observation',
      label: 'Observed Spill (synthetic anchor)',
      lat: spill.lat,
      lon: spill.lon,
      color: '#f59e0b',
      popup: run?.characterization?.detection?.detected
        ? `Confidence ${(run.characterization.detection.confidence * 100).toFixed(1)}%`
        : 'No spill detected',
    });
  }
  if (hindcast) {
    pointMarkers.push({
      id: 'origin',
      label: 'Estimated Origin (hindcast)',
      lat: hindcast.origin_location.lat,
      lon: hindcast.origin_location.lon,
      color: '#a78bfa',
      radiusKm: hindcast.uncertainty_radius_km,
      popup: `± ${hindcast.uncertainty_radius_km} km · release ~${new Date(hindcast.origin_time).toLocaleString()}`,
    });
  }

  const candidateTracks = selectedCandidate
    ? [{ mmsi: selectedCandidate.mmsi, points: selectedCandidate.track, color: '#f97316' }]
    : [];

  const candidateVessels = (run?.attribution?.candidates ?? []).map((c) => ({
    mmsi: c.mmsi,
    name: c.vesselName,
    lat: c.track[c.track.length - 1]?.lat ?? 0,
    lon: c.track[c.track.length - 1]?.lon ?? 0,
    sog: c.trajectory_features.speed_at_min_distance ?? c.trajectory_features.mean_speed_knots ?? 0,
    status: `score ${c.score}`,
  }));

  const centerCoords: [number, number] =
    spill && hindcast
      ? [(spill.lat + hindcast.origin_location.lat) / 2, (spill.lon + hindcast.origin_location.lon) / 2]
      : spill
        ? [spill.lat, spill.lon]
        : FALLBACK_CENTER;

  const det = run?.detection;
  const env = run?.environment;
  const attribution = run?.attribution;

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>Incident Investigation Workspace</h1>
              <span className={`badge ${det?.detected ? 'badge-available' : 'badge-demo'}`}>
                {det?.detected ? 'Live Pipeline' : 'Idle'}
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
              End-to-end correlation: SAR spill detection → drift hindcast/forecast → AIS vessel attribution
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <label className="btn btn-ghost" style={{ cursor: 'pointer' }}>
              <Upload size={14} />
              <input
                type="file"
                accept="image/jpeg,image/png,image/tiff"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  setUploadFile(f ?? null);
                }}
              />
              {uploadFile ? uploadFile.name.slice(0, 24) : 'Select SAR image'}
            </label>
            <button className="btn btn-primary" onClick={() => execute(uploadFile)} disabled={running}>
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? 'Running pipeline…' : 'Run pipeline'}
            </button>
          </div>
        </div>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {error && (
          <div className="card" style={{ borderColor: 'rgba(239,68,68,0.4)', background: 'rgba(239,68,68,0.06)', padding: '12px 16px', fontSize: '0.82rem', color: '#f87171' }}>
            <AlertTriangle size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
            {error}
          </div>
        )}

        {/* Step-by-Step Investigation Pipeline Bar (live status) */}
        <div className="card" style={{ padding: '14px 20px', background: 'var(--navy-900)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            {[
              { n: 1, tag: 'Satellite Observation', title: det ? `${det.detected ? 'Spill' : 'Clean'} · ${(det.confidence * 100).toFixed(0)}%` : '—', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.4)' },
              { n: 2, tag: 'Hindcast Origin', title: hindcast ? `${hindcast.origin_location.lat.toFixed(3)}, ${hindcast.origin_location.lon.toFixed(3)}` : '—', color: '#a78bfa', bg: 'rgba(167,139,250,0.15)', border: 'rgba(167,139,250,0.4)' },
              { n: 3, tag: 'AIS Candidates', title: attribution ? `${attribution.candidates.length} vessels` : '—', color: '#60a5fa', bg: 'rgba(96,165,250,0.15)', border: 'rgba(96,165,250,0.4)' },
              { n: 4, tag: 'Anomaly Analysis', title: attribution ? `${attribution.candidates.filter((c) => c.behaviour.anomaly_score > 30).length} flagged` : '—', color: '#f87171', bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.4)' },
              { n: 5, tag: 'Top Suspect', title: attribution?.candidates?.[0] ? `#${attribution.candidates[0].mmsi} (${attribution.candidates[0].score})` : '—', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.4)' },
            ].map((step, i, arr) => (
              <Fragment key={step.n}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 26, height: 26, borderRadius: '50%', background: step.bg, border: `1px solid ${step.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: step.color, fontSize: '0.75rem', fontWeight: 700 }}>{step.n}</div>
                  <div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{step.tag}</div>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>{step.title}</div>
                  </div>
                </div>
                {i < arr.length - 1 && <ChevronRight size={16} color="var(--text-muted)" />}
              </Fragment>
            ))}
          </div>
        </div>

        {/* Main Grid: Map & Investigation Side Dossier */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 420px', gap: 16, minHeight: 600 }}>
          {/* Map Area */}
          <div className="card" style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <MapPin size={16} color="var(--accent)" />
                <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Incident Geospatial Correlator</span>
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                {run ? `Run ${run.run_id} · ${run.status}` : '—'}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 520 }}>
              <MaritimeMap
                vessels={candidateVessels}
                tracks={candidateTracks}
                driftLayers={driftLayers}
                pointMarkers={pointMarkers}
                selectedVessel={selectedCandidate?.mmsi ?? null}
                onVesselClick={(mmsi) => {
                  const c = attribution?.candidates.find((x) => x.mmsi === mmsi);
                  if (c) setSelectedCandidate(c);
                }}
                center={centerCoords}
                zoom={9}
                height="100%"
              />
            </div>
          </div>

          {/* Dossier Side Panel */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
            {/* Tab navigation */}
            <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', background: 'var(--navy-900)' }}>
              {(['summary', 'spill', 'ais', 'evidence'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    flex: 1,
                    padding: '10px 8px',
                    fontSize: '0.72rem',
                    fontWeight: activeTab === tab ? 600 : 400,
                    color: activeTab === tab ? 'var(--accent)' : 'var(--text-muted)',
                    borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                    background: 'transparent',
                    borderTop: 'none',
                    borderLeft: 'none',
                    borderRight: 'none',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: 18 }}>
              {activeTab === 'summary' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700 }}>
                      Run {run?.run_id ?? '—'}
                    </h3>
                    <span className={`badge ${run?.status === 'completed' ? 'badge-available' : 'badge-demo'}`}>
                      {run?.status ?? 'idle'}
                    </span>
                  </div>

                  <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>
                    {run?.detection?.source_label?.description ??
                      'Run the pipeline to detect a spill, estimate its origin by backward drift, and rank nearby AIS vessels.'}
                  </p>

                  <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
                    <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>
                      Timeline Sequence
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {(run?.timeline ?? []).map((t, idx) => (
                        <div key={idx} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: t.status === 'completed' ? 'var(--green-400)' : t.status === 'failed' ? 'var(--red-500)' : '#fbbf24', marginTop: 4, flexShrink: 0 }} />
                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{t.event}</span>
                              <span className={`badge ${t.status === 'completed' ? 'badge-available' : 'badge-demo'}`} style={{ fontSize: '0.6rem' }}>
                                {t.status}
                              </span>
                            </div>
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>{t.description}</div>
                          </div>
                        </div>
                      ))}
                      {!run && <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>No pipeline run yet.</div>}
                    </div>
                  </div>

                  {run?.disclaimers?.length ? (
                    <div style={{ padding: '10px 12px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 6 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#fbbf24', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Info size={12} /> Data provenance notes
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: '0.68rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                        {run.disclaimers.map((d, i) => <li key={i}>{d}</li>)}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}

              {activeTab === 'spill' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>Satellite Observation Metadata</div>
                  <div style={{ padding: '10px 12px', background: 'var(--navy-950)', borderRadius: 6, border: '1px solid var(--border)' }}>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Image:</div>
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, wordBreak: 'break-all' }}>{det?.image_id ?? '—'}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>Detection method:</div>
                    <div style={{ fontSize: '0.78rem', color: det?.model_available ? '#4ade80' : '#fbbf24' }}>
                      {det?.detection_method ?? '—'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>Confidence:</div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: det?.detected ? '#f87171' : '#4ade80' }}>
                      {det ? `${(det.confidence * 100).toFixed(1)}% — ${det.detected ? 'OIL SPILL' : 'no spill'}` : '—'}
                    </div>
                  </div>

                  {run?.characterization?.geometry ? (
                    <div style={{ padding: '10px 12px', background: 'rgba(34,211,238,0.05)', border: '1px solid var(--border)', borderRadius: 6 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>Slick Geometry (weak segmentation)</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        Type: {run.characterization.geometry.geometry_type}<br />
                        Area: {run.characterization.geometry.area_px} px² · Perimeter: {run.characterization.geometry.perimeter_px} px<br />
                        Length: {run.characterization.geometry.length_px}px × Width: {run.characterization.geometry.width_px}px (AR {run.characterization.geometry.aspect_ratio})<br />
                        Orientation: {run.characterization.geometry.orientation_deg}° · Centroid: ({run.characterization.geometry.centroid_px.join(', ')}) px
                      </div>
                      <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 6 }}>
                        {run.characterization.segmentation_note}
                      </div>
                    </div>
                  ) : null}

                  {hindcast ? (
                    <div style={{ padding: '10px 12px', background: 'rgba(167,139,250,0.06)', border: '1px solid rgba(167,139,250,0.2)', borderRadius: 6 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#a78bfa', marginBottom: 4 }}>Hindcast (Origin Estimate)</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        Origin: {hindcast.origin_location.lat.toFixed(4)}, {hindcast.origin_location.lon.toFixed(4)}<br />
                        Release window: ~{new Date(hindcast.origin_time).toLocaleString()} (±{hindcast.estimated_release_window_hours} h)<br />
                        Uncertainty: ±{hindcast.uncertainty_radius_km} km · Confidence: {(hindcast.confidence * 100).toFixed(0)}%
                      </div>
                      <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: 6 }}>{hindcast.disclaimer}</div>
                    </div>
                  ) : (
                    <div style={{ padding: '10px 12px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 6, fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      Hindcast not available for this run.
                    </div>
                  )}

                  {env?.samples?.length ? (
                    <div style={{ padding: '10px 12px', background: 'var(--navy-950)', borderRadius: 6, border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 600, marginBottom: 4, color: env.dataClass === 'model' ? '#4ade80' : '#fbbf24' }}>
                        Environmental Forcing ({env.provider} · {env.dataClass})
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                        {env.samples.length} samples · {env.note}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}

              {activeTab === 'ais' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                    Ranked Candidate Vessels ({attribution?.candidates.length ?? 0})
                  </div>
                  {!attribution?.candidates.length && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>No candidates found around the estimated origin/time.</div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 420, overflowY: 'auto' }}>
                    {attribution?.candidates.map((c) => (
                      <div
                        key={c.mmsi}
                        onClick={() => setSelectedCandidate(c)}
                        style={{
                          padding: '8px 10px',
                          borderRadius: 6,
                          background: selectedCandidate?.mmsi === c.mmsi ? 'rgba(34,211,238,0.1)' : 'var(--navy-950)',
                          border: `1px solid ${selectedCandidate?.mmsi === c.mmsi ? 'var(--accent)' : 'var(--border)'}`,
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600 }}>
                          <span>#{c.rank} {c.vesselName}</span>
                          <span style={{ color: c.score > 60 ? '#fbbf24' : 'var(--accent)' }}>{c.score.toFixed(1)}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          <span>MMSI: {c.mmsi}</span>
                          <span>min {c.min_distance_km.toFixed(1)} km · Δt {c.time_diff_hours?.toFixed(1) ?? '—'} h</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  {attribution?.excluded?.length ? (
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {attribution.excluded.length} vessels excluded by filtering (see methodology).
                    </div>
                  ) : null}
                </div>
              )}

              {activeTab === 'evidence' && selectedCandidate && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                      #{selectedCandidate.rank} {selectedCandidate.vesselName}
                    </div>
                    <span className="badge badge-anomaly">Score {selectedCandidate.score.toFixed(1)}</span>
                  </div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>MMSI {selectedCandidate.mmsi}</div>

                  {/* Score components */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {Object.entries(selectedCandidate.score_components).map(([k, v]) => (
                      <div key={k}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)' }}>
                          <span style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}</span>
                          <span>{v.toFixed(0)}</span>
                        </div>
                        <div style={{ height: 4, background: 'var(--navy-950)', borderRadius: 2, marginTop: 2 }}>
                          <div style={{ height: '100%', width: `${v}%`, borderRadius: 2, background: v > 70 ? '#fbbf24' : v > 40 ? '#60a5fa' : '#64748b' }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Evidence bullets */}
                  <div>
                    <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>Evidence</div>
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      {selectedCandidate.evidence.map((e, i) => <li key={i}>{e}</li>)}
                      {selectedCandidate.behaviour.anomaly_flags.map((f, i) => <li key={`f${i}`} style={{ color: '#f87171' }}>{f}</li>)}
                    </ul>
                  </div>

                  {/* Trajectory features */}
                  <div>
                    <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>Trajectory</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                      Min distance: <b>{selectedCandidate.trajectory_features.min_distance_to_origin_km.toFixed(2)} km</b> at{' '}
                      {selectedCandidate.trajectory_features.min_distance_time ? new Date(selectedCandidate.trajectory_features.min_distance_time).toLocaleString() : '—'}<br />
                      Mean/max SOG: {selectedCandidate.trajectory_features.mean_speed_knots?.toFixed(1) ?? '—'} / {selectedCandidate.trajectory_features.max_speed_knots?.toFixed(1) ?? '—'} kn<br />
                      Dwell near origin: {selectedCandidate.trajectory_features.dwell_minutes_near_origin.toFixed(0)} min<br />
                      Σ|ΔCOG|: {selectedCandidate.trajectory_features.heading_changes_deg?.toFixed(0) ?? '—'}° · Σ|ΔSOG|: {selectedCandidate.trajectory_features.speed_changes_knots?.toFixed(1) ?? '—'} kn<br />
                      AIS points in window: {selectedCandidate.track.length}
                    </div>
                  </div>

                  <div style={{ padding: '8px 10px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 6, fontSize: '0.64rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                    {selectedCandidate.disclaimer}
                  </div>
                </div>
              )}

              {activeTab === 'evidence' && !selectedCandidate && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Select a candidate vessel to inspect its evidence.</div>
              )}
            </div>
          </div>
        </div>

        {/* Run history */}
        {priorRuns.length > 0 && (
          <div className="card" style={{ padding: '14px 20px' }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: 8 }}>Recent Pipeline Runs</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {priorRuns.map((r) => (
                <span key={r.id} className="badge badge-offline" title={r.title}>
                  {r.id}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
