// src/netpulse/MapView.tsx
//
// Real basemap (free CARTO "light_all" raster tiles - no API key), native
// Leaflet zoom/pan/scroll. Draws the exact same per-sector wedge idea as
// the old SVG MapCanvas (colors.ts / geo.ts are direct ports of
// core/utils.py), just on real tiles instead of a flat projection.
//
// One component covers every map in the app:
//   - Planning / Clashes: sites + wedges, colored by layerMode, clickable
//   - Clashes: an optional adjustable "measure" circle around a picked site
//   - Add Site: `pickable` mode - click/drag to choose a new site's
//     lat/lon, with 7km/14km reference rings around the pin

import { useEffect, useMemo, useRef } from 'react';
import { MapContainer, TileLayer, Polygon, CircleMarker, Circle, Marker, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Site, Sector } from './api';
import { colorFor, statusLabel, type LayerMode, regionColorFor, CLASH_TYPE_LABELS, CLASH_TYPE_ORDER, sectorHasType } from './colors';
import { wedgePolygon, safeHalfAngle, bboxOf } from './geo';

const TILE_URL = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

const pinIcon = (color: string) =>
  L.divIcon({
    className: '',
    html: `<div style="width:16px;height:16px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 16],
  });

// Site markers now follow the selected map view. In the region view they
// use the region color; in all other views they stay neutral so the map
// reads as a geographic summary rather than a conflict alert.
function siteMarkerColor(site: Site, isHighlight: boolean, layerMode: LayerMode): string {
  if (isHighlight) return '#F59E0B';
  if (layerMode === 'Regions') return regionColorFor(site.g);
  return '#0F172A';
}

function siteStatusColor(site: Site): string {
  if (site.clash) return '#DC2626';
  if (site.soft) return '#F59E0B';
  return '#0F172A';
}

function siteTypeCounts(site: Site): Record<string, number> {
  const counts: Record<string, number> = {};
  CLASH_TYPE_ORDER.forEach((t) => { counts[t] = 0; });
  site.sec.forEach((sec) => {
    CLASH_TYPE_ORDER.forEach((t) => {
      if (sectorHasType(sec, t)) counts[t] = (counts[t] || 0) + 1;
    });
  });
  return counts;
}

function FitToSites({ sites }: { sites: Site[] }) {
  const map = useMap();
  const signature = useMemo(() => sites.map((s) => s.s).sort().join('|'), [sites]);
  useEffect(() => {
    if (!sites.length) return;
    const box = bboxOf(sites.map((s) => [s.y, s.x] as [number, number]));
    if (!box) return;
    map.fitBounds(box.bounds, { padding: [40, 40], maxZoom: 13 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  return null;
}

function FlyTo({ target }: { target: { lat: number; lon: number; zoom?: number } | null | undefined }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lon], target.zoom ?? 14, { duration: 0.6 });
  }, [target?.lat, target?.lon, target?.zoom]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function ClickCatcher({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click(e) { onPick(e.latlng.lat, e.latlng.lng); } });
  return null;
}

export function MapView({
  sites, layerMode, height = 520,
  onSelectSite, onSelectSector, highlightSite,
  circle, focusSite, fitToSites = true,
  pickable = false, pickPosition = null, onPick, referenceRings = false,
  showLabels = false,
  wedgeRadius = 180,
  siteColorMode = 'default',
  showSectorIds = true,
}: {
  sites: Site[];
  layerMode: LayerMode;
  height?: number;
  onSelectSite?: (site: Site) => void;
  onSelectSector?: (site: Site, sector: Sector) => void;
  highlightSite?: string | null;
  circle?: { lat: number; lon: number; radiusKm: number; color?: string } | null;
  focusSite?: { lat: number; lon: number; zoom?: number } | null;
  fitToSites?: boolean;
  pickable?: boolean;
  pickPosition?: [number, number] | null;
  onPick?: (lat: number, lon: number) => void;
  referenceRings?: boolean;
  // Permanent site-id labels above every site marker, matching the
  // Voronoi Compare tab's "real map" view (instead of hover-only info).
  showLabels?: boolean;
  wedgeRadius?: number;
  siteColorMode?: 'default' | 'clash-status';
  showSectorIds?: boolean;
}) {
  const initialCenter: [number, number] = sites.length ? [sites[0].y, sites[0].x] : pickPosition || [27.5, 30.6];

  return (
    <div className="rounded-lg overflow-hidden border border-[var(--color-border)]" style={{ height }}>
      <MapContainer center={initialCenter} zoom={sites.length ? 11 : 6} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
        {fitToSites && !pickable && <FitToSites sites={sites} />}
        {focusSite && <FlyTo target={focusSite} />}
        {pickable && onPick && <ClickCatcher onPick={onPick} />}

        {sites.map((site) => {
          const isHighlight = highlightSite === site.s;
          const markerColor = siteColorMode === 'clash-status'
            ? (isHighlight ? '#F59E0B' : siteStatusColor(site))
            : siteMarkerColor(site, isHighlight, layerMode);
          const labelStyle = siteColorMode === 'clash-status'
            ? {
                background: isHighlight ? '#FEF3C7' : (site.clash ? '#FEE2E2' : site.soft ? '#FEF3C7' : '#FFFFFF'),
                border: isHighlight ? '#F59E0B' : (site.clash ? '#DC2626' : site.soft ? '#F59E0B' : '#0F172A'),
                text: isHighlight ? '#92400E' : (site.clash ? '#B91C1C' : site.soft ? '#92400E' : '#0F172A'),
              }
            : { background: '#FFFFFF', border: '#0F172A', text: '#0F172A' };
          const azimuths = site.sec.map((s) => s.a ?? 0);
          return (
            <div key={site.s}>
              {site.sec.map((sec, idx) => {
                const others = azimuths.filter((_, j) => j !== idx);
                const halfAngle = safeHalfAngle(sec.a ?? 0, others);
                const positions = wedgePolygon(site.y, site.x, sec.a ?? 0, wedgeRadius, halfAngle);
                return (
                  <Polygon
                    key={sec.i}
                    positions={positions}
                    pathOptions={{ color: '#fff', weight: 1, fillColor: colorFor(sec, layerMode, site.g), fillOpacity: 0.78 }}
                    eventHandlers={{
                      click: () => (onSelectSector ? onSelectSector(site, sec) : onSelectSite?.(site)),
                    }}
                  >
                    <Tooltip sticky>
                      <div className="text-xs font-mono">
                        <div className="font-semibold">{site.s} &middot; {site.g}</div>
                        <div>{showSectorIds ? `Sector ${sec.i} · ` : ''}PCI {sec.p ?? '\u2014'} &middot; Mod4 {sec.m ?? '\u2014'} &middot; RSI {sec.r ?? '\u2014'}</div>
                        <div className="opacity-70">{statusLabel(sec)}</div>
                      </div>
                    </Tooltip>
                  </Polygon>
                );
              })}
              <CircleMarker
                center={[site.y, site.x]}
                radius={isHighlight ? 7.5 : 5.5}
                pathOptions={{ color: '#ffffff', weight: 2.6, fillColor: markerColor, fillOpacity: 1 }}
                eventHandlers={{ click: () => onSelectSite?.(site) }}
                zIndexOffset={1000}
              >
                {showLabels ? (
                  <Tooltip permanent direction="top" offset={[0, -6]} className="!font-mono !font-bold !text-[11px] !rounded !shadow" opacity={1}>
                    <span
                      className="inline-block rounded border px-1.5 py-0.5"
                      style={{ background: labelStyle.background, color: labelStyle.text, borderColor: labelStyle.border }}
                    >
                      {site.s}
                    </span>
                  </Tooltip>
                ) : (
                  <Tooltip>
                    <div className="text-xs font-mono">
                      <div className="font-semibold">{site.s} &middot; {site.g}</div>
                      <div>{site.n} sector(s)</div>
                      {Object.entries(siteTypeCounts(site)).filter(([, count]) => count > 0).map(([type, count]) => (
                        <div key={type}>{CLASH_TYPE_LABELS[type]}: {count}</div>
                      ))}
                      {Object.values(siteTypeCounts(site)).every((count) => count === 0) && <div>{CLASH_TYPE_LABELS.clear}</div>}
                    </div>
                  </Tooltip>
                )}
              </CircleMarker>
            </div>
          );
        })}

        {circle && (
          <Circle
            center={[circle.lat, circle.lon]}
            radius={circle.radiusKm * 1000}
            pathOptions={{ color: circle.color || '#33D6B0', fillOpacity: 0.06, weight: 1.5, dashArray: '6 6' }}
          />
        )}

        {pickable && pickPosition && (
          <>
            <Marker
              position={pickPosition}
              icon={pinIcon('#F9A825')}
              draggable
              eventHandlers={{ dragend: (e) => { const ll = (e.target as L.Marker).getLatLng(); onPick?.(ll.lat, ll.lng); } }}
            />
            {referenceRings && (
              <>
                <Circle center={pickPosition} radius={7000} pathOptions={{ color: '#D32F2F', dashArray: '6 6', weight: 1.3, fillOpacity: 0 }} />
                <Circle center={pickPosition} radius={14000} pathOptions={{ color: '#7C3AED', dashArray: '2 8', weight: 1, fillOpacity: 0 }} />
              </>
            )}
          </>
        )}
      </MapContainer>
    </div>
  );
}