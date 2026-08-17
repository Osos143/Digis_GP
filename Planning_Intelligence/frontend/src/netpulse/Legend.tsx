// src/netpulse/Legend.tsx - port of core/mapview.py's LEGENDS dict: a
// gradient bar with min/mid/max labels for PCI/RSI, or colored swatches
// with plain-English labels for Mod4/Mod3/Clashes/Sectors.
import type { LayerMode } from './colors';

const LEGENDS: Record<LayerMode, { kind: 'gradient'; stops: string[]; labels: string[] } | { kind: 'swatches'; items: [string, string][] }> = {
  Regions: { kind: 'swatches', items: [['Alexandria', '#2563EB'], ['Sinai', '#DC2626'], ['Upper Egypt', '#10B981'], ['Delta', '#F59E0B']] },
  Sectors: { kind: 'swatches', items: [['Not yet planned', '#94A3B8']] },
  PCI: { kind: 'gradient', stops: ['#274690', '#0EA5E9', '#33D6B0', '#F9A825', '#D32F2F'], labels: ['0', '504', '1007'] },
  RSI: { kind: 'gradient', stops: ['#2D1B69', '#7C3AED', '#33D6B0', '#FACC15'], labels: ['0', '415', '830'] },
  Mod4: { kind: 'swatches', items: [['Group 0', '#00ACC1'], ['Group 1', '#1565C0'], ['Group 2', '#F9A825'], ['Group 3', '#D32F2F']] },
  Mod3: { kind: 'swatches', items: [['Group 0', '#00ACC1'], ['Group 1', '#1565C0'], ['Group 2', '#FACC15']] },
  Clashes: {
    kind: 'swatches', items: [
      ['Clear', '#2E7D32'],
      ['PCI collision \u00b7 7km \u00b7 hard', '#D32F2F'],
      ['PCI confusion \u00b7 14km \u00b7 hard', '#EC4899'],
      ['RSI reuse \u00b7 14km \u00b7 hard', '#1565C0'],
      ['Mod3 adjacent \u00b7 hard', '#111827'],
      ['Mod4 intra-site \u00b7 hard', '#7C3AED'],
      ['Mod4 inter-site \u00b7 soft', '#F9A825'],
      ['Mod3 non-adj reuse \u00b7 soft', '#0EA5E9'],
      ['Mod4 non-adj intra-site \u00b7 soft', '#34D399'],
    ],
  },
};

export function Legend({ layerMode }: { layerMode: LayerMode }) {
  const spec = LEGENDS[layerMode];
  return (
    <div className="bg-white border border-[var(--color-border)] rounded-lg px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">{layerMode}</div>
      {spec.kind === 'gradient' ? (
        <div>
          <div className="h-2.5 rounded-full mb-1.5" style={{ background: `linear-gradient(90deg, ${spec.stops.join(',')})` }} />
          <div className="flex justify-between text-[10px] font-mono text-gray-400">
            {spec.labels.map((l) => <span key={l}>{l}</span>)}
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {spec.items.map(([label, color]) => (
            <div key={label} className="flex items-center gap-1.5 text-xs text-gray-700">
              <span className="w-2.5 h-2.5 rounded-sm inline-block shrink-0" style={{ background: color }} />
              {label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
