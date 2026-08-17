"""
validator.py - Independent verification of the final plan.

Reports EXACTLY the KPIs used by the reference clash sheet, plus Mod3:

    PCI Collision              = Adjacent 1st Neigh PCI clash
                                 = Tier-1 (adjacent) neighbors sharing PCI

    PCI Confusion              = 2nd Neigh PCI clash
                                 = Tier-2 neighbors sharing PCI

    Mod3 Intra-site            = Ring-adjacent co-site sectors sharing Mod3

    Mod3 non-adj Intra-site    = Non-adjacent co-site sectors sharing Mod3
                                 (informational for 4-5 sector sites where
                                  ring-adjacency is the strict rule)

    Mod4 Inter-site            = Adjacent 1st Neigh mod4 clash
                                 = For each sector S, find its 1st neighbor
                                   (the nearest inter-site sector that S
                                   points at).  Count 1 if mod4(S) equals
                                   mod4(1st_neighbor).  This is per-sector,
                                   not per-pair.  Maximum possible = number
                                   of sectors in the network.

    Mod4 Intra-site            = Adjacent 1st Neigh co-site mod4 clash
                                 = Ring-adjacent co-site sectors sharing Mod4

    Mod4 non-adj Intra-site    = Non-Adjacent 1st Neigh co-site mod4 clash
                                 = Non-adjacent co-site sectors sharing Mod4

    Total Clashes              = Sum of all counts above

Every clash record includes:
    sector_a, sector_b, site_a, site_b,
    pci_a, pci_b, mod3_a, mod3_b, mod4_a, mod4_b, rsi_a, rsi_b

Detection is independent of the planner - every check is recomputed
from scratch.

The pass flag is True only when ALL hard rules are zero:
    PCI Collision, PCI Confusion, Mod3 Intra-site, RSI Reuse (Tier-2)
"""
from collections import defaultdict

from constraints import get_mod3, group_sectors_by_site


# --- helpers ------------------------------------------------------------------
def _sector_by_id(sectors):
    return {s["site_sector_id"]: s for s in sectors}


def _site_of(sectors):
    return {s["site_sector_id"]: s["site_id"] for s in sectors}


def _mod4_of(assignment):
    if not assignment:
        return None
    if assignment.get("mod4") is not None:
        return assignment["mod4"]
    pci = assignment.get("pci")
    return None if pci is None else pci % 4


def _pair_record(sector_by_id, assignments, sid_a, sid_b, clash_type):
    """Standard clash record with all IDs and current assignments."""
    a = sector_by_id[sid_a]
    b = sector_by_id[sid_b]
    aa = assignments.get(sid_a, {})
    bb = assignments.get(sid_b, {})
    pci_a, pci_b = aa.get("pci"), bb.get("pci")
    return {
        "clash_type": clash_type,
        "sector_a":   sid_a,
        "sector_b":   sid_b,
        "site_a":     a["site_id"],
        "site_b":     b["site_id"],
        "pci_a":      pci_a,
        "pci_b":      pci_b,
        "mod3_a":     None if pci_a is None else pci_a % 3,
        "mod3_b":     None if pci_b is None else pci_b % 3,
        "mod4_a":     _mod4_of(aa),
        "mod4_b":     _mod4_of(bb),
        "rsi_a":      aa.get("rsi"),
        "rsi_b":      bb.get("rsi"),
    }


def _site_count_from_pairs(records):
    return len({record["site_a"] for record in records} | {record["site_b"] for record in records})


def _sector_set_from_pairs(records):
    sectors = set()
    for record in records:
        a = record.get("sector_a")
        b = record.get("sector_b")
        if a:
            sectors.add(a)
        if b:
            sectors.add(b)
    return sectors


# --- hard-rule checks ---------------------------------------------------------
def _check_pci_collision(sectors, graph, assignments):
    """Tier-1 pairs sharing the same PCI."""
    sector_by_id = _sector_by_id(sectors)
    seen = set()
    result = []
    for sid in graph["ids"]:
        for nb, _ in graph["tier1"].get(sid, []):
            if nb <= sid:
                continue
            key = (sid, nb)
            if key in seen:
                continue
            seen.add(key)
            a = assignments.get(sid)
            b = assignments.get(nb)
            if a and b and a.get("pci") is not None and a["pci"] == b.get("pci"):
                result.append(_pair_record(sector_by_id, assignments, sid, nb, "PCI Collision"))
    return result


def _check_pci_confusion(sectors, graph, assignments):
    """Tier-2 pairs sharing the same PCI."""
    sector_by_id = _sector_by_id(sectors)
    seen = set()
    result = []
    for sid in graph["ids"]:
        for nb, _ in graph["tier2"].get(sid, []):
            if nb <= sid:
                continue
            key = (sid, nb)
            if key in seen:
                continue
            seen.add(key)
            a = assignments.get(sid)
            b = assignments.get(nb)
            if a and b and a.get("pci") is not None and a["pci"] == b.get("pci"):
                result.append(_pair_record(sector_by_id, assignments, sid, nb, "PCI Confusion"))
    return result


def _check_rsi_reuse(sectors, graph, assignments):
    """Tier-2 pairs sharing the same RSI - hard rule."""
    sector_by_id = _sector_by_id(sectors)
    seen = set()
    result = []
    for sid in graph["ids"]:
        for nb, _ in graph["tier2"].get(sid, []):
            if nb <= sid:
                continue
            key = (sid, nb)
            if key in seen:
                continue
            seen.add(key)
            a = assignments.get(sid)
            b = assignments.get(nb)
            if a and b and a.get("rsi") is not None and a["rsi"] == b.get("rsi"):
                result.append(_pair_record(sector_by_id, assignments, sid, nb, "RSI Reuse"))
    return result


# --- Mod3 checks --------------------------------------------------------------
def _check_mod3(sectors, assignments):
    """
    Mod3 validation with multi-granularity reporting.

    Detection method:
        For each site, examine every co-site pair.
        A pair (A, B) shares Mod3 if (pci_A % 3) == (pci_B % 3).
        Classify pair as:
            - "ring_adjacent" if A, B are next to each other in azimuth ring
            - "non_adjacent"  otherwise

    Rule violations (hard) for site with >=2 sectors:
        - ANY ring-adjacent pair sharing Mod3 (violates ring rule)
        - Site with 4-5 sectors NOT using all 3 Mod3 values

    Reports each metric by pairs, sectors, and sites.
    """
    sector_by_id = _sector_by_id(sectors)
    by_site = defaultdict(list)
    for s in sectors:
        by_site[s["site_id"]].append(s)

    # Multi-granularity accumulators
    adj_pairs = []              # ring-adjacent Mod3 clashes (pair records)
    adj_sectors = set()         # sectors involved in any ring-adjacent clash
    adj_sites = set()           # sites with any ring-adjacent clash

    non_adj_pairs = []          # non-adjacent Mod3 reuse (pair records)
    non_adj_sectors = set()     # sectors involved in any non-adjacent reuse
    non_adj_sites = set()       # sites with any non-adjacent reuse

    rule_violation_sites = set()  # sites violating the strict Mod3 rule

    for site_id, site_sectors in by_site.items():
        ordered = sorted(site_sectors, key=lambda s: s["azimuth"])
        ids = [s["site_sector_id"] for s in ordered]
        n = len(ids)
        if n < 2:
            continue

        site_has_adjacent = False

        # Check every pair
        for i in range(n):
            for j in range(i + 1, n):
                a, b = ids[i], ids[j]
                aa = assignments.get(a)
                bb = assignments.get(b)
                if not aa or not bb:
                    continue
                pa, pb = aa.get("pci"), bb.get("pci")
                if pa is None or pb is None:
                    continue
                if get_mod3(pa) != get_mod3(pb):
                    continue

                is_ring_adjacent = (j == i + 1) or (i == 0 and j == n - 1)

                if is_ring_adjacent:
                    adj_pairs.append(_pair_record(sector_by_id, assignments, a, b, "Mod3 Adjacent"))
                    adj_sectors.update([a, b])
                    adj_sites.add(site_id)
                    site_has_adjacent = True
                else:
                    non_adj_pairs.append(_pair_record(sector_by_id, assignments, a, b, "Mod3 Non-Adjacent"))
                    non_adj_sectors.update([a, b])
                    non_adj_sites.add(site_id)

        # Rule violation check
        if site_has_adjacent:
            rule_violation_sites.add(site_id)

        # For 4-5 sector sites, check all 3 Mod3 values are present
        if n >= 4:
            mod3s = set()
            for sid in ids:
                a = assignments.get(sid)
                if a and a.get("pci") is not None:
                    mod3s.add(get_mod3(a["pci"]))
            if len(mod3s) < 3:
                rule_violation_sites.add(site_id)

    return {
        "adjacent_pairs":         adj_pairs,
        "adjacent_sectors":       adj_sectors,
        "adjacent_sites":         adj_sites,
        "non_adjacent_pairs":     non_adj_pairs,
        "non_adjacent_sectors":   non_adj_sectors,
        "non_adjacent_sites":     non_adj_sites,
        "rule_violation_sites":   rule_violation_sites,
    }


def _check_mod4_inter_site(sectors, graph, assignments):
    """
    Adjacent 1st Neigh mod4 clash (matches reference sheet).

    Detection method (per-sector, directed):
        For each sector S:
            Find S's 1st inter-site neighbor N:
                - The NEAREST sector on a DIFFERENT site
                - Whose bearing is inside S's antenna cone
                  (alignment(S, N) > 0 - i.e. bearing within 90° of azimuth)
            If S has no such neighbor, skip.
            If mod4(S) == mod4(N), count 1 clash for S.

    Reports the same clash by:
        - Sector count  (how many sectors have their 1st neighbor clashing)
                        This is the reference sheet's KPI.  Max = num sectors.
        - Pair count    (distinct undirected (A, B) pairs that clash from
                         either direction)
        - Site count    (distinct sites with any clashing sector)
    """
    from facing import alignment  # local import

    sector_by_id = _sector_by_id(sectors)
    site_of = _site_of(sectors)

    clashing_sectors = set()  # sectors whose 1st neighbor shares Mod4
    clashing_pairs = set()    # unique (min, max) sector pairs
    clashing_sites = set()    # sites with any clashing sector
    pair_records = []

    for sid in graph["ids"]:
        if sid not in sector_by_id:
            continue
        me = sector_by_id[sid]
        my_site = site_of[sid]

        # Find 1st inter-site neighbor (nearest that I point at)
        first_neighbor = None
        for nb, _ in graph["tier1"].get(sid, []):
            if nb not in sector_by_id:
                continue
            if site_of.get(nb) == my_site:
                continue
            other = sector_by_id[nb]
            if alignment(me, other) > 0.0:
                first_neighbor = nb
                break

        if first_neighbor is None:
            continue

        ma = _mod4_of(assignments.get(sid))
        mb = _mod4_of(assignments.get(first_neighbor))
        if ma is None or mb is None or ma != mb:
            continue

        # This sector has a clash
        clashing_sectors.add(sid)
        clashing_sites.add(my_site)

        # Record the pair (only once, undirected)
        pair_key = tuple(sorted([sid, first_neighbor]))
        if pair_key not in clashing_pairs:
            clashing_pairs.add(pair_key)
            pair_records.append(_pair_record(sector_by_id, assignments, sid, first_neighbor, "Mod4 Inter-site"))

    return {
        "sectors": clashing_sectors,  # per-sector directed count (reference KPI)
        "pairs": clashing_pairs,      # undirected pair set
        "sites": clashing_sites,      # distinct sites involved
        "pair_records": pair_records, # detail records for drill-down
    }


def _check_mod4_intra_site(sectors, assignments):
    """
    Co-site Mod4 clashes, split into ring-adjacent (HARD) and
    non-adjacent (informational).

    Detection method (per-site):
        For each site:
            Sort sectors by azimuth (ring order).
            For every pair (i, j):
                if mod4(i) == mod4(j):
                    - if ring-adjacent → ring-adjacent clash
                    - else → non-adjacent clash

    Reports by pairs, sectors, and sites.
    """
    sector_by_id = _sector_by_id(sectors)
    by_site = defaultdict(list)
    for s in sectors:
        by_site[s["site_id"]].append(s)

    adj_pairs = []
    adj_sectors = set()
    adj_sites = set()

    non_adj_pairs = []
    non_adj_sectors = set()
    non_adj_sites = set()

    for site_id, site_sectors in by_site.items():
        ordered = sorted(site_sectors, key=lambda s: s["azimuth"])
        ids = [s["site_sector_id"] for s in ordered]
        n = len(ids)
        if n < 2:
            continue

        for i in range(n):
            for j in range(i + 1, n):
                a, b = ids[i], ids[j]
                ma = _mod4_of(assignments.get(a))
                mb = _mod4_of(assignments.get(b))
                if ma is None or mb is None or ma != mb:
                    continue

                is_ring_adjacent = (j == i + 1) or (i == 0 and j == n - 1)
                if is_ring_adjacent:
                    adj_pairs.append(_pair_record(sector_by_id, assignments, a, b, "Mod4 Intra-site"))
                    adj_sectors.update([a, b])
                    adj_sites.add(site_id)
                else:
                    non_adj_pairs.append(_pair_record(sector_by_id, assignments, a, b, "Mod4 non-adj Intra-site"))
                    non_adj_sectors.update([a, b])
                    non_adj_sites.add(site_id)

    return {
        "adjacent_pairs":         adj_pairs,
        "adjacent_sectors":       adj_sectors,
        "adjacent_sites":         adj_sites,
        "non_adjacent_pairs":     non_adj_pairs,
        "non_adjacent_sectors":   non_adj_sectors,
        "non_adjacent_sites":     non_adj_sites,
    }


# --- helper for old-plan comparison -------------------------------------------
def planned_only(sectors):
    """Sectors that already carry a PCI - use before validate() on an old plan."""
    return [s for s in sectors if s["pci"] is not None]


# --- Public API ---------------------------------------------------------------
STATS_DEFINITIONS = [
    ("Total Clashes", "Sum of the clash types below."),
    ("PCI Collision", "Tier-1 neighbor sharing the same PCI - hard rule."),
    ("PCI Confusion", "Tier-2 neighbor sharing the same PCI - hard rule."),
    ("Mod3 Clash", "Co-site Mod3 reuse on the same site - hard rule."),
    ("Mod4 Inter-site", "Inter-site Mod4 reuse - soft."),
    ("Mod4 Intra-site", "Co-site Mod4 reuse - soft."),
    ("RSI Reuse", "Tier-2 RSI reuse - hard rule."),
]


def clash_report_with_definitions(sectors, graph, assignments):
    """Compatibility shim used by the network builder and UI."""
    report = validate(sectors, graph, assignments)
    hard = report.get("hard", {})
    soft = report.get("soft", {})
    values = {
        "Total Clashes": sum(
            value for key, value in {
                "PCI Collision": hard.get("pci_collisions", 0),
                "PCI Confusion": hard.get("pci_confusions", 0),
                "Mod3 Clash": hard.get("mod3_small_site_clashes", 0) + hard.get("mod3_large_site_adjacent_clashes", 0),
                "Mod4 Inter-site": soft.get("mod4_inter_site_sectors", 0),
                "Mod4 Intra-site": hard.get("mod4_co_site_violations", 0),
                "RSI Reuse": hard.get("rsi_reuse_violations", 0),
            }.items()
        ),
        "PCI Collision": hard.get("pci_collisions", 0),
        "PCI Confusion": hard.get("pci_confusions", 0),
        "Mod3 Clash": hard.get("mod3_small_site_clashes", 0) + hard.get("mod3_large_site_adjacent_clashes", 0),
        "Mod4 Inter-site": soft.get("mod4_inter_site_sectors", 0),
        "Mod4 Intra-site": hard.get("mod4_co_site_violations", 0),
        "RSI Reuse": hard.get("rsi_reuse_violations", 0),
    }
    return [{"metric": metric, "description": description, "value": values.get(metric, 0)} for metric, description in STATS_DEFINITIONS]


def validate(sectors, graph, assignments):
    """
    Independent validation with multi-granularity KPI reporting.

    Each Mod3/Mod4 metric is reported three ways:
        - by pairs   (unique clashing pairs)
        - by sectors (sectors involved in any clash)
        - by sites   (distinct sites with any clash)

    Hard rules (must all be 0 for report["pass"] = True):
        PCI Collision, PCI Confusion, RSI Reuse,
        Mod3 Adjacent, Mod3 Rule Violations,
        Mod4 Intra-site (ring-adjacent).
    """
    pci_col   = _check_pci_collision(sectors, graph, assignments)
    pci_conf  = _check_pci_confusion(sectors, graph, assignments)
    rsi_reuse = _check_rsi_reuse(sectors, graph, assignments)
    mod3      = _check_mod3(sectors, assignments)
    m4_inter  = _check_mod4_inter_site(sectors, graph, assignments)
    m4_intra  = _check_mod4_intra_site(sectors, assignments)

    counts = {
        # PCI / RSI (pair granularity retained for drill-down)
        "PCI Collision (pairs)":                 len(pci_col),
        "PCI Confusion (pairs)":                 len(pci_conf),
        "RSI Reuse (pairs)":                     len(rsi_reuse),
        "PCI Collision (sites)":                 _site_count_from_pairs(pci_col),
        "PCI Confusion (sites)":                 _site_count_from_pairs(pci_conf),
        "RSI Reuse (sites)":                     _site_count_from_pairs(rsi_reuse),

        # Mod3 adjacent (hard)
        "Mod3 Adjacent (pairs)":                 len(mod3["adjacent_pairs"]),
        "Mod3 Adjacent (sectors)":               len(mod3["adjacent_sectors"]),
        "Mod3 Adjacent (sites)":                 len(mod3["adjacent_sites"]),

        # Mod3 rule violations (hard)
        "Mod3 Rule Violations (sites)":          len(mod3["rule_violation_sites"]),

        # Mod3 non-adjacent (informational - expected on 4-5 sector sites)
        "Mod3 Non-Adj Reuse (pairs)":            len(mod3["non_adjacent_pairs"]),
        "Mod3 Non-Adj Reuse (sectors)":          len(mod3["non_adjacent_sectors"]),
        "Mod3 Non-Adj Reuse (sites)":            len(mod3["non_adjacent_sites"]),

        # Mod4 Inter-site (informational)
        "Mod4 Inter-site (sectors)":             len(m4_inter["sectors"]),
        "Mod4 Inter-site (pairs)":               len(m4_inter["pairs"]),
        "Mod4 Inter-site (sites)":               len(m4_inter["sites"]),

        # Mod4 Intra-site adjacent (hard)
        "Mod4 Intra-site (pairs)":               len(m4_intra["adjacent_pairs"]),
        "Mod4 Intra-site (sectors)":             len(m4_intra["adjacent_sectors"]),
        "Mod4 Intra-site (sites)":               len(m4_intra["adjacent_sites"]),

        # Mod4 Intra-site non-adjacent (informational)
        "Mod4 non-adj Intra-site (pairs)":       len(m4_intra["non_adjacent_pairs"]),
        "Mod4 non-adj Intra-site (sectors)":     len(m4_intra["non_adjacent_sectors"]),
        "Mod4 non-adj Intra-site (sites)":       len(m4_intra["non_adjacent_sites"]),
    }

    # Hard summary - use site-level counts for the hard-rule KPIs shown in the UI.
    hard = {
        "pci_collision":         _site_count_from_pairs(pci_col),
        "pci_confusion":         _site_count_from_pairs(pci_conf),
        "rsi_reuse":             _site_count_from_pairs(rsi_reuse),
        "mod3_adjacent":         len(mod3["adjacent_sites"]),         # sites
        "mod4_intra_site":       len(m4_intra["adjacent_sites"]),     # sites
        "mod3_rule_violations":  len(mod3["rule_violation_sites"]),   # sites
        "pci_collisions":        _site_count_from_pairs(pci_col),
        "pci_confusions":        _site_count_from_pairs(pci_conf),
        "rsi_reuse_violations":  _site_count_from_pairs(rsi_reuse),
        "mod3_small_site_clashes": len(mod3["adjacent_sites"]),
        "mod3_large_site_adjacent_clashes": len(mod3["adjacent_sites"]),
        "mod4_co_site_violations": len(m4_intra["adjacent_sites"]),
    }
    soft = {
        "mod3_non_adj_reuse_sites":         len(mod3["non_adjacent_sites"]),
        "mod4_inter_site_sectors":          len(m4_inter["sectors"]),
        "mod4_inter_site_sites":            len(m4_inter["sites"]),
        "mod4_non_adj_intra_site_sites":    len(m4_intra["non_adjacent_sites"]),
        "mod4_inter_site_raw":              len(m4_inter["pairs"]),
        "mod4_inter_site_weighted":         float(len(m4_inter["pairs"])),
        "mod4_clash_sector_pairs":          len(m4_inter["pairs"]),
        "mod4_clash_sector_pairs_weighted": float(len(m4_inter["pairs"])),
    }

    is_pass = all(v == 0 for v in [hard["pci_collision"], hard["pci_confusion"], hard["rsi_reuse"], hard["mod3_adjacent"], hard["mod3_rule_violations"], hard["mod4_intra_site"]])

    sector_flags = {
        # Exact validator-owned sector sets used for map-level clash coloring.
        "pci_collision": sorted(_sector_set_from_pairs(pci_col)),
        "pci_confusion": sorted(_sector_set_from_pairs(pci_conf)),
        "rsi_reuse": sorted(_sector_set_from_pairs(rsi_reuse)),
        "mod3_adjacent": sorted(mod3["adjacent_sectors"]),
        "mod3_non_adj_reuse": sorted(mod3["non_adjacent_sectors"]),
        "mod4_inter_site": sorted(m4_inter["sectors"]),
        "mod4_intra_site": sorted(m4_intra["adjacent_sectors"]),
        "mod4_non_adj_intra_site": sorted(m4_intra["non_adjacent_sectors"]),
    }

    return {
        "pass":     is_pass,
        "hard":     hard,
        "soft":     soft,
        "counts":   counts,
        "sector_flags": sector_flags,
        "details": {
            "PCI Collision":                pci_col,
            "PCI Confusion":                pci_conf,
            "RSI Reuse":                    rsi_reuse,
            "Mod3 Adjacent":                mod3["adjacent_pairs"],
            "Mod3 Non-Adj Reuse":           mod3["non_adjacent_pairs"],
            "Mod3 Rule Violation Sites":    sorted(mod3["rule_violation_sites"]),
            "Mod4 Inter-site":              m4_inter["pair_records"],
            "Mod4 Intra-site":              m4_intra["adjacent_pairs"],
            "Mod4 non-adj Intra-site":      m4_intra["non_adjacent_pairs"],
        },
        "coverage": {
            "sectors_planned": len(assignments),
            "sectors_total":   len(sectors),
        },
    }
# --- Command-line test --------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys
    from bulk_plan import bulk_plan

    src = sys.argv[1] if len(sys.argv) > 1 else "data/NR5G_PCI_RSI_Planning.xlsx"
    sectors, graph, assignments = bulk_plan(src)
    report = validate(sectors, graph, assignments)

    print(json.dumps({
        "pass":     report["pass"],
        "counts":   report["counts"],
        "hard":     report["hard"],
        "soft":     report["soft"],
        "coverage": report["coverage"],
    }, indent=2))
    print("\nPASS" if report["pass"] else "\nFAIL - hard rule violated")

    for clash_type, records in report["details"].items():
        if records:
            print(f"\n{clash_type} ({len(records)}):")
            for r in records[:5]:
                print(f"  {r['sector_a']} <-> {r['sector_b']}   "
                      f"sites {r['site_a']}/{r['site_b']}   "
                      f"PCI {r['pci_a']}/{r['pci_b']}   "
                      f"Mod3 {r['mod3_a']}/{r['mod3_b']}   "
                      f"Mod4 {r['mod4_a']}/{r['mod4_b']}   "
                      f"RSI {r['rsi_a']}/{r['rsi_b']}")
            if len(records) > 5:
                print(f"  ... and {len(records) - 5} more")