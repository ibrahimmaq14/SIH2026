'use client';

import { useEffect, useState } from 'react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid, Legend
} from 'recharts';
import { BarChart3, Activity, Gauge, TrendingUp, Compass, Clock, Info } from 'lucide-react';
import { getAnalytics } from '@/lib/api';
import type { Analytics } from '@/lib/types';

const COLORS = ['#22d3ee', '#60a5fa', '#a78bfa', '#f472b6', '#fbbf24', '#4ade80', '#94a3b8'];

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getAnalytics();
        setAnalytics(data);
      } catch (err) {
        console.error('Failed to load analytics', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <>
      <div className="page-header">
        <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>AIS Telemetry Analytics</h1>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
          Exploratory data analysis reproducing the methodology & statistical correlations from the Jupyter notebook
        </p>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Key Statistical Highlights Row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
          <div className="card">
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Dataset Records</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent)', marginTop: 4 }}>
              {loading ? '...' : analytics?.totalRecords?.toLocaleString()}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Across {analytics?.uniqueVessels} unique vessels (MMSI)
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Speed Over Ground (SOG) Mode</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#60a5fa', marginTop: 4 }}>
              {loading ? '...' : `${analytics?.sogStats.mode} kn`}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Mean: {analytics?.sogStats.mean} kn · Median: {analytics?.sogStats.median} kn
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Modal Vessel Length</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#4ade80', marginTop: 4 }}>
              {loading ? '...' : `${analytics?.avgTrackLength} m`}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Calculated via statistical mode as in notebook (Sec 1.2)
            </div>
          </div>

          <div className="card">
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Geographic Coverage</div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fbbf24', marginTop: 4 }}>
              {loading ? '...' : `${analytics?.geoBounds.latMin.toFixed(1)}° to ${analytics?.geoBounds.latMax.toFixed(1)}°N`}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Lon: {analytics?.geoBounds.lonMin.toFixed(1)}° to {analytics?.geoBounds.lonMax.toFixed(1)}°W
            </div>
          </div>
        </div>

        {/* Notebook Feature Correlation Matrix Card */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <TrendingUp size={16} color="var(--accent)" />
            <span style={{ fontSize: '0.88rem', fontWeight: 600 }}>Notebook Pearson Correlation Matrix</span>
            <span className="badge badge-available" style={{ marginLeft: 'auto' }}>Notebook Sec 1.3 & 1.4</span>
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0 0 16px 0', lineHeight: 1.5 }}>
            Direct replication of correlations tested in the notebook to determine if speed (SOG) and course (COG) vary with vessel type, length, or beam width.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {[
              { label: 'SOG vs Vessel Type', val: analytics?.correlations.sogVesselType, note: 'Minimal correlation (~0%) — SOG does not vary by type' },
              { label: 'COG vs Vessel Type', val: analytics?.correlations.cogVesselType, note: 'Negligible correlation — heading independent of type' },
              { label: 'Length vs SOG', val: analytics?.correlations.lengthSog, note: 'Vessel length modifies SOG by ~10-15%' },
              { label: 'Length vs COG', val: analytics?.correlations.lengthCog, note: 'Vessel length modifies COG by ~16%' },
              { label: 'Width vs SOG', val: analytics?.correlations.widthSog, note: 'Vessel beam modifies SOG by ~12%' },
              { label: 'Width vs COG', val: analytics?.correlations.widthCog, note: 'Vessel beam modifies COG by ~13%' },
            ].map((c) => (
              <div key={c.label} style={{ padding: '12px 14px', background: 'var(--navy-950)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{c.label}</span>
                  <span style={{ fontSize: '0.95rem', fontWeight: 700, color: (c.val || 0) > 0.1 ? '#22d3ee' : '#94a3b8' }}>
                    {c.val !== undefined ? c.val.toFixed(4) : '—'}
                  </span>
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 4 }}>{c.note}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Charts Grid 1: Speed Distribution & Hourly Activity */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* SOG Speed Distribution */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>Speed Over Ground (SOG) Histogram</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 14 }}>Observation counts across velocity bins (knots)</div>
            <div style={{ height: 260, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={analytics?.sogDistribution || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                  <XAxis dataKey="range" stroke="var(--text-muted)" fontSize={10} tickLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={10} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: 'var(--navy-800)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  />
                  <Bar dataKey="count" fill="#22d3ee" radius={[4, 4, 0, 0]} name="AIS Records" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Diurnal / Hourly Telemetry Distribution */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>Hourly Telemetry Distribution (UTC)</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 14 }}>AIS message frequency extracted from BaseDateTime</div>
            <div style={{ height: 260, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analytics?.hourlyActivity || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                  <XAxis dataKey="hour" stroke="var(--text-muted)" fontSize={10} tickLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={10} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: 'var(--navy-800)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  />
                  <Line type="monotone" dataKey="count" stroke="#a78bfa" strokeWidth={2} dot={{ fill: '#a78bfa', r: 3 }} name="Observations" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Charts Grid 2: Top Active Vessels & Navigational Status */}
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 16 }}>
          {/* Top Vessels by Telemetry Density */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>Top 10 Tracked Vessels by Observation Count</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 14 }}>High-density vessels providing longitudinal track telemetry for SVR model fitting</div>
            <div style={{ height: 280, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={(analytics?.vesselActivity || []).slice(0, 10)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                  <XAxis type="number" stroke="var(--text-muted)" fontSize={10} tickLine={false} />
                  <YAxis dataKey="vesselName" type="category" stroke="var(--text-muted)" fontSize={10} tickLine={false} width={110} />
                  <Tooltip
                    contentStyle={{ background: 'var(--navy-800)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                  />
                  <Bar dataKey="observations" fill="#60a5fa" radius={[0, 4, 4, 0]} name="Observations" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Navigational Status Distribution */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>Navigational Status Classification</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: 14 }}>Underway, at anchor, moored breakdown</div>
            <div style={{ height: 280, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={analytics?.statusDistribution || []}
                    dataKey="count"
                    nameKey="status"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) => `${name ? String(name).substring(0, 10) : 'N/A'} ${((percent || 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {(analytics?.statusDistribution || []).map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: 'var(--navy-800)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
