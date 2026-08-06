"""
core/utils.py - shared helpers for every view. Colour scales, sector-wedge
geometry (for pydeck PolygonLayer), and small formatting helpers.

Nothing here talks to Streamlit or the pipeline modules directly - views
import from here, and from core/state.py for data. Keeping this boundary
means a new view never needs to duplicate a colour scale or the wedge
math.
"""

from __future__ import annotations

import math

EARTH_R_M = 6_371_008.8


# ---------------- geometry (sector wedges for the map) ----------------

def dest_point(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Destination point given a start point, bearing, and distance (spherical)."""
    brg = math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat), math.radians(lon)
    d_r = dist_m / EARTH_R_M
    lat2 = math.asin(math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d_r) * math.cos(lat1),
        math.cos(d_r) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def wedge_polygon(lat: float, lon: float, azimuth: float, radius_m: float = 130, half_angle: float = 34, steps: int = 6) -> list[list[float]]:
    """Pie-slice polygon around (lat, lon) pointing toward `azimuth`.
    Returns [[lon, lat], ...] - pydeck's PolygonLayer wants lon/lat order."""
    pts = [[lon, lat]]
    for i in range(steps + 1):
        a = azimuth - half_angle + (2 * half_angle) * (i / steps)
        plat, plon = dest_point(lat, lon, a, radius_m)
        pts.append([plon, plat])
    pts.append([lon, lat])
    return pts


def circle_polygon(lat: float, lon: float, radius_m: float, steps: int = 72) -> list[list[float]]:
    """A full-circle ring (no center point) around (lat, lon) at `radius_m`
    - used for the Clashes tab's measuring tool, drawn as an unfilled
    outline so it reads as a "how far is this" ruler, not a sector."""
    pts = []
    for i in range(steps + 1):
        a = 360.0 * i / steps
        plat, plon = dest_point(lat, lon, a, radius_m)
        pts.append([plon, plat])
    return pts


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters - used by the Clashes tab to measure
    how far a clicked site's neighbors really are. Matches neighbor_graph.py's
    own 7km/14km thresholds closely enough at these distances (a few meters
    difference at most between this and its flat-earth ENU projection)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(a))


def safe_half_angle(azimuth: float, sibling_azimuths: list[float], default: float = 34.0, min_angle: float = 8.0, margin: float = 3.0) -> float:
    """Shrinks the wedge half-angle when a co-located sector (same site)
    points in a nearby direction, so their wedges don't overlap enough to
    blend into what looks like a single torn/split shape. `sibling_azimuths`
    is every OTHER sector's azimuth at the same site - pass [] for a
    single-sector site to just get `default` back."""
    if not sibling_azimuths:
        return default
    gaps = []
    for other in sibling_azimuths:
        d = abs(azimuth - other) % 360
        gaps.append(min(d, 360 - d))
    return min(default, max(min_angle, min(gaps) / 2 - margin))


# ---------------- colour scales ----------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _multi_stop(stops: list[tuple[float, str]]):
    def scale(v: float) -> list[int]:
        for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
            if v0 <= v <= v1:
                t = (v - v0) / (v1 - v0)
                r0, g0, b0 = _hex_to_rgb(c0)
                r1, g1, b1 = _hex_to_rgb(c1)
                return [int(_lerp(r0, r1, t)), int(_lerp(g0, g1, t)), int(_lerp(b0, b1, t)), 200]
        r, g, b = _hex_to_rgb(stops[-1][1])
        return [r, g, b, 200]
    return scale


PCI_SCALE = _multi_stop([(0, '#274690'), (252, '#0EA5E9'), (504, '#33D6B0'), (756, '#FFA94D'), (1007, '#FF5D5D')])
RSI_SCALE = _multi_stop([(0, '#2D1B69'), (277, '#7C3AED'), (554, '#33D6B0'), (830, '#FACC15')])
MOD4_COLORS = {0: [51, 214, 176, 200], 1: [108, 140, 255, 200], 2: [255, 169, 77, 200], 3: [255, 93, 93, 200]}
MOD3_COLORS = {0: [51, 214, 176, 200], 1: [108, 140, 255, 200], 2: [250, 204, 21, 200]}
NEUTRAL_RGB = [108, 140, 255, 190]
SIGNAL_RGB = [51, 214, 176, 220]
WARN_RGB = [255, 169, 77, 220]
CRIT_RGB = [255, 93, 93, 220]

# One distinct colour per clash TYPE, not just severity - so the map can
# show WHICH rule is violated, not just "something's wrong". Checked in
# this order (most severe first) since one sector can have several flags
# at once but a wedge can only show one colour.
COLLISION_RGB = [255, 59, 59, 230]    # PCI collision  - hard, 7km  (worst)
CONFUSION_RGB = [255, 79, 216, 230]   # PCI confusion  - hard, 14km
MOD4_CLASH_RGB = [255, 169, 77, 220]  # Mod4 clash     - soft, structural
RSI_REUSE_RGB = [108, 140, 255, 220]  # RSI reuse      - soft
MOD3_SOFT_RGB = [250, 204, 21, 220]   # Mod3 soft      - soft, pigeonhole


def status_of(sec: dict) -> str:
    if sec.get("c4") or sec.get("cc") or sec.get("cr") or sec.get("cf"):
        return "crit"
    if sec.get("c3"):
        return "soft"
    return "clear"


def clash_type(sec: dict) -> str:
    """Which single clash type to show for this sector, worst first."""
    if sec.get("cc"):
        return "collision"
    if sec.get("cf"):
        return "confusion"
    if sec.get("c4"):
        return "mod4"
    if sec.get("cr"):
        return "rsi"
    if sec.get("c3"):
        return "mod3"
    return "clear"


CLASH_TYPE_COLORS = {
    "collision": COLLISION_RGB, "confusion": CONFUSION_RGB, "mod4": MOD4_CLASH_RGB,
    "rsi": RSI_REUSE_RGB, "mod3": MOD3_SOFT_RGB, "clear": SIGNAL_RGB,
}


def status_label(sec: dict) -> str:
    flags = []
    if sec.get("cc"):
        flags.append("PCI collision (7km, hard)")
    if sec.get("cf"):
        flags.append("PCI confusion (14km, hard)")
    if sec.get("c4"):
        flags.append("Mod4 clash (soft)")
    if sec.get("cr"):
        flags.append("RSI reuse (soft)")
    if sec.get("c3"):
        flags.append("Mod3 soft (soft)")
    return " · ".join(flags) if flags else "Clear - no conflicts"


def color_for(sec: dict, layer_mode: str) -> list[int]:
    """Colour for one sector wedge/dot. 'Sectors' mode needs no PCI/RSI/Mod4
    at all - it's what "before planning" uses, when those fields don't exist yet."""
    if layer_mode == "Sectors":
        return NEUTRAL_RGB
    if layer_mode == "PCI":
        return PCI_SCALE(sec["p"])
    if layer_mode == "RSI":
        return RSI_SCALE(sec["r"])
    if layer_mode == "Mod4":
        return MOD4_COLORS[sec["m"]]
    if layer_mode == "Mod3":
        return MOD3_COLORS[sec["t"]]
    return CLASH_TYPE_COLORS[clash_type(sec)]


def fmt(n) -> str:
    return f"{n:,}"


def pct(n, d) -> str:
    return f"{(100 * n / d):.1f}" if d else "0.0"
