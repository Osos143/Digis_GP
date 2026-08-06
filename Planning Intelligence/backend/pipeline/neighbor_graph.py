"""
neighbor_graph.py - Stage 2 of the PCI + Mod4/Mod3 + RSI planning pipeline.

Builds a spatial neighbor graph over list[dict] sectors (from loader.py) using a KD-tree.

Two tiers, matching the two failure modes PCI/RSI planning has to avoid:
    - tier1 ("direct", default 7 km): sectors that can physically see each other -> must not share the same PCI/RSI (collision).
    - tier2 ("extended", default 14 km): sectors within this wider radius-> must not share the same PCI either (confusion),
         since a UE could report the same PCI from two genuinely different physical cells.

Distances are computed on a local flat-earth (ENU) projection centered on
the dataset's centroid - accurate enough for cell-planning distances (tens of km) without a full geodesy library.

A "graph" here is just a plain dict:
    {
        "ids": [site_sector_id, ...],
        "tier1": {site_sector_id: [(neighbor_id, dist_m), ...]},
        "tier2": {site_sector_id: [(neighbor_id, dist_m), ...]},
        "tier1_radius_m": float,
        "tier2_radius_m": float,
    }

Results are cached to disk keyed on a hash of (sector ids + coords, radii), so re-running on an unchanged dataset skips the KD-tree rebuild.
"""

import hashlib
import json
import pickle
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_TIER1_M = 7_000.0   # direct neighbor radius (mod3/mod4, collision)
DEFAULT_TIER2_M = 14_000.0  # extended radius (confusion, RSI reuse)
CACHE_DIR = Path(".cache")

# Priority stages assignment_engine.assign_mod4() resolves in strict order,
# and validator.check_mod4_staged_conflicts() measures in the same order -
# a single shared definition so planning and validation can never drift
# apart on what "priority" means. See ranked_inter_site_neighbors() below.
MOD4_STAGE_NAMES = ("rank1", "rank2_5", "rest_tier1", "tier2_only")


# -- Public API -------------------------------------------------------------------
def direct_neighbors(graph: dict, sector_id: str) -> list[str]:
    return [n for n, _ in graph["tier1"].get(sector_id, [])] # return list of direct neighbor IDs for a given sector ID and ignore distances


def extended_neighbors(graph: dict, sector_id: str) -> list[str]:
    return [n for n, _ in graph["tier2"].get(sector_id, [])] # return list of extended neighbor IDs for a given sector ID and ignore distances


def ranked_inter_site_neighbors(graph: dict, sector_id: str, site_of: dict[str, str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Split a sector's neighbors (excluding co-site siblings) into four
    priority groups, nearest-to-farthest within each group, matching
    MOD4_STAGE_NAMES:
        rank1:      the single nearest inter-site neighbor
        rank2_5:    the 2nd-to-5th nearest
        rest_tier1: any remaining Tier-1 (<=7km) neighbors
        tier2_only: Tier-2 (<=14km) neighbors not already counted in Tier-1

    tier1/tier2 lists are already sorted by distance (see
    build_neighbor_graph), so plain slicing/filtering preserves
    nearest-first order - no re-sorting needed here.

    Co-site pairs (distance 0, same site) are always excluded - those are
    governed by a separate co-site rule (see assignment_engine.assign_mod4
    and constraints.ring_adjacent_ids), not this inter-site priority.
    """
    site_id = site_of.get(sector_id)
    tier1 = [nb for nb, _ in graph["tier1"].get(sector_id, []) if site_of.get(nb) != site_id]
    tier1_set = set(tier1)
    tier2_only = [nb for nb, _ in graph["tier2"].get(sector_id, []) if site_of.get(nb) != site_id and nb not in tier1_set]
    return tier1[:1], tier1[1:5], tier1[5:], tier2_only


# -- Internal helpers ---------------------------------------------------------------
def _latlon_to_enu(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Project lat/lon (degrees) to local flat-earth ENU meters around the centroid .""" # East-North-Up (ENU) coordinate system 
    
    # Compute the centroid of the dataset in radians 
    lat0 = np.radians(lats.mean())
    lon0 = np.radians(lons.mean())
    
    # Convert lat/lon to radians
    lat_r = np.radians(lats)
    lon_r = np.radians(lons)

    # Compute ENU coordinates in meters using the equirectangular approximation
    x = EARTH_RADIUS_M * (lon_r - lon0) * np.cos(lat0)   # east (x-axis)
    y = EARTH_RADIUS_M * (lat_r - lat0)                  # north (y-axis)
    return np.column_stack([x, y])

# -- Caching ------------------------------------------------------------------------
def _cache_key(sectors: list[dict], tier1_m: float, tier2_m: float) -> str:
    '''Compute a cache key based on the sector IDs, coordinates, and tier radii.'''
    payload = json.dumps(
        {
            "ids": [s["site_sector_id"] for s in sectors],
            "coords": [(round(s["lat"], 6), round(s["lon"], 6)) for s in sectors],
            "tier1_m": tier1_m,
            "tier2_m": tier2_m,
        },
        sort_keys=True,
    ).encode() # create a JSON string of the sector , then encode it to bytes
    return hashlib.sha256(payload).hexdigest()[:16] # return the first 16 characters of the SHA-256 hash of the payload as the cache key


# -- KD-tree neighbor search --------------------------------------------------------
def _tier_from_tree(tree: cKDTree, coords: np.ndarray, ids: list[str], radius_m: float) -> dict:
    '''Build a tiered neighbor list for each sector using the KD-tree.'''
    
    tier: dict[str, list[tuple[str, float]]] = {sid: [] for sid in ids} # initialize a dictionary to hold the neighbor lists for each sector ID
    pairs = tree.query_pairs(r=radius_m, output_type="ndarray") # find all pairs of points within the specified radius using the KD-tree excluding self-pairs in index form (i, j)
    
    if len(pairs):
        dists = np.linalg.norm(coords[pairs[:, 0]] - coords[pairs[:, 1]], axis=1) # compute the Euclidean distance between each pair of coordinates
    else:
        dists = np.array([]) # if there are no pairs, create an empty array for distances
    
    for (i, j), d in zip(pairs, dists):
        tier[ids[i]].append((ids[j], float(d))) # add the neighbor (with distance) to the list for sector i
        tier[ids[j]].append((ids[i], float(d))) # add the neighbor (with distance) to the list for sector j (mutual neighbors)
    
    # Sort the neighbor lists for each sector by distance
    for sid in ids:
        tier[sid].sort(key=lambda t: t[1])
    
    return tier

# -- Main function -------------------------------------------------------------------
def build_neighbor_graph(
    sectors: list[dict],
    tier1_m: float = DEFAULT_TIER1_M,
    tier2_m: float = DEFAULT_TIER2_M,
    use_cache: bool = True ) -> dict:
    """
    Build tiered neighbor lists for every sector using a KD-tree over the projected coordinates.

    Note: sectors on the same site (identical lat/lon, different azimuth)
    are always mutual tier1 neighbors at distance 0 - intentional, since
    co-sited sectors are the tightest possible reuse-distance case.
    """
    if not sectors:
        return {"ids": [], "tier1": {}, "tier2": {}, "tier1_radius_m": tier1_m, "tier2_radius_m": tier2_m} # return an empty graph if there are no sectors

    cache_path = None
    # Check if caching is enabled and if so, create the cache directory and compute the cache key for the given sectors and tier radii 
    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        key = _cache_key(sectors, tier1_m, tier2_m)
        cache_path = CACHE_DIR / f"neighbor_graph_{key}.pkl"
        
        # If a cached graph exists for the given key, load and return it
        if cache_path.exists():
            with open(cache_path, "rb") as f:
                return pickle.load(f)

    # for each sector, extract the site_sector_id, lat, and lon, and convert lat/lon to ENU coordinates
    ids = [s["site_sector_id"] for s in sectors]
    lats = np.array([s["lat"] for s in sectors])
    lons = np.array([s["lon"] for s in sectors])
    coords = _latlon_to_enu(lats, lons)

    # Build a KD-tree from the ENU coordinates and generate tiered neighbor lists for each sector
    tree = cKDTree(coords)
    tier1 = _tier_from_tree(tree, coords, ids, tier1_m)
    tier2 = _tier_from_tree(tree, coords, ids, tier2_m)

    # Create the final graph dictionary containing sector IDs, tiered neighbor lists, and tier radii
    graph = {
        "ids": ids,
        "tier1": tier1,
        "tier2": tier2,
        "tier1_radius_m": tier1_m,
        "tier2_radius_m": tier2_m,
    }
    
    # Cache the graph to disk if caching is enabled
    if cache_path is not None:
        with open(cache_path, "wb") as f:
            pickle.dump(graph, f)

    return graph

# -- Graph summary -------------------------------------------------------------------
def summarize(graph: dict) -> dict:
    t1_counts = [len(v) for v in graph["tier1"].values()]
    t2_counts = [len(v) for v in graph["tier2"].values()]
    return {
        "nodes": len(graph["ids"]),
        "tier1_radius_m": graph["tier1_radius_m"],
        "tier2_radius_m": graph["tier2_radius_m"],
        "avg_tier1_neighbors": round(float(np.mean(t1_counts)), 2) if t1_counts else 0,
        "max_tier1_neighbors": max(t1_counts) if t1_counts else 0,
        "avg_tier2_neighbors": round(float(np.mean(t2_counts)), 2) if t2_counts else 0,
        "max_tier2_neighbors": max(t2_counts) if t2_counts else 0,
        "isolated_nodes": sum(1 for c in t1_counts if c == 0),
    }


if __name__ == "__main__":
    import sys
    from loader import load_sectors

    src = sys.argv[1] if len(sys.argv) > 1 else "data/NR5G_PCI_RSI_Planning.xlsx"
    sectors = load_sectors(src)
    graph = build_neighbor_graph(sectors)
    print(json.dumps(summarize(graph), indent=2))

    example = next(s for s in sectors if s["requires_planning"])
    print(f"\nExample - {example['site_sector_id']} (site {example['site_id']}):")
    print(f"  tier1 (<= {graph['tier1_radius_m']/1000:.0f} km): {direct_neighbors(graph, example['site_sector_id'])[:8]}")
    print(f"  tier2 (<= {graph['tier2_radius_m']/1000:.0f} km) count: {len(extended_neighbors(graph, example['site_sector_id']))}")