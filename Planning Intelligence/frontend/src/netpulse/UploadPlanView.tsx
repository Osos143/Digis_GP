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

import { useRef, useState } from 'react';
import {
  UploadCloud, FileSpreadsheet, Play, CheckCircle2, AlertTriangle,
  FileCheck2, FilePlus2, Download,
} from 'lucide-react';
import { api } from './api';
import { Card, PageHeader, PrimaryButton, Pill, LoadingBlock } from './ui';

type Mode = 'raw' | 'final';

export function UploadPlanView({ workbook, setWorkbook }: { workbook: string; setWorkbook: (w: string) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<Mode>('raw');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // raw-file flow: upload -> preview -> run planning -> result
  const [uploaded, setUploaded] = useState<{ workbook: string; label: string; sectors: number; sites: number } | null>(null);
  const [planning, setPlanning] = useState(false);
  const [result, setResult] = useState<{ pass: boolean; written: number; collisions: number; confusions: number; mod3: number; workbook: string } | null>(null);

  // final-file flow: upload -> immediately active
  const [finalResult, setFinalResult] = useState<{
    workbook: string; label: string; sectors: number; sites: number;
    pass: boolean; collisions: number; confusions: number; mod3: number;
  } | null>(null);

  const resetOutcomes = () => {
    setUploaded(null);
    setResult(null);
    setFinalResult(null);
    setError(null);
  };

  const onPickFile = (f: File | null) => {
    setFile(f);
    resetOutcomes();
  };

  const onSwitchMode = (m: Mode) => {
    setMode(m);
    setFile(null);
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

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <PageHeader
        title="Upload &amp; Plan"
        subtitle="Upload a workbook, then use it across every tab."
      />

      <div className="flex gap-2">
        <button
          onClick={() => onSwitchMode('raw')}
          className={`flex items-center gap-2 px-4 py-2 rounded text-sm font-medium border ${mode === 'raw' ? 'bg-primary text-white border-primary' : 'bg-white border-[var(--color-border)]'}`}
        >
          <FilePlus2 className="w-4 h-4" /> Raw
        </button>
        <button
          onClick={() => onSwitchMode('final')}
          className={`flex items-center gap-2 px-4 py-2 rounded text-sm font-medium border ${mode === 'final' ? 'bg-primary text-white border-primary' : 'bg-white border-[var(--color-border)]'}`}
        >
          <FileCheck2 className="w-4 h-4" /> Final
        </button>
      </div>

      <Card className="p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">1</div>
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
          className="border-2 border-dashed border-[var(--color-border)] rounded-lg p-8 text-center cursor-pointer hover:border-primary hover:bg-primary/5 transition-colors"
        >
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(e) => onPickFile(e.target.files?.[0] || null)}
          />
          <UploadCloud className="w-8 h-8 mx-auto text-gray-400 mb-2" />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-sm font-medium text-[var(--color-text)]">
              <FileSpreadsheet className="w-4 h-4 text-primary" /> {file.name}
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
      </Card>

      {mode === 'raw' && uploaded && (
        <Card className="p-6 space-y-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm shrink-0">2</div>
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

      {mode === 'final' && finalResult && (
        <Card className="p-5">
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
        </Card>
      )}

    </div>
  );
}