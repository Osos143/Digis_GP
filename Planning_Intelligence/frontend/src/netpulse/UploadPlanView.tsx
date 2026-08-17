// src/netpulse/UploadPlanView.tsx - the only entry point for getting a
// workbook into Network Pulse. No shipped demo data is ever used here -
// the active workbook is always something you explicitly uploaded, via
// one of two paths:
//
//   1. Raw workbook  - PCI/RSI/Mod4 blank, runs the real pipeline
//      (loader -> neighbor_graph -> assignment_engine -> validator ->
//      exporter) and the RESULT becomes the active workbook.
//   2. Final workbook - already has PCI/RSI/Mod4 for every sector,
//      loaded and validated as-is (no replanning) and becomes the
//      active workbook immediately.
//
// Whichever workbook ends up active here is what every other tab
// (Planning / Clashes / Assignments / Add Site / Assistant) reads.

import { useEffect, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import {
  UploadCloud, FileSpreadsheet, Play, CheckCircle2, AlertTriangle,
  FileCheck2, FilePlus2, Download,
} from 'lucide-react';
import { api } from './api';
import { Card, PrimaryButton, Pill, LoadingBlock } from './ui';

type Mode = 'raw' | 'final';
const UPLOAD_PLAN_STATE_KEY = 'netpulse-upload-plan-state';

type ColumnGuideItem = {
  key: string;
  title: string;
  meaning: string;
  exampleRaw: string | number | boolean | null;
  exampleFinal: string | number | boolean | null;
  category: 'Identity' | 'Planning' | 'Geometry' | 'Radio' | 'Assignments';
  numericRange?: { min: number; max: number };
};

type UploadPlanPersistedState = {
  mode: Mode;
  selectedFileName: string | null;
  uploaded: { workbook: string; label: string; sectors: number; sites: number } | null;
  result: { pass: boolean; written: number; collisions: number; confusions: number; mod3: number; workbook: string } | null;
  finalResult: {
    workbook: string; label: string; sectors: number; sites: number;
    pass: boolean; collisions: number; confusions: number; mod3: number;
  } | null;
};

function loadUploadPlanState(): UploadPlanPersistedState {
  try {
    const raw = localStorage.getItem(UPLOAD_PLAN_STATE_KEY);
    if (!raw) {
      return { mode: 'raw', selectedFileName: null, uploaded: null, result: null, finalResult: null };
    }
    const parsed = JSON.parse(raw) as Partial<UploadPlanPersistedState>;
    return {
      mode: parsed.mode === 'final' ? 'final' : 'raw',
      selectedFileName: parsed.selectedFileName ?? null,
      uploaded: parsed.uploaded ?? null,
      result: parsed.result ?? null,
      finalResult: parsed.finalResult ?? null,
    };
  } catch {
    return { mode: 'raw', selectedFileName: null, uploaded: null, result: null, finalResult: null };
  }
}

const COLUMN_GUIDE: ColumnGuideItem[] = [
  {
    key: 'site_sector_ID',
    title: 'Site-Sector Unique ID',
    meaning: 'Unique identifier for one sector within the whole network workbook.',
    exampleRaw: 'SITE_001_AZ0',
    exampleFinal: 'SITE_001_AZ0',
    category: 'Identity',
  },
  {
    key: 'siteID',
    title: 'Site ID',
    meaning: 'Physical site identifier shared by all sectors of the same site.',
    exampleRaw: 'SITE_001',
    exampleFinal: 'SITE_001',
    category: 'Identity',
  },
  {
    key: 'sectors_count',
    title: 'Sectors Per Site',
    meaning: 'Total number of sectors that belong to this site.',
    exampleRaw: 3,
    exampleFinal: 3,
    category: 'Identity',
    numericRange: { min: 1, max: 12 },
  },
  {
    key: 'sectorID',
    title: 'Sector Index',
    meaning: 'Sector index/order inside the site, commonly 1..3.',
    exampleRaw: 1,
    exampleFinal: 1,
    category: 'Identity',
    numericRange: { min: 1, max: 12 },
  },
  {
    key: 'Requires_Planning',
    title: 'Needs Planning Flag',
    meaning: 'TRUE/FALSE flag indicating whether this sector should be planned in raw flow.',
    exampleRaw: true,
    exampleFinal: false,
    category: 'Planning',
  },
  {
    key: 'Azimuth',
    title: 'Azimuth (deg)',
    meaning: 'Main antenna direction in degrees between 0 and 359.',
    exampleRaw: 0,
    exampleFinal: 0,
    category: 'Geometry',
    numericRange: { min: 0, max: 359 },
  },
  {
    key: 'Latitude',
    title: 'Latitude',
    meaning: 'Latitude coordinate of the sector location.',
    exampleRaw: 30.12345,
    exampleFinal: 30.12345,
    category: 'Geometry',
    numericRange: { min: -90, max: 90 },
  },
  {
    key: 'Longitude',
    title: 'Longitude',
    meaning: 'Longitude coordinate of the sector location.',
    exampleRaw: 31.12345,
    exampleFinal: 31.12345,
    category: 'Geometry',
    numericRange: { min: -180, max: 180 },
  },
  {
    key: 'Freq Band',
    title: 'Frequency Band',
    meaning: 'NR frequency band label used by the sector.',
    exampleRaw: 'n78',
    exampleFinal: 'n78',
    category: 'Radio',
  },
  {
    key: 'Cell Radius',
    title: 'Cell Radius (m)',
    meaning: 'Coverage radius estimate in meters; must be positive.',
    exampleRaw: 1000,
    exampleFinal: 1000,
    category: 'Radio',
    numericRange: { min: 1, max: 100000 },
  },
  {
    key: 'RSI',
    title: 'RSI Value',
    meaning: 'RSI assignment for the sector. Raw may be blank; final must be filled.',
    exampleRaw: null,
    exampleFinal: 120,
    category: 'Assignments',
    numericRange: { min: 0, max: 830 },
  },
  {
    key: 'PCI',
    title: 'PCI Value',
    meaning: 'PCI assignment for the sector. Raw may be blank; final must be filled.',
    exampleRaw: null,
    exampleFinal: 340,
    category: 'Assignments',
    numericRange: { min: 0, max: 1007 },
  },
  {
    key: 'Mod4',
    title: 'Mod4 Value',
    meaning: 'Mod4 class for PCI consistency. Raw may be blank; final must be filled.',
    exampleRaw: null,
    exampleFinal: 0,
    category: 'Assignments',
    numericRange: { min: 0, max: 3 },
  },
] as const;

const REQUIRED_COLUMNS = COLUMN_GUIDE.map((col) => col.key);

export function UploadPlanView({ workbook, setWorkbook }: { workbook: string; setWorkbook: (w: string) => void }) {
  const persisted = loadUploadPlanState();
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<Mode>(persisted.mode);
  const [file, setFile] = useState<File | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(persisted.selectedFileName);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // raw-file flow: upload -> preview -> run planning -> result
  const [uploaded, setUploaded] = useState<{ workbook: string; label: string; sectors: number; sites: number } | null>(persisted.uploaded);
  const [planning, setPlanning] = useState(false);
  const [result, setResult] = useState<{ pass: boolean; written: number; collisions: number; confusions: number; mod3: number; workbook: string } | null>(persisted.result);

  // final-file flow: upload -> immediately active
  const [finalResult, setFinalResult] = useState<{
    workbook: string; label: string; sectors: number; sites: number;
    pass: boolean; collisions: number; confusions: number; mod3: number;
  } | null>(persisted.finalResult);

  useEffect(() => {
    if (persisted.result?.workbook && !workbook) {
      setWorkbook(persisted.result.workbook);
    }
    if (persisted.finalResult?.workbook && !workbook) {
      setWorkbook(persisted.finalResult.workbook);
    }
  }, [persisted.result?.workbook, persisted.finalResult?.workbook, setWorkbook, workbook]);

  useEffect(() => {
    localStorage.setItem(UPLOAD_PLAN_STATE_KEY, JSON.stringify({
      mode,
      selectedFileName,
      uploaded,
      result,
      finalResult,
    } satisfies UploadPlanPersistedState));
  }, [finalResult, mode, result, selectedFileName, uploaded]);

  const resetOutcomes = () => {
    setUploaded(null);
    setResult(null);
    setFinalResult(null);
    setError(null);
  };

  const onPickFile = (f: File | null) => {
    setFile(f);
    setSelectedFileName(f?.name ?? null);
    resetOutcomes();
  };

  const onSwitchMode = (m: Mode) => {
    setMode(m);
    setFile(null);
    setSelectedFileName(null);
    resetOutcomes();
    if (fileRef.current) fileRef.current.value = '';
  };

  const onUploadRaw = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const out = await api.upload(file);
      setUploaded(out);
      setSelectedFileName(file.name);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
    }
  };

  const onRunPlanning = async () => {
    if (!uploaded) return;
    setPlanning(true);
    setError(null);
    try {
      const out = await api.replan(uploaded.workbook);
      setResult(out);
      setWorkbook(out.workbook); // this becomes the active workbook for every other tab
    } catch (e) {
      setError(String(e));
    } finally {
      setPlanning(false);
    }
  };

  const onUploadFinal = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    setFinalResult(null);
    try {
      const out = await api.uploadFinal(file);
      setFinalResult(out);
      setWorkbook(out.workbook); // active everywhere immediately, no planning step
      setSelectedFileName(file.name);
    } catch (e) {
      setError(String(e));
    } finally {
      setUploading(false);
    }
  };

  const downloadCurrent = () => {
    if (!workbook) return;
    window.open(api.downloadUrl(workbook), '_blank');
  };

  const planningStages = [
    'Load workbook',
    'Build graph',
    'Assign PCI / Mod4 / RSI',
    'Validate',
    'Export',
  ];

  const displayExample = (value: string | number | boolean | null) => {
    if (value === null) return '(blank)';
    if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
    return String(value);
  };

  const downloadTemplate = (templateMode: Mode) => {
    const sampleRow = COLUMN_GUIDE.map((col) => (
      templateMode === 'raw' ? col.exampleRaw : col.exampleFinal
    ));
    const data = [REQUIRED_COLUMNS, sampleRow];

    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(data);
    XLSX.utils.book_append_sheet(wb, ws, 'Planning');
    const buffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });

    const blob = new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = templateMode === 'raw' ? 'raw_upload_template.xlsx' : 'final_upload_template.xlsx';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="inline-flex gap-2 rounded-2xl border border-slate-200 bg-gradient-to-r from-slate-50 to-white p-1.5 shadow-sm">
        <button
          onClick={() => onSwitchMode('raw')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border transition-all ${mode === 'raw' ? 'bg-gradient-to-r from-primary to-secondary text-white border-primary shadow' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}
        >
          <FilePlus2 className="w-4 h-4" /> Raw
        </button>
        <button
          onClick={() => onSwitchMode('final')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border transition-all ${mode === 'final' ? 'bg-gradient-to-r from-secondary to-primary text-white border-secondary shadow' : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'}`}
        >
          <FileCheck2 className="w-4 h-4" /> Final
        </button>
      </div>

      <Card className="p-6 space-y-5 border-slate-200 shadow-[0_8px_24px_rgba(15,23,42,0.06)]">
        <div className="flex items-center gap-3">
          <div className="w-2 self-stretch rounded-full bg-gradient-to-b from-primary to-secondary shrink-0" />
          <div>
            <div className="font-semibold text-sm">{mode === 'raw' ? 'Upload a raw workbook' : 'Upload a final workbook'}</div>
            <div className="text-xs text-gray-500">
              {mode === 'raw'
                ? '.xlsx with a "Planning" sheet - PCI/RSI/Mod4 can be blank, the pipeline will fill them in.'
                : '.xlsx that already has PCI/RSI/Mod4 assigned for every sector - loaded and validated as-is, no replanning.'}
            </div>
          </div>
        </div>

        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-slate-300 rounded-2xl p-8 text-center cursor-pointer bg-gradient-to-b from-white to-slate-50 hover:border-primary hover:bg-primary/5 transition-all"
        >
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(e) => onPickFile(e.target.files?.[0] || null)}
          />
          <UploadCloud className="w-8 h-8 mx-auto text-slate-400 mb-2" />
          {file || selectedFileName ? (
            <div className="flex items-center justify-center gap-2 text-sm font-medium text-[var(--color-text)]">
              <FileSpreadsheet className="w-4 h-4 text-primary" /> {file?.name || selectedFileName}
            </div>
          ) : (
            <div className="text-sm text-gray-500">Click to choose an .xlsx file, or drop it here</div>
          )}
        </div>

        <PrimaryButton onClick={mode === 'raw' ? onUploadRaw : onUploadFinal} disabled={!file || uploading}>
          {uploading ? 'Uploading...' : mode === 'raw' ? 'Upload' : 'Use workbook'}
        </PrimaryButton>

        {error && (
          <div className="bg-red-50 border border-red-200 text-[var(--color-critical)] rounded p-3 text-sm flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> {error}
          </div>
        )}

        {mode === 'raw' && uploaded && (
          <div className="bg-green-50 border border-green-200 text-[var(--color-success)] rounded p-3 text-sm flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            Validated - {uploaded.sectors.toLocaleString()} sectors across {uploaded.sites} sites ({uploaded.label}).
          </div>
        )}

        {mode === 'final' && finalResult && (
          <div className="rounded-2xl border border-secondary/25 bg-gradient-to-r from-secondary/10 to-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-green-100 text-green-700 flex items-center justify-center">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-[var(--color-text)]">Workbook loaded</div>
                  <div className="text-xs text-gray-500">{finalResult.label}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone={finalResult.pass ? 'pass' : 'fail'}>{finalResult.pass ? 'Ready' : 'Review'}</Pill>
              </div>
            </div>
            <div className="mt-4 flex items-center gap-3 flex-wrap text-xs text-gray-600">
              <span className="rounded-full bg-gray-100 px-2.5 py-1">{finalResult.sectors.toLocaleString()} sectors</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1">{finalResult.sites} sites</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1">{finalResult.collisions} collisions</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1">{finalResult.confusions} confusions</span>
              <span className="rounded-full bg-gray-100 px-2.5 py-1">{finalResult.mod3} Mod3</span>
            </div>
          </div>
        )}

        <div className="relative overflow-hidden rounded-3xl border border-primary/15 bg-gradient-to-br from-primary/5 via-white to-secondary/10 p-5 space-y-4 shadow-[0_10px_30px_rgba(21,101,192,0.08)]">
          <div className="absolute -top-12 -right-10 h-24 w-24 rounded-full bg-primary/10 blur-2xl" />
          <div className="absolute -bottom-12 -left-10 h-28 w-28 rounded-full bg-secondary/15 blur-2xl" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.8),transparent_45%)]" />

          <div className="relative overflow-hidden rounded-2xl border border-primary/15 bg-white/85 px-4 py-3 shadow-sm">
            <div className="absolute -right-6 -top-6 h-16 w-16 rounded-full bg-primary/10" />
            <div className="absolute -left-8 -bottom-8 h-20 w-20 rotate-12 rounded-2xl bg-secondary/15" />
            <div className="relative flex items-start justify-between gap-3 flex-wrap">
              <div>
                <div className="inline-flex items-center rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  Template Guide
                </div>
                <div className="mt-2 text-base font-bold text-slate-800">Workbook Columns Reference</div>
                <div className="text-xs text-slate-600 mt-1">Understand each field, check valid ranges, and use mode-specific examples before upload.</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-primary" />
                <span className="h-2.5 w-2.5 rounded-full bg-secondary" />
                <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
              </div>
            </div>
          </div>

          <div className="relative flex items-start justify-between gap-4 flex-wrap">
            <div className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="rounded-full bg-white/90 border border-primary/15 px-2.5 py-1 text-[10px] font-semibold text-primary">13 required columns</span>
                <span className="rounded-full bg-white/90 border border-secondary/20 px-2.5 py-1 text-[10px] font-semibold text-[var(--color-secondary)]">Sheet name: Planning</span>
                <span className="rounded-full bg-white/90 border border-slate-200 px-2.5 py-1 text-[10px] font-semibold text-slate-700">Mode: {mode === 'raw' ? 'Raw' : 'Final'}</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => downloadTemplate(mode)}
              className="inline-flex items-center gap-2 bg-gradient-to-r from-slate-900 to-slate-700 text-white border border-slate-700 px-3.5 py-2 rounded-xl text-xs font-semibold hover:opacity-95 shadow transition-all"
            >
              <Download className="w-3.5 h-3.5" /> Download {mode === 'raw' ? 'Raw' : 'Final'} Template
            </button>
          </div>

          <div className="relative rounded-2xl border border-slate-200/80 bg-white/95 p-3 shadow-sm">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">Example row preview</div>
        <div className="overflow-x-auto">
          <div className="min-w-[1300px] grid [grid-template-columns:repeat(13,minmax(0,1fr))] gap-2">
            {COLUMN_GUIDE.map((col) => (
              <div
                key={`head-${col.key}`}
                className="rounded-lg border border-primary/15 bg-primary/5 px-2 py-1.5 text-[10px] font-semibold text-primary text-center truncate"
                title={col.key}
              >
                {col.key}
              </div>
            ))}
            {COLUMN_GUIDE.map((col) => (
              <div
                key={`sample-${col.key}`}
                className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-[11px] text-slate-700 font-medium text-center truncate"
                title={displayExample(mode === 'raw' ? col.exampleRaw : col.exampleFinal)}
              >
                {displayExample(mode === 'raw' ? col.exampleRaw : col.exampleFinal)}
              </div>
            ))}
          </div>
        </div>
      </div>

          <div className="relative grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {COLUMN_GUIDE.map((col) => (
              <div
                key={col.key}
                className="h-full rounded-2xl border border-slate-200/90 bg-white/95 p-3 shadow-[0_4px_16px_rgba(15,23,42,0.05)] hover:-translate-y-0.5 hover:shadow-[0_10px_20px_rgba(15,23,42,0.08)] transition-all"
              >
                <div className="h-full flex flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-semibold text-[var(--color-text)] leading-tight">{col.key}</div>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-600 shrink-0">
                      {col.category}
                    </span>
                  </div>
                  <div className="text-xs text-gray-600 mt-1">{col.title}</div>
                  <div className="text-xs text-gray-500 mt-2 min-h-10">{col.meaning}</div>
                  <div className="mt-2 min-h-6 flex items-center gap-2 flex-wrap text-[10px]">
                    {col.numericRange ? (
                      <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 font-semibold text-amber-700">
                        Range: {col.numericRange.min} to {col.numericRange.max}
                      </span>
                    ) : (
                      <span className="rounded-full bg-slate-50 border border-slate-200 px-2 py-0.5 font-semibold text-slate-600">
                        Range: N/A
                      </span>
                    )}
                  </div>
                  <div className="mt-auto pt-3 rounded-xl border border-secondary/20 bg-gradient-to-r from-primary/5 to-secondary/10 px-2 py-1.5 text-[11px]">
                    <div className="text-[10px] uppercase tracking-wide font-semibold text-[var(--color-secondary)]">
                      {mode === 'raw' ? 'Raw example' : 'Final example'}
                    </div>
                    <div className="font-semibold text-slate-800">
                      {displayExample(mode === 'raw' ? col.exampleRaw : col.exampleFinal)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {mode === 'raw' && uploaded && (
        <Card className="p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-2 self-stretch rounded-full bg-gradient-to-b from-primary to-secondary shrink-0" />
            <div>
              <div className="font-semibold text-sm">Plan</div>
              <div className="text-xs text-gray-500">Run the workbook through the planning pipeline.</div>
            </div>
          </div>
          <PrimaryButton onClick={onRunPlanning} disabled={planning}>
            <Play className="w-4 h-4" /> {planning ? 'Planning...' : 'Run'}
          </PrimaryButton>

          {planning && (
            <div className="space-y-3">
              <div className="rounded-xl border border-primary/20 bg-gradient-to-r from-primary/10 to-secondary/10 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-primary">Planning in progress</div>
                    <div className="text-sm text-[var(--color-text)] mt-1">Processing workbook through the live planning pipeline.</div>
                  </div>
                  <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin shrink-0" />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2 text-xs">
                {planningStages.map((stage, index) => (
                  <div
                    key={stage}
                    className={`rounded-lg border px-2 py-2 text-center shadow-sm ${index === 0 ? 'bg-primary/10 border-primary/40 text-primary font-semibold' : 'bg-white border-[var(--color-border)] text-gray-600'}`}
                  >
                    {stage}
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {mode === 'raw' && result && (
        <Card className="p-6 space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            <Pill tone={result.pass ? 'pass' : 'fail'}>{result.pass ? 'Ready' : 'Review'}</Pill>
            <span className="text-sm text-gray-600">{result.written.toLocaleString()} sectors planned</span>
          </div>
          <button
            onClick={downloadCurrent}
            className="flex items-center gap-2 bg-white border border-[var(--color-border)] px-4 py-2 rounded text-sm font-medium hover:bg-gray-50 shadow-sm"
          >
            <Download className="w-4 h-4" /> Download
          </button>
        </Card>
      )}

    </div>
  );
}