'use client';

import { useEffect, useState } from 'react';
import { Satellite, AlertTriangle, Eye, ChevronLeft, ChevronRight, ZoomIn, Info } from 'lucide-react';
import { getSARSummary, getSARDetections, getSARRegions, getSARImageURL } from '@/lib/api';
import type { SARSummary, SARDetection } from '@/lib/types';

export default function DetectionPage() {
  const [summary, setSummary] = useState<SARSummary | null>(null);
  const [detections, setDetections] = useState<SARDetection[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [selected, setSelected] = useState<SARDetection | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [sum, det, reg] = await Promise.all([
          getSARSummary(),
          getSARDetections(),
          getSARRegions(),
        ]);
        setSummary(sum);
        setDetections(det);
        setRegions(reg);
        if (det.length > 0) setSelected(det[0]);
      } catch {
        // API unavailable
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const currentIndex = selected ? detections.findIndex(d => d.id === selected.id) : 0;

  const navigate = (dir: number) => {
    const next = currentIndex + dir;
    if (next >= 0 && next < detections.length) {
      setSelected(detections[next]);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>Oil Spill Detection</h1>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
          SAR Satellite Imagery Analysis — Classification Dataset
        </p>
      </div>

      <div className="page-body">
        {/* Alert banner */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
          background: 'rgba(34, 197, 94, 0.08)', border: '1px solid rgba(34, 197, 94, 0.2)',
          borderRadius: 8, marginBottom: 20, fontSize: '0.78rem', color: '#4ade80',
        }}>
          <Info size={16} />
          <span>
            <strong>Trained classifier active</strong> — detections below are REAL model inference on repository SAR images
            (texture + HistGradientBoosting, 89.5% holdout / 87.5% 5-fold CV). Note: the README&apos;s claimed CNN never existed in the repo.
          </span>
        </div>

        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'Total SAR Images', value: summary?.totalImages?.toLocaleString() || '—', color: '#60a5fa' },
            { label: 'Oil Spill (Class 1)', value: summary?.class1Count?.toLocaleString() || '—', color: '#f87171' },
            { label: 'Clean (Class 0)', value: summary?.class0Count?.toLocaleString() || '—', color: '#4ade80' },
            { label: 'Image Format', value: summary?.imageFormat || '—', color: '#94a3b8' },
            { label: 'Classifier', value: summary?.modelStatus?.startsWith('Trained') ? 'Trained · 87.5% CV' : (summary?.modelStatus || '—'), color: '#4ade80' },
            { label: 'Regions', value: regions.length.toString(), color: '#a78bfa' },
          ].map(s => (
            <div key={s.label} className="card" style={{ padding: '14px 16px' }}>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {s.label}
              </div>
              <div style={{ fontSize: '1.2rem', fontWeight: 700, color: s.color, marginTop: 2 }}>
                {loading ? '...' : s.value}
              </div>
            </div>
          ))}
        </div>

        {/* Main workspace */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, minHeight: 500 }}>
          {/* Image viewer */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column', padding: 0 }}>
            {/* Toolbar */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 16px', borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => navigate(-1)} disabled={currentIndex <= 0} style={{ padding: '6px 8px' }}>
                  <ChevronLeft size={16} />
                </button>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  {currentIndex + 1} / {detections.length}
                </span>
                <button className="btn btn-ghost" onClick={() => navigate(1)} disabled={currentIndex >= detections.length - 1} style={{ padding: '6px 8px' }}>
                  <ChevronRight size={16} />
                </button>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                {selected && (
                  <span className={`badge ${selected.class === 1 ? 'badge-anomaly' : 'badge-available'}`}>
                    {selected.className}
                  </span>
                )}
                <span className="badge badge-demo">Demo</span>
              </div>
            </div>

            {/* Image area */}
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--navy-950)', padding: 20, minHeight: 400,
            }}>
              {selected ? (
                <img
                  src={getSARImageURL(selected.class, selected.filename)}
                  alt={selected.className}
                  style={{
                    maxWidth: '100%', maxHeight: '100%', objectFit: 'contain',
                    borderRadius: 4, border: '1px solid var(--border)',
                  }}
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none';
                  }}
                />
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  {loading ? 'Loading SAR imagery...' : 'Select an image to view'}
                </div>
              )}
            </div>
          </div>

          {/* Side panel - details & list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto' }}>
            {/* Selected image metadata */}
            {selected && (
              <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Eye size={16} color="var(--accent)" />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Image Details</span>
                </div>
                {[
                  ['ID', selected.id],
                  ['Classification', selected.className],
                  ['Region', selected.region || 'Unknown'],
                  ['Dimensions', selected.dimensions],
                  ['Status', selected.status],
                ].map(([k, v]) => (
                  <div key={k} style={{
                    display: 'flex', justifyContent: 'space-between',
                    fontSize: '0.72rem', padding: '4px 0',
                    borderBottom: '1px solid var(--border)',
                  }}>
                    <span style={{ color: 'var(--text-muted)' }}>{k}</span>
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
                <div style={{
                  marginTop: 10, padding: '8px 10px', borderRadius: 6,
                  background: 'rgba(251, 191, 36, 0.06)', border: '1px solid rgba(251, 191, 36, 0.15)',
                  fontSize: '0.68rem', color: '#fbbf24',
                }}>
                  {selected.note}
                </div>
              </div>
            )}

            {/* Detection list */}
            <div className="card" style={{ flex: 1, overflow: 'auto' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, marginBottom: 10 }}>
                Sample Detections
              </div>
              {detections.map((d) => (
                <div
                  key={d.id}
                  style={{
                    padding: '8px 10px', marginBottom: 4, borderRadius: 6, cursor: 'pointer',
                    background: selected?.id === d.id ? 'rgba(34, 211, 238, 0.08)' : 'transparent',
                    borderLeft: `3px solid ${d.class === 1 ? '#ef4444' : '#4ade80'}`,
                    transition: 'background 0.15s',
                  }}
                  onClick={() => setSelected(d)}
                >
                  <div style={{ fontSize: '0.75rem', fontWeight: 500, marginBottom: 2 }}>
                    {d.id}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    <span>{d.region}</span>
                    <span className={`badge ${d.class === 1 ? 'badge-anomaly' : 'badge-available'}`} style={{ fontSize: '0.6rem' }}>
                      {d.className}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
