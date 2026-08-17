// src/netpulse/geo.ts
//
// Port of core/utils.py's dest_point()/wedge_polygon() - the same sector
// wedge geometry the old pydeck map used, now producing [lat, lon] pairs
// (Leaflet's coordinate order) instead of pydeck's [lon, lat].

const EARTH_R_M = 6_371_008.8;

export function destPoint(lat: number, lon: number, bearingDeg: number, distM: number): [number, number] {
  const brg = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180, lon1 = (lon * Math.PI) / 180;
  const dR = distM / EARTH_R_M;
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(dR) + Math.cos(lat1) * Math.sin(dR) * Math.cos(brg));
  const lon2 = lon1 + Math.atan2(
    Math.sin(brg) * Math.sin(dR) * Math.cos(lat1),
    Math.cos(dR) - Math.sin(lat1) * Math.sin(lat2),
  );
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

/** Pie-slice polygon around (lat, lon) pointing toward `azimuth`, as
 * [lat, lon] pairs ready for a Leaflet <Polygon positions=...>. */
export function wedgePolygon(lat: number, lon: number, azimuth: number, radiusM = 120, halfAngle = 28, steps = 6): [number, number][] {
  const pts: [number, number][] = [[lat, lon]];
  for (let i = 0; i <= steps; i++) {
    const a = azimuth - halfAngle + (2 * halfAngle) * (i / steps);
    pts.push(destPoint(lat, lon, a, radiusM));
  }
  pts.push([lat, lon]);
  return pts;
}

/** Shrinks a wedge's half-angle when a co-located sibling sector points
 * nearby, so two overlapping wedges at the same site stay visually
 * distinguishable - port of core/utils.py's safe_half_angle(). */
export function safeHalfAngle(azimuth: number, siblingAzimuths: number[], fallback = 28, minAngle = 8, margin = 3): number {
  if (!siblingAzimuths.length) return fallback;
  let smallestGap = Infinity;
  for (const other of siblingAzimuths) {
    const d = Math.abs(azimuth - other) % 360;
    smallestGap = Math.min(smallestGap, Math.min(d, 360 - d));
  }
  return Math.min(fallback, Math.max(minAngle, smallestGap / 2 - margin));
}

/** Centre + zoom that frames a set of [lat, lon] points - used to fit the
 * map to whichever region/subset is currently on screen. */
export function bboxOf(points: [number, number][]): { center: [number, number]; bounds: [[number, number], [number, number]] } | null {
  if (!points.length) return null;
  const lats = points.map((p) => p[0]);
  const lons = points.map((p) => p[1]);
  const latMin = Math.min(...lats), latMax = Math.max(...lats);
  const lonMin = Math.min(...lons), lonMax = Math.max(...lons);
  return {
    center: [(latMin + latMax) / 2, (lonMin + lonMax) / 2],
    bounds: [[latMin, lonMin], [latMax, lonMax]],
  };
}
