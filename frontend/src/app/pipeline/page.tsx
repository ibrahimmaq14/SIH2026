'use client';

import { useEffect, useState } from 'react';
import {
  Activity, CheckCircle2, AlertCircle, Clock, Server,
  Database, Cpu, Layers, GitFork, Shield, Info, RefreshCw
} from 'lucide-react';
import { getPipelineStatus, checkHealth } from '@/lib/api';
import type { PipelineStage } from '@/lib/types';

export default function PipelinePage() {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [health, setHealth] = useState<{ status: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const [pipeRes, healthRes] = await Promise.allSettled([
        getPipelineStatus(),
        checkHealth(),
      ]);
      if (pipeRes.status === 'fulfilled') setStages(pipeRes.value.pipeline);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Available':
        return <span className="badge badge-available">Operational / Available</span>;
      case 'Demo':
        return <span className="badge badge-demo">Demo Mode</span>;
      case 'Not Configured':
        return <span className="badge badge-offline">Not Configured</span>;
      case 'Offline':
      default:
        return <span className="badge badge-anomaly">Offline / Error</span>;
    }
  };

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>System & Pipeline Architecture Status</h1>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
              Transparent telemetry of machine learning pipelines, data ingestion status, and processing readiness
            </p>
          </div>
          <button className="btn btn-ghost" onClick={loadStatus} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh Status
          </button>
        </div>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* System Overview Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Server size={18} color="var(--accent)" />
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>Backend API Service</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: health?.status === 'ok' ? 'var(--green-400)' : '#f87171' }}>
              {health?.status === 'ok' ? 'FastAPI 0.115.0 (Online)' : 'Connecting...'}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>Port: 8000 · In-Memory Telemetry Engine</div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Database size={18} color="#60a5fa" />
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>Telemetry Ingestion</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#60a5fa' }}>52,943 AIS Records</div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>Preprocessed & Interpolated via Pandas</div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Cpu size={18} color="#a78bfa" />
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>SAR Spill Classifier</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#a78bfa' }}>Trained · 87.5% CV</div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Texture + HistGradientBoosting on 5,630 SAR images (89.5% holdout)
            </div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Activity size={18} color="#fbbf24" />
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>Anomaly Engine</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#4ade80' }}>SVR Model (Scikit-Learn)</div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>Replicating Notebook SVR Formula</div>
          </div>
        </div>

        {/* Visual Pipeline Flow */}
        <div className="card" style={{ padding: '24px' }}>
          <div style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: 16 }}>
            End-to-End Processing Pipeline Architecture
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {stages.map((stage, idx) => (
              <div
                key={stage.stage}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '14px 18px',
                  background: 'var(--navy-950)',
                  borderRadius: 8,
                  border: '1px solid var(--border)',
                  borderLeft: `4px solid ${
                    stage.status === 'Available' ? 'var(--green-500)' :
                    stage.status === 'Demo' ? 'var(--amber-500)' :
                    stage.status === 'Not Configured' ? 'var(--navy-600)' : 'var(--red-500)'
                  }`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: '50%',
                    background: 'var(--navy-800)', border: '1px solid var(--border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)'
                  }}>
                    {idx + 1}
                  </div>

                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {stage.stage}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 2 }}>
                      {stage.description}
                    </div>
                    {stage.methodology && (
                      <div style={{ fontSize: '0.68rem', color: 'var(--accent)', marginTop: 2 }}>
                        Methodology: {stage.methodology}
                      </div>
                    )}
                    {stage.note && (
                      <div style={{ fontSize: '0.68rem', color: '#fbbf24', marginTop: 2 }}>
                        Note: {stage.note}
                      </div>
                    )}
                  </div>
                </div>

                <div style={{ flexShrink: 0, textAlign: 'right' }}>
                  {getStatusBadge(stage.status)}
                  {stage.lastRun && (
                    <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      {stage.lastRun}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Technical Honesty & Methodology Notice */}
        <div className="card" style={{ background: 'rgba(34,211,238,0.03)', border: '1px solid rgba(34,211,238,0.15)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Shield size={16} color="var(--accent)" />
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--accent)' }}>
              Technical Transparency & Future Roadmap
            </span>
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
            This application faithfully wraps the repository&apos;s data and ML work.
            The notebook&apos;s <strong>SVR anomaly detection</strong> is packaged in the backend and reused inside the attribution pipeline.
            The claimed CNN never existed in the repository; the system instead ships an <strong>honestly trained texture classifier</strong> (89.5% holdout / 87.5% 5-fold CV on the 5,630-image dataset, trained via <code>backend/train_sar_classifier.py</code>).
            New capabilities implemented on top: slick weak-segmentation, environmental providers (Open-Meteo real data + labelled synthetic demo), great-circle drift hindcast/forecast with ensemble uncertainty, and origin-anchored AIS vessel attribution with transparent scoring weights. All synthetic/demo outputs are labelled as such.
          </p>
        </div>
      </div>
    </>
  );
}
