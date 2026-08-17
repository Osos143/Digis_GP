// src/netpulse/PlanningView.tsx
//
// Same five numbers everywhere: this page, the Clashes tab, and the
// Region breakdown all read from the same kpi fields (mod4_clash_count,
// rsi_clash_count, mod3_soft_count, pci_collision_count,
// pci_confusion_count) - so a number here always matches what the other
// tabs show. Full explanation of each metric is a hover tooltip, not
// permanent on-page text.
import { useEffect, useMemo, useState } from 'react';
import { Radio, MapPin, Search, ShieldAlert, Target, Sparkles, TrendingUp } from 'lucide-react';
import { api, type NetworkData, type Site } from './api';
import { Card, LoadingBlock, ErrorBlock, FeatureCard, AccentHeader } from './ui';
import { MapView } from './MapView';
import { Legend } from './Legend';
import type { LayerMode } from './colors';

const REGION_NAMES: Record<string, string> = { ALX: 'Alexandria', SIN: 'Sinai', UPP: 'Upper Egypt', DEL: 'Delta' };

export function PlanningView({ workbook, isActive = true }: { workbook: string; setWorkbook: (w: string) => void; isActive?: boolean }) {
  const [data, setData] = useState<NetworkData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layerMode, setLayerMode] = useState<LayerMode>('Regions');
  const [region, setRegion] = useState<string>('');
  const [siteFilter, setSiteFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [showRuleSummary, setShowRuleSummary] = useState(false);

  useEffect(() => {
    setError(null);
    api.network(workbook).then(setData).catch((e) => setError(String(e)));
  }, [workbook]);

  const k = data?.kpi;
  const validation = k?.validation;
  const summary = k?.summary;
  const hardIssues = summary?.hard_issues ?? ((validation?.hard.pci_collisions || 0) + (validation?.hard.pci_confusions || 0)
    + (validation?.hard.mod3_small_site_clashes || 0) + (validation?.hard.mod3_large_site_adjacent_clashes || 0)
    + (validation?.hard.mod4_co_site_violations || 0) + (validation?.hard.rsi_reuse_violations || 0));
  const sites = useMemo(() => (region ? (data?.sites.filter((s) => s.g === region) ?? []) : (data?.sites ?? [])), [data, region]);
  const siteOptions = useMemo(() => Array.from(new Set((data?.sites ?? []).map((site) => site.s))).sort(), [data?.sites]);
  const searchValue = search.trim().toLowerCase();
  const filteredSites = useMemo(() => {
    return sites.filter((site) => {
      const siteTokens = [site.s, site.g, String(site.n)];
      const matchesSite = !siteFilter || site.s === siteFilter;
      const matchesSearch = !searchValue || siteTokens.some((token) => token.toLowerCase().includes(searchValue));
      return matchesSite && matchesSearch;
    });
  }, [sites, searchValue, siteFilter]);

  const mapFocus = useMemo(() => {
    if (!filteredSites.length) return null;
    if (!region) return null;
    const centerSite = filteredSites[0];
    return { lat: centerSite.y, lon: centerSite.x, zoom: 10 };
  }, [filteredSites, region]);

  const kpiHighlights = useMemo(() => {
    const statusValue = summary?.status || (validation?.pass ? 'PASS' : 'FAIL');
    const statusTone = statusValue === 'PASS' ? 'hero' as const : 'hard' as const;
    return [
      { label: 'Status', value: statusValue, tone: statusTone, sub: 'Current workbook status', icon: ShieldAlert },
      { label: 'Hard issues', value: hardIssues.toLocaleString(), tone: hardIssues > 0 ? 'hard' as const : 'neutral' as const, sub: 'Priority blockers', icon: Target },
      { label: 'Coverage', value: `${(k?.total_sectors || 0).toLocaleString()} sectors`, tone: 'neutral' as const, sub: `${(k?.total_sites || 0).toLocaleString()} sites`, icon: Radio },
    ];
  }, [hardIssues, k, summary, validation]);

  const regionEntries = useMemo(() => Object.entries(k?.regions || {}), [k]);
  const regionDetails = useMemo(() => {
    const grouped = (data?.sites || []).reduce<Record<string, Site[]>>((acc, site) => {
      const regionCode = site.g || 'UNK';
      if (!acc[regionCode]) acc[regionCode] = [];
      acc[regionCode].push(site);
      return acc;
    }, {});

    return Object.fromEntries(Object.entries(grouped).map(([code, sitesInRegion]) => {
      const distribution = sitesInRegion.reduce<Record<string, number>>((acc, site) => {
        const sectorCount = site.sec?.length ?? 0;
        acc[String(sectorCount)] = (acc[String(sectorCount)] || 0) + 1;
        return acc;
      }, {});

      const sortedDistribution = Object.entries(distribution).sort((a, b) => Number(a[0]) - Number(b[0]));

      return [code, {
        distribution: sortedDistribution,
      }];
    }));
  }, [data?.sites]);
  const detailedSections = useMemo(() => {
    const knownLabels: Record<string, { label: string; kind: 'pair' | 'sector' | 'site'; unit: string; definition: string }> = {
      pci_collision: { label: 'PCI collision', kind: 'pair', unit: 'PER SITE', definition: 'Two sectors within 7 km share the same PCI.' },
      pci_confusion: { label: 'PCI confusion', kind: 'pair', unit: 'PER SITE', definition: 'Two sectors within 14 km share the same PCI.' },
      rsi_reuse: { label: 'RSI reuse', kind: 'pair', unit: 'PER SITE', definition: 'Two sectors within 14 km share the same RSI.' },
      mod3_adjacent: { label: 'Mod3 adjacent', kind: 'site', unit: 'PER SITE', definition: 'Adjacent sectors on the same site share the same Mod3.' },
      mod4_intra_site: { label: 'Mod4 intra-site', kind: 'site', unit: 'PER SITE', definition: 'Adjacent sectors on the same site share the same Mod4.' },
      mod3_non_adj_reuse_sites: { label: 'Mod3 non-adj reuse', kind: 'site', unit: 'PER SITE', definition: 'Sites with 4-5 sectors reuse Mod3 on non-adjacent sectors.' },
      mod4_inter_site_sectors: { label: 'Mod4 inter-site (sector)', kind: 'sector', unit: 'PER SECTOR', definition: 'Sectors whose 1st neighbor (nearest within 7 km, in antenna direction) shares Mod4.' },
      mod4_inter_site_sites: { label: 'Mod4 inter-site (site)', kind: 'site', unit: 'PER SITE', definition: 'Sites whose 1st neighbor (nearest within 7 km, in antenna direction) shares Mod4.' },
      mod4_non_adj_intra_site_sites: { label: 'Mod4 non-adj intra-site', kind: 'site', unit: 'PER SITE', definition: 'Sites with 5 sectors reuse Mod4 on non-adjacent sectors.' },
    };

    // Keys that are internal/duplicate helper metrics, not distinct rule rows.
    const hiddenKeys = new Set([
      'pci_collisions', 'pci_confusions', 'rsi_reuse_violations',
      'mod3_small_site_clashes', 'mod3_large_site_adjacent_clashes', 'mod4_co_site_violations',
      'mod4_inter_site_raw', 'mod4_inter_site_weighted', 'mod4_clash_sector_pairs', 'mod4_clash_sector_pairs_weighted',
      'mod3_rule_violations',
    ]);

    const fallbackDefinition = (key: string) => {
      if (key.includes('mod4_inter_site')) return 'Nearest inter-site neighbor in the antenna direction shares the same Mod4.';
      if (key.includes('mod3')) return 'Mod3 rule metric exported from the workbook report sheet.';
      if (key.includes('mod4')) return 'Mod4 rule metric exported from the workbook report sheet.';
      if (key.includes('pci')) return 'PCI rule metric exported from the workbook report sheet.';
      if (key.includes('rsi')) return 'RSI rule metric exported from the workbook report sheet.';
      return 'KPI value exported from the workbook report sheet.';
    };

    const fallbackKind = (key: string): 'pair' | 'sector' | 'site' => {
      if (key.includes('pair')) return 'pair';
      if (key.includes('sector')) return 'sector';
      return 'site';
    };

    const fallbackUnit = (kind: 'pair' | 'sector' | 'site') => (kind === 'pair' ? 'PER PAIR' : kind === 'sector' ? 'PER SECTOR' : 'PER SITE');

    const mergedHard = { ...(validation?.hard ?? {}), ...(summary?.hard ?? {}) } as Record<string, number>;
    const mergedSoft = { ...(validation?.soft ?? {}), ...(summary?.soft ?? {}) } as Record<string, number>;

    const toRows = (source: Record<string, number> | undefined, tone: 'hard' | 'soft' | 'neutral') => {
      const rows: Array<{ name: string; value: string; tone: 'hard' | 'soft' | 'neutral'; kind: 'pair' | 'sector' | 'site'; note: string; unit: string; definition: string }> = [];

      Object.entries(source ?? {}).forEach(([key, value]) => {
        if (value === undefined || value === null || hiddenKeys.has(key)) return;

        const known = knownLabels[key];
        const kind = known?.kind ?? fallbackKind(key);
        const unit = known?.unit ?? fallbackUnit(kind);
        const definition = known?.definition ?? fallbackDefinition(key);
        const name = known?.label ?? key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());

        rows.push({
          name,
          value: Number(value).toLocaleString(),
          tone,
          kind,
          note: unit,
          unit,
          definition,
        });
      });

      return rows;
    };

    return [
      { title: 'Hard rules', rows: toRows(mergedHard, 'hard') },
      { title: 'Soft rules', rows: toRows(mergedSoft, 'soft') },
    ];
  }, [summary, validation]);

  if (error) return <ErrorBlock message={error} />;
  if (!data) return <LoadingBlock label="Loading the current plan..." />;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <FeatureCard className="p-5">
        <div className="relative space-y-5">
          <AccentHeader
            title="Reference KPI metrics"
            subtitle="A polished, executive-friendly snapshot of the current workbook health."
            actions={
              <div className="flex flex-wrap gap-2">
                <div className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-primary shadow-sm">{summary?.status || (validation?.pass ? 'PASS' : 'FAIL')}</div>
                <div className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold text-slate-700 shadow-sm">{hardIssues} hard issues</div>
              </div>
            }
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {kpiHighlights.map((metric) => {
              const toneClasses = metric.tone === 'hero' ? 'from-primary/10 via-primary/5 to-white border-primary/20' : metric.tone === 'hard' ? 'from-red-50 via-white to-white border-red-200' : 'from-slate-50 via-white to-white border-slate-200';
              const valueClasses = metric.tone === 'hero' ? 'text-primary' : metric.tone === 'hard' ? 'text-[var(--color-critical)]' : 'text-[var(--color-text)]';
              const Icon = metric.icon;
              return (
                <div key={metric.label} className={`rounded-2xl border bg-gradient-to-br ${toneClasses} p-4 shadow-[0_16px_40px_-20px_rgba(15,23,42,0.45)]`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-gray-500">{metric.label}</div>
                      <div className={`mt-2 text-2xl font-bold ${valueClasses}`}>{metric.value}</div>
                    </div>
                    <div className="rounded-xl bg-white/85 p-2 shadow-sm">
                      <Icon className="w-4 h-4 text-gray-600" />
                    </div>
                  </div>
                  <div className="mt-3 text-xs text-gray-600">{metric.sub}</div>
                </div>
              );
            })}
          </div>
        </div>
      </FeatureCard>

      <FeatureCard className="p-5">
        <div className="relative space-y-4">
          <AccentHeader
            title="Detailed KPI breakdown"
            subtitle="Concise rule-level view of hard and soft impacts."
            actions={
              <button
                onClick={() => setShowRuleSummary(true)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-600 shadow-sm transition hover:border-primary/30 hover:text-primary"
              >
                Rule summary
              </button>
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            {detailedSections.map((section) => {
              const sectionAccent = section.title === 'Hard rules' ? 'bg-[linear-gradient(135deg,#fef2f2_0%,#fff7f7_100%)] border-red-200' : 'bg-[linear-gradient(135deg,#fefce8_0%,#fffdf5_100%)] border-amber-200';
              const isSoft = section.title === 'Soft rules';
              return (
                <div key={section.title} className={`rounded-2xl border ${sectionAccent} p-4 shadow-[0_16px_40px_-22px_rgba(15,23,42,0.4)]`}>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-800">{section.title}</div>
                    <div className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide shadow-sm ${section.title === 'Hard rules' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                      {section.rows.length} items
                    </div>
                  </div>
                  <div className={`mt-4 ${isSoft ? 'grid gap-2 xl:grid-cols-1' : 'space-y-2'}`}>
                    {section.rows.map((row) => (
                      <div key={row.name} className="rounded-xl border border-white/80 bg-white/95 px-3 py-3 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:border-slate-300">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-slate-800">{row.name}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-600">{row.definition}</div>
                          </div>
                          <div className="flex min-w-[96px] flex-col items-end">
                            <span className={`inline-flex min-w-16 justify-center rounded-full px-2.5 py-1 text-sm font-semibold ${row.tone === 'hard' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>{row.value}</span>
                            <span className="mt-1 whitespace-nowrap text-center text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{row.unit}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </FeatureCard>

      {showRuleSummary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="max-h-[80vh] w-full max-w-4xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-sm font-semibold uppercase tracking-[0.22em] text-primary">Rule definitions</div>
                <h3 className="mt-1 text-xl font-semibold text-slate-800">Hard and soft rule explanations</h3>
              </div>
              <button onClick={() => setShowRuleSummary(false)} className="rounded-full border border-slate-200 px-3 py-1 text-sm text-slate-600 hover:bg-slate-50">Close</button>
            </div>
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-red-200 bg-red-50/70 p-4">
                <div className="text-sm font-semibold text-red-700">Hard rules</div>
                <div className="mt-3 space-y-3 text-sm text-slate-700">
                  <div><div className="font-semibold">PCI collision</div><div className="mt-1 text-xs leading-5 text-slate-600">Two neighboring sectors within 7 km share the same PCI, so a UE cannot distinguish them. This is a blocker and should remain at 0.</div></div>
                  <div><div className="font-semibold">PCI confusion</div><div className="mt-1 text-xs leading-5 text-slate-600">Two sectors within 14 km reuse the same PCI, which confuses UE measurement reports and handover logic.</div></div>
                  <div><div className="font-semibold">RSI reuse</div><div className="mt-1 text-xs leading-5 text-slate-600">Two sectors within 14 km share the same RSI and can cause PRACH preamble collisions during random access.</div></div>
                  <div><div className="font-semibold">Mod3 adjacent</div><div className="mt-1 text-xs leading-5 text-slate-600">Ring-adjacent sectors on the same site share the same Mod3 and can interfere at coverage boundaries.</div></div>
                  <div><div className="font-semibold">Mod4 intra-site</div><div className="mt-1 text-xs leading-5 text-slate-600">Ring-adjacent sectors on the same site share the same Mod4 and can degrade uplink channel estimation.</div></div>
                </div>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
                <div className="text-sm font-semibold text-amber-700">Soft rules</div>
                <div className="mt-3 space-y-3 text-sm text-slate-700">
                  <div><div className="font-semibold">Mod3 non-adj reuse</div><div className="mt-1 text-xs leading-5 text-slate-600">Sites with 4–5 sectors reuse Mod3 on non-adjacent sectors, which is often unavoidable and remains informational.</div></div>
                  <div><div className="font-semibold">Mod4 non-adj intra-site</div><div className="mt-1 text-xs leading-5 text-slate-600">Sites with 5 sectors reuse Mod4 on non-adjacent sectors and remain a soft structural concern.</div></div>
                  <div><div className="font-semibold">Mod4 inter-site</div><div className="mt-1 text-xs leading-5 text-slate-600">The nearest inter-site neighbor in the antenna direction shares the same Mod4 and creates a soft clash.</div></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <FeatureCard className="p-5 space-y-4">
        <AccentHeader title="Network map" subtitle="Filter the active workbook and inspect the network by region, site, and assignment layer." />
        <div className="flex items-center gap-2 flex-wrap rounded-2xl border border-white/80 bg-white/75 p-3 shadow-sm backdrop-blur">
            <select value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)} className="text-xs border border-[var(--color-border)] rounded px-2 py-1.5 bg-white min-w-[140px]">
              <option value="">All sites</option>
              {siteOptions.map((site) => <option key={site} value={site}>{site}</option>)}
            </select>
            <label className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search sites"
                className="pl-7 pr-3 py-1.5 text-xs border border-[var(--color-border)] rounded bg-white min-w-[180px]"
              />
            </label>
            <select value={region} onChange={(e) => setRegion(e.target.value)} className="text-xs border border-[var(--color-border)] rounded px-2 py-1.5 bg-white">
              <option value="">All regions</option>
              {Object.entries(REGION_NAMES).map(([code, name]) => <option key={code} value={code}>{code} &middot; {name}</option>)}
            </select>
            {(['Regions', 'PCI', 'Mod4', 'Mod3', 'RSI'] as LayerMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setLayerMode(m)}
                className={`px-3 py-1.5 rounded text-xs font-medium border ${layerMode === m ? 'bg-primary text-white border-primary' : 'bg-white border-[var(--color-border)] text-gray-600 hover:bg-gray-50'}`}
              >
                {m}
              </button>
            ))}
        </div>
        <div className="space-y-3">
          <MapView sites={filteredSites} layerMode={layerMode} height={480} focusSite={mapFocus} active={isActive} />
          <div className="rounded-2xl border border-white/80 bg-white/80 p-3 shadow-sm">
            <Legend layerMode={layerMode} />
          </div>
        </div>
      </FeatureCard>

      <FeatureCard className="p-5 space-y-4">
        <AccentHeader title="Region breakdown" subtitle="Sites and sectors by region across the current workbook." />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {regionEntries.map(([code, r]) => (
            <div key={code} className="border border-[var(--color-border)] rounded-2xl bg-white p-4 shadow-sm">
              <div className="text-sm font-semibold">{code} &middot; {REGION_NAMES[code] || code}</div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-xl bg-slate-50 p-2">
                  <div className="text-[11px] uppercase tracking-wide text-gray-500">Sites</div>
                  <div className="text-base font-semibold text-[var(--color-text)]">{r.sites.toLocaleString()}</div>
                </div>
                <div className="rounded-xl bg-slate-50 p-2">
                  <div className="text-[11px] uppercase tracking-wide text-gray-500">Sectors</div>
                  <div className="text-base font-semibold text-[var(--color-text)]">{r.sectors.toLocaleString()}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </FeatureCard>

      <FeatureCard className="p-5 space-y-4">
        <AccentHeader title="Regional structure" subtitle="A focused view of how many sites have how many sectors." />
        <div className="grid gap-3 xl:grid-cols-2">
          {regionEntries.map(([code, r]) => {
            const details = regionDetails[code] || { distribution: [] };
            return (
              <div key={code} className="rounded-2xl border border-slate-200 bg-[linear-gradient(135deg,#ffffff_0%,#f8fbff_100%)] p-4 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{code} &middot; {REGION_NAMES[code] || code}</div>
                    <div className="mt-1 text-xs text-slate-500">Site-to-sector distribution</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">{r.sites.toLocaleString()} sites</span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700">{r.sectors.toLocaleString()} sectors</span>
                  </div>
                </div>

                {details.distribution.length > 0 && (
                  <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Distribution</div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {details.distribution.map(([sectorCount, siteCount]) => (
                        <div key={sectorCount} className="rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{sectorCount} sectors</div>
                          <div className="mt-1 flex items-end justify-between gap-2">
                            <span className="text-xl font-semibold text-slate-800">{siteCount}</span>
                            <span className="text-xs text-slate-500">sites</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </FeatureCard>
    </div>
  );
}