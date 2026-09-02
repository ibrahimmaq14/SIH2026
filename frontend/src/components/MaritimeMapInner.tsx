'use client';

import React from 'react';
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Polyline,
  Popup,
  LayersControl,
} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import type { TrackPoint, Anomaly } from '@/lib/types';

interface VesselMarker {
  mmsi: number;
  name: string;
  lat: number;
  lon: number;
  sog: number;
  status: string;
}

/** Optional drift-trajectory layer (hindcast or forecast). */
export interface DriftLayer {
  id: string;
  label: string;
  points: { lat: number; lon: number; timestamp?: string }[];
  color: string;
  dashed?: boolean;
}

/** Optional marker for origin/observation points. */
export interface PointMarker {
  id: string;
  label: string;
  lat: number;
  lon: number;
  color: string;
  radiusKm?: number; // when set, an uncertainty circle is drawn
  popup?: string;
}

export interface MaritimeMapProps {
  vessels?: VesselMarker[];
  tracks?: { mmsi: number; points: TrackPoint[]; color?: string }[];
  anomalies?: Anomaly[];
  spillRegion?: { lat: number; lon: number; radius: number };
  /** NEW v2 layers — all optional so existing usage is unchanged */
  driftLayers?: DriftLayer[];
  pointMarkers?: PointMarker[];
  center?: [number, number];
  zoom?: number;
  onVesselClick?: (mmsi: number) => void;
  selectedVessel?: number | null;
  height?: string;
}

export default function MaritimeMapInner({
  vessels = [],
  tracks = [],
  anomalies = [],
  spillRegion,
  driftLayers = [],
  pointMarkers = [],
  center,
  zoom = 8,
  onVesselClick,
  selectedVessel,
  height = '100%',
}: MaritimeMapProps) {
  // Calculate center from data if not provided
  const mapCenter: [number, number] = center || (() => {
    if (vessels.length > 0) {
      const avgLat = vessels.reduce((s, v) => s + v.lat, 0) / vessels.length;
      const avgLon = vessels.reduce((s, v) => s + v.lon, 0) / vessels.length;
      return [avgLat, avgLon] as [number, number];
    }
    return [28.6, -94.9]; // Gulf of Mexico default
  })();

  const cartoApiKey = process.env.NEXT_PUBLIC_CARTO_API_KEY || 'cb1_2krl_1_8d5202e6f7970176b1a30773';
  const tileUrl = `https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=${cartoApiKey}`;

  return (
    <div style={{ height, width: '100%', borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)' }}>
      <MapContainer
        center={mapCenter}
        zoom={zoom}
        style={{ height: '100%', width: '100%' }}
        zoomControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url={tileUrl}
          subdomains="abcd"
          maxZoom={20}
        />

        <LayersControl position="topright">
          <LayersControl.Overlay checked name="Vessels">
            <React.Fragment>
              {vessels.map((v) => (
                <CircleMarker
                  key={v.mmsi}
                  center={[v.lat, v.lon]}
                  radius={selectedVessel === v.mmsi ? 8 : 5}
                  pathOptions={{
                    color: selectedVessel === v.mmsi ? '#22d3ee' : '#60a5fa',
                    fillColor: selectedVessel === v.mmsi ? '#22d3ee' : '#60a5fa',
                    fillOpacity: selectedVessel === v.mmsi ? 0.9 : 0.6,
                    weight: selectedVessel === v.mmsi ? 3 : 1,
                  }}
                  eventHandlers={{
                    click: () => onVesselClick?.(v.mmsi),
                  }}
                >
                  <Popup>
                    <div style={{ fontSize: '0.8rem', minWidth: 160 }}>
                      <div style={{ fontWeight: 700, marginBottom: 4 }}>{v.name || `MMSI: ${v.mmsi}`}</div>
                      <div>MMSI: {v.mmsi}</div>
                      <div>SOG: {v.sog} kn</div>
                      <div>Status: {v.status}</div>
                      <div>Pos: {v.lat.toFixed(4)}, {v.lon.toFixed(4)}</div>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </React.Fragment>
          </LayersControl.Overlay>

          <LayersControl.Overlay checked name="Vessel Tracks">
            <React.Fragment>
              {tracks.map((t) => (
                <Polyline
                  key={t.mmsi}
                  positions={t.points.map((p) => [p.lat, p.lon] as [number, number])}
                  pathOptions={{
                    color: t.color || (selectedVessel === t.mmsi ? '#22d3ee' : '#3b82f6'),
                    weight: selectedVessel === t.mmsi ? 3 : 1.5,
                    opacity: selectedVessel === t.mmsi ? 0.9 : 0.4,
                    dashArray: selectedVessel === t.mmsi ? undefined : '4 6',
                  }}
                />
              ))}
            </React.Fragment>
          </LayersControl.Overlay>

          <LayersControl.Overlay checked name="AIS Anomalies">
            <React.Fragment>
              {anomalies.map((a, i) => (
                <CircleMarker
                  key={`anomaly-${i}`}
                  center={[a.lat, a.lon]}
                  radius={6}
                  pathOptions={{
                    color: '#ef4444',
                    fillColor: '#ef4444',
                    fillOpacity: 0.7,
                    weight: 2,
                  }}
                >
                  <Popup>
                    <div style={{ fontSize: '0.8rem', minWidth: 160 }}>
                      <div style={{ fontWeight: 700, marginBottom: 4, color: '#ef4444' }}>⚠ Anomaly Detected</div>
                      <div>SOG: {a.sog} kn (predicted: {a.predictedSog})</div>
                      <div>Deviation: {a.difference.toFixed(1)}</div>
                      <div>COG: {a.cog}°</div>
                      <div>Time: {new Date(a.timestamp).toLocaleString()}</div>
                    </div>
                  </Popup>
                </CircleMarker>
              ))}
            </React.Fragment>
          </LayersControl.Overlay>

          {spillRegion && (
            <LayersControl.Overlay checked name="Oil Spill Region">
              <CircleMarker
                center={[spillRegion.lat, spillRegion.lon]}
                radius={spillRegion.radius || 20}
                pathOptions={{
                  color: '#f59e0b',
                  fillColor: '#f59e0b',
                  fillOpacity: 0.15,
                  weight: 2,
                  dashArray: '8 4',
                }}
              >
                <Popup>
                  <div style={{ fontSize: '0.8rem' }}>
                    <div style={{ fontWeight: 700, color: '#f59e0b' }}>Investigation Area</div>
                    <div>Demo region for investigation workflow</div>
                  </div>
                </Popup>
              </CircleMarker>
            </LayersControl.Overlay>
          )}

          {/* NEW v2: drift trajectory layers (hindcast/forecast) */}
          {driftLayers.map((layer) => (
            <LayersControl.Overlay checked key={layer.id} name={layer.label}>
              <React.Fragment>
                <Polyline
                  positions={layer.points.map((p) => [p.lat, p.lon] as [number, number])}
                  pathOptions={{
                    color: layer.color,
                    weight: 2.5,
                    opacity: 0.85,
                    dashArray: layer.dashed ? '6 5' : undefined,
                  }}
                />
                {layer.points.map((p, i) => (
                  <CircleMarker
                    key={`${layer.id}-pt-${i}`}
                    center={[p.lat, p.lon]}
                    radius={i === 0 ? 6 : 3}
                    pathOptions={{ color: layer.color, fillColor: layer.color, fillOpacity: 0.8, weight: 1 }}
                  >
                    <Popup>
                      <div style={{ fontSize: '0.78rem', minWidth: 140 }}>
                        <div style={{ fontWeight: 700, color: layer.color }}>{layer.label}</div>
                        {p.timestamp && <div>{new Date(p.timestamp).toLocaleString()}</div>}
                        <div>{p.lat.toFixed(4)}, {p.lon.toFixed(4)}</div>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </React.Fragment>
            </LayersControl.Overlay>
          ))}

          {/* NEW v2: point markers (origin, observation) with optional uncertainty circle */}
          {pointMarkers.map((m) => (
            <LayersControl.Overlay checked key={m.id} name={m.label}>
              <React.Fragment>
                {m.radiusKm ? (
                  <Circle
                    center={[m.lat, m.lon]}
                    radius={m.radiusKm * 1000}
                    pathOptions={{ color: m.color, fillColor: m.color, fillOpacity: 0.08, weight: 1.5, dashArray: '4 6' }}
                  />
                ) : null}
                <CircleMarker
                  center={[m.lat, m.lon]}
                  radius={7}
                  pathOptions={{ color: m.color, fillColor: m.color, fillOpacity: 0.9, weight: 2 }}
                >
                  <Popup>
                    <div style={{ fontSize: '0.8rem', minWidth: 150 }}>
                      <div style={{ fontWeight: 700, color: m.color }}>{m.label}</div>
                      <div>{m.lat.toFixed(4)}, {m.lon.toFixed(4)}</div>
                      {m.popup && <div style={{ marginTop: 4, color: '#94a3b8' }}>{m.popup}</div>}
                    </div>
                  </Popup>
                </CircleMarker>
              </React.Fragment>
            </LayersControl.Overlay>
          ))}
        </LayersControl>
      </MapContainer>
    </div>
  );
}
