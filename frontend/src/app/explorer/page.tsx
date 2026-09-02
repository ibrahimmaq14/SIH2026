'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Database, Search, Filter, ChevronLeft, ChevronRight,
  Ship, Satellite, AlertTriangle, CheckCircle2, Download, Eye
} from 'lucide-react';
import { getVessels, getAllAnomalies, getSARDetections, getSARSummary, getSARImageURL, getVesselTypes } from '@/lib/api';
import type { Vessel, SARDetection, Anomaly, SARSummary } from '@/lib/types';

export default function DataExplorerPage() {
  const [activeTab, setActiveTab] = useState<'ais' | 'sar' | 'detections' | 'anomalies'>('ais');

  // AIS state
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [aisTotal, setAisTotal] = useState(0);
  const [aisPage, setAisPage] = useState(1);
  const [aisTotalPages, setAisTotalPages] = useState(1);
  const [aisSearch, setAisSearch] = useState('');
  const [aisVesselType, setAisVesselType] = useState('');
  const [vesselTypes, setVesselTypes] = useState<string[]>([]);
  const [selectedVesselRow, setSelectedVesselRow] = useState<Vessel | null>(null);

  // SAR state
  const [sarSummary, setSarSummary] = useState<SARSummary | null>(null);

  // Detections state
  const [detections, setDetections] = useState<SARDetection[]>([]);

  // Anomalies state
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [anomLoading, setAnomLoading] = useState(false);

  const [loading, setLoading] = useState(true);

  // Load AIS data
  const loadAisData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getVessels({
        page: aisPage,
        pageSize: 25,
        search: aisSearch,
        vesselType: aisVesselType || undefined,
      });
      setVessels(res.vessels);
      setAisTotal(res.total);
      setAisTotalPages(res.totalPages);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [aisPage, aisSearch, aisVesselType]);

  useEffect(() => {
    loadAisData();
  }, [loadAisData]);

  useEffect(() => {
    async function loadAux() {
      try {
        const [types, sarSum, dets, anoms] = await Promise.allSettled([
          getVesselTypes(),
          getSARSummary(),
          getSARDetections(),
          getAllAnomalies(6.0, 30)
        ]);

        if (types.status === 'fulfilled') setVesselTypes(types.value);
        if (sarSum.status === 'fulfilled') setSarSummary(sarSum.value);
        if (dets.status === 'fulfilled') setDetections(dets.value);
        if (anoms.status === 'fulfilled') setAnomalies(anoms.value.allAnomalies || []);
      } catch (e) {
        console.error(e);
      }
    }
    loadAux();
  }, []);

  return (
    <>
      <div className="page-header">
        <h1 style={{ fontSize: '1.3rem', fontWeight: 700, margin: 0 }}>Data Schema & Telemetry Explorer</h1>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '4px 0 0' }}>
          Direct inspection of live repository datasets, satellite imagery catalogues, and algorithmic detection tables
        </p>
      </div>

      <div className="page-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Navigation Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', gap: 4 }}>
          {[
            { id: 'ais', label: 'AIS Telemetry Records', count: aisTotal, icon: Ship },
            { id: 'sar', label: 'SAR Imagery Catalog', count: sarSummary?.totalImages, icon: Satellite },
            { id: 'detections', label: 'Spill Detections (Demo)', count: detections.length, icon: CheckCircle2 },
            { id: 'anomalies', label: 'SVR Anomaly Records', count: anomalies.length, icon: AlertTriangle },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 16px',
                  fontSize: '0.78rem',
                  fontWeight: active ? 600 : 400,
                  color: active ? 'var(--accent)' : 'var(--text-muted)',
                  borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                  background: 'transparent',
                  borderTop: 'none',
                  borderLeft: 'none',
                  borderRight: 'none',
                  cursor: 'pointer',
                }}
              >
                <Icon size={15} />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span style={{ fontSize: '0.68rem', padding: '1px 6px', borderRadius: 10, background: 'var(--navy-800)', color: 'var(--text-secondary)' }}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab 1: AIS Telemetry Records */}
        {activeTab === 'ais' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Filters */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ position: 'relative', minWidth: 280 }}>
                <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input
                  className="input-field"
                  placeholder="Filter by MMSI, Vessel Name, IMO..."
                  value={aisSearch}
                  onChange={(e) => { setAisSearch(e.target.value); setAisPage(1); }}
                  style={{ paddingLeft: 30 }}
                />
              </div>

              <select
                className="input-field"
                value={aisVesselType}
                onChange={(e) => { setAisVesselType(e.target.value); setAisPage(1); }}
                style={{ maxWidth: 180 }}
              >
                <option value="">All Vessel Types</option>
                {vesselTypes.map((t) => (
                  <option key={t} value={t}>Type: {t}</option>
                ))}
              </select>

              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Page {aisPage} of {aisTotalPages} ({aisTotal} records)
                </span>
                <button className="btn btn-ghost" onClick={() => setAisPage(p => Math.max(1, p - 1))} disabled={aisPage <= 1} style={{ padding: '6px' }}>
                  <ChevronLeft size={14} />
                </button>
                <button className="btn btn-ghost" onClick={() => setAisPage(p => Math.min(aisTotalPages, p + 1))} disabled={aisPage >= aisTotalPages} style={{ padding: '6px' }}>
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>

            {/* Main AIS Table */}
            <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--border)' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>MMSI</th>
                    <th>Vessel Name</th>
                    <th>IMO</th>
                    <th>CallSign</th>
                    <th>Type</th>
                    <th>SOG (kn)</th>
                    <th>COG (°)</th>
                    <th>Status</th>
                    <th>Length</th>
                    <th>Width</th>
                    <th>Draft</th>
                    <th>Cargo</th>
                    <th>Latitude</th>
                    <th>Longitude</th>
                    <th>Last Telemetry</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={15} style={{ textAlign: 'center', padding: 30 }}>Loading telemetry data...</td></tr>
                  ) : vessels.length === 0 ? (
                    <tr><td colSpan={15} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>No matching telemetry found</td></tr>
                  ) : vessels.map((v) => (
                    <tr
                      key={v.MMSI}
                      onClick={() => setSelectedVesselRow(v)}
                      style={{ cursor: 'pointer', background: selectedVesselRow?.MMSI === v.MMSI ? 'rgba(34,211,238,0.08)' : undefined }}
                    >
                      <td style={{ fontWeight: 600, color: 'var(--accent)' }}>{v.MMSI}</td>
                      <td style={{ fontWeight: 500 }}>{v.VesselName}</td>
                      <td>{v.IMO}</td>
                      <td>{v.CallSign}</td>
                      <td>{v.VesselType}</td>
                      <td>{v.SOG?.toFixed(1)}</td>
                      <td>{v.COG?.toFixed(1)}</td>
                      <td><span className="badge badge-available" style={{ fontSize: '0.62rem' }}>{v.Status}</span></td>
                      <td>{v.Length}m</td>
                      <td>{v.Width}m</td>
                      <td>{v.Draft}m</td>
                      <td>{v.Cargo}</td>
                      <td>{v.LAT?.toFixed(4)}</td>
                      <td>{v.LON?.toFixed(4)}</td>
                      <td style={{ fontSize: '0.72rem' }}>{new Date(v.BaseDateTime).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Row Detail Inspector Drawer / Modal */}
            {selectedVesselRow && (
              <div className="card" style={{ background: 'var(--navy-900)', border: '1px solid var(--accent)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--accent)' }}>
                    Selected Record Telemetry: {selectedVesselRow.VesselName} ({selectedVesselRow.MMSI})
                  </div>
                  <button className="btn btn-ghost" onClick={() => setSelectedVesselRow(null)} style={{ padding: '4px 8px', fontSize: '0.7rem' }}>
                    Close
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8, fontSize: '0.72rem' }}>
                  <div><strong>MMSI:</strong> {selectedVesselRow.MMSI}</div>
                  <div><strong>Vessel Name:</strong> {selectedVesselRow.VesselName}</div>
                  <div><strong>IMO:</strong> {selectedVesselRow.IMO}</div>
                  <div><strong>CallSign:</strong> {selectedVesselRow.CallSign}</div>
                  <div><strong>Type:</strong> {selectedVesselRow.VesselType}</div>
                  <div><strong>SOG:</strong> {selectedVesselRow.SOG} kn</div>
                  <div><strong>COG:</strong> {selectedVesselRow.COG}°</div>
                  <div><strong>Heading:</strong> {selectedVesselRow.Heading}°</div>
                  <div><strong>Length:</strong> {selectedVesselRow.Length} m</div>
                  <div><strong>Width:</strong> {selectedVesselRow.Width} m</div>
                  <div><strong>Draft:</strong> {selectedVesselRow.Draft} m</div>
                  <div><strong>Cargo Code:</strong> {selectedVesselRow.Cargo}</div>
                  <div><strong>Latitude:</strong> {selectedVesselRow.LAT}</div>
                  <div><strong>Longitude:</strong> {selectedVesselRow.LON}</div>
                  <div><strong>Timestamp:</strong> {selectedVesselRow.BaseDateTime}</div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: SAR Imagery Catalog */}
        {activeTab === 'sar' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div className="card" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
              <div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Total SAR Images</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--accent)' }}>{sarSummary?.totalImages}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Clean Baseline (Class 0)</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#4ade80' }}>{sarSummary?.class0Count}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Oil Spill (Class 1)</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 700, color: '#f87171' }}>{sarSummary?.class1Count}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Dimensions & Color</div>
                <div style={{ fontSize: '1rem', fontWeight: 600 }}>{sarSummary?.imageFormat}</div>
              </div>
            </div>

            <div style={{ padding: '14px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)', borderRadius: 8, fontSize: '0.75rem', color: '#fbbf24' }}>
              <strong>Dataset Organization:</strong> Images are binary categorized by presence of surface oil slick damping in Sentinel-1 / ERS radar backscatter. Class 0 contains clean water surface; Class 1 contains verified oil slicks.
            </div>
          </div>
        )}

        {/* Tab 3: Detections (Demo findings) */}
        {activeTab === 'detections' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--border)' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Detection ID</th>
                    <th>Classification</th>
                    <th>Region Code</th>
                    <th>Resolution</th>
                    <th>Status</th>
                    <th>Model Note</th>
                  </tr>
                </thead>
                <tbody>
                  {detections.map((d) => (
                    <tr key={d.id}>
                      <td style={{ fontWeight: 600, color: 'var(--accent)' }}>{d.id}</td>
                      <td>
                        <span className={`badge ${d.class === 1 ? 'badge-anomaly' : 'badge-available'}`}>
                          {d.className}
                        </span>
                      </td>
                      <td>{d.region || 'Gulf/Global'}</td>
                      <td>{d.dimensions}</td>
                      <td><span className="badge badge-demo">Demo</span></td>
                      <td style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{d.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 4: Anomalies */}
        {activeTab === 'anomalies' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--border)' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Actual SOG (kn)</th>
                    <th>Predicted SOG (kn)</th>
                    <th>Deviation (Δ)</th>
                    <th>COG (°)</th>
                    <th>Heading</th>
                    <th>Latitude</th>
                    <th>Longitude</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.length === 0 ? (
                    <tr><td colSpan={9} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>No anomalous telemetry records</td></tr>
                  ) : anomalies.map((a, idx) => (
                    <tr key={idx}>
                      <td>{new Date(a.timestamp).toLocaleString()}</td>
                      <td style={{ fontWeight: 600, color: '#f87171' }}>{a.sog.toFixed(1)}</td>
                      <td>{a.predictedSog.toFixed(1)}</td>
                      <td style={{ fontWeight: 700, color: '#f87171' }}>Δ {a.difference.toFixed(1)}</td>
                      <td>{a.cog.toFixed(1)}°</td>
                      <td>{a.heading}°</td>
                      <td>{a.lat.toFixed(4)}</td>
                      <td>{a.lon.toFixed(4)}</td>
                      <td><span className="badge badge-anomaly" style={{ fontSize: '0.62rem' }}>Speed Anomaly</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
