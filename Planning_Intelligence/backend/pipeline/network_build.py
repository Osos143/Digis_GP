"""
network_build.py - the one place that turns pipeline output (loader.py /
neighbor_graph.py / validator.py) into the flat, dashboard-shaped JSON
every view reads: {"kpi": {...}, "sites": [...]}.

Nothing here decides a PCI/RSI/Mod4 value or a pass/fail - that's still
100% validator.py's job. This file only re-derives PER-SECTOR conflict
flags (so the map can color one wedge at a time) and rolls validator.py's
network-wide report into a flat kpi dict the views can read without
knowing validator.py's return shape.

Site shape:  {"s": site_id, "g": region, "y": lat, "x": lon, "n": sector_count,
              "clash": bool, "soft": bool, "sec": [sector, ...]}
Sector shape: {"i": site_sector_id, "a": azimuth, "p": pci, "m": mod4, "r": rsi,
               "t": mod3, "cc": pci_collision, "cf": pci_confusion,
               "c4": mod4_clash, "cr": rsi_reuse, "c3": mod3_violation}

cc/cf/c3 are hard-rule flags (should all be False everywhere in a passing
plan - Mod3 is now checked between ring-adjacent co-site siblings only,
see constraints.ring_adjacent_ids, and is achievable for every site size);
c4/cr are soft, expected to be common in a dense network - see
validator.py's own docstring for why.
"""

from __future__ import annotations

import os

from loader import load_sectors
from neighbor_graph import build_neighbor_graph
from constraints import get_mod3
from validator import validate, clash_report_with_definitions
from bulk_plan import region_of

REGION_NAMES = {"ALX": "Alexandria", "SIN": "Sinai", "UPP": "Upper Egypt", "DEL": "Delta"}


# --- per-sector conflict flags --------------------------------------------------------
def _sector_flags_from_validator(report: dict, sector_ids: list[str]) -> dict[str, dict]:
    """Build per-sector clash flags from validator-owned sector sets.

    This keeps map coloring strictly consistent with KPI counting logic.
    """
    sf = report.get("sector_flags", {}) if isinstance(report, dict) else {}
    cc_set = set(sf.get("pci_collision", []))
    cf_set = set(sf.get("pci_confusion", []))
    c4_set = set(sf.get("mod4_inter_site", []))
    cr_set = set(sf.get("rsi_reuse", []))
    c3_set = set(sf.get("mod3_adjacent", []))
    c3n_set = set(sf.get("mod3_non_adj_reuse", []))
    c4i_set = set(sf.get("mod4_intra_site", []))
    c4n_set = set(sf.get("mod4_non_adj_intra_site", []))

    flags: dict[str, dict] = {}
    for sid in sector_ids:
        flags[sid] = {
            "cc": sid in cc_set,
            "cf": sid in cf_set,
            "c4": sid in c4_set,
            "cr": sid in cr_set,
            "c3": sid in c3_set,
            "c3n": sid in c3n_set,
            "c4i": sid in c4i_set,
            "c4n": sid in c4n_set,
        }
    return flags


# --- site/sector assembly -------------------------------------------------------------
def _build_sites(sectors: list[dict], flags: dict[str, dict] | None, assignments: dict | None) -> list[dict]:
    by_site: dict[str, list[dict]] = {}
    for s in sectors:
        by_site.setdefault(s["site_id"], []).append(s)

    sites = []
    for site_id, secs in by_site.items():
        secs = sorted(secs, key=lambda s: s["azimuth"])
        sec_rows = []
        any_clash = any_soft = False
        for s in secs:
            sid = s["site_sector_id"]
            row = {"i": sid, "a": s["azimuth"]}
            if assignments is not None and sid in assignments:
                a = assignments[sid]
                pci = a.get("pci")
                row.update({"p": pci, "m": a.get("mod4"), "r": a.get("rsi"), "t": get_mod3(pci) if pci is not None else None})
            if flags is not None:
                f = flags.get(sid, {"cc": False, "cf": False, "c4": False, "cr": False, "c3": False})
                row.update(f)
                # c3 (Mod3) is a hard rule now, same severity bucket as
                # cc/cf/c4/cr - there's no longer a separate "soft" flag
                # at the sector level (any_soft is kept, always False, so
                # the site dict's shape doesn't change for other views).
                any_clash = any_clash or f["cc"] or f["cf"] or f["cr"] or f["c3"] or f.get("c4i", False)
                any_soft = any_soft or f["c4"] or f.get("c3n", False) or f.get("c4n", False)
            sec_rows.append(row)

        sites.append({
            "s": site_id, "g": region_of(site_id),
            "y": secs[0]["lat"], "x": secs[0]["lon"], "n": len(secs),
            "clash": any_clash, "soft": any_soft,
            "sec": sec_rows,
        })
    return sites


def _region_breakdown(sites: list[dict]) -> dict:
    out = {r: {"sectors": 0, "sites": 0, "mod4_clash": 0, "rsi_clash": 0, "mod3_soft": 0} for r in REGION_NAMES}
    for site in sites:
        r = out.setdefault(site["g"], {"sectors": 0, "sites": 0, "mod4_clash": 0, "rsi_clash": 0, "mod3_soft": 0})
        r["sites"] += 1
        for sec in site["sec"]:
            r["sectors"] += 1
            r["mod4_clash"] += bool(sec.get("c4"))
            r["rsi_clash"] += bool(sec.get("cr"))
            r["mod3_soft"] += bool(sec.get("c3"))
    return out


# --- public API -------------------------------------------------------------------
def build_network_json(xlsx_path: str) -> dict:
    """Full dashboard JSON for an already-planned workbook: every sector
    carries PCI/RSI/Mod4 plus its own conflict flags, and `kpi` is rolled
    up straight from validator.validate()."""
    sectors = load_sectors(xlsx_path)
    graph = build_neighbor_graph(sectors)
    assignments = {
        s["site_sector_id"]: {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
        for s in sectors
    }

    report = validate(sectors, graph, assignments)
    flags = _sector_flags_from_validator(report, graph["ids"])
    sites = _build_sites(sectors, flags, assignments)

    pcis = [a["pci"] for a in assignments.values() if a["pci"] is not None]
    rsis = [a["rsi"] for a in assignments.values() if a["rsi"] is not None]
    soft = report.get("soft", {})
    mod4_pairs_raw = soft.get("mod4_inter_site_raw", soft.get("mod4_clash_sector_pairs", 0))
    mod4_pairs_weighted = soft.get("mod4_inter_site_weighted", soft.get("mod4_clash_sector_pairs_weighted", 0.0))

    kpi = {
        "total_sectors": len(sectors),
        "total_sites": len(sites),
        "source": os.path.basename(xlsx_path),
        "validation": report,
        # headline, sector-pair based (the metric validator.py itself calls
        # out as the meaningful one - see check_mod4_sector_pairs' docstring)
        "mod4_pairs_raw": mod4_pairs_raw,
        "mod4_pairs_weighted": mod4_pairs_weighted,
        # per-sector counts, for the map legend / percentages / region table
        "mod4_clash_count": sum(f["c4"] for f in flags.values()),
        "rsi_clash_count": sum(f["cr"] for f in flags.values()),
        "pci_collision_count": report["hard"]["pci_collisions"],
        "pci_confusion_count": report["hard"]["pci_confusions"],
        "mod3_soft_count": sum(f["c3"] for f in flags.values()),
        "pci_range_used": (min(pcis), max(pcis)) if pcis else (0, 0),
        "rsi_range_used": (min(rsis), max(rsis)) if rsis else (0, 0),
        "regions": _region_breakdown(sites),
        # separate comparison report (does not affect pass/fail) - matches
        # the old planning file's Stats sheet layout, each number paired
        # with a plain-language description ready for direct display.
        # These six numbers/labels are unchanged by today's Mod3/Mod4
        # redesign - clash_report()'s own definitions still match.
        "stats_report": clash_report_with_definitions(sectors, graph, assignments),
    }
    return {"kpi": kpi, "sites": sites}


def build_raw_json(xlsx_path: str) -> dict:
    """Bare JSON for a not-yet-planned workbook: sites/sectors with only
    geometry (no PCI/RSI/Mod4, no conflict flags) - "before planning"."""
    sectors = load_sectors(xlsx_path, plan_all=True)
    sites = _build_sites(sectors, flags=None, assignments=None)
    kpi = {
        "total_sectors": len(sectors),
        "total_sites": len(sites),
        "source": os.path.basename(xlsx_path),
        "regions": {r: {"sectors": 0, "sites": 0} for r in REGION_NAMES},
    }
    for site in sites:
        kpi["regions"].setdefault(site["g"], {"sectors": 0, "sites": 0})
        kpi["regions"][site["g"]]["sites"] += 1
        kpi["regions"][site["g"]]["sectors"] += site["n"]
    return {"kpi": kpi, "sites": sites}