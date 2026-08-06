// src/netpulse/ClashesView.tsx - mirrors views/clashes_view.py
//
// Real map + a measuring circle around any clicked site + a "what is
// this clash?" tool + the sector-level Explainer (moved here from the
// AI Agent tab - it's a Clashes-tab feature, not an agent feature: pick
// any sector directly by ID and see its full PCI/Mod4/RSI/Mod3 picture
// and every hard/soft conflict, with no model involved at all).
import { useEffect, useMemo, useState } from 'react';
import { Ruler, Info, ChevronDown, ChevronUp, AlertOctagon, Shield, Radio, Network as NetworkIcon, Layers, CheckCircle, Search, XCircle } from 'lucide-react';
import { api, type NetworkData, type Site, type Sector, type ClashDefinition } from './api';
import { Card, PageHeader, LoadingBlock, ErrorBlock } from './ui';
import { MapView } from './MapView';
import { Legend } from './Legend';
import { statusLabel, haversineKm, CLASH_TYPE_COLORS, CLASH_TYPE_LABELS, CLASH_TYPE_ORDER, sectorHasType, type LayerMode } from './colors';

const REGION_NAMES: Record<string, string> = { ALX: 'Alexandria', SIN: 'Sinai', UPP: 'Upper Egypt', DEL: 'Delta' };
const TYPE_LABELS = CLASH_TYPE_LABELS;
const TYPE_ICON: Record<string, any> = {
  clear: CheckCircle,
  collision: AlertOctagon,
  confusion: Shield,
  rsi: NetworkIcon,
  mod3: Layers,
  mod4_intra: Layers,
  mod4: Radio,
  mod3_non_adj: Layers,
  mod4_non_adj: Radio,
};

function ClashDefCard({ type, def }: { type: string; def: ClashDefinition }) {
  const hard = def.severity.startsWith('hard');
  const Icon = TYPE_ICON[type] || Info;
  const color = CLASH_TYPE_COLORS[type] || '#64748B';
  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: hard ? '#FCA5A5' : '#FDE68A', background: hard ? 'linear-gradient(135deg,#FEF2F2,#FFF)' : 'linear-gradient(135deg,#FFFBEB,#FFF)' }}
    >
      <div className="flex items-start gap-3 p-3">
        <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 shadow-sm" style={{ background: color }}>
          <Icon className="w-4.5 h-4.5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-[var(--color-text)]">{def.label}</span>
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0"
              style={{ background: hard ? '#FEE2E2' : '#FEF3C7', color: hard ? '#B91C1C' : '#92400E' }}
            >
              {def.severity}
            </span>
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5 font-mono">{def.threshold}</div>
          <p className="text-xs text-gray-700 mt-1.5 leading-relaxed">{def.rule}</p>
        </div>
      </div>
    </div>
  );
}

function TypeDistributionBar({ counts, total }: { counts: Record<string, number>; total: number }) {
  const order = [...CLASH_TYPE_ORDER];
  if (!total) return null;
  return (
    <div className="mb-4">
      <div className="grid gap-1.5 mt-2 sm:grid-cols-2 xl:grid-cols-3">
        {order.map((t) => {
          const Icon = TYPE_ICON[t];
          const count = counts[t] || 0;
          const active = count > 0;
          return (
            <div
              key={t}
              className={`flex items-center justify-between rounded-lg border px-2.5 py-1.5 text-[11px] ${active ? 'bg-white' : 'bg-slate-50'}`}
              style={{ borderColor: active ? `${CLASH_TYPE_COLORS[t]}66` : '#E2E8F0' }}
              title={`${TYPE_LABELS[t]}: ${count}`}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <Icon className="w-3 h-3 shrink-0" style={{ color: CLASH_TYPE_COLORS[t] }} />
                <span className={`${active ? 'text-gray-700' : 'text-gray-400'} truncate`}>{TYPE_LABELS[t] || t}</span>
              </div>
              <span className={`font-semibold ${active ? 'text-gray-700' : 'text-gray-400'}`}>{count.toLocaleString()}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- sector explainer, redesigned: search-style picker + a clean fact
// card instead of a raw JSON dump front-and-center ---
function SectorExplainer({ workbook }: { workbook: string }) {
  const [sectorId, setSectorId] = useState('');
  const [query, setQuery] = useState('');
  const [sectors, setSectors] = useState<{ id: string }[]>([]);
  const [explanation, setExplanation] = useState<any>(null);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.sectors(workbook).then((rows) => setSectors(rows.map((r) => ({ id: r.id })))).catch(() => {});
  }, [workbook]);

  const matches = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.trim().toUpperCase();
    return sectors.filter((s) => s.id.toUpperCase().includes(q)).slice(0, 8);
  }, [query, sectors]);

  const pick = async (id: string) => {
    setSectorId(id);
    setQuery(id);
    setExplainError(null);
    setLoading(true);
    try { setExplanation(await api.explain(id, workbook)); }
    catch (e) { setExplainError(String(e)); }
    finally { setLoading(false); }
  };

  const FIELD_META: Record<string, { label: string; color: string }> = {
    pci: { label: 'PCI', color: '#1565C0' }, mod4: { label: 'Mod4', color: '#00ACC1' },
    rsi: { label: 'RSI', color: '#7C3AED' }, mod3: { label: 'Mod3', color: '#F9A825' },
  };

  const HARD_ITEMS = [
    { key: 'pci_collision', label: 'PCI collision (7km, hard)' },
    { key: 'pci_confusion', label: 'PCI confusion (14km, hard)' },
    { key: 'rsi_reuse', label: 'RSI reuse (14km, hard)' },
    { key: 'mod3_adjacent', label: 'Mod3 adjacent (hard)' },
    { key: 'mod4_intra_site', label: 'Mod4 intra-site (hard)' },
  ] as const;

  const SOFT_ITEMS = [
    { key: 'mod4_inter_site', label: 'Mod4 inter-site (soft)' },
    { key: 'mod3_non_adj', label: 'Mod3 non-adj reuse (soft)' },
    { key: 'mod4_non_adj', label: 'Mod4 non-adj intra-site (soft)' },
  ] as const;

  const formatSource = (item: any) => {
    const id = item?.neighbor || item?.sibling || item?.site || 'unknown';
    const dist = item?.distance_m != null ? ` · ${(item.distance_m / 1000).toFixed(1)}km` : '';
    return `${id}${dist}`;
  };

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-gray-400" />
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setExplanation(null); }}
          placeholder="Search a sector, e.g. ALX3282-1"
          className="w-full pl-8 pr-3 py-2 text-sm border border-[var(--color-border)] rounded-full focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {matches.length > 0 && !sectorId && (
          <div className="absolute z-10 mt-1 w-full bg-white border border-[var(--color-border)] rounded-lg shadow-lg max-h-44 overflow-auto">
            {matches.map((s) => (
              <button key={s.id} onClick={() => pick(s.id)} className="w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-primary/5">{s.id}</button>
            ))}
          </div>
        )}
      </div>

      {loading && <LoadingBlock label="Explaining this sector..." />}
      {explainError && <ErrorBlock message={explainError} />}

      {explanation && !explanation.error && (
        <div className="space-y-3">
          <div className="grid grid-cols-4 gap-2">
            {Object.entries(FIELD_META).map(([k, meta]) => (
              <div key={k} className="rounded-lg border border-[var(--color-border)] p-2 text-center" style={{ background: `${meta.color}0D` }}>
                <div className="text-[9px] uppercase font-semibold text-gray-400">{meta.label}</div>
                <div className="text-base font-bold" style={{ color: meta.color }}>{explanation.sector[k]}</div>
              </div>
            ))}
          </div>

          <div className={`flex items-center gap-2 text-xs font-medium rounded-lg p-2.5 ${explanation.clean ? 'bg-green-50 text-[var(--color-success)]' : 'bg-red-50 text-[var(--color-critical)]'}`}>
            {explanation.clean ? <CheckCircle className="w-4 h-4 shrink-0" /> : <XCircle className="w-4 h-4 shrink-0" />}
            {explanation.clean ? 'No hard-rule violations on this sector.' : 'Hard-rule conflict(s) found on this sector.'}
          </div>

          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-red-700">Hard KPI clashes (why + from what)</div>
            {HARD_ITEMS.map((entry) => {
              const items = explanation.hard?.[entry.key] as any[] | undefined;
              if (!items?.length) return null;
              return (
                <div key={entry.key} className="text-xs bg-red-50/60 border border-red-100 rounded-lg p-2.5">
                  <div className="font-semibold text-red-700 mb-1">{entry.label}</div>
                  {items.map((item, idx) => <div key={idx} className="text-gray-600">{formatSource(item)}</div>)}
                </div>
              );
            })}
          </div>

          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Soft KPI clashes (why + from what)</div>
            {SOFT_ITEMS.map((entry) => {
              const items = explanation.soft?.[entry.key] as any[] | undefined;
              if (!items?.length) return null;
              return (
                <div key={entry.key} className="text-xs bg-amber-50/60 border border-amber-100 rounded-lg p-2.5">
                  <div className="font-semibold text-amber-700 mb-1">{entry.label}</div>
                  {items.map((item, idx) => <div key={idx} className="text-gray-600">{formatSource(item)}</div>)}
                </div>
              );
            })}
          </div>

          <button onClick={() => { setSectorId(''); setQuery(''); setExplanation(null); }} className="text-xs text-primary hover:underline">Search another sector</button>
        </div>
      )}
    </div>
  );
}

export function ClashesView({ workbook }: { workbook: string }) {
  const [data, setData] = useState<NetworkData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState('');
  const [types, setTypes] = useState<string[]>(Object.keys(TYPE_LABELS));
  const [colorMode, setColorMode] = useState<'Clash type' | 'Mod4 group' | 'Mod3 group'>('Clash type');
  const [center, setCenter] = useState<Site | null>(null);
  const [radiusKm, setRadiusKm] = useState(7);
  const [rightTab, setRightTab] = useState<'measure' | 'explain'>('measure');
  const [wedgeRadius, setWedgeRadius] = useState(180);

  const [defs, setDefs] = useState<Record<string, ClashDefinition> | null>(null);
  const [selected, setSelected] = useState<{ site: Site; sector: Sector } | null>(null);
  const [liveInfo, setLiveInfo] = useState<any>(null);
  const [loadingInfo, setLoadingInfo] = useState(false);
  const [showAllDefs, setShowAllDefs] = useState(false);

  useEffect(() => {
    setError(null);
    api.network(workbook).then(setData).catch((e) => setError(String(e)));
  }, [workbook]);

  useEffect(() => { api.clashInfo().then(setDefs).catch(() => {}); }, []);

  const layerMode: LayerMode = colorMode === 'Clash type' ? 'Clashes' : colorMode === 'Mod4 group' ? 'Mod4' : 'Mod3';

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.sites
      .filter((s) => !region || s.g === region)
      .map((s) => ({
        ...s,
        sec: s.sec.filter((sec) => types.some((t) => sectorHasType(sec, t))),
      }))
      .filter((s) => s.sec.length > 0);
  }, [data, region, types]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    CLASH_TYPE_ORDER.forEach((t) => { counts[t] = 0; });
    filtered.forEach((s) => s.sec.forEach((sec) => {
      CLASH_TYPE_ORDER.forEach((t) => {
        if (sectorHasType(sec, t)) counts[t] = (counts[t] || 0) + 1;
      });
    }));
    return counts;
  }, [filtered]);
  const totalShown = filtered.reduce((sum, s) => sum + s.sec.length, 0);

  const neighbors = useMemo(() => {
    if (!data || !center) return [];
    return data.sites
      .filter((s) => s.s !== center.s)
      .map((s) => ({ site: s.s, region: s.g, km: haversineKm(center.y, center.x, s.y, s.x) }))
      .filter((n) => n.km <= radiusKm)
      .sort((a, b) => a.km - b.km);
  }, [data, center, radiusKm]);

  const selectedSiteTypeCounts = useMemo(() => {
    if (!center) return null;
    const counts: Record<string, number> = {};
    CLASH_TYPE_ORDER.forEach((t) => { counts[t] = 0; });
    center.sec.forEach((sec) => {
      CLASH_TYPE_ORDER.forEach((t) => {
        if (sectorHasType(sec, t)) counts[t] = (counts[t] || 0) + 1;
      });
    });
    return counts;
  }, [center]);

  const onSelectSector = async (site: Site, sector: Sector) => {
    setCenter(site);
    setSelected({ site, sector });
    setLoadingInfo(true);
    try { setLiveInfo(await api.clashInfoForSector(sector.i, workbook)); }
    catch (e) { setLiveInfo({ error: String(e) }); }
    finally { setLoadingInfo(false); }
  };

  if (error) return <ErrorBlock message={error} />;
  if (!data) return <LoadingBlock label="Loading clash data..." />;

  const activeTypesOnSelected = selected ? CLASH_TYPE_ORDER
    .filter((t) => t !== 'clear')
    .filter((t) => sectorHasType(selected.sector, t))
    : [];

  const TAB_META: { key: typeof rightTab; label: string; icon: any }[] = [
    { key: 'measure', label: 'Measure', icon: Ruler },
    { key: 'explain', label: 'Explainer', icon: Search },
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <PageHeader title="Clashes" subtitle="Click any sector to see why it clashes." />

      <Card className="p-5">
        <div className="flex flex-wrap gap-3 items-center mb-4">
          <select value={region} onChange={(e) => setRegion(e.target.value)} className="text-sm border border-[var(--color-border)] rounded px-3 py-2 bg-white">
            <option value="">All regions</option>
            {Object.entries(REGION_NAMES).map(([code, name]) => <option key={code} value={code}>{code} &middot; {name}</option>)}
          </select>

          <div className="flex flex-wrap gap-1.5">
            {Object.entries(TYPE_LABELS).map(([t, label]) => {
              const Icon = TYPE_ICON[t];
              const active = types.includes(t);
              return (
                <button
                  key={t}
                  onClick={() => setTypes((cur) => cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t])}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all"
                  style={active
                    ? { background: `${CLASH_TYPE_COLORS[t]}1A`, borderColor: CLASH_TYPE_COLORS[t], color: CLASH_TYPE_COLORS[t] }
                    : { background: '#fff', borderColor: 'var(--color-border)', color: '#94A3B8' }}
                >
                  <Icon className="w-3 h-3" />
                  {label}
                </button>
              );
            })}
          </div>

          <div className="flex gap-1.5 ml-auto items-center">
            <label className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5">
              <span className="text-xs text-gray-500">Wedge radius</span>
              <input
                type="range"
                min={120}
                max={4000}
                step={50}
                value={wedgeRadius}
                onChange={(e) => setWedgeRadius(Number(e.target.value))}
                className="w-24 accent-primary"
              />
              <span className="text-xs font-mono text-slate-700">{wedgeRadius}m</span>
            </label>
            <span className="text-xs text-gray-400 self-center mr-1">Colour sectors by:</span>
            {(['Clash type', 'Mod4 group', 'Mod3 group'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setColorMode(m)}
                className={`px-3 py-1.5 rounded text-xs font-medium border ${colorMode === m ? 'bg-primary text-white border-primary' : 'bg-white border-[var(--color-border)] text-gray-600'}`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        <TypeDistributionBar counts={typeCounts} total={totalShown} />
        <p className="text-xs text-gray-500 mb-3">{totalShown.toLocaleString()} sectors shown across {filtered.length.toLocaleString()} sites{region ? ` \u00b7 ${region}` : ''}</p>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4">
          <div className="space-y-3">
            <MapView
              sites={filtered}
              layerMode={layerMode}
              height={520}
              onSelectSector={onSelectSector}
              onSelectSite={setCenter}
              highlightSite={center?.s}
              circle={center ? { lat: center.y, lon: center.x, radiusKm } : null}
              wedgeRadius={wedgeRadius}
              showSectorIds={false}
            />
            <Legend layerMode={layerMode} />
          </div>

          <div>
            <div className="flex gap-1 mb-3 bg-gray-100 rounded-full p-1">
              {TAB_META.map((t) => {
                const Icon = t.icon;
                return (
                  <button
                    key={t.key}
                    onClick={() => setRightTab(t.key)}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-full text-xs font-medium transition-all ${rightTab === t.key ? 'bg-white shadow-sm text-primary' : 'text-gray-500'}`}
                  >
                    <Icon className="w-3.5 h-3.5" /> {t.label}
                  </button>
                );
              })}
            </div>

            {rightTab === 'measure' && (
              <div className="border border-[var(--color-border)] rounded-lg p-4 bg-gradient-to-br from-white to-gray-50">
                {!center ? (
                  <p className="text-xs text-gray-500">Click any site or sector wedge on the map to measure its neighbors.</p>
                ) : (
                  <>
                    <div className="text-sm font-medium mb-2">{center.s} selected</div>
                    <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-white p-2.5">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-1.5">Site clash types</div>
                      <div className="flex flex-wrap gap-1.5">
                        {CLASH_TYPE_ORDER
                          .filter((t) => t !== 'clear')
                          .filter((t) => (selectedSiteTypeCounts?.[t] || 0) > 0)
                          .map((t) => (
                            <span
                              key={t}
                              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]"
                              style={{ borderColor: CLASH_TYPE_COLORS[t], color: CLASH_TYPE_COLORS[t], background: `${CLASH_TYPE_COLORS[t]}14` }}
                            >
                              {TYPE_LABELS[t]}: {selectedSiteTypeCounts?.[t] || 0}
                            </span>
                          ))}
                        {selectedSiteTypeCounts && Object.values(selectedSiteTypeCounts).every((v) => v === 0) && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-green-300 bg-green-50 px-2 py-0.5 text-[11px] text-green-700">
                            {TYPE_LABELS.clear}
                          </span>
                        )}
                      </div>
                    </div>
                    <label className="text-xs text-gray-500">Radius: {radiusKm.toFixed(1)} km</label>
                    <input type="range" min={1} max={20} step={0.5} value={radiusKm} onChange={(e) => setRadiusKm(Number(e.target.value))} className="w-full accent-primary" />
                    <p className="text-[11px] text-gray-400 mt-1 mb-3">7 km = Mod4/PCI collision range &middot; 14 km = RSI/confusion range</p>
                    <p className="text-xs text-gray-500 mb-2">{neighbors.length} site(s) within {radiusKm.toFixed(1)} km</p>
                    <div className="max-h-56 overflow-auto space-y-1">
                      {neighbors.map((n) => (
                        <div key={n.site} className="flex justify-between text-xs border-b border-gray-100 py-1">
                          <span>{n.site} <span className="text-gray-400">({n.region})</span></span>
                          <span className="font-mono">{n.km.toFixed(2)} km</span>
                        </div>
                      ))}
                    </div>
                    <button onClick={() => { setCenter(null); setSelected(null); setLiveInfo(null); }} className="mt-3 text-xs text-primary hover:underline">Clear selection</button>
                  </>
                )}
              </div>
            )}

            {rightTab === 'explain' && (
              <div className="border border-[var(--color-border)] rounded-lg p-4 bg-gradient-to-br from-white to-gray-50">
                <SectorExplainer workbook={workbook} />
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 border border-[var(--color-border)] rounded-lg p-4 bg-gradient-to-br from-white to-gray-50">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Info className="w-4 h-4 text-primary" /> Clash Inspector
            </div>
            {selected && <div className="text-xs text-gray-500">{selected.site.s} &middot; {statusLabel(selected.sector)}</div>}
          </div>

          {!selected ? (
            <p className="text-xs text-gray-500 mb-2">Click any sector wedge on the map to inspect its clash profile.</p>
          ) : loadingInfo ? (
            <LoadingBlock label="Inspecting selected sector..." />
          ) : (
            <div className="space-y-3 mb-3">
              <div className="flex flex-wrap gap-1.5">
                {activeTypesOnSelected.length === 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-green-300 bg-green-50 px-2 py-0.5 text-[11px] text-green-700">
                    <CheckCircle className="w-3 h-3" /> Clear
                  </span>
                )}
                {activeTypesOnSelected.map((t) => (
                  <span key={t} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]" style={{ borderColor: CLASH_TYPE_COLORS[t], color: CLASH_TYPE_COLORS[t], background: `${CLASH_TYPE_COLORS[t]}14` }}>
                    {TYPE_LABELS[t]}
                  </span>
                ))}
              </div>

              {defs && activeTypesOnSelected.filter((t) => !!defs[t]).map((t) => <ClashDefCard key={t} type={t} def={defs[t]} />)}

              {liveInfo?.live_explanation && !liveInfo.live_explanation.error && (
                <div className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-1">
                  <div className="font-semibold text-gray-600 mb-1">Live causes for this sector</div>
                  {liveInfo.live_explanation.hard?.pci_collision?.length > 0 && (
                    <div>PCI collision with: {liveInfo.live_explanation.hard.pci_collision.map((c: any) => `${c.neighbor} (${(c.distance_m / 1000).toFixed(1)}km)`).join(', ')}</div>
                  )}
                  {liveInfo.live_explanation.hard?.pci_confusion?.length > 0 && (
                    <div>PCI confusion with: {liveInfo.live_explanation.hard.pci_confusion.map((c: any) => `${c.neighbor} (${(c.distance_m / 1000).toFixed(1)}km)`).join(', ')}</div>
                  )}
                  {liveInfo.live_explanation.soft?.mod4_clash?.length > 0 && (
                    <div>Mod4 inter-site with: {liveInfo.live_explanation.soft.mod4_clash.slice(0, 5).map((c: any) => `${c.neighbor} (${(c.distance_m / 1000).toFixed(1)}km)`).join(', ')}{liveInfo.live_explanation.soft.mod4_clash.length > 5 ? ` +${liveInfo.live_explanation.soft.mod4_clash.length - 5} more` : ''}</div>
                  )}
                  {(liveInfo.live_explanation.hard?.rsi_reuse?.length > 0 || liveInfo.live_explanation.soft?.rsi_reuse?.length > 0) && (
                    <div>RSI reuse with: {(liveInfo.live_explanation.hard?.rsi_reuse || liveInfo.live_explanation.soft?.rsi_reuse).slice(0, 5).map((c: any) => `${c.neighbor} (${(c.distance_m / 1000).toFixed(1)}km)`).join(', ')}</div>
                  )}
                </div>
              )}
            </div>
          )}

          <button onClick={() => setShowAllDefs((v) => !v)} className="flex items-center gap-1 text-xs text-primary hover:underline">
            {showAllDefs ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showAllDefs ? 'Hide full clash reference' : 'Show full clash reference'}
          </button>
          {showAllDefs && defs && (
            <div className="space-y-2 mt-3">
              {Object.entries(defs).filter(([k]) => k !== 'clear').map(([k, d]) => <ClashDefCard key={k} type={k} def={d} />)}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}