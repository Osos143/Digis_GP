// src/netpulse/api.ts
//
// One thin fetch wrapper per backend endpoint (backend/main.py). Mirrors
// exactly what core/state.py + core/*_ops.py did for the Streamlit app -
// this file makes no planning decisions, it only calls the API and
// returns what it gave back.

const API_BASE = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

// Fired when the API says the active workbook's file is gone (deleted
// upload, server restart, manual cleanup) - App.tsx listens for this to
// drop the stale workbook id and send the user back to Upload & Plan.
export const WORKBOOK_MISSING_EVENT = 'netpulse:workbook-missing';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    if (res.status === 404 && /no longer available/i.test(text)) {
      window.dispatchEvent(new CustomEvent(WORKBOOK_MISSING_EVENT));
    }
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export type Sector = {
  i: string; a: number; p?: number; m?: number; r?: number; t?: number;
  cc?: boolean; cf?: boolean; c4?: boolean; cr?: boolean; c3?: boolean;
  c3n?: boolean; c4i?: boolean; c4n?: boolean;
};

export type Site = {
  s: string; g: string; y: number; x: number; n: number;
  clash?: boolean; soft?: boolean; sec: Sector[];
};

export type KpiRow = { metric: string; description: string; value: number };

export type NetworkData = {
  kpi: {
    total_sectors: number; total_sites: number; source: string;
    validation?: { pass: boolean; hard: Record<string, number>; soft: Record<string, number>; coverage: Record<string, number> };
    summary?: { source: string; status: string; hard_issues: number; soft_issues: number; hard: Record<string, number>; soft: Record<string, number>; coverage?: Record<string, number> };
    mod4_clash_count: number; rsi_clash_count: number; pci_collision_count: number;
    pci_confusion_count: number; mod3_soft_count: number;
    pci_range_used: [number, number]; rsi_range_used: [number, number];
    regions: Record<string, { sectors: number; sites: number; mod4_clash: number; rsi_clash: number; mod3_soft: number }>;
    stats_report: KpiRow[];
  };
  sites: Site[];
};

export type SectorRow = {
  id: string; site: string; region: string; lat: number; lon: number; az: number;
  pci?: number; mod4?: number; rsi?: number; mod3?: number;
  c4: boolean; cc: boolean; cr: boolean; c3: boolean; cf: boolean;
  c3n?: boolean; c4i?: boolean; c4n?: boolean;
};

// Bare sector row - no clash flags, no validation. pci/mod4/rsi can be
// null for a not-yet-planned sector. Used by the Voronoi Compare tab so
// an old / partial / differently-shaped workbook can never error here.
export type RawSectorRow = {
  id: string; site: string; lat: number; lon: number; az: number;
  pci: number | null; mod4: number | null; rsi: number | null;
};

export type ToolCall = { name: string; input: Record<string, any>; result: any };
export type AgentReply = { reply: string; tool_calls: ToolCall[]; model: string };
export type ClashDefinition = { label: string; severity: string; threshold: string; rule: string; source: string };
export type PlanAssignment = { pci: number; mod4: number; rsi: number };
export type ReplanEditorOptions = { valid_pci: number[]; suggested_pci: number[]; valid_mod4: number[]; valid_mod3: number[] };
export type ExistingReplanPreview = {
  old: Record<string, PlanAssignment>;
  assignments: Record<string, PlanAssignment>;
  neighbors: { sector: string; neighbor: string; pci: number; mod4: number; rsi: number }[];
  editor_options: Record<string, ReplanEditorOptions>;
};

export const api = {
  workbooks: () => req<{ id: string; label: string }[]>('/api/workbooks'),
  network: (workbook: string) => req<NetworkData>(`/api/network?workbook=${encodeURIComponent(workbook)}`),
  raw: (workbook = 'raw') => req<NetworkData>(`/api/raw?workbook=${encodeURIComponent(workbook)}`),
  sectors: (workbook: string) => req<SectorRow[]>(`/api/sectors?workbook=${encodeURIComponent(workbook)}`),
  sectorsRaw: (workbook: string) => req<RawSectorRow[]>(`/api/sectors_raw?workbook=${encodeURIComponent(workbook)}`),
  // api.ts — replace the existing `upload` entry and add `uploadFinal`
  upload: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);
    return res.json() as Promise<{ workbook: string; label: string; sectors: number; sites: number }>;
  },
  uploadFinal: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/api/upload_final`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);
    return res.json() as Promise<{
      workbook: string; label: string; sectors: number; sites: number;
      pass: boolean; collisions: number; confusions: number; mod3: number;
    }>;
},
  replan: (workbook: string) => req<{ workbook: string; written: number; pass: boolean; collisions: number; confusions: number; mod3: number }>(
    `/api/replan?workbook=${encodeURIComponent(workbook)}`, { method: 'POST' }
  ),
  explain: (sectorId: string, workbook: string) =>
    req<any>(`/api/explain/${encodeURIComponent(sectorId)}?workbook=${encodeURIComponent(workbook)}`),
  chat: (workbook: string, message: string) =>
    req<{ reply: string }>('/api/chat', { method: 'POST', body: JSON.stringify({ workbook, message }) }),
  agentTools: () => req<{ name: string; description: string }[]>('/api/agent/tools'),
  agentInfo: () => req<{ model: string; url: string }>('/api/agent/info'),
  agentChat: (workbook: string, message: string, model: 'claude' | 'ollama', history: { role: string; content: string }[] = []) =>
    req<AgentReply>('/api/agent/chat', { method: 'POST', body: JSON.stringify({ workbook, message, model, history }) }),
  clashInfo: () => req<Record<string, ClashDefinition>>('/api/clash_info'),
  clashInfoForSector: (sectorId: string, workbook: string) =>
    req<{ definition?: ClashDefinition; live_explanation?: any }>(`/api/clash_info/${encodeURIComponent(sectorId)}?workbook=${encodeURIComponent(workbook)}`),
  addSiteNewPreview: (workbook: string, site_id: string, lat: number, lon: number, azimuths: number[]) =>
    req<any>(`/api/addsite/new/preview?workbook=${encodeURIComponent(workbook)}`, {
      method: 'POST', body: JSON.stringify({ site_id, lat, lon, azimuths }),
    }),
  addSiteNewCommit: (tmp_id: string, assignments: any) =>
    req<any>('/api/addsite/new/commit', { method: 'POST', body: JSON.stringify({ tmp_id, assignments }) }),
  replanSitePreview: (workbook: string, target_site: string) =>
    req<ExistingReplanPreview>('/api/replan_site/preview', { method: 'POST', body: JSON.stringify({ workbook, target_site }) }),
  replanSiteOptions: (workbook: string, target_site: string, assignments: Record<string, PlanAssignment>, mod3_choices: Record<string, number>) =>
    req<{ editor_options: Record<string, ReplanEditorOptions> }>('/api/replan_site/options', {
      method: 'POST', body: JSON.stringify({ workbook, target_site, assignments, mod3_choices }),
    }),
  replanSiteCommit: (workbook: string, assignments: any) =>
    req<any>('/api/replan_site/commit', { method: 'POST', body: JSON.stringify({ workbook, assignments }) }),
  downloadUrl: (workbook: string) => `${API_BASE}/api/download?workbook=${encodeURIComponent(workbook)}`,
};