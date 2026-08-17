// src/netpulse/colors.ts
//
// Direct TS port of the color/clash logic in utils.py - same stops, same
// thresholds, same "worst clash type wins" ordering, so a wedge on this
// map means exactly what it meant in the Streamlit app.

// Both Sector (from network JSON, used by the map) and SectorRow (flat
// table rows) carry the same clash flags / p/m/r/t fields - this is the
// minimal shape every helper below actually needs, so both satisfy it.
type ClashFlaggable = {
  p?: number; m?: number; r?: number; t?: number;
  cc?: boolean; cf?: boolean; c4?: boolean; cr?: boolean; c3?: boolean;
  c3n?: boolean; c4i?: boolean; c4n?: boolean;
};

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function multiStop(stops: [number, string][]) {
  return (v: number): string => {
    for (let i = 0; i < stops.length - 1; i++) {
      const [v0, c0] = stops[i];
      const [v1, c1] = stops[i + 1];
      if (v >= v0 && v <= v1) {
        const t = (v - v0) / (v1 - v0);
        const [r0, g0, b0] = hexToRgb(c0);
        const [r1, g1, b1] = hexToRgb(c1);
        const r = Math.round(r0 + (r1 - r0) * t);
        const g = Math.round(g0 + (g1 - g0) * t);
        const b = Math.round(b0 + (b1 - b0) * t);
        return `rgb(${r},${g},${b})`;
      }
    }
    return stops[stops.length - 1][1];
  };
}

export const PCI_SCALE = multiStop([[0, '#274690'], [252, '#0EA5E9'], [504, '#33D6B0'], [756, '#F9A825'], [1007, '#D32F2F']]);
export const RSI_SCALE = multiStop([[0, '#2D1B69'], [277, '#7C3AED'], [554, '#33D6B0'], [830, '#FACC15']]);

export const MOD4_COLORS: Record<number, string> = { 0: '#00ACC1', 1: '#1565C0', 2: '#F9A825', 3: '#D32F2F' };
export const MOD3_COLORS: Record<number, string> = { 0: '#00ACC1', 1: '#1565C0', 2: '#FACC15' };
export const NEUTRAL_RGB = '#94A3B8';
export const REGION_COLORS: Record<string, string> = {
  ALX: '#2563EB',
  SIN: '#DC2626',
  UPP: '#10B981',
  DEL: '#F59E0B',
  UNK: '#64748B',
};

export const CLASH_TYPE_COLORS: Record<string, string> = {
  collision: '#D32F2F',    // PCI collision - hard, 7km (worst)
  confusion: '#EC4899',    // PCI confusion - hard, 14km
  rsi: '#1565C0',          // RSI reuse - hard
  mod3: '#111827',         // Mod3 adjacent - hard
  mod4_intra: '#7C3AED',   // Mod4 intra-site adjacent - hard
  mod4: '#F9A825',         // Mod4 inter-site - soft
  mod3_non_adj: '#0EA5E9', // Mod3 non-adjacent reuse - soft
  mod4_non_adj: '#34D399', // Mod4 non-adjacent intra-site - soft
  clear: '#2E7D32',
};

export const CLASH_TYPE_LABELS: Record<string, string> = {
  clear: 'Clear',
  collision: 'PCI collision (7km, hard)',
  confusion: 'PCI confusion (14km, hard)',
  rsi: 'RSI reuse (14km, hard)',
  mod3: 'Mod3 adjacent (hard)',
  mod4_intra: 'Mod4 intra-site (hard)',
  mod4: 'Mod4 inter-site (soft)',
  mod3_non_adj: 'Mod3 non-adj reuse (soft)',
  mod4_non_adj: 'Mod4 non-adj intra-site (soft)',
};

export const CLASH_TYPE_ORDER = [
  'collision', 'confusion', 'rsi', 'mod3', 'mod4_intra',
  'mod4', 'mod3_non_adj', 'mod4_non_adj', 'clear',
] as const;

export function sectorHasType(sec: ClashFlaggable, type: string): boolean {
  if (type === 'collision') return !!sec.cc;
  if (type === 'confusion') return !!sec.cf;
  if (type === 'rsi') return !!sec.cr;
  if (type === 'mod3') return !!sec.c3;
  if (type === 'mod4_intra') return !!sec.c4i;
  if (type === 'mod4') return !!sec.c4;
  if (type === 'mod3_non_adj') return !!sec.c3n;
  if (type === 'mod4_non_adj') return !!sec.c4n;
  if (type === 'clear') {
    return !sec.cc && !sec.cf && !sec.cr && !sec.c3 && !sec.c4i && !sec.c4 && !sec.c3n && !sec.c4n;
  }
  return false;
}

export function clashType(sec: ClashFlaggable): string {
  if (sec.cc) return 'collision';
  if (sec.cf) return 'confusion';
  if (sec.cr) return 'rsi';
  if (sec.c3) return 'mod3';
  if (sec.c4i) return 'mod4_intra';
  if (sec.c4) return 'mod4';
  if (sec.c3n) return 'mod3_non_adj';
  if (sec.c4n) return 'mod4_non_adj';
  return 'clear';
}

export function statusLabel(sec: ClashFlaggable): string {
  const flags: string[] = [];
  if (sec.cc) flags.push('PCI collision (7km, hard)');
  if (sec.cf) flags.push('PCI confusion (14km, hard)');
  if (sec.cr) flags.push('RSI reuse (14km, hard)');
  if (sec.c3) flags.push('Mod3 adjacent (hard)');
  if (sec.c4i) flags.push('Mod4 intra-site (hard)');
  if (sec.c4) flags.push('Mod4 inter-site (soft)');
  if (sec.c3n) flags.push('Mod3 non-adj reuse (soft)');
  if (sec.c4n) flags.push('Mod4 non-adj intra-site (soft)');
  return flags.length ? flags.join(' \u00b7 ') : 'Clear - no conflicts';
}

export function statusOf(sec: ClashFlaggable): 'clear' | 'soft' | 'crit' {
  if (sec.cc || sec.cf || sec.cr || sec.c3 || sec.c4i) return 'crit';
  if (sec.c4 || sec.c3n || sec.c4n) return 'soft';
  return 'clear';
}

export type LayerMode = 'Regions' | 'PCI' | 'Mod4' | 'RSI' | 'Mod3' | 'Clashes' | 'Sectors';

export function regionColorFor(regionCode?: string): string {
  const normalized = (regionCode || 'UNK').toUpperCase();
  return REGION_COLORS[normalized] || REGION_COLORS.UNK;
}

export function colorFor(sec: ClashFlaggable, layerMode: LayerMode, regionCode?: string): string {
  if (layerMode === 'Regions') return regionColorFor(regionCode);
  if (layerMode === 'Sectors') return NEUTRAL_RGB;
  if (layerMode === 'PCI') return sec.p != null ? PCI_SCALE(sec.p) : NEUTRAL_RGB;
  if (layerMode === 'RSI') return sec.r != null ? RSI_SCALE(sec.r) : NEUTRAL_RGB;
  if (layerMode === 'Mod4') return sec.m != null ? MOD4_COLORS[sec.m] : NEUTRAL_RGB;
  if (layerMode === 'Mod3') return sec.t != null ? MOD3_COLORS[sec.t] : NEUTRAL_RGB;
  return CLASH_TYPE_COLORS[clashType(sec)];
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371.0088;
  const p1 = (lat1 * Math.PI) / 180, p2 = (lat2 * Math.PI) / 180;
  const dphi = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
