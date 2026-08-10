const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export interface SessionSummary {
  session_id: string;
  status: string;
  filename?: string;
  current_stage?: string;
  stage_message?: string;
  error: string | null;
  dataset: Record<string, unknown>;
  anomaly_count: number;
  matched_cause_count: number;
  explained_count: number;
  created_at: string;
  updated_at: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speedMBs: number;
}

export interface Anomaly {
  incident_id?: string;
  anomaly_type?: string;
  anomaly_severity?: string;
  anomaly_score?: number;
  cell_id?: string;
  eci?: string;
  pci?: string;
  timestamp?: string;
  actual_lte_dl_throughput?: number;
  expected_tp_p75?: number;
  expected_tp_ml_hgb_resource_q50?: number;
  expected_tp_ml_hgb_temporal_q50?: number;
  expected_tp_ml_q75_resource?: number;
  expected_tp_ml_lstm_q50?: number;
  lte_rsrp?: number;
  lte_rsrq?: number;
  lte_sinr?: number;
  lte_bler?: number;
  lte_cqi?: number;
  lte_mcs?: number;
  rb_usage_value?: number;
  carrier_count?: number;
  latitude?: number;
  longitude?: number;
  speed?: number;
  id?: string;
  [key: string]: unknown;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json();
}

export function uploadDatasetWithProgress(
  file: File,
  onProgress?: (progress: UploadProgress) => void
): Promise<SessionSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const startTime = Date.now();

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const loaded = event.loaded;
        const total = event.total;
        const percentage = Math.round((loaded / total) * 100);
        const elapsedTimeSec = (Date.now() - startTime) / 1000;
        const speedMBs = elapsedTimeSec > 0 ? (loaded / (1024 * 1024)) / elapsedTimeSec : 0;

        if (onProgress) {
          onProgress({ loaded, total, percentage, speedMBs });
        }
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve(data);
        } catch (e) {
          reject(new Error('Invalid JSON response from backend server'));
        }
      } else {
        let errMessage = xhr.statusText;
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.detail) errMessage = res.detail;
        } catch (_) {}
        reject(new Error(`Upload failed (HTTP ${xhr.status}): ${errMessage}`));
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error during file upload. Please verify the backend is running.'));
    };

    xhr.ontimeout = () => {
      reject(new Error('Upload request timed out.'));
    };

    const form = new FormData();
    form.append('file', file);

    xhr.open('POST', `${API_BASE}/sessions`);
    xhr.send(form);
  });
}

export async function uploadDataset(file: File): Promise<SessionSummary> {
  return uploadDatasetWithProgress(file);
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  return handleResponse<SessionSummary[]>(res);
}

export async function getSession(sessionId: string, full = false): Promise<SessionSummary & { anomalies?: Anomaly[] }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}?full=${full}`);
  return handleResponse(res);
}

export async function getAnomalies(sessionId: string): Promise<Anomaly[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/anomalies`);
  return handleResponse<Anomaly[]>(res);
}

export async function getThresholds(sessionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/thresholds`);
  return handleResponse(res);
}

export async function submitThresholds(
  sessionId: string,
  thresholds?: Record<string, unknown>,
  explain = true,
  anomalyIds?: string[],
): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/thresholds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thresholds, explain, anomaly_ids: anomalyIds }),
  });
  return handleResponse(res);
}

export interface PlotItem {
  id?: string;
  filename: string;
  title: string;
  category: string;
  chart_type?: string;
  x_label?: string;
  y_label?: string;
  png_url: string;
  json_url?: string;
  html_url?: string;
  url?: string;
  size_bytes?: number;
}

export async function listPlots(sessionId: string): Promise<{ session_id: string; count: number; plots: PlotItem[] }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/plots`);
  return handleResponse(res);
}

export interface RCADiagnosis {
  category: string;
  problem_name: string;
  reason: string;
  cause_id: string;
  severity: string;
}

export interface RCASupportingEvidence {
  id: string;
  name: string;
  reason: string;
}

export interface RCARecommendedSolution {
  recommended_actions: string[];
  standards_and_vendor_references: Array<{ source: string; note: string }>;
}

export interface RCAExplanation {
  explanation?: string;
  executive_summary?: string;
  root_cause_narrative?: string;
  supporting_evidence?: string[];
  recommended_actions?: string[];
}

export interface RCAResult {
  incident_id: string;
  diagnosis: RCADiagnosis;
  supporting_evidence?: RCASupportingEvidence[];
  key_kpi_evidence: Record<string, any>;
  recommended_solution: RCARecommendedSolution;
  explanation?: RCAExplanation;
}

export async function getAnomalyIds(sessionId: string): Promise<{ session_id: string; count: number; anomaly_ids: string[] }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/anomalies/ids`);
  return handleResponse(res);
}

export async function analyzeRCA(sessionId: string, anomalyId: string): Promise<{ status: string; source: string; data: RCAResult }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/rca/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ anomaly_id: anomalyId }),
  });
  return handleResponse(res);
}

export async function getCachedRCA(sessionId: string, anomalyId: string): Promise<{ status: string; data: RCAResult }> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/rca/${anomalyId}`);
  return handleResponse(res);
}

export interface ChatMessagePayload {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  status: string;
  response: string;
  thinking?: string;
  model_used: string;
  mode: string;
  fallback?: boolean;
}

export async function sendChatMessage(
  message: string,
  mode: 'chat' | 'reasoning' = 'chat',
  sessionId?: string,
  anomalyId?: string,
  history?: ChatMessagePayload[]
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      mode,
      session_id: sessionId || undefined,
      anomaly_id: anomalyId || undefined,
      history: history && history.length > 0 ? history : undefined,
    }),
  });
  return handleResponse(res);
}

export interface UserProfile {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  initials: string;
}

export interface UserAuthResponse {
  status: string;
  message?: string;
  user: UserProfile;
  token?: string;
}

export async function loginUser(email: string, password: string): Promise<UserAuthResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<UserAuthResponse>(res);
}

export async function registerUser(
  full_name: string,
  email: string,
  password: string,
  role: string = 'Optimization Eng.'
): Promise<UserAuthResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ full_name, email, password, role }),
  });
  return handleResponse<UserAuthResponse>(res);
}
