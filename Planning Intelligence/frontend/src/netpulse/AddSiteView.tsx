// src/netpulse/AddSiteView.tsx - mirrors views/add_site_view.py
//
// "Add a brand-new site" now picks lat/lon from a real, clickable map
// (draggable pin + 7km/14km reference rings), with number inputs to
// fine-tune afterwards - and the map flies to the right region as soon
// as a recognisable site-ID prefix (ALX/SIN/UPP/DEL) is typed.
import { useEffect, useState } from 'react';
import { PlusCircle, RefreshCw } from 'lucide-react';
import { api, type ExistingReplanPreview, type NetworkData, type PlanAssignment, type Site } from './api';
import { Card, PrimaryButton, LoadingBlock, ErrorBlock } from './ui';
import { MapView } from './MapView';
import { Legend } from './Legend';
import { haversineKm, MOD4_COLORS } from './colors';

const REGION_NAMES: Record<string, string> = { ALX: 'Alexandria', SIN: 'Sinai', UPP: 'Upper Egypt', DEL: 'Delta' };
const MOD3_COLORS: Record<number, string> = { 0: '#00ACC1', 1: '#1565C0', 2: '#FACC15' };

function SectionShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white/95 shadow-[0_8px_24px_rgba(15,23,42,0.06)] overflow-hidden">
      <div className="relative border-b border-slate-200 bg-gradient-to-r from-primary/5 via-white to-secondary/10 px-5 py-4">
        <div className="absolute -right-8 -top-8 h-20 w-20 rounded-full bg-primary/10 blur-2xl" />
        <div className="absolute -left-6 -bottom-8 h-20 w-20 rounded-3xl bg-secondary/15 blur-2xl" />
        <div className="relative flex items-start gap-3">
          <div className="w-2 self-stretch rounded-full bg-gradient-to-b from-primary to-secondary shrink-0" />
          <div>
            <div className="text-sm font-semibold text-slate-900">{title}</div>
            <div className="text-xs text-slate-600 mt-1">{subtitle}</div>
          </div>
        </div>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

function AssignmentTable({ assignments }: { assignments: Record<string, PlanAssignment> }) {
  return (
    <table className="w-full text-sm border border-[var(--color-border)] rounded overflow-hidden">
      <thead className="bg-gray-50 text-xs text-gray-500 uppercase"><tr><th className="px-3 py-2 text-left">Sector</th><th className="px-3 py-2 text-left">PCI</th><th className="px-3 py-2 text-left">Mod4</th><th className="px-3 py-2 text-left">RSI</th></tr></thead>
      <tbody className="divide-y divide-gray-100">
        {Object.entries(assignments).sort().map(([sid, a]) => (
          <tr key={sid}><td className="px-3 py-1.5 font-mono text-xs">{sid}</td><td className="px-3 py-1.5">{a.pci}</td><td className="px-3 py-1.5">{a.mod4}</td><td className="px-3 py-1.5">{a.rsi}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function EditableAssignmentTable({
  assignments,
  options,
  mod3Choices,
  onChangeMod4,
  onChangeMod3,
  onChangePci,
}: {
  assignments: Record<string, PlanAssignment>;
  options: ExistingReplanPreview['editor_options'];
  mod3Choices: Record<string, number>;
  onChangeMod4: (sid: string, mod4: number) => void;
  onChangeMod3: (sid: string, mod3: number) => void;
  onChangePci: (sid: string, pci: number) => void;
}) {
  return (
    <div className="space-y-2">
      <table className="w-full text-sm border border-[var(--color-border)] rounded overflow-hidden">
        <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
          <tr>
            <th className="px-3 py-2 text-left">Sector</th>
            <th className="px-3 py-2 text-left">Mod4 color</th>
            <th className="px-3 py-2 text-left">Mod3 color</th>
            <th className="px-3 py-2 text-left">Valid PCI</th>
            <th className="px-3 py-2 text-left">RSI</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {Object.entries(assignments).sort().map(([sid, assignment]) => {
            const editor = options[sid];
            const mod4Choices = Array.from(new Set([assignment.mod4, ...(editor?.valid_mod4 ?? [0, 1, 2, 3])]));
            const mod3ChoicesForSector = Array.from(new Set([mod3Choices[sid] ?? (assignment.pci % 3), ...(editor?.valid_mod3 ?? [0, 1, 2])]));
            const suggestions = Array.from(new Set([assignment.pci, ...(editor?.suggested_pci ?? []), ...(editor?.valid_pci ?? [])]));
            return (
              <tr key={sid}>
                <td className="px-3 py-2 font-mono text-xs">{sid}</td>
                <td className="px-3 py-2">
                  <select
                    value={assignment.mod4}
                    onChange={(e) => onChangeMod4(sid, Number(e.target.value))}
                    className="w-full min-w-32 border border-[var(--color-border)] rounded px-2 py-1 text-sm bg-white"
                  >
                    {mod4Choices.map((mod4) => (
                      <option key={mod4} value={mod4}>Group {mod4}</option>
                    ))}
                  </select>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-gray-500">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: MOD4_COLORS[assignment.mod4] ?? '#64748B' }} />
                    <span>{MOD4_COLORS[assignment.mod4] ?? 'Custom'}</span>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <select
                    value={mod3Choices[sid] ?? (assignment.pci % 3)}
                    onChange={(e) => onChangeMod3(sid, Number(e.target.value))}
                    className="w-full min-w-32 border border-[var(--color-border)] rounded px-2 py-1 text-sm bg-white"
                  >
                    {mod3ChoicesForSector.map((mod3) => (
                      <option key={mod3} value={mod3}>Group {mod3}</option>
                    ))}
                  </select>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-gray-500">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: MOD3_COLORS[mod3Choices[sid] ?? (assignment.pci % 3)] ?? '#64748B' }} />
                    <span>{MOD3_COLORS[mod3Choices[sid] ?? (assignment.pci % 3)] ?? 'Custom'}</span>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <select
                    value={assignment.pci}
                    onChange={(e) => onChangePci(sid, Number(e.target.value))}
                    className="w-full min-w-44 border border-[var(--color-border)] rounded px-2 py-1 text-sm bg-white"
                  >
                    {suggestions.length ? suggestions.map((pci) => (
                      <option key={pci} value={pci}>PCI {pci}</option>
                    )) : <option value={assignment.pci}>No valid PCI for this Mod4/Mod3</option>}
                  </select>
                  <div className="mt-1 text-[11px] text-gray-500">Filtered by Mod4 {assignment.mod4} and Mod3 {mod3Choices[sid] ?? (assignment.pci % 3)}</div>
                </td>
                <td className="px-3 py-2">
                  <div className="inline-flex items-center gap-2 rounded-full border border-secondary/20 bg-secondary/10 px-2.5 py-1 text-[11px] font-semibold text-[var(--color-secondary)]">
                    <span className="h-2 w-2 rounded-full bg-secondary" /> RSI {assignment.rsi}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="rounded-full border border-secondary/20 bg-secondary/10 px-2.5 py-1 font-semibold text-[var(--color-secondary)]">RSI is preserved from the active workbook</span>
        <span className="text-gray-400">Choose Mod4 and Mod3 first. The PCI dropdown then shows only values that remain valid for that combination under the current draft.</span>
      </div>
    </div>
  );
}

function NeighborTable({ neighbors }: { neighbors: { sector: string; neighbor: string; pci: number; mod4: number; rsi: number }[] }) {
  if (!neighbors.length) return <p className="text-xs text-gray-500">No planned tier-1 neighbors found within 7 km - this site would be isolated.</p>;
  return (
    <div className="max-h-56 overflow-auto border border-[var(--color-border)] rounded">
      <table className="w-full text-xs">
        <thead className="bg-gray-50 sticky top-0"><tr><th className="px-3 py-1.5 text-left">New sector</th><th className="px-3 py-1.5 text-left">Existing neighbor</th><th className="px-3 py-1.5 text-left">PCI</th><th className="px-3 py-1.5 text-left">Mod4</th><th className="px-3 py-1.5 text-left">RSI</th></tr></thead>
        <tbody className="divide-y divide-gray-100">
          {neighbors.slice(0, 60).map((n, i) => (
            <tr key={i}><td className="px-3 py-1">{n.sector}</td><td className="px-3 py-1">{n.neighbor}</td><td className="px-3 py-1">{n.pci}</td><td className="px-3 py-1">{n.mod4}</td><td className="px-3 py-1">{n.rsi}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AddSiteView({ workbook, setWorkbook, isActive = true }: { workbook: string; setWorkbook: (w: string) => void; isActive?: boolean }) {
  const [data, setData] = useState<NetworkData | null>(null);
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [error, setError] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [committed, setCommitted] = useState<string | null>(null);

  useEffect(() => { api.network(workbook).then(setData).catch((e) => setError(String(e))); }, [workbook]);

  // --- Re-plan existing ---
  const [target, setTarget] = useState('');
  const [existingPreview, setExistingPreview] = useState<ExistingReplanPreview | null>(null);
  const [existingDraft, setExistingDraft] = useState<Record<string, PlanAssignment>>({});
  const [existingMod3Choices, setExistingMod3Choices] = useState<Record<string, number>>({});
  const [refreshingExistingOptions, setRefreshingExistingOptions] = useState(false);
  const previewExisting = async () => {
    setError(null);
    try {
      const preview = await api.replanSitePreview(workbook, target);
      setExistingPreview(preview);
      setExistingDraft(preview.assignments);
      setExistingMod3Choices(Object.fromEntries(Object.entries(preview.assignments).map(([sid, assignment]) => [sid, assignment.pci % 3])));
    }
    catch (e) { setError(String(e)); }
  };
  const refreshExistingOptions = async (assignments: Record<string, PlanAssignment>, mod3Choices: Record<string, number>) => {
    if (!target) return;
    setRefreshingExistingOptions(true);
    try {
      const out = await api.replanSiteOptions(workbook, target, assignments, mod3Choices);
      const normalizedAssignments = { ...assignments };
      let changed = false;
      for (const [sid, editor] of Object.entries(out.editor_options)) {
        const current = normalizedAssignments[sid];
        if (!current) continue;
        if (editor.valid_pci.length && !editor.valid_pci.includes(current.pci)) {
          normalizedAssignments[sid] = { ...current, pci: editor.valid_pci[0] };
          changed = true;
        }
      }
      if (changed) {
        setExistingDraft(normalizedAssignments);
        setExistingMod3Choices((cur) => {
          const next = { ...cur };
          for (const [sid, assignment] of Object.entries(normalizedAssignments)) next[sid] = assignment.pci % 3;
          return next;
        });
      }
      setExistingPreview((cur) => cur ? { ...cur, editor_options: out.editor_options } : cur);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshingExistingOptions(false);
    }
  };
  const updateExistingDraft = (sid: string, patch: Partial<PlanAssignment>, nextMod3Choice?: number) => {
    const next = { ...existingDraft, [sid]: { ...existingDraft[sid], ...patch } };
    const mod3Next = nextMod3Choice == null
      ? existingMod3Choices
      : { ...existingMod3Choices, [sid]: nextMod3Choice };
    setExistingDraft(next);
    setExistingMod3Choices(mod3Next);
    void refreshExistingOptions(next, mod3Next);
  };
  const updateExistingMod4Choice = (sid: string, mod4: number) => {
    updateExistingDraft(sid, { mod4 }, existingMod3Choices[sid] ?? (existingDraft[sid].pci % 3));
  };
  const updateExistingMod3Choice = (sid: string, mod3: number) => {
    updateExistingDraft(sid, {}, mod3);
  };
  const updateExistingPciChoice = (sid: string, pci: number) => {
    updateExistingDraft(sid, { pci }, pci % 3);
  };
  const commitExisting = async () => {
    setCommitting(true);
    try {
      const out = await api.replanSiteCommit(workbook, existingDraft);
      setWorkbook(out.workbook);
      setCommitted(`Committed. Overall validation: ${out.report.pass ? 'PASS' : 'FAIL'}.`);
      setExistingPreview(null);
      setExistingDraft({});
      setExistingMod3Choices({});
    } catch (e) { setError(String(e)); } finally { setCommitting(false); }
  };

  // --- New site ---
  const [siteId, setSiteId] = useState('');
  const [lat, setLat] = useState(27.5);
  const [lon, setLon] = useState(30.6);
  const [nSectors, setNSectors] = useState(3);
  const [azimuths, setAzimuths] = useState<number[]>([0, 120, 240]);
  const [newPreview, setNewPreview] = useState<any>(null);
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lon: number; zoom?: number } | null>(null);

  const newRegion = siteId.slice(0, 3).toUpperCase();
  const newRegionValid = newRegion.length === 3 && !!REGION_NAMES[newRegion];

  // As soon as the ID prefix resolves to a known region, jump the picker
  // map there and re-centre the pin on that region's own sites - exactly
  // the "take me to the written region after I write site id" flow.
  useEffect(() => {
    if (!newRegionValid || !data) return;
    const cands = data.sites.filter((s) => s.g === newRegion);
    if (!cands.length) return;
    const clat = cands.reduce((a, s) => a + s.y, 0) / cands.length;
    const clon = cands.reduce((a, s) => a + s.x, 0) / cands.length;
    setLat(clat);
    setLon(clon);
    setFlyTarget({ lat: clat, lon: clon, zoom: 11 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newRegion, newRegionValid]);

  const setSectorCount = (n: number) => {
    setNSectors(n);
    const defaults = [0, 120, 240, 60, 300];
    setAzimuths(defaults.slice(0, n));
  };

  const previewNew = async () => {
    setError(null);
    try { setNewPreview(await api.addSiteNewPreview(workbook, siteId, lat, lon, azimuths)); }
    catch (e) { setError(String(e)); }
  };
  const commitNew = async () => {
    setCommitting(true);
    try {
      const out = await api.addSiteNewCommit(newPreview.tmp_id, newPreview.assignments);
      setWorkbook(out.workbook);
      setCommitted(`Committed. Overall validation: ${out.report.pass ? 'PASS' : 'FAIL'}.`);
      setNewPreview(null);
    } catch (e) { setError(String(e)); } finally { setCommitting(false); }
  };

  const nearestKm = (targetLat: number, targetLon: number, region: string, exclude?: string) => {
    if (!data) return null;
    const cands = data.sites.filter((s) => s.g === region && s.s !== exclude);
    if (!cands.length) return null;
    return Math.min(...cands.map((s) => haversineKm(targetLat, targetLon, s.y, s.x)));
  };

  if (error) return <ErrorBlock message={error} />;
  if (!data) return <LoadingBlock label="Loading network..." />;

  const region = mode === 'new' ? newRegion : target.slice(0, 3);
  const existingSite = mode === 'existing' ? data.sites.find((s) => s.s === target) ?? null : null;
  const previewSite: Site | null = mode === 'existing' && existingPreview
    ? (() => {
        const assigned = existingDraft;
        const mappedIds = new Set<string>();
        const sec = existingSite
          ? [
              ...existingSite.sec.map((sector) => {
                mappedIds.add(sector.i);
                const assignment = assigned[sector.i] ?? existingPreview.old?.[sector.i] ?? {};
                return { ...sector, p: assignment.pci, m: assignment.mod4, r: assignment.rsi };
              }),
              ...Object.entries(assigned)
                .filter(([sid]) => !mappedIds.has(sid))
                .map(([sid, assignment]: any) => ({ i: sid, a: 0, p: assignment.pci, m: assignment.mod4, r: assignment.rsi })),
            ]
          : Object.entries(assigned).map(([sid, assignment]: any) => ({ i: sid, a: 0, p: assignment.pci, m: assignment.mod4, r: assignment.rsi }));

        return {
          s: target,
          g: existingSite?.g ?? region,
          y: existingSite?.y ?? 0,
          x: existingSite?.x ?? 0,
          n: sec.length,
          sec,
        };
      })()
    : mode === 'new' && newPreview
    ? { s: siteId, g: region, y: lat, x: lon, n: azimuths.length,
        sec: Object.entries(newPreview.assignments).map(([sid, a]: any, idx: number) => ({ i: sid, a: azimuths[idx] ?? 0, p: a.pci, m: a.mod4, r: a.rsi })) }
    : null;

  const contextSites = data.sites.filter((s) => s.g === region && s.s !== (mode === 'existing' ? target : siteId));
  const mapSites = previewSite ? [...contextSites, previewSite] : contextSites;
  const pickerSites = newRegionValid ? data.sites.filter((s) => s.g === newRegion) : [];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {committed && <div className="rounded-2xl border border-green-200 bg-gradient-to-r from-green-50 to-white text-[var(--color-success)] p-4 text-sm shadow-sm">{committed}</div>}

      <div className="inline-flex gap-2 rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-50 to-white p-1.5 shadow-sm">
        <button onClick={() => setMode('existing')} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border transition-all ${mode === 'existing' ? 'bg-gradient-to-r from-primary to-secondary text-white border-primary shadow' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}>
          <RefreshCw className="w-4 h-4" /> Re-plan an existing site
        </button>
        <button onClick={() => setMode('new')} className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border transition-all ${mode === 'new' ? 'bg-gradient-to-r from-secondary to-primary text-white border-secondary shadow' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}>
          <PlusCircle className="w-4 h-4" /> Add a brand-new site
        </button>
      </div>

      {mode === 'existing' ? (
        <SectionShell
          title="Re-plan Existing Site"
          subtitle="Adjust PCI and Mod4 for one live site while preserving its current RSI from the active workbook."
        >
          <div className="rounded-2xl border border-primary/15 bg-gradient-to-r from-primary/5 to-white p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-800">Existing-site safe edit mode</div>
              <div className="text-xs text-slate-600 mt-1">Preview a local replan, inspect neighbors, and commit only after reviewing the live map and clash context.</div>
            </div>
            <div className="flex items-center gap-2 text-[11px] flex-wrap">
              <span className="rounded-full border border-secondary/20 bg-secondary/10 px-2.5 py-1 font-semibold text-[var(--color-secondary)]">RSI locked</span>
              <span className="rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 font-semibold text-primary">PCI editable</span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-semibold text-slate-700">Mod4 editable</span>
            </div>
          </div>

          <div className="flex gap-3 items-end">
            <div className="flex-1 max-w-xs">
              <label className="text-xs text-gray-500 mb-1 block">Site to re-plan</label>
              <select value={target} onChange={(e) => setTarget(e.target.value)} className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm bg-white shadow-sm">
                <option value="">Select a site...</option>
                {data.sites.map((s) => <option key={s.s} value={s.s}>{s.s} &middot; {REGION_NAMES[s.g]} &middot; {s.n} sector(s)</option>)}
              </select>
            </div>
            <PrimaryButton onClick={previewExisting} disabled={!target}>Preview</PrimaryButton>
          </div>

          {existingPreview && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-sm font-semibold mb-2">Current (before)</div><AssignmentTable assignments={existingPreview.old} /></div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold">New plan (after)</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">RSI stays identical to the current workbook for every sector on this site.</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void refreshExistingOptions(existingDraft, existingMod3Choices)}
                      className="text-xs text-primary hover:underline disabled:text-gray-400"
                      disabled={refreshingExistingOptions}
                    >
                      {refreshingExistingOptions ? 'Refreshing choices...' : 'Refresh valid choices'}
                    </button>
                  </div>
                  <EditableAssignmentTable
                    assignments={existingDraft}
                    options={existingPreview.editor_options}
                    mod3Choices={existingMod3Choices}
                    onChangeMod4={updateExistingMod4Choice}
                    onChangeMod3={updateExistingMod3Choice}
                    onChangePci={updateExistingPciChoice}
                  />
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-sm font-semibold mb-2">Tier-1 neighbors this plan was checked against</div>
                <NeighborTable neighbors={existingPreview.neighbors} />
              </div>
              <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <MapView sites={mapSites} layerMode="Mod4" height={420} highlightSite={target} active={isActive} />
                <Legend layerMode="Mod4" />
              </div>
              <PrimaryButton onClick={commitExisting} disabled={committing}>{committing ? 'Committing...' : 'Commit'}</PrimaryButton>
            </>
          )}
        </SectionShell>
      ) : (
        <SectionShell
          title="Add Brand-New Site"
          subtitle="Place a new site on the live map, fine-tune its geometry, preview the generated plan, and commit after review."
        >
          <div className="rounded-2xl border border-secondary/20 bg-gradient-to-r from-secondary/10 to-white p-4">
            <div className="text-sm font-semibold text-slate-800">Map-first planning flow</div>
            <div className="text-xs text-slate-600 mt-1">Choose a region from the site ID prefix, drop the site on the real map, and review the proposed PCI / Mod4 / RSI plan before commit.</div>
          </div>

          <div>
            <label className="text-xs text-gray-500 mb-1 block">New site ID</label>
            <input value={siteId} onChange={(e) => setSiteId(e.target.value.toUpperCase())} placeholder="e.g. ALX9999" className="w-full max-w-xs border border-slate-200 rounded-xl px-3 py-2 text-sm shadow-sm" />
            <p className="text-[11px] text-gray-400 mt-1">
              {newRegionValid ? `Recognised region: ${newRegion} \u00b7 ${REGION_NAMES[newRegion]} - map centred below.` : 'Start with a known region prefix (ALX/SIN/UPP/DEL) to auto-centre the map.'}
            </p>
          </div>

          <div>
            <label className="text-sm font-medium mb-2 block">Click the map to place the new site</label>
            <div className="space-y-3">
              <MapView
                sites={pickerSites}
                layerMode="Mod4"
                height={420}
                active={isActive}
                pickable
                pickPosition={[lat, lon]}
                onPick={(la, lo) => { setLat(la); setLon(lo); }}
                referenceRings
                focusSite={flyTarget}
                fitToSites={false}
              />
              <p className="text-[11px] text-gray-400">Dashed red ring = 7km tier-1 collision range &middot; dashed violet ring = 14km tier-2 confusion range. Drag the pin, or click anywhere on the map, to move it.</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Latitude (fine-tune)</label>
              <input type="number" step="0.000001" value={lat} onChange={(e) => setLat(Number(e.target.value))} className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm font-mono shadow-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Longitude (fine-tune)</label>
              <input type="number" step="0.000001" value={lon} onChange={(e) => setLon(Number(e.target.value))} className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm font-mono shadow-sm" />
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500 mb-1 block">Number of sectors: {nSectors}</label>
            <input type="range" min={1} max={5} value={nSectors} onChange={(e) => setSectorCount(Number(e.target.value))} className="w-48 accent-primary" />
            <div className="flex gap-3 mt-2 flex-wrap">
              {azimuths.map((az, i) => (
                <div key={i}>
                  <label className="text-[10px] text-gray-400 block">Sector {i + 1} azimuth</label>
                  <input type="number" min={0} max={359} value={az} onChange={(e) => setAzimuths((cur) => cur.map((v, j) => j === i ? Number(e.target.value) : v))} className="w-24 border border-slate-200 rounded-xl px-2 py-1 text-sm shadow-sm" />
                </div>
              ))}
            </div>
          </div>

          {newRegionValid && nearestKm(lat, lon, newRegion) != null && (
            <p className="text-xs text-gray-500">Nearest already-planned site in {newRegion}: ~{nearestKm(lat, lon, newRegion)!.toFixed(1)} km away.</p>
          )}

          <PrimaryButton onClick={previewNew} disabled={!siteId}>Preview</PrimaryButton>

          {newPreview && (
            <>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="text-sm font-semibold mb-2">Proposed plan</div><AssignmentTable assignments={newPreview.assignments} /></div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="text-sm font-semibold mb-2">Tier-1 neighbors this plan was checked against</div>
                <NeighborTable neighbors={newPreview.neighbors} />
              </div>
              <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <MapView sites={mapSites} layerMode="Mod4" height={420} highlightSite={siteId} active={isActive} />
                <Legend layerMode="Mod4" />
              </div>
              <PrimaryButton onClick={commitNew} disabled={committing}>{committing ? 'Committing...' : 'Commit'}</PrimaryButton>
            </>
          )}
        </SectionShell>
      )}
    </div>
  );
}
