// src/netpulse/voronoi.ts
//
// Minimal bounded Voronoi diagram via half-plane clipping (Sutherland-
// Hodgman against each perpendicular bisector). Exact geometry, no extra
// dependency - fine for the small point counts (a handful of sectors)
// this view ever deals with.

export type Pt = [number, number];

const EARTH_R = 6_371_000;

export function project(lat: number, lon: number, lat0: number, lon0: number): Pt {
  const x = EARTH_R * ((lon - lon0) * Math.PI) / 180 * Math.cos((lat0 * Math.PI) / 180);
  const y = EARTH_R * ((lat - lat0) * Math.PI) / 180;
  return [x, y];
}

export function unproject(x: number, y: number, lat0: number, lon0: number): [number, number] {
  const lat = lat0 + (y / EARTH_R) * (180 / Math.PI);
  const lon = lon0 + (x / (EARTH_R * Math.cos((lat0 * Math.PI) / 180))) * (180 / Math.PI);
  return [lat, lon];
}

type Tag = { kind: 'bbox' } | { kind: 'clip'; other: string };
type VPt = { p: Pt; tag: Tag };

function clipHalfPlane(poly: VPt[], site: Pt, other: Pt, otherId: string): VPt[] {
  const mx = (site[0] + other[0]) / 2, my = (site[1] + other[1]) / 2;
  const dx = other[0] - site[0], dy = other[1] - site[1];
  const side = (p: Pt) => (p[0] - mx) * dx + (p[1] - my) * dy; // < 0 => closer to `site`
  const inter = (p1: Pt, p2: Pt): VPt => {
    const f1 = side(p1), f2 = side(p2);
    const t = f1 / (f1 - f2);
    return { p: [p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1])], tag: { kind: 'clip', other: otherId } };
  };
  const out: VPt[] = [];
  for (let i = 0; i < poly.length; i++) {
    const cur = poly[i], prev = poly[(i - 1 + poly.length) % poly.length];
    const curIn = side(cur.p) < 0, prevIn = side(prev.p) < 0;
    if (curIn) {
      if (!prevIn) out.push(inter(prev.p, cur.p));
      out.push(cur);
    } else if (prevIn) {
      out.push(inter(prev.p, cur.p));
    }
  }
  return out;
}

export type VoronoiSeed = { id: string; x: number; y: number };
export type VoronoiEdge = { a: string; b: string; seg: [Pt, Pt] };

export function boundedVoronoi(seeds: VoronoiSeed[], bbox: { minX: number; minY: number; maxX: number; maxY: number }) {
  const bboxPoly: VPt[] = [
    { p: [bbox.minX, bbox.minY], tag: { kind: 'bbox' } },
    { p: [bbox.maxX, bbox.minY], tag: { kind: 'bbox' } },
    { p: [bbox.maxX, bbox.maxY], tag: { kind: 'bbox' } },
    { p: [bbox.minX, bbox.maxY], tag: { kind: 'bbox' } },
  ];

  const cells = new Map<string, Pt[]>();
  const edgesMap = new Map<string, VoronoiEdge>();

  for (const s of seeds) {
    let poly = bboxPoly;
    for (const o of seeds) {
      if (o.id === s.id || !poly.length) continue;
      poly = clipHalfPlane(poly, [s.x, s.y], [o.x, o.y], o.id);
    }
    cells.set(s.id, poly.map((v) => v.p));

    for (let i = 0; i < poly.length; i++) {
      const v1 = poly[i], v2 = poly[(i + 1) % poly.length];
      if (v1.tag.kind === 'clip' && v2.tag.kind === 'clip' && v1.tag.other === v2.tag.other) {
        const other = v1.tag.other;
        const key = [s.id, other].sort().join('|');
        if (!edgesMap.has(key)) edgesMap.set(key, { a: s.id, b: other, seg: [v1.p, v2.p] });
      }
    }
  }

  return { cells, edges: Array.from(edgesMap.values()) };
}

// Simple average-of-vertices centroid - good enough for the small,
// mostly-convex cells this view ever deals with, used to place each
// polygon's ID-tag label.
export function centroid(poly: Pt[]): Pt {
  const n = poly.length || 1;
  const sx = poly.reduce((a, p) => a + p[0], 0);
  const sy = poly.reduce((a, p) => a + p[1], 0);
  return [sx / n, sy / n];
}

export type Adjacency = { a: string; b: string; seg: [Pt, Pt] };

// Robust adjacency detection: for every edge of every finished cell,
// take its midpoint and find the two seeds nearest to it. On a genuine
// shared Voronoi boundary those two distances are (almost) equal - the
// cell's own owner and its true neighbor across that edge. This reads
// adjacency directly from final geometry, so it can't miss an edge that
// got interrupted mid-way by a third seed's clip (the earlier bug:
// tracking adjacency via clip-order bookkeeping in boundedVoronoi's own
// `edges` return silently dropped any edge a third seed's bisector
// happened to cut through partway along).
export function cellAdjacencies(seeds: VoronoiSeed[], cells: Map<string, Pt[]>): Adjacency[] {
  const results: Adjacency[] = [];
  const seen = new Set<string>();

  for (const s of seeds) {
    const poly = cells.get(s.id);
    if (!poly || poly.length < 2) continue;

    for (let i = 0; i < poly.length; i++) {
      const p1 = poly[i], p2 = poly[(i + 1) % poly.length];
      const mid: Pt = [(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2];

      let best = Infinity, second = Infinity, bestId = '', secondId = '';
      for (const t of seeds) {
        const d = Math.hypot(mid[0] - t.x, mid[1] - t.y);
        if (d < best) { second = best; secondId = bestId; best = d; bestId = t.id; }
        else if (d < second) { second = d; secondId = t.id; }
      }

      const tol = Math.max(0.5, best * 1e-3); // meters - generous enough to absorb float noise, tight enough not to false-positive on bbox edges
      const isRealEdge = bestId && secondId && Math.abs(best - second) < tol && (bestId === s.id || secondId === s.id);
      if (!isRealEdge) continue; // this edge borders the panel frame, not another cell

      const neighborId = bestId === s.id ? secondId : bestId;
      const key = [s.id, neighborId].sort().join('|') + '@' + mid.map((v) => v.toFixed(1)).join(',');
      if (seen.has(key)) continue;
      seen.add(key);
      results.push({ a: s.id, b: neighborId, seg: [p1, p2] });
    }
  }

  return results;
}