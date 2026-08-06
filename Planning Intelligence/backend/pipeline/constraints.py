"""
constraints.py - Hard-rule filtering and candidate generation.

Answers ONLY: which PCI and RSI values are legal for a given sector?

Hard rules enforced:
    - PCI collision:  Tier-1 neighbors must not share PCI
    - PCI confusion:  Tier-2 neighbors must not share PCI
    - Mod3 (site-size-aware, STRICT):
          <=3 sectors: every co-site pair must have different Mod3
          4-5 sectors: ring-adjacent must differ AND all 3 Mod3 values
                       must appear on the site (unavoidable reuse falls
                       only on non-adjacent pairs)
    - RSI reuse:      Tier-2 neighbors must not share RSI

Mod4 is planned separately by assignment_engine.assign_mod4() - this
module only sees the target Mod4 as an already-fixed value.
"""
from neighbor_graph import direct_neighbors, extended_neighbors

# 3GPP-defined ranges
PCI_MIN, PCI_MAX = 0, 1007
RSI_MIN, RSI_MAX = 0, 830


# --- small helpers -------------------------------------------------------------
def get_mod3(pci: int) -> int:
    return pci % 3


def get_mod4(pci: int) -> int:
    return pci % 4


def group_sectors_by_site(sectors: list[dict]) -> dict[str, list[dict]]:
    """Map site_id to the full sector dicts on that site."""
    by_site: dict[str, list[dict]] = {}
    for s in sectors:
        by_site.setdefault(s["site_id"], []).append(s)
    return by_site


def ring_adjacent_ids(sector: dict, sectors_by_site: dict) -> set[str]:
    """
    Ring-adjacent co-site siblings: sort by azimuth, treat as a ring,
    take the two immediate neighbors.
    """
    siblings = sectors_by_site.get(sector["site_id"], [])
    ordered = sorted(siblings, key=lambda s: s["azimuth"])
    ids = [s["site_sector_id"] for s in ordered]
    n = len(ids)
    if n < 2:
        return set()
    i = ids.index(sector["site_sector_id"])
    return {ids[(i - 1) % n], ids[(i + 1) % n]} - {sector["site_sector_id"]}


def mod4_co_site_siblings(sector: dict, sectors_by_site: dict) -> set[str]:
    """
    Which co-site siblings must have a DIFFERENT Mod4 from `sector`.
        <=4 sectors: every sibling
        5 sectors:   ring-adjacent siblings only
    """
    site_sectors = sectors_by_site.get(sector["site_id"], [])
    if len(site_sectors) <= 4:
        return {s["site_sector_id"] for s in site_sectors
                if s["site_sector_id"] != sector["site_sector_id"]}
    return ring_adjacent_ids(sector, sectors_by_site)


# --- Mod3 rule helpers ---------------------------------------------------------
def _sorted_site_ids_by_azimuth(site_id: str, sectors_by_site: dict) -> list[str]:
    """Site's sector IDs ordered by azimuth (defines the ring)."""
    siblings = sectors_by_site.get(site_id, [])
    ordered = sorted(siblings, key=lambda s: s["azimuth"])
    return [s["site_sector_id"] for s in ordered]


def mod3_forbidden_for_sector(
    sector: dict,
    sectors_by_site: dict,
    assignments: dict,
) -> set[int]:
    """
    Which Mod3 values are forbidden for `sector` under the strict rule.

    Rule per site size:
        1-3 sectors: every already-assigned sibling's Mod3 is forbidden
                     (all pairs must differ - achievable since 3 values
                     available for 1-3 sectors).

        4-5 sectors: ring-adjacent siblings' Mod3 forbidden (must differ)
                     AND if any Mod3 value is not yet used on the site,
                     the currently-being-planned sector should PREFER
                     one of those unused values.  This preference is
                     enforced by returning ONLY the ring-adjacent
                     forbidden set here; the missing-value preference
                     is applied as a soft filter by the caller.
    """
    site_id = sector["site_id"]
    site_sectors = sectors_by_site.get(site_id, [])
    n = len(site_sectors)
    sid = sector["site_sector_id"]

    forbidden = set()

    if n <= 3:
        # every sibling must differ
        for sib in site_sectors:
            sib_id = sib["site_sector_id"]
            if sib_id == sid:
                continue
            a = assignments.get(sib_id)
            if a and a.get("pci") is not None:
                forbidden.add(get_mod3(a["pci"]))
    else:
        # ring-adjacent only
        adj = ring_adjacent_ids(sector, sectors_by_site)
        for sib_id in adj:
            a = assignments.get(sib_id)
            if a and a.get("pci") is not None:
                forbidden.add(get_mod3(a["pci"]))

    return forbidden


def mod3_preferred_for_sector(
    sector: dict,
    sectors_by_site: dict,
    assignments: dict,
) -> set[int]:
    """
    Which Mod3 values are PREFERRED for `sector` (on 4-5 sector sites):
    those not yet used by any assigned sibling on the site.

    This encodes the "use all 3 Mod3 values" preference: if some Mod3
    value hasn't been used yet on this site, prefer it to help achieve
    full coverage.

    Returns the FULL set {0, 1, 2} for 1-3 sector sites (no preference
    needed - every sector already gets a unique Mod3 anyway).
    """
    site_id = sector["site_id"]
    site_sectors = sectors_by_site.get(site_id, [])
    n = len(site_sectors)
    sid = sector["site_sector_id"]

    if n <= 3:
        return {0, 1, 2}

    used = set()
    for sib in site_sectors:
        sib_id = sib["site_sector_id"]
        if sib_id == sid:
            continue
        a = assignments.get(sib_id)
        if a and a.get("pci") is not None:
            used.add(get_mod3(a["pci"]))

    unused = {0, 1, 2} - used
    return unused if unused else {0, 1, 2}


def would_break_non_adjacent_reuse_rule(
    sector: dict,
    candidate_mod3: int,
    sectors_by_site: dict,
    assignments: dict,
) -> bool:
    """
    On 4-5 sector sites, if placing `candidate_mod3` on `sector` would
    put the same Mod3 value on an already-assigned ADJACENT sibling,
    return True (breaks the ring-adjacent rule).

    Also checks: if this candidate creates a Mod3 reuse pattern that
    can no longer satisfy "all 3 values must appear" given the
    remaining unassigned siblings, return True.

    Returns False otherwise (candidate is safe).
    """
    site_id = sector["site_id"]
    site_sectors = sectors_by_site.get(site_id, [])
    n = len(site_sectors)
    sid = sector["site_sector_id"]

    if n <= 3:
        # For small sites, adjacency check is enough (all pairs must differ)
        return False  # handled by mod3_forbidden_for_sector

    # 4-5 sector site: check ring-adjacent conflict
    adj = ring_adjacent_ids(sector, sectors_by_site)
    for sib_id in adj:
        a = assignments.get(sib_id)
        if a and a.get("pci") is not None and get_mod3(a["pci"]) == candidate_mod3:
            return True

    # Check: does using this candidate still allow all 3 values to appear?
    used = set()
    unassigned_count = 0
    for sib in site_sectors:
        sib_id = sib["site_sector_id"]
        if sib_id == sid:
            used.add(candidate_mod3)  # simulate placement
            continue
        a = assignments.get(sib_id)
        if a and a.get("pci") is not None:
            used.add(get_mod3(a["pci"]))
        else:
            unassigned_count += 1

    missing = {0, 1, 2} - used
    # If more values are missing than unassigned sectors remain, we can't cover them all
    if len(missing) > unassigned_count:
        return True

    return False


# --- main function --------------------------------------------------------------
def compute_forbidden_sets(
    sector: dict,
    graph: dict,
    assignments: dict,
    sectors_by_site: dict,
    rsi_use_tier2: bool = False,
) -> dict:
    """
    Build the hard-rule forbidden sets for a sector's PCI and RSI.
    Only already-assigned neighbors contribute constraints.
    """
    forbidden = {
        "pci_collision":    set(),
        "pci_confusion":    set(),
        "mod3_forbidden":   set(),  # HARD Mod3 exclusion set
        "mod3_preferred":   {0, 1, 2},  # preferred Mod3 values (all 3 by default)
        "rsi_forbidden":    set(),
        "rsi_neighbor_counts": {},
    }

    sid = sector["site_sector_id"]
    rsi_counts: dict[int, int] = {}

    # Tier-1 neighbors
    for nb in direct_neighbors(graph, sid):
        a = assignments.get(nb)
        if a is None:
            continue
        if a.get("pci") is not None:
            forbidden["pci_collision"].add(a["pci"])
        if a.get("rsi") is not None:
            forbidden["rsi_forbidden"].add(a["rsi"])
            rsi_counts[a["rsi"]] = rsi_counts.get(a["rsi"], 0) + 1

    # Tier-2 neighbors
    for nb in extended_neighbors(graph, sid):
        a = assignments.get(nb)
        if a is None:
            continue
        if a.get("pci") is not None:
            forbidden["pci_confusion"].add(a["pci"])
        if a.get("rsi") is not None:
            forbidden["rsi_forbidden"].add(a["rsi"])
            rsi_counts[a["rsi"]] = rsi_counts.get(a["rsi"], 0) + 1

    # Mod3 hard rule (site-size-aware)
    forbidden["mod3_forbidden"] = mod3_forbidden_for_sector(sector, sectors_by_site, assignments)
    # Mod3 preference (use all 3 values on 4-5 sector sites)
    forbidden["mod3_preferred"] = mod3_preferred_for_sector(sector, sectors_by_site, assignments)

    forbidden["rsi_neighbor_counts"] = rsi_counts
    return forbidden


def valid_pci_candidates(forbidden: dict, pci_min: int = PCI_MIN, pci_max: int = PCI_MAX) -> list[int]:
    """
    PCIs satisfying every HARD rule:
        - not in pci_collision (Tier-1)
        - not in pci_confusion (Tier-2)
        - not in a forbidden Mod3 group (site-size-aware)

    Mod3 preference and Mod4 preference are applied by the caller.
    """
    pci_forbidden = forbidden["pci_collision"] | forbidden["pci_confusion"]
    mod3_forbidden = forbidden["mod3_forbidden"]
    return [pci for pci in range(pci_min, pci_max + 1)
            if pci not in pci_forbidden and get_mod3(pci) not in mod3_forbidden]


def valid_rsi_candidates(forbidden: dict, rsi_min: int = RSI_MIN, rsi_max: int = RSI_MAX) -> list[int]:
    """RSIs satisfying the HARD Tier-2 reuse rule."""
    taken = forbidden["rsi_forbidden"]
    return [rsi for rsi in range(rsi_min, rsi_max + 1) if rsi not in taken]


def rsi_conflict_counts(forbidden: dict, rsi_min: int = RSI_MIN, rsi_max: int = RSI_MAX) -> dict[int, int]:
    """How many neighbors use each RSI - used as a tie-breaker."""
    counts = {v: 0 for v in range(rsi_min, rsi_max + 1)}
    for r, c in forbidden.get("rsi_neighbor_counts", {}).items():
        counts[r] = c
    return counts