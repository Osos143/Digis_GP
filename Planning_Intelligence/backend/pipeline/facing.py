"""
facing.py - Shared geometry: bearing, distance, alignment, interference potential.

Used by both assignment_engine.py (Mod4 planning) and validator.py (KPI check).
Keeping geometry in one file guarantees planner and validator agree on what
"facing" means.

The alignment model uses pure vector geometry (cosine projection).
No tuned constants: every number is either physical (Earth radius) or
falls out of the geometry itself.
"""
import math

EARTH_RADIUS_M = 6_371_000.0  # WGS84 mean Earth radius (physical constant)


# --- basic geometry ------------------------------------------------------------
def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing (0=N, 90=E) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def angle_diff(a: float, b: float) -> float:
    """Smallest difference between two compass angles, in [0, 180]."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def distance_m(a: dict, b: dict) -> float:
    """Great-circle distance between two sectors in meters (haversine)."""
    phi1, phi2 = math.radians(a["lat"]), math.radians(b["lat"])
    dphi = math.radians(b["lat"] - a["lat"])
    dlam = math.radians(b["lon"] - a["lon"])
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


# --- alignment / interference --------------------------------------------------
def alignment(a: dict, b: dict) -> float:
    """
    How much of a's main beam points at b.  Cosine of angular offset,
    clamped to [0, 1].

    offset = 0°  (dead ahead)      -> 1.0
    offset = 60°                    -> 0.5
    offset >= 90° (perpendicular)   -> 0.0

    Returns 0.0 if the two sectors are at the same location (bearing
    undefined - co-site pairs are handled by a separate rule).
    """
    if a["lat"] == b["lat"] and a["lon"] == b["lon"]:
        return 0.0
    bearing = bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"])
    offset = angle_diff(a["azimuth"], bearing)
    return max(0.0, math.cos(math.radians(offset)))


def interference_potential(a: dict, b: dict, distance: float | None = None) -> float:
    """
    Physical interference weight between two sectors:
        (alignment(a, b) + alignment(b, a)) / distance^2

    Returns 0 if neither antenna points at the other.  Used by the
    planner to prioritize which clashes to fix first (larger = worse).
    """
    ab = alignment(a, b)
    ba = alignment(b, a)
    if ab == 0.0 and ba == 0.0:
        return 0.0
    d = distance if distance is not None else distance_m(a, b)
    if d <= 0:
        return 0.0
    return (ab + ba) / (d * d)


def is_facing(a: dict, b: dict) -> bool:
    """
    True if at least one antenna has a component pointing at the other.
    Fast check that doesn't require computing distance.
    """
    return alignment(a, b) > 0.0 or alignment(b, a) > 0.0