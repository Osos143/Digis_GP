"""
assignment_engine.py - Mod4 / PCI / RSI assignment.

Three stages:
    1. Mod4 via weighted graph coloring (DSATUR + local search repair)
    2. PCI matching Mod4 where possible, respecting Mod3 and collision/confusion
    3. RSI respecting Tier-2 reuse

All hard rules from constraints.py are strictly enforced.  Soft
optimization (weighted Mod4 clash minimization) uses
facing.interference_potential.
"""
import hashlib
import time

from neighbor_graph import direct_neighbors, extended_neighbors
from facing import interference_potential
from constraints import (
    group_sectors_by_site,
    mod4_co_site_siblings,
    compute_forbidden_sets,
    valid_pci_candidates,
    valid_rsi_candidates,
    rsi_conflict_counts,
    get_mod4,
    PCI_MIN, PCI_MAX,
    RSI_MIN, RSI_MAX,
)

MOD4_COLORS = (0, 1, 2, 3)
REPAIR_TIME_BUDGET_S = 60  # wall-clock safety net for exceptionally dense pockets
DELTA_EPSILON = 1e-9       # floating-point improvement threshold


# --- deterministic tie-breaking ------------------------------------------------
def _hash_pick(sid: str, salt: str, candidates: list) -> int:
    """Pick one candidate deterministically via MD5 hash of sid+salt."""
    digest = hashlib.md5(f"{sid}:{salt}".encode()).hexdigest()
    return candidates[int(digest, 16) % len(candidates)]


def _hardest_first_order(sectors: list[dict], graph: dict) -> list[dict]:
    """Sort so sectors with the most Tier-2 neighbors are planned first."""
    return sorted(
        sectors,
        key=lambda s: (-len(extended_neighbors(graph, s["site_sector_id"])),
                       s["site_sector_id"]),
    )

# Replace _hardest_first_order calls with:
def _pci_planning_order(sectors_to_plan, graph):
    """
    Order sectors for PCI planning:
        1. Group by site
        2. Sort sites by hardest-first (most Tier-2 neighbors)
        3. Within each site, sort sectors by azimuth (ring order)

    This helps the 4-5 sector site Mod3 rule succeed: siblings are
    processed in a predictable order so ring constraints and full
    Mod3 coverage can be tracked as we go.
    """
    from collections import defaultdict
    by_site = defaultdict(list)
    for s in sectors_to_plan:
        by_site[s["site_id"]].append(s)

    # Compute site hardness = max Tier-2 degree of any sector on the site
    site_hardness = {
        site_id: max(len(extended_neighbors(graph, s["site_sector_id"])) for s in sectors)
        for site_id, sectors in by_site.items()
    }

    # Sort sites by hardness descending, then site_id for determinism
    sorted_sites = sorted(by_site.keys(), key=lambda sid: (-site_hardness[sid], sid))

    result = []
    for site_id in sorted_sites:
        # Within site: sort by azimuth
        sectors = sorted(by_site[site_id], key=lambda s: s["azimuth"])
        result.extend(sectors)
    return result

# --- Mod4 helpers --------------------------------------------------------------
def _build_interference_edges(ids_to_plan, graph, sector_by_id, site_of):
    """
    Precompute the Mod4 interference graph edges: Tier-1 inter-site
    pairs with nonzero interference_potential.  Weight = potential.
    """
    edges: dict[str, list[tuple[str, float]]] = {}
    for sid in ids_to_plan:
        lst = []
        for nb in direct_neighbors(graph, sid):
            if site_of.get(nb) == site_of.get(sid):
                continue  # co-site handled separately
            if sid in sector_by_id and nb in sector_by_id:
                w = interference_potential(sector_by_id[sid], sector_by_id[nb])
                if w > 0:
                    lst.append((nb, w))
        edges[sid] = lst
    return edges


def _same_color_weight(sid, color, mod4_of, edges):
    """Sum of edge weights from sid to neighbors currently holding `color`."""
    return sum(w for nb, w in edges.get(sid, []) if mod4_of.get(nb) == color)


def _co_site_forbidden(sid, sector_by_id, sectors_by_site, mod4_of, exclude=None):
    """
    Which Mod4 colors are off-limits for sid due to its mandatory
    co-site siblings' CURRENT colors.  `exclude` optionally drops one
    sibling (used during swap moves).
    """
    siblings = mod4_co_site_siblings(sector_by_id[sid], sectors_by_site)
    return {mod4_of[s] for s in siblings
            if s in mod4_of and s != sid and s != exclude}


def _recolor_delta(sid, new_color, mod4_of, edges):
    """Change in total interference weight if sid were recolored (no mutation)."""
    old = mod4_of[sid]
    delta = 0.0
    for nb, w in edges.get(sid, []):
        nc = mod4_of.get(nb)
        if nc == old:
            delta -= w
        if nc == new_color:
            delta += w
    return delta


def _recolor_legal(sid, new_color, sector_by_id, sectors_by_site, mod4_of):
    return new_color not in _co_site_forbidden(sid, sector_by_id, sectors_by_site, mod4_of)


def _swap_delta(sid1, sid2, mod4_of, edges):
    """
    Change in total weight from swapping sid1 and sid2's colors.
    Since siblings are on the same site and edges only exist for
    inter-site pairs, the two individual deltas sum with no cross term.
    """
    c1, c2 = mod4_of[sid1], mod4_of[sid2]
    return _recolor_delta(sid1, c2, mod4_of, edges) + _recolor_delta(sid2, c1, mod4_of, edges)


def _swap_legal(sid1, sid2, sector_by_id, sectors_by_site, mod4_of):
    """True if swapping colors keeps BOTH sectors legal against OTHER siblings."""
    c1, c2 = mod4_of[sid1], mod4_of[sid2]
    ok1 = c2 not in _co_site_forbidden(sid1, sector_by_id, sectors_by_site, mod4_of, exclude=sid2)
    ok2 = c1 not in _co_site_forbidden(sid2, sector_by_id, sectors_by_site, mod4_of, exclude=sid1)
    return ok1 and ok2


def _weighted_repair(mod4_of, edges, sector_by_id, sectors_by_site, site_of, ids_to_plan):
    """
    Post-DSATUR local search.  Each round applies the single
    best-improving recolor OR co-site swap.  Terminates when no
    improving move exists or the time budget is reached.
    """
    ids_set = set(ids_to_plan)
    t0 = time.time()
    round_num = 0

    while True:
        if time.time() - t0 > REPAIR_TIME_BUDGET_S:
            print(f"  [mod4 repair] time budget ({REPAIR_TIME_BUDGET_S}s) reached at round {round_num}")
            break

        round_num += 1

        # Find clashing sectors (nonzero same-color weight)
        clashing = [sid for sid in ids_to_plan
                    if _same_color_weight(sid, mod4_of[sid], mod4_of, edges) > DELTA_EPSILON]
        if not clashing:
            break  # mathematical floor - nothing to improve

        # Sort by worst-first to explore high-impact moves first
        clashing.sort(key=lambda sid: (-_same_color_weight(sid, mod4_of[sid], mod4_of, edges), sid))

        best = None  # (delta, kind, args)

        for sid in clashing:
            # Try recolors
            for c in MOD4_COLORS:
                if c == mod4_of[sid]:
                    continue
                if not _recolor_legal(sid, c, sector_by_id, sectors_by_site, mod4_of):
                    continue
                d = _recolor_delta(sid, c, mod4_of, edges)
                if d < -DELTA_EPSILON and (best is None or d < best[0]):
                    best = (d, "recolor", (sid, c))

            # Try swaps with co-site siblings
            for sib in sectors_by_site.get(site_of[sid], []):
                sib_id = sib["site_sector_id"]
                if sib_id == sid or sib_id not in ids_set:
                    continue
                if mod4_of[sib_id] == mod4_of[sid]:
                    continue
                if not _swap_legal(sid, sib_id, sector_by_id, sectors_by_site, mod4_of):
                    continue
                d = _swap_delta(sid, sib_id, mod4_of, edges)
                if d < -DELTA_EPSILON and (best is None or d < best[0]):
                    best = (d, "swap", (sid, sib_id))

        if best is None:
            break  # mathematical floor

        _, kind, args = best
        if kind == "recolor":
            sid, c = args
            mod4_of[sid] = c
        else:
            s1, s2 = args
            mod4_of[s1], mod4_of[s2] = mod4_of[s2], mod4_of[s1]

        if round_num % 100 == 0:
            total = sum(_same_color_weight(s, mod4_of[s], mod4_of, edges) for s in ids_to_plan) / 2.0
            print(f"  [mod4 repair] round {round_num}: total weight ~= {total:.6f}")

    return mod4_of


# --- Public API: Mod4 ----------------------------------------------------------
def assign_mod4(sectors_to_plan, graph, existing_mod4=None, geometry_sectors=None):
    """
    Assign Mod4 via DSATUR + weighted local search repair.
    existing_mod4 entries are locked and never modified.
    """
    existing_mod4 = existing_mod4 or {}
    geometry_sectors = geometry_sectors or sectors_to_plan
    ids_to_plan = [s["site_sector_id"] for s in sectors_to_plan]

    sector_by_id = {s["site_sector_id"]: s for s in geometry_sectors}
    site_of = {s["site_sector_id"]: s["site_id"] for s in geometry_sectors}
    sectors_by_site = group_sectors_by_site(geometry_sectors)

    mod4_of = dict(existing_mod4)
    edges = _build_interference_edges(ids_to_plan, graph, sector_by_id, site_of)

    # DSATUR initial coloring
    uncolored = set(ids_to_plan)
    while uncolored:
        def sat_key(sid):
            colors = {mod4_of[nb] for nb, _ in edges.get(sid, []) if nb in mod4_of}
            weight = sum(w for _, w in edges.get(sid, []))
            return (len(colors), weight, sid)  # most constrained first

        next_sid = max(uncolored, key=sat_key)
        forbidden = _co_site_forbidden(next_sid, sector_by_id, sectors_by_site, mod4_of)
        candidates = [c for c in MOD4_COLORS if c not in forbidden] or list(MOD4_COLORS)

        # Pick color minimizing weighted clash; deterministic tie-break
        best = min(candidates, key=lambda c: (
            _same_color_weight(next_sid, c, mod4_of, edges),
            _hash_pick(next_sid, f"mod4:{c}", [c]),  # deterministic ordering key
        ))
        mod4_of[next_sid] = best
        uncolored.remove(next_sid)

    # Local search repair
    mod4_of = _weighted_repair(mod4_of, edges, sector_by_id, sectors_by_site, site_of, ids_to_plan)
    return {sid: mod4_of[sid] for sid in ids_to_plan}

# --- Public API: PCI + RSI -----------------------------------------------------
def assign_pci_rsi(
    sectors_to_plan, graph, all_sectors_for_site_grouping, mod4_of,
    existing_assignments=None, rsi_use_tier2=True,
):
    """
    Assign PCI and RSI after Mod4 is fixed.

    PCI:
        - hard: no collision, no confusion, respect Mod3 rule
        - prefer PCI matching assigned Mod4
        - prefer Mod3 values still missing on the site (to satisfy the
          "use all 3 Mod3 values on 4-5 sector sites" rule)
        - order: site-by-site in azimuth order (ring-aware) so co-site
          Mod3 rules can be tracked as we go
        - tie-break: least globally-used, then deterministic hash

    RSI:
        - hard: no Tier-2 reuse
        - order: hardest-first (most Tier-2 neighbors) since RSI has no
          per-site constraints, just global density pressure
        - fallback: if no legal RSI exists, pick the least-conflicted one
    """
    existing_assignments = existing_assignments or {}
    ids_to_plan = [s["site_sector_id"] for s in sectors_to_plan]
    sectors_by_site = group_sectors_by_site(all_sectors_for_site_grouping)

    assignments = {sid: dict(a) for sid, a in existing_assignments.items()}

    # Global usage counters, seeded from locked neighbors
    pci_usage: dict[int, int] = {}
    rsi_usage: dict[int, int] = {}
    for a in existing_assignments.values():
        if a.get("pci") is not None:
            pci_usage[a["pci"]] = pci_usage.get(a["pci"], 0) + 1
        if a.get("rsi") is not None:
            rsi_usage[a["rsi"]] = rsi_usage.get(a["rsi"], 0) + 1

    # ============================================================
    # PCI pass - ordered by site+azimuth so Mod3 rules track cleanly
    # ============================================================
    pci_order = _pci_planning_order(sectors_to_plan, graph)

    for s in pci_order:
        sid = s["site_sector_id"]
        forbidden = compute_forbidden_sets(s, graph, assignments, sectors_by_site)
        target_mod4 = mod4_of[sid]

        candidates = valid_pci_candidates(forbidden)
        if not candidates:
            print(f"  [WARN] no legal PCI for '{sid}' - structural infeasibility")
            pci_forbidden = forbidden["pci_collision"] | forbidden["pci_confusion"]
            candidates = [p for p in range(PCI_MIN, PCI_MAX + 1) if p not in pci_forbidden]
            if not candidates:
                raise ValueError(f"sector '{sid}' cannot be assigned any legal PCI")

        # Layered preferences: Mod4 match AND preferred Mod3, then relax step by step
        mod3_preferred = forbidden["mod3_preferred"]
        ideal      = [p for p in candidates if get_mod4(p) == target_mod4 and (p % 3) in mod3_preferred]
        mod4_only  = [p for p in candidates if get_mod4(p) == target_mod4]
        mod3_only  = [p for p in candidates if (p % 3) in mod3_preferred]

        if ideal:
            pool = ideal
        elif mod4_only:
            pool = mod4_only
        elif mod3_only:
            pool = mod3_only
        else:
            pool = candidates

        min_use = min(pci_usage.get(p, 0) for p in pool)
        tied = [p for p in pool if pci_usage.get(p, 0) == min_use]
        chosen = _hash_pick(sid, "pci", tied)

        assignments[sid] = {"pci": chosen, "rsi": None}
        pci_usage[chosen] = pci_usage.get(chosen, 0) + 1

    # ============================================================
    # RSI pass - hardest-first (Tier-2 density is what matters here)
    # ============================================================
    rsi_order = _hardest_first_order(sectors_to_plan, graph)

    for s in rsi_order:
        sid = s["site_sector_id"]
        forbidden = compute_forbidden_sets(s, graph, assignments, sectors_by_site,
                                           rsi_use_tier2=rsi_use_tier2)
        candidates = valid_rsi_candidates(forbidden)

        if not candidates:
            print(f"  [WARN] no legal RSI for '{sid}' - forced reuse (structural)")
            counts = rsi_conflict_counts(forbidden)
            min_conflict = min(counts.values())
            candidates = [r for r in range(RSI_MIN, RSI_MAX + 1) if counts[r] == min_conflict]

        counts = rsi_conflict_counts(forbidden)
        min_conflict = min(counts[r] for r in candidates)
        best = [r for r in candidates if counts[r] == min_conflict]

        min_use = min(rsi_usage.get(r, 0) for r in best)
        tied = [r for r in best if rsi_usage.get(r, 0) == min_use]
        chosen = _hash_pick(sid, "rsi", tied)

        assignments[sid]["rsi"] = chosen
        rsi_usage[chosen] = rsi_usage.get(chosen, 0) + 1

    return {
        sid: {
            "pci": assignments[sid]["pci"],
            "rsi": assignments[sid]["rsi"],
            "mod4": assignments[sid]["pci"] % 4,
        }
        for sid in ids_to_plan
    }


# --- Public API: full pipeline -------------------------------------------------
def assign_all(
    sectors_to_plan, graph, all_sectors_for_site_grouping,
    existing_assignments=None, rsi_use_tier2=True,
):
    """Full assignment: Mod4 -> PCI -> RSI."""
    existing_assignments = existing_assignments or {}
    existing_mod4 = {sid: a["mod4"] for sid, a in existing_assignments.items()
                     if a.get("mod4") is not None}
    mod4_of = assign_mod4(sectors_to_plan, graph, existing_mod4,
                          geometry_sectors=all_sectors_for_site_grouping)
    return assign_pci_rsi(sectors_to_plan, graph, all_sectors_for_site_grouping, mod4_of,
                          existing_assignments=existing_assignments, rsi_use_tier2=rsi_use_tier2)