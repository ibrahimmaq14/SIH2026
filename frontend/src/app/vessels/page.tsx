'use client';

import { useEffect, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Ship, Search, ChevronLeft, ChevronRight, AlertTriangle, X, MapPin } from 'lucide-react';
import { getVessels, getVesselTrack, getVesselAnomalies } from '@/lib/api';
import type { Vessel, VesselTrackResponse, AnomalyResponse, TrackPoint } from '@/lib/types';

const MaritimeMap = dynamic(() => import('@/components/MaritimeMap'), { ssr: false });

export default function VesselsPage() {
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('MMSI');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [loading, setLoading] = useState(true);
  const [selectedVessel, setSelectedVessel] = useState<number | null>(null);
  const [vesselTrack, setVesselTrack] = useState<VesselTrackResponse | null>(null);
  const [vesselAnomalies, setVesselAnomalies] = useState<AnomalyResponse | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const loadVessels = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getVessels({ page, pageSize: 30, search, sortBy, sortOrder });
      setVessels(res.vessels);
      setTotal(res.total);
      setTotalPages(res.totalPages);
    } catch { /* API unavailable */ }
    finally { setLoading(false); }
  }, [page, search, sortBy, sortOrder]);

  useEffect(() => { loadVessels(); }, [loadVessels]);

  const selectVessel = async (mmsi: number) => {
    setSelectedVessel(mmsi);
    setDrawerOpen(true);
    try {
      const [track, anomalies] = await Promise.all([
        getVesselTrack(mmsi),
        getVesselAnomalies(mmsi),
      ]);
      setVesselTrack(track);
      setVesselAnomalies(anomalies);
    } catch { /* API unavailable */ }
  };

  const handleSort = (col: string) => {
    if (sortBy === col) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(col);
      setSortOrder('asc');
    }
    setPage(1);
  };

  const vesselMarkers = vessels.map(v => ({
    mmsi: v.MMSI, name: v.VesselName, lat: v.LAT, lon: v.LON, sog: v.SOG, status: v.Status,
  }));

  const tracks = vesselTrack ? [{
    mmsi: vesselTrack.mmsi,
    points: vesselTrack.track,
  }] : [];

  const tableColumns = [
    { key: 'MMSI', label: 'MMSI' },
    { key: 'VesselName', label: 'Name' },
    { key: 'VesselType', label: 'Type' },
    { key: 'SOG', label: 'SOG (kn)' },
    { key: 'COG', label: 'COG (°)' },
    { key: 'Status', label: 'Status' },
    { key: 'LAT', label: 'Lat' },
    { key: 'LON', label: 'Lon' },
    { key: 'ObservationCount', label: 'Obs' },
  ];

  return (
    <>
      <div className="page-header">
        <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>AIS Vessel Analysis</h1>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
          Interactive vessel tracking and anomaly detection
        </p>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)' }}>
        {/* Map */}
        <div style={{ height: '45%', minHeight: 280, marginBottom: 12 }}>
          <MaritimeMap
            vessels={vesselMarkers}
            tracks={tracks}
            anomalies={vesselAnomalies?.anomalies || []}
            selectedVessel={selectedVessel}
            onVesselClick={selectVessel}
            height="100%"
          />
        </div>

        {/* Table controls */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10 }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 320 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              className="input-field"
              placeholder="Search by MMSI, name, IMO, callsign..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              style={{ paddingLeft: 30 }}
            />
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {total} vessels · Page {page}/{totalPages}
          </span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button className="btn btn-ghost" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={{ padding: '6px' }}>
              <ChevronLeft size={14} />
            </button>
            <button className="btn btn-ghost" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={{ padding: '6px' }}>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflow: 'auto', borderRadius: 8, border: '1px solid var(--border)' }}>
          <table className="data-table">
            <thead>
              <tr>
                {tableColumns.map(col => (
                  <th key={col.key} onClick={() => handleSort(col.key)}>
                    {col.label} {sortBy === col.key ? (sortOrder === 'asc' ? '↑' : '↓') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={tableColumns.length} style={{ textAlign: 'center', padding: 40 }}>Loading vessels...</td></tr>
              ) : vessels.length === 0 ? (
                <tr><td colSpan={tableColumns.length} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>No vessels found</td></tr>
              ) : vessels.map(v => (
                <tr
                  key={v.MMSI}
                  className={selectedVessel === v.MMSI ? 'selected' : ''}
                  onClick={() => selectVessel(v.MMSI)}
                  style={{ cursor: 'pointer' }}
                >
                  <td style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{v.MMSI}</td>
                  <td style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.VesselName}</td>
                  <td>{v.VesselType}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{v.SOG?.toFixed(1)}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{v.COG?.toFixed(1)}</td>
                  <td><span className="badge badge-available" style={{ fontSize: '0.6rem' }}>{v.Status}</span></td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{v.LAT?.toFixed(4)}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{v.LON?.toFixed(4)}</td>
                  <td style={{ fontVariantNumeric: 'tabular-nums' }}>{v.ObservationCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Vessel detail drawer */}
      {drawerOpen && selectedVessel && (
        <div style={{
          position: 'fixed', right: 0, top: 0, bottom: 0, width: 380,
          background: 'var(--navy-900)', borderLeft: '1px solid var(--border)',
          zIndex: 50, overflow: 'auto', boxShadow: '-4px 0 32px rgba(0,0,0,0.3)',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '16px 20px', borderBottom: '1px solid var(--border)',
            position: 'sticky', top: 0, background: 'var(--navy-900)', zIndex: 1,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Ship size={18} color="var(--accent)" />
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Vessel Detail</span>
            </div>
            <button onClick={() => setDrawerOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}>
              <X size={18} />
            </button>
          </div>

          <div style={{ padding: 20 }}>
            {vesselTrack?.info ? (
              <>
                <h3 style={{ margin: '0 0 16px', fontSize: '1.1rem', fontWeight: 700 }}>
                  {vesselTrack.info.vesselName}
                </h3>
                {[
                  ['MMSI', vesselTrack.info.mmsi],
                  ['IMO', vesselTrack.info.imo],
                  ['Call Sign', vesselTrack.info.callSign],
                  ['Type', vesselTrack.info.vesselType],
                  ['Length', `${vesselTrack.info.length} m`],
                  ['Width', `${vesselTrack.info.width} m`],
                  ['Draft', `${vesselTrack.info.draft} m`],
                  ['Cargo', vesselTrack.info.cargo],
                  ['Observations', vesselTrack.info.observationCount],
                ].map(([k, v]) => (
                  <div key={String(k)} style={{
                    display: 'flex', justifyContent: 'space-between',
                    padding: '6px 0', fontSize: '0.78rem',
                    borderBottom: '1px solid var(--border)',
                  }}>
                    <span style={{ color: 'var(--text-muted)' }}>{k}</span>
                    <span style={{ fontWeight: 500 }}>{String(v)}</span>
                  </div>
                ))}

                {/* Track summary */}
                {vesselTrack.track.length > 0 && (
                  <div style={{ marginTop: 20 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <MapPin size={14} color="var(--accent)" />
                      <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>Track ({vesselTrack.track.length} points)</span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                      <div>First: {new Date(vesselTrack.track[0].timestamp).toLocaleString()}</div>
                      <div>Last: {new Date(vesselTrack.track[vesselTrack.track.length - 1].timestamp).toLocaleString()}</div>
                    </div>
                  </div>
                )}

                {/* Anomalies */}
                <div style={{ marginTop: 20 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                    <AlertTriangle size={14} color="#f87171" />
                    <span style={{ fontSize: '0.78rem', fontWeight: 600 }}>
                      Anomaly Detection
                    </span>
                    {vesselAnomalies && (
                      <span className="badge badge-anomaly" style={{ marginLeft: 'auto' }}>
                        {vesselAnomalies.anomalyCount}
                      </span>
                    )}
                  </div>

                  {vesselAnomalies?.model_info && (
                    <div style={{
                      padding: '10px 12px', borderRadius: 6, marginBottom: 10,
                      background: 'rgba(34, 211, 238, 0.04)', border: '1px solid var(--border)',
                      fontSize: '0.68rem', color: 'var(--text-muted)',
                    }}>
                      <div><strong>Model:</strong> {vesselAnomalies.model_info.type}</div>
                      <div><strong>Features:</strong> {vesselAnomalies.model_info.features.join(', ')} → {vesselAnomalies.model_info.target}</div>
                      <div><strong>R² Score:</strong> {vesselAnomalies.model_info.r2Score}</div>
                      <div><strong>Threshold:</strong> ±{vesselAnomalies.threshold}</div>
                    </div>
                  )}

                  {vesselAnomalies?.error && (
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      {vesselAnomalies.error}
                    </div>
                  )}

                  {vesselAnomalies?.anomalies?.slice(0, 10).map((a, i) => (
                    <div key={i} style={{
                      padding: '6px 8px', marginBottom: 3, borderRadius: 4,
                      background: 'rgba(239, 68, 68, 0.06)',
                      borderLeft: '3px solid #ef4444',
                      fontSize: '0.68rem',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>SOG: {a.sog} → {a.predictedSog}</span>
                        <span style={{ color: '#f87171' }}>Δ{a.difference.toFixed(1)}</span>
                      </div>
                      <div style={{ color: 'var(--text-muted)' }}>
                        {new Date(a.timestamp).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.82rem', padding: '20px 0', textAlign: 'center' }}>
                Loading vessel data...
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
