'use client';

import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import {
  Ship, Satellite, AlertTriangle, Activity, Eye, Radio
} from 'lucide-react';
import { getVessels, getAllAnomalies, getSARSummary, getPipelineStatus, getAnalytics } from '@/lib/api';
import type { Vessel, AllAnomaliesResponse, SARSummary, PipelineStatusResponse, Analytics } from '@/lib/types';

const MaritimeMap = dynamic(() => import('@/components/MaritimeMap'), { ssr: false });

export default function OverviewPage() {
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [anomalyData, setAnomalyData] = useState<AllAnomaliesResponse | null>(null);
  const [sarSummary, setSarSummary] = useState<SARSummary | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatusResponse | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedVessel, setSelectedVessel] = useState<number | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [vesselRes, anomRes, sarRes, pipeRes, analyticsRes] = await Promise.allSettled([
          getVessels({ page: 1, pageSize: 200 }),
          getAllAnomalies(6.0, 15),
          getSARSummary(),
          getPipelineStatus(),
          getAnalytics(),
        ]);
        if (vesselRes.status === 'fulfilled') setVessels(vesselRes.value.vessels);
        if (anomRes.status === 'fulfilled') setAnomalyData(anomRes.value);
        if (sarRes.status === 'fulfilled') setSarSummary(sarRes.value);
        if (pipeRes.status === 'fulfilled') setPipeline(pipeRes.value);
        if (analyticsRes.status === 'fulfilled') setAnalytics(analyticsRes.value);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const vesselMarkers = vessels.map(v => ({
    mmsi: v.MMSI, name: v.VesselName, lat: v.LAT, lon: v.LON, sog: v.SOG, status: v.Status,
  }));

  const anomalyCount = anomalyData?.allAnomalies?.length || 0;
  const pipelineAvailable = pipeline?.pipeline?.filter(p => p.status === 'Available').length || 0;
  const pipelineTotal = pipeline?.pipeline?.length || 0;

  const statCards = [
    {
      label: 'Vessels Tracked',
      value: analytics?.uniqueVessels || vessels.length || '—',
      icon: Ship,
      color: '#60a5fa',
      sub: `${analytics?.totalRecords?.toLocaleString() || '—'} AIS observations`,
    },
    {
      label: 'AIS Anomalies',
      value: anomalyCount,
      icon: AlertTriangle,
      color: '#f87171',
      sub: `SVR threshold: ${anomalyData?.threshold || 6.0}`,
    },
    {
      label: 'SAR Images',
      value: sarSummary?.totalImages?.toLocaleString() || '—',
      icon: Satellite,
      color: '#fbbf24',
      sub: sarSummary?.modelStatus || 'Loading...',
    },
    {
      label: 'Pipeline',
      value: `${pipelineAvailable}/${pipelineTotal}`,
      icon: Activity,
      color: '#4ade80',
      sub: 'Services available',
    },
  ];

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
              Maritime Intelligence Overview
            </h1>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
              Oil Spill Detection System — AIS Analysis & Satellite Monitoring
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: error ? '#ef4444' : '#4ade80' }} />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {loading ? 'Loading...' : error ? 'Connection Error' : 'Live'}
            </span>
          </div>
        </div>
      </div>

      <div className="page-body">
        {/* Stat Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 20 }}>
          {statCards.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.label} className="card" style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: `${card.color}15`,
                  border: `1px solid ${card.color}30`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <Icon size={20} color={card.color} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    {card.label}
                  </div>
                  <div className="stat-value" style={{ color: card.color, fontSize: '1.5rem', margin: '2px 0' }}>
                    {loading ? '...' : card.value}
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {card.sub}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Main Map */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, height: 'calc(100vh - 280px)', minHeight: 400 }}>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            {!loading && (
              <MaritimeMap
                vessels={vesselMarkers}
                anomalies={anomalyData?.allAnomalies || []}
                selectedVessel={selectedVessel}
                onVesselClick={setSelectedVessel}
                height="100%"
              />
            )}
            {loading && (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                <Radio size={20} style={{ marginRight: 8, animation: 'spin 2s linear infinite' }} />
                Loading maritime data...
              </div>
            )}
          </div>

          {/* Side panel */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, overflow: 'auto' }}>
            {/* Active anomalies */}
            <div className="card" style={{ flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <AlertTriangle size={16} color="#f87171" />
                <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Recent Anomalies</span>
                <span className="badge badge-anomaly" style={{ marginLeft: 'auto' }}>
                  {anomalyCount}
                </span>
              </div>
              {anomalyData?.vessels?.slice(0, 5).map((v) => (
                <div
                  key={v.mmsi}
                  style={{
                    padding: '8px 10px', marginBottom: 4, borderRadius: 6,
                    background: selectedVessel === v.mmsi ? 'rgba(34, 211, 238, 0.08)' : 'transparent',
                    cursor: 'pointer', transition: 'background 0.15s',
                    borderLeft: `3px solid ${selectedVessel === v.mmsi ? '#22d3ee' : 'transparent'}`,
                  }}
                  onClick={() => setSelectedVessel(v.mmsi)}
                >
                  <div style={{ fontSize: '0.78rem', fontWeight: 500 }}>{v.vesselName}</div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
                    <span>MMSI: {v.mmsi}</span>
                    <span style={{ color: '#f87171' }}>{v.anomalyCount} anomalies</span>
                  </div>
                </div>
              ))}
              {(!anomalyData || anomalyData.vessels.length === 0) && !loading && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', padding: '8px 0' }}>
                  No anomalies detected yet
                </div>
              )}
            </div>

            {/* Pipeline status */}
            <div className="card" style={{ flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <Activity size={16} color="#4ade80" />
                <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>System Status</span>
              </div>
              {pipeline?.pipeline?.map((stage) => (
                <div key={stage.stage} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '5px 0', fontSize: '0.72rem',
                }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{stage.stage}</span>
                  <span className={`badge ${
                    stage.status === 'Available' ? 'badge-available' :
                    stage.status === 'Demo' ? 'badge-demo' :
                    stage.status === 'Offline' ? 'badge-offline' : 'badge-offline'
                  }`}>
                    {stage.status}
                  </span>
                </div>
              ))}
            </div>

            {/* SAR dataset */}
            <div className="card" style={{ flex: '0 0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Satellite size={16} color="#fbbf24" />
                <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>SAR Dataset</span>
                <span className="badge badge-demo" style={{ marginLeft: 'auto' }}>Demo</span>
              </div>
              {sarSummary?.classes?.map((c) => (
                <div key={c.id} style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: '0.72rem', padding: '3px 0', color: 'var(--text-secondary)',
                }}>
                  <span>{c.name}</span>
                  <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{c.count.toLocaleString()}</span>
                </div>
              ))}
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 8, fontStyle: 'italic' }}>
                {sarSummary?.modelStatus || 'Loading...'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
