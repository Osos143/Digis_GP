// src/netpulse/AssignmentsView.tsx - mirrors assignments_view.py
import { useEffect, useMemo, useState } from 'react';
import { Download, Search } from 'lucide-react';
import { api, type SectorRow } from './api';
import { Card, PageHeader, SecondaryButton, LoadingBlock, ErrorBlock } from './ui';
import { CLASH_TYPE_ORDER, CLASH_TYPE_LABELS, sectorHasType } from './colors';

export function AssignmentsView({ workbook }: { workbook: string }) {
  const [rows, setRows] = useState<SectorRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [region, setRegion] = useState('');
  const [mod4, setMod4] = useState<string>('');
  const [clashType, setClashType] = useState('');
  const [sortKey, setSortKey] = useState<'id' | 'site' | 'region' | 'az' | 'pci' | 'mod4' | 'rsi' | 'mod3' | 'clash_types'>('id');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [rowLimit, setRowLimit] = useState<'100' | '500' | '1000' | 'all'>('500');

  useEffect(() => {
    setError(null);
    api.sectors(workbook).then(setRows).catch((e) => setError(String(e)));
  }, [workbook]);

  const regionOptions = useMemo(() => {
    if (!rows) return [];
    return Array.from(new Set(rows.map((r) => r.region))).sort();
  }, [rows]);

  const mod4Options = useMemo(() => {
    if (!rows) return [] as number[];
    return Array.from(new Set(rows.map((r) => r.mod4).filter((m): m is number => m != null))).sort((a, b) => a - b);
  }, [rows]);

  const filtered = useMemo(() => {
    if (!rows) return [];
    const qU = q.trim().toUpperCase();
    return rows.filter((r) => {
      if (qU && !r.id.toUpperCase().includes(qU) && !r.site.toUpperCase().includes(qU)) return false;
      if (region && r.region !== region) return false;
      if (mod4 !== '' && String(r.mod4) !== mod4) return false;
      if (clashType && !sectorHasType(r, clashType)) return false;
      return true;
    });
  }, [rows, q, region, mod4, clashType]);

  const clashLabelsForRow = (r: SectorRow) => {
    const labels = CLASH_TYPE_ORDER.filter((t) => t !== 'clear' && sectorHasType(r, t)).map((t) => CLASH_TYPE_LABELS[t]);
    if (labels.length) return labels.join(' | ');
    return CLASH_TYPE_LABELS.clear;
  };

  const sorted = useMemo(() => {
    const toNum = (v: unknown) => (typeof v === 'number' ? v : Number(v ?? -1));

    const copy = [...filtered];
    copy.sort((a, b) => {
      let av: string | number;
      let bv: string | number;
      if (sortKey === 'id' || sortKey === 'site' || sortKey === 'region') {
        av = String(a[sortKey] ?? '').toUpperCase();
        bv = String(b[sortKey] ?? '').toUpperCase();
      } else if (sortKey === 'clash_types') {
        av = clashLabelsForRow(a).toUpperCase();
        bv = clashLabelsForRow(b).toUpperCase();
      } else {
        av = toNum(a[sortKey]);
        bv = toNum(b[sortKey]);
      }

      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  const visibleRows = useMemo(() => {
    if (rowLimit === 'all') return sorted;
    return sorted.slice(0, Number(rowLimit));
  }, [sorted, rowLimit]);

  const onSort = (key: 'id' | 'site' | 'region' | 'az' | 'pci' | 'mod4' | 'rsi' | 'mod3' | 'clash_types') => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('asc');
  };

  const downloadCsv = () => {
    const header = ['id', 'site', 'region', 'az', 'pci', 'mod4', 'rsi', 'mod3', 'clash_types'];
    const lines = filtered.map((r) => [r.id, r.site, r.region, r.az, r.pci, r.mod4, r.rsi, r.mod3, clashLabelsForRow(r)].join(','));
    const blob = new Blob([header.join(',') + '\n' + lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'assignments_filtered.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  if (error) return <ErrorBlock message={error} />;
  if (!rows) return <LoadingBlock label="Loading assignments..." />;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <PageHeader
        title="Assignments"
        subtitle="Every sector's PCI / Mod4 / RSI, filterable and sortable."
        actions={<SecondaryButton onClick={downloadCsv}><Download className="w-4 h-4" /> Download CSV</SecondaryButton>}
      />

      <Card className="p-5">
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="relative flex-1 min-w-[220px] max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ALX3282 or ALX3282-1"
              className="w-full pl-9 pr-3 py-2 border border-[var(--color-border)] rounded text-sm bg-gray-50 focus:bg-white focus:ring-1 focus:ring-primary outline-none" />
          </div>
          <select value={region} onChange={(e) => setRegion(e.target.value)} className="text-sm border border-[var(--color-border)] rounded px-3 py-2 bg-white">
            <option value="">All regions</option>
            {regionOptions.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select value={mod4} onChange={(e) => setMod4(e.target.value)} className="text-sm border border-[var(--color-border)] rounded px-3 py-2 bg-white">
            <option value="">All Mod4</option>
            {mod4Options.map((m) => <option key={m} value={m}>Mod4 {m}</option>)}
          </select>
          <select value={clashType} onChange={(e) => setClashType(e.target.value)} className="text-sm border border-[var(--color-border)] rounded px-3 py-2 bg-white">
            <option value="">All clash types</option>
            {CLASH_TYPE_ORDER.map((t) => <option key={t} value={t}>{CLASH_TYPE_LABELS[t]}</option>)}
          </select>
          <select value={rowLimit} onChange={(e) => setRowLimit(e.target.value as '100' | '500' | '1000' | 'all')} className="text-sm border border-[var(--color-border)] rounded px-3 py-2 bg-white">
            <option value="100">Show 100</option>
            <option value="500">Show 500</option>
            <option value="1000">Show 1000</option>
            <option value="all">Show all sectors</option>
          </select>
        </div>

        <p className="text-xs text-gray-500 mb-2">{filtered.length.toLocaleString()} of {rows.length.toLocaleString()} sectors</p>

        <div className="overflow-auto max-h-[560px] border border-[var(--color-border)] rounded">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('id')}>Sector</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('site')}>Site</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('region')}>Region</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('az')}>Azimuth</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('pci')}>PCI</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('mod4')}>Mod4</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('rsi')}>RSI</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('mod3')}>Mod3</th>
                <th className="px-3 py-2 font-semibold cursor-pointer" onClick={() => onSort('clash_types')}>Clash Types</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {visibleRows.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-3 py-1.5 font-mono text-xs">{r.id}</td>
                  <td className="px-3 py-1.5">{r.site}</td>
                  <td className="px-3 py-1.5">{r.region}</td>
                  <td className="px-3 py-1.5">{r.az}&deg;</td>
                  <td className="px-3 py-1.5">{r.pci ?? '\u2014'}</td>
                  <td className="px-3 py-1.5">{r.mod4 ?? '\u2014'}</td>
                  <td className="px-3 py-1.5">{r.rsi ?? '\u2014'}</td>
                  <td className="px-3 py-1.5">{r.mod3 ?? '\u2014'}</td>
                  <td className="px-3 py-1.5 text-xs">{clashLabelsForRow(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rowLimit !== 'all' && sorted.length > Number(rowLimit) && (
          <p className="text-xs text-gray-400 mt-2">Showing first {Number(rowLimit).toLocaleString()} of {sorted.length.toLocaleString()} - choose Show all sectors or narrow filters.</p>
        )}
      </Card>
    </div>
  );
}
