// src/netpulse/VoronoiCompareView.tsx
//
// Two ways to view the same before/after comparison:
//   - "Diagram" - abstract Voronoi diagram: one badge label per SITE at
//     its hub dot, plus a small ID tag on every individual sector cell.
//     Cell borders are white by default; wherever two REAL Voronoi-
//     adjacent cells belong to different sites AND share the same Mod4
//     value, that shared border is drawn in red instead. Adjacency is
//     detected directly from final cell geometry (see voronoi.ts's
//     cellAdjacencies) rather than clip-order bookkeeping, so a clash
//     boundary can't be silently dropped just because a third site's
//     cell cuts across it partway along.
//   - "Real map" - actual sector wedges on a real basemap at true
//     lat/lon, colored by Mod4. A clash reads purely from two same-
//     color wedges visually overlapping once the wedge-size slider is
//     large enough - no connecting lines here either.
//
// Both panels only ever draw sectors that carry a PCI - unplanned or
// missing rows are simply left out with a note, never an error.

import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Polygon as LeafletPolygon, CircleMarker, Tooltip as LeafletTooltip, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { UploadCloud, FileSpreadsheet, GitBranch, AlertTriangle, LayoutGrid, Map as MapIcon, Tag } from 'lucide-react';
import { api, type RawSectorRow } from './api';
import { Card, PageHeader, PrimaryButton, LoadingBlock, ErrorBlock } from './ui';
import { haversineKm } from './colors';
import { wedgePolygon, safeHalfAngle, bboxOf } from './geo';
import { project, boundedVoronoi, centroid, cellAdjacencies, type Pt } from './voronoi';

const MOD4_COLOR: Record<number, string> = { 0: '#0FBF8F', 1: '#4C6FFF', 2: '#FF9A2E', 3: '#FF4040' };
const BG = '#0A0E12';
const PANEL_BG = '#11171E';
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const TILE_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; CARTO';
const DOT = '\u00B7';

type Seed = { id: string; site: string; mod4: number; x: number; y: number };
type Bbox = { minX: number; minY: number; maxX: number; maxY: number };

function NoWorkbookVoronoiState({ navigate }: { navigate: (v: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center space-y-4 py-20">
      <UploadCloud className="w-10 h-10 text-gray-400" />
      <h3 className="text-lg font-semibold text-[var(--color-text)]">No workbook loaded yet</h3>
      <p className="text-sm text-gray-500 max-w-sm">Go to Upload &amp; Plan and upload a raw or already-planned .xlsx file to get started.</p>
      <button
        onClick={() => navigate('np-upload')}
        className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded text-sm font-medium hover:opacity-90 shadow-sm"
      >
        <UploadCloud className="w-4 h-4" /> Go to Upload &amp; Plan
      </button>
    </div>
  );
}

function buildSeeds(sectors: RawSectorRow[], lat0: number, lon0: number): { seeds: Seed[]; hubs: Map<string, Pt> } {
  const siteXY = new Map<string, Pt>();
  sectors.forEach((s) => { if (!siteXY.has(s.site)) siteXY.set(s.site, project(s.lat, s.lon, lat0, lon0)); });
  const pts = Array.from(siteXY.values());
  let spacing = 1000;
  if (pts.length > 1) {
    const gaps = pts.map((p, i) => Math.min(...pts.filter((_, j) => j !== i).map((q) => Math.hypot(p[0] - q[0], p[1] - q[1]))));
    gaps.sort((a, b) => a - b);
    spacing = gaps[Math.floor(gaps.length / 2)];
  }
  const offset = Math.max(120, Math.min(900, 0.34 * spacing));
  const seeds = sectors.map((s) => {
    const [x, y] = siteXY.get(s.site)!;
    const az = ((s.az || 0) * Math.PI) / 180;
    return { id: s.id, site: s.site, mod4: s.mod4 as number, x: x + offset * Math.sin(az), y: y + offset * Math.cos(az) };
  });
  return { seeds, hubs: siteXY };
}

// Genuine clash edges: real Voronoi-adjacent cells (see voronoi.ts's
// cellAdjacencies), different site, same Mod4. Returns world-space
// segments directly - ready to project into SVG or just count.
function findClashEdges(seeds: Seed[], cells: Map<string, Pt[]>): [Pt, Pt][] {
  const adjacencies = cellAdjacencies(seeds, cells);
  const seedById = new Map(seeds.map((s) => [s.id, s]));
  const segs: [Pt, Pt][] = [];
  adjacencies.forEach((e) => {
    const sa = seedById.get(e.a), sb = seedById.get(e.b);
    if (sa && sb && sa.site !== sb.site && sa.mod4 === sb.mod4) segs.push(e.seg);
  });
  return segs;
}

function worldToSvg(bbox: Bbox, size: number) {
  const w = bbox.maxX - bbox.minX || 1;
  const h = bbox.maxY - bbox.minY || 1;
  const scale = size / Math.max(w, h);
  const offX = (size - w * scale) / 2;
  const offY = (size - h * scale) / 2;
  return (p: Pt): Pt => [offX + (p[0] - bbox.minX) * scale, offY + (bbox.maxY - p[1]) * scale];
}

// ---------------------------------------------------------------------
// Diagram mode
// ---------------------------------------------------------------------
function DiagramPanel({
  badge, subtitle, sectors, missingSites, sharedBbox, sharedLat0Lon0,
}: {
  badge: string; subtitle: string; sectors: RawSectorRow[]; missingSites: string[];
  sharedBbox: Bbox; sharedLat0Lon0: [number, number];
}) {
  const SIZE = 480;
  const [lat0, lon0] = sharedLat0Lon0;

  const geo = useMemo(() => {
    if (!sectors.length) return null;
    const { seeds, hubs } = buildSeeds(sectors, lat0, lon0);
    const { cells } = boundedVoronoi(seeds, sharedBbox);
    const toSvg = worldToSvg(sharedBbox, SIZE);

    const cellSvg = new Map<string, Pt[]>();
    cells.forEach((poly, id) => cellSvg.set(id, poly.map(toSvg)));

    const redEdges: [Pt, Pt][] = findClashEdges(seeds, cells).map(([p1, p2]) => [toSvg(p1), toSvg(p2)]);

    const hubLabels: { site: string; p: Pt }[] = [];
    hubs.forEach((xy, site) => hubLabels.push({ site, p: toSvg(xy) }));

    const sectorLabels: { id: string; p: Pt }[] = seeds.map((s) => {
      const poly = cellSvg.get(s.id);
      const c = poly && poly.length ? centroid(poly) : toSvg([s.x, s.y]);
      return { id: s.id, p: c };
    });

    return { seeds, cellSvg, redEdges, hubLabels, sectorLabels };
  }, [sectors, sharedBbox, lat0, lon0]);

  return (
    <div className="rounded-xl overflow-hidden border border-white/10" style={{ background: BG }}>
      <div className="px-4 py-3 text-center">
        <span className="inline-block px-3 py-1 rounded-full text-white font-mono font-bold text-xs tracking-wide" style={{ background: badge === 'BEFORE' ? '#3A4753' : 'linear-gradient(90deg,#1565C0,#00ACC1)' }}>
          {badge} {DOT} {badge === 'BEFORE' ? 'old planning' : 'current planning'}
        </span>
        <div className="text-slate-500 text-[11px] mt-1.5 truncate px-2">{subtitle}</div>
      </div>

      {geo ? (
        <div className="px-3 pb-3">
          <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full rounded-lg" style={{ background: PANEL_BG, border: '1px solid #26313C' }}>
            {geo.seeds.map((s) => {
              const poly = geo.cellSvg.get(s.id);
              if (!poly || !poly.length) return null;
              return (
                <polygon
                  key={s.id}
                  points={poly.map((p) => p.join(',')).join(' ')}
                  fill={MOD4_COLOR[s.mod4] ?? '#3A4753'}
                  fillOpacity={0.94}
                  stroke="#fff"
                  strokeWidth={1.6}
                />
              );
            })}

            {/* clash borders drawn on top of the plain white cell edges,
                exactly where two real Voronoi-adjacent different-site
                cells share a Mod4 value */}
            {geo.redEdges.map((seg, i) => (
              <line key={`r-${i}`} x1={seg[0][0]} y1={seg[0][1]} x2={seg[1][0]} y2={seg[1][1]} stroke="#FF1E1E" strokeWidth={5} strokeLinecap="round" />
            ))}

            {geo.sectorLabels.map((l) => {
              const w = Math.max(30, l.id.length * 5.6 + 8);
              return (
                <g key={l.id} opacity={0.92}>
                  <rect x={l.p[0] - w / 2} y={l.p[1] - 8} width={w} height={14} rx={3} fill="#0A0E12" fillOpacity={0.72} />
                  <text x={l.p[0]} y={l.p[1] + 2.5} textAnchor="middle" fontSize={8.5} fontFamily="monospace" fill="#fff">
                    {l.id}
                  </text>
                </g>
              );
            })}

            {geo.hubLabels.map((h) => {
              const w = Math.max(52, h.site.length * 8.5 + 16);
              return (
                <g key={h.site}>
                  <circle cx={h.p[0]} cy={h.p[1]} r={6} fill="#fff" stroke="#0A0E12" strokeWidth={2} />
                  <rect x={h.p[0] - w / 2} y={h.p[1] - 32} width={w} height={22} rx={5} fill="#fff" stroke="#0A0E12" strokeWidth={1.3} />
                  <text x={h.p[0]} y={h.p[1] - 17} textAnchor="middle" fontSize={12} fontFamily="monospace" fontWeight="bold" fill="#0A0E12">
                    {h.site}
                  </text>
                  <line x1={h.p[0]} y1={h.p[1] - 10} x2={h.p[0]} y2={h.p[1] - 5} stroke="#0A0E12" strokeWidth={1.3} />
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div className="h-[300px] flex items-center justify-center text-sm text-slate-500 px-6 text-center">No planned sectors found here yet.</div>
      )}

      {missingSites.length > 0 && (
        <div className="px-4 py-2 bg-amber-500/10 border-t border-amber-500/20 text-[11px] text-amber-300 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> Not planned yet: {missingSites.join(', ')}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
// Real map mode
// ---------------------------------------------------------------------
function FitToPoints({ points }: { points: [number, number][] }) {
  const map = useMap();
  const sig = points.map((p) => p.join(',')).join('|');
  useEffect(() => {
    if (!points.length) return;
    const box = bboxOf(points);
    if (box) map.fitBounds(box.bounds, { padding: [50, 50], maxZoom: 16 });
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function MapPanel({
  badge, subtitle, sectors, missingSites, wedgeRadius, showLabels,
}: {
  badge: string; subtitle: string; sectors: RawSectorRow[]; missingSites: string[];
  wedgeRadius: number; showLabels: boolean;
}) {
  const sitesById = useMemo(() => {
    const bySite = new Map<string, RawSectorRow[]>();
    sectors.forEach((s) => { const arr = bySite.get(s.site) || []; arr.push(s); bySite.set(s.site, arr); });
    return bySite;
  }, [sectors]);

  const allPoints: [number, number][] = sectors.map((s) => [s.lat, s.lon]);

  return (
    <div className="rounded-xl overflow-hidden border border-[var(--color-border)]">
      <div className="bg-[#111827] px-4 py-2.5 flex items-center gap-2">
        <span className="inline-block px-2.5 py-0.5 rounded-full text-white text-[11px] font-mono font-bold" style={{ background: badge === 'Before' ? '#3A4753' : 'linear-gradient(90deg,#1565C0,#00ACC1)' }}>
          {badge}
        </span>
        <span className="text-[11px] text-slate-400 truncate">{subtitle}</span>
      </div>
      {sectors.length ? (
        <div style={{ height: 440 }}>
          <MapContainer center={allPoints[0] || [27.5, 30.6]} zoom={13} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
            <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
            <FitToPoints points={allPoints} />

            {Array.from(sitesById.entries()).map(([site, secs]) => {
              const azimuths = secs.map((s) => s.az || 0);
              return (
                <div key={site}>
                  {secs.map((s, idx) => {
                    const others = azimuths.filter((_, j) => j !== idx);
                    const halfAngle = safeHalfAngle(s.az || 0, others, 34);
                    const positions = wedgePolygon(s.lat, s.lon, s.az || 0, wedgeRadius, halfAngle);
                    return (
                      <LeafletPolygon
                        key={s.id}
                        positions={positions}
                        pathOptions={{ color: '#fff', weight: 1, fillColor: MOD4_COLOR[s.mod4 as number] ?? '#94A3B8', fillOpacity: 0.55 }}
                      >
                        <LeafletTooltip sticky>
                          <div className="text-xs font-mono">{s.id} &middot; Mod4 {s.mod4}</div>
                        </LeafletTooltip>
                      </LeafletPolygon>
                    );
                  })}
                  <CircleMarker center={[secs[0].lat, secs[0].lon]} radius={4} pathOptions={{ color: '#fff', weight: 1.4, fillColor: '#0F172A', fillOpacity: 1 }}>
                    {showLabels ? (
                      <LeafletTooltip key={`perm-${site}`} permanent direction="top" offset={[0, -6]} className="!bg-white !text-[#0F172A] !font-mono !font-bold !text-[11px] !border !border-[#0F172A] !px-1.5 !py-0.5 !rounded !shadow">
                        {site}
                      </LeafletTooltip>
                    ) : (
                      <LeafletTooltip key={`hover-${site}`}>{site}</LeafletTooltip>
                    )}
                  </CircleMarker>
                </div>
              );
            })}
          </MapContainer>
        </div>
      ) : (
        <div className="h-[440px] flex items-center justify-center text-sm text-gray-400 px-6 text-center">No planned sectors found here yet.</div>
      )}
      {missingSites.length > 0 && (
        <div className="px-4 py-2 bg-amber-50 border-t border-amber-200 text-[11px] text-amber-700 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> Not planned yet: {missingSites.join(', ')}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
export function VoronoiCompareView({ workbook, navigate }: { workbook: string; navigate: (v: string) => void }) {
  const [newSectors, setNewSectors] = useState<RawSectorRow[] | null>(null);
  const [oldSectors, setOldSectors] = useState<RawSectorRow[] | null>(null);
  const [oldLabel, setOldLabel] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'diagram' | 'map'>('diagram');

  const [wedgeRadius, setWedgeRadius] = useState(300);
  const [showLabels, setShowLabels] = useState(true);

  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const [targetSite, setTargetSite] = useState('');
  const [nNeighbors, setNNeighbors] = useState(4);

  useEffect(() => {
    if (!workbook) return;
    api.sectorsRaw(workbook).then(setNewSectors).catch((e) => setError(String(e)));
  }, [workbook]);

  const onUploadOld = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      // Old workbook may be either raw (needs planning) or already planned.
      // Try raw endpoint first, then fall back to final endpoint.
      let out: { workbook: string; label: string };
      try {
        out = await api.upload(file);
      } catch {
        out = await api.uploadFinal(file);
      }
      setOldLabel(out.label);
      setOldSectors(await api.sectorsRaw(out.workbook));
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
    }
  };

  const allSites = useMemo(() => {
    if (!newSectors) return [];
    return Array.from(new Set(newSectors.map((s) => s.site))).sort();
  }, [newSectors]);

  const siteCoord = useMemo(() => {
    const m = new Map<string, { lat: number; lon: number }>();
    (newSectors || []).forEach((s) => { if (!m.has(s.site)) m.set(s.site, { lat: s.lat, lon: s.lon }); });
    return m;
  }, [newSectors]);

  const cluster = useMemo(() => {
    if (!targetSite || !siteCoord.has(targetSite)) return [];
    const t = siteCoord.get(targetSite)!;
    const others = allSites
      .filter((s) => s !== targetSite)
      .map((s) => ({ s, km: haversineKm(t.lat, t.lon, siteCoord.get(s)!.lat, siteCoord.get(s)!.lon) }))
      .sort((a, b) => a.km - b.km)
      .slice(0, nNeighbors)
      .map((x) => x.s);
    return [targetSite, ...others];
  }, [targetSite, allSites, siteCoord, nNeighbors]);

  const buildPanelData = (sectors: RawSectorRow[] | null) => {
    if (!sectors || !cluster.length) return { sectors: [] as RawSectorRow[], missing: [] as string[] };
    const clusterSet = new Set(cluster);
    const planned = sectors.filter((s) => clusterSet.has(s.site) && s.pci != null && s.mod4 != null);
    const present = new Set(planned.map((s) => s.site));
    return { sectors: planned, missing: cluster.filter((s) => !present.has(s)) };
  };

  const before = useMemo(() => buildPanelData(oldSectors), [oldSectors, cluster]);
  const after = useMemo(() => buildPanelData(newSectors), [newSectors, cluster]);

  const frame = useMemo(() => {
    if (!after.sectors.length) return null;
    const lat0 = after.sectors.reduce((a, s) => a + s.lat, 0) / after.sectors.length;
    const lon0 = after.sectors.reduce((a, s) => a + s.lon, 0) / after.sectors.length;
    const { seeds } = buildSeeds(after.sectors, lat0, lon0);
    const xs = seeds.map((s) => s.x), ys = seeds.map((s) => s.y);
    const spanX = Math.max(...xs) - Math.min(...xs) || 500;
    const spanY = Math.max(...ys) - Math.min(...ys) || 500;
    const pad = Math.max(spanX, spanY) * 0.35 + 220;
    const bbox: Bbox = { minX: Math.min(...xs) - pad, minY: Math.min(...ys) - pad, maxX: Math.max(...xs) + pad, maxY: Math.max(...ys) + pad };
    return { lat0, lon0, bbox };
  }, [after.sectors]);

  // Clash counts computed directly (not via a render callback), using
  // the same shared frame both diagrams render against, so the badge
  // always matches what's actually drawn in either view mode.
  const clashCount = (sectors: RawSectorRow[]) => {
    if (!frame || !sectors.length) return 0;
    const { seeds } = buildSeeds(sectors, frame.lat0, frame.lon0);
    const { cells } = boundedVoronoi(seeds, frame.bbox);
    return findClashEdges(seeds, cells).length;
  };
  const beforeCount = useMemo(() => clashCount(before.sectors), [before.sectors, frame]);
  const afterCount = useMemo(() => clashCount(after.sectors), [after.sectors, frame]);

  const verdict = !before.sectors.length
    ? null
    : afterCount === 0 && beforeCount > 0
    ? { label: 'FULLY SOLVED', color: '#0FBF8F' }
    : afterCount < beforeCount
    ? { label: 'IMPROVED', color: '#0FBF8F' }
    : afterCount === beforeCount
    ? { label: 'UNCHANGED', color: '#94A3B8' }
    : { label: 'REGRESSED', color: '#FF4040' };

  if (!workbook) return <NoWorkbookVoronoiState navigate={navigate} />;
  if (error) return <ErrorBlock message={error} />;
  if (!newSectors) return <LoadingBlock label="Loading current network..." />;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <PageHeader title="Voronoi Compare" subtitle="Upload an older plan and see a clear before/after coverage comparison for any site cluster." />

      <Card className="p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">1</div>
          <div className="font-semibold text-sm">Upload the old workbook</div>
        </div>
        <div
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) setFile(f); }}
          className="border-2 border-dashed border-[var(--color-border)] rounded-xl p-8 text-center cursor-pointer hover:border-primary hover:bg-primary/5 transition-all"
        >
          <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <UploadCloud className="w-7 h-7 mx-auto text-gray-400 mb-2" />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-sm font-medium">
              <FileSpreadsheet className="w-4 h-4 text-primary" /> {file.name}
            </div>
          ) : (
            <div className="text-sm text-gray-500">Click to choose the old .xlsx, or drop it here</div>
          )}
        </div>
        <PrimaryButton onClick={onUploadOld} disabled={!file || uploading}>
          {uploading ? 'Uploading...' : 'Load old workbook'}
        </PrimaryButton>
        {oldLabel && <div className="text-sm text-[var(--color-success)]">Loaded: {oldLabel}</div>}
      </Card>

      <Card className="p-6 space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">2</div>
          <div className="font-semibold text-sm">Pick a site to compare</div>
        </div>
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Site</label>
            <select value={targetSite} onChange={(e) => setTargetSite(e.target.value)} className="border border-[var(--color-border)] rounded px-3 py-2 text-sm bg-white min-w-[220px]">
              <option value="">Select a site...</option>
              {allSites.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Nearby sites: {nNeighbors}</label>
            <input type="range" min={1} max={10} value={nNeighbors} onChange={(e) => setNNeighbors(Number(e.target.value))} className="w-48 accent-primary" />
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-full p-1 ml-auto">
            <button
              onClick={() => setViewMode('diagram')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${viewMode === 'diagram' ? 'bg-white shadow-sm text-primary' : 'text-gray-500'}`}
            >
              <LayoutGrid className="w-3.5 h-3.5" /> Diagram
            </button>
            <button
              onClick={() => setViewMode('map')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${viewMode === 'map' ? 'bg-white shadow-sm text-primary' : 'text-gray-500'}`}
            >
              <MapIcon className="w-3.5 h-3.5" /> Real map
            </button>
          </div>
        </div>

        {viewMode === 'map' && (
          <div className="flex flex-wrap items-center gap-5 pt-3 border-t border-[var(--color-border)]">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Wedge size</span>
              <input type="range" min={60} max={1200} step={20} value={wedgeRadius} onChange={(e) => setWedgeRadius(Number(e.target.value))} className="w-44 accent-primary" />
              <span className="text-xs font-mono text-gray-400 w-14">{wedgeRadius}m</span>
            </div>
            <button
              type="button"
              onClick={() => setShowLabels((v) => !v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${showLabels ? 'bg-primary/10 border-primary text-primary' : 'bg-white border-[var(--color-border)] text-gray-500'}`}
            >
              <Tag className="w-3.5 h-3.5" /> Site labels {showLabels ? 'on' : 'off'}
            </button>
            <span className="text-[11px] text-gray-400">Tip: increase wedge size until clashing (same-color) wedges visibly overlap.</span>
          </div>
        )}
      </Card>

      {targetSite && frame && (
        <Card className="p-6 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <h3 className="font-semibold flex items-center gap-2"><GitBranch className="w-4 h-4 text-primary" /> {cluster.join(', ')}</h3>
            {verdict && (
              <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold" style={{ background: `${verdict.color}1A`, color: verdict.color }}>
                {verdict.label} {DOT} {beforeCount} &rarr; {afterCount} clash boundaries
              </span>
            )}
          </div>

          {viewMode === 'diagram' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DiagramPanel
                badge="BEFORE" subtitle={oldLabel || 'No file uploaded yet'}
                sectors={before.sectors} missingSites={before.missing}
                sharedBbox={frame.bbox} sharedLat0Lon0={[frame.lat0, frame.lon0]}
              />
              <DiagramPanel
                badge="AFTER" subtitle={`Active workbook: ${workbook}`}
                sectors={after.sectors} missingSites={after.missing}
                sharedBbox={frame.bbox} sharedLat0Lon0={[frame.lat0, frame.lon0]}
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MapPanel
                badge="Before" subtitle={oldLabel || 'No file uploaded yet'}
                sectors={before.sectors} missingSites={before.missing}
                wedgeRadius={wedgeRadius} showLabels={showLabels}
              />
              <MapPanel
                badge="After" subtitle={`Active workbook: ${workbook}`}
                sectors={after.sectors} missingSites={after.missing}
                wedgeRadius={wedgeRadius} showLabels={showLabels}
              />
            </div>
          )}

          <div className="flex flex-wrap gap-4 items-center justify-center pt-3 border-t border-[var(--color-border)] text-xs text-gray-600">
            {[0, 1, 2, 3].map((m) => (
              <span key={m} className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: MOD4_COLOR[m] }} /> Mod4 group {m}
              </span>
            ))}
            <span className="flex items-center gap-1.5"><span className="w-4 h-1 bg-white border border-gray-300 inline-block rounded" /> Site boundary</span>
            <span className="flex items-center gap-1.5"><span className="w-4 h-1 bg-[#FF1E1E] inline-block rounded" /> Mod4 clash</span>
          </div>
        </Card>
      )}
    </div>
  );
}