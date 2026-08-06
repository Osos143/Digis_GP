"""
core/explain.py - the "Why?" logic behind the Assistant tab's clash
explainer. Every fact here comes directly from neighbor_graph.py's own
tier1/tier2 lists and the assignments already validated by validator.py -
this file does not re-decide anything, it just walks the same graph
validator.py already trusts and reports what it finds for ONE sector
instead of the whole network.

Narration (turning the facts into a sentence) is the only place an LLM
is allowed to touch this pipeline, and even then only to phrase facts
that were already computed here - never to produce a number itself.
"""

from __future__ import annotations

import json

from neighbor_graph import direct_neighbors, extended_neighbors
from constraints import get_mod3, get_mod4
from facing import alignment


def explain_sector(sector_id: str, sectors: list[dict], graph: dict, assignments: dict) -> dict:
    if sector_id not in assignments:
        return {"error": f"'{sector_id}' not found in this workbook."}

    site_of = {s["site_sector_id"]: s["site_id"] for s in sectors}
    sector_by_id = {s["site_sector_id"]: s for s in sectors}
    me = assignments[sector_id]
    my_site = site_of[sector_id]
    me_sector = sector_by_id[sector_id]
    my_dist = {nb: d for nb, d in graph["tier1"].get(sector_id, [])}
    my_dist.update({nb: d for nb, d in graph["tier2"].get(sector_id, [])})

    collisions, confusions, rsi_reuse = [], [], []
    for nb in direct_neighbors(graph, sector_id):
        if nb not in assignments:
            continue
        a = assignments[nb]
        entry = {"neighbor": nb, "site": site_of.get(nb), "distance_m": round(my_dist.get(nb, 0)), "pci": a["pci"], "mod4": a["mod4"], "rsi": a["rsi"]}
        if a["pci"] == me["pci"]:
            collisions.append(entry)

    for nb in extended_neighbors(graph, sector_id):
        if nb not in assignments:
            continue
        a = assignments[nb]
        if a["pci"] == me["pci"]:
            confusions.append({"neighbor": nb, "site": site_of.get(nb), "distance_m": round(my_dist.get(nb, 0)), "pci": a["pci"]})
        if a["rsi"] == me["rsi"] and site_of.get(nb) != my_site:
            entry = {"neighbor": nb, "site": site_of.get(nb), "distance_m": round(my_dist.get(nb, 0)), "rsi": a["rsi"]}
            if entry not in rsi_reuse:
                rsi_reuse.append(entry)

    # Exact Mod4 inter-site check for this sector: nearest inter-site
    # neighbor in antenna direction, as validator uses for KPI counting.
    mod4_inter_site = []
    first_neighbor = None
    for nb, _ in graph["tier1"].get(sector_id, []):
        if nb not in sector_by_id or nb not in assignments:
            continue
        if site_of.get(nb) == my_site:
            continue
        if alignment(me_sector, sector_by_id[nb]) > 0.0:
            first_neighbor = nb
            break
    if first_neighbor is not None:
        nb_a = assignments[first_neighbor]
        my_mod4 = me.get("mod4") if me.get("mod4") is not None else get_mod4(me.get("pci"))
        nb_mod4 = nb_a.get("mod4") if nb_a.get("mod4") is not None else get_mod4(nb_a.get("pci"))
        if my_mod4 is not None and nb_mod4 is not None and my_mod4 == nb_mod4:
            mod4_inter_site.append({
                "neighbor": first_neighbor,
                "site": site_of.get(first_neighbor),
                "distance_m": round(my_dist.get(first_neighbor, 0)),
                "mod4": nb_mod4,
                "why": "Nearest inter-site neighbor in sector direction shares Mod4",
            })

    siblings = [s["site_sector_id"] for s in sorted(sectors, key=lambda x: x["azimuth"]) if s["site_id"] == my_site and s["site_sector_id"] != sector_id]
    ring = [s["site_sector_id"] for s in sorted(sectors, key=lambda x: x["azimuth"]) if s["site_id"] == my_site]
    idx_of = {sid: i for i, sid in enumerate(ring)}

    def is_ring_adj(a_sid: str, b_sid: str) -> bool:
        n = len(ring)
        if n < 2:
            return False
        ia = idx_of.get(a_sid)
        ib = idx_of.get(b_sid)
        if ia is None or ib is None:
            return False
        return abs(ia - ib) == 1 or abs(ia - ib) == n - 1

    mod3_adjacent, mod3_non_adj = [], []
    mod4_intra_site, mod4_non_adj = [], []
    my_mod3 = get_mod3(me["pci"]) if me.get("pci") is not None else None
    my_mod4 = me.get("mod4") if me.get("mod4") is not None else get_mod4(me.get("pci"))
    for sib in siblings:
        if sib not in assignments:
            continue
        sb = assignments[sib]
        sib_mod3 = get_mod3(sb["pci"]) if sb.get("pci") is not None else None
        sib_mod4 = sb.get("mod4") if sb.get("mod4") is not None else get_mod4(sb.get("pci"))
        adjacent = is_ring_adj(sector_id, sib)

        if my_mod3 is not None and sib_mod3 is not None and my_mod3 == sib_mod3:
            rec = {"sibling": sib, "pci": sb.get("pci"), "mod3": sib_mod3}
            if adjacent:
                mod3_adjacent.append(rec)
            else:
                mod3_non_adj.append(rec)

        if my_mod4 is not None and sib_mod4 is not None and my_mod4 == sib_mod4:
            rec = {"sibling": sib, "mod4": sib_mod4}
            if adjacent:
                mod4_intra_site.append(rec)
            else:
                mod4_non_adj.append(rec)

    return {
        "sector": {"id": sector_id, "site": my_site, "pci": me["pci"], "mod4": me["mod4"], "rsi": me["rsi"], "mod3": get_mod3(me["pci"])},
        "hard": {
            "pci_collision": collisions,
            "pci_confusion": confusions,
            "rsi_reuse": rsi_reuse,
            "mod3_adjacent": mod3_adjacent,
            "mod4_intra_site": mod4_intra_site,

            # Back-compat key used by older UI.
            "mod3_violation": mod3_adjacent,
        },
        "soft": {
            "mod4_inter_site": mod4_inter_site,
            "mod3_non_adj": mod3_non_adj,
            "mod4_non_adj": mod4_non_adj,

            # Back-compat keys used by older UI.
            "mod4_clash": mod4_inter_site,
            "mod3_soft": mod3_non_adj,
        },
        "clean": not (collisions or confusions or rsi_reuse or mod3_adjacent or mod4_intra_site),
    }


def _template_narration(exp: dict) -> str:
    s = exp["sector"]
    lines = [f"**{s['id']}** (site {s['site']}) - PCI {s['pci']}, Mod4 {s['mod4']}, RSI {s['rsi']}."]

    hard = exp.get("hard", {})
    if hard.get("pci_collision"):
        names = ", ".join(f"{c['neighbor']} ({round(c['distance_m']/1000, 1)} km)" for c in hard.get("pci_collision", []))
        lines.append(f"🔴 **Hard PCI collision** with: {names}. Same physical-layer PCI within 7 km will confuse UE cell search - this must be fixed.")
    if hard.get("pci_confusion"):
        names = ", ".join(f"{c['neighbor']} ({round(c['distance_m']/1000, 1)} km)" for c in hard.get("pci_confusion", []))
        lines.append(f"🔴 **Hard PCI confusion** with: {names}. Same PCI within 14 km risks a UE reporting an ambiguous handover target.")
    if hard.get("rsi_reuse"):
        names = ", ".join(f"{c['neighbor']} ({round(c['distance_m']/1000, 1)} km)" for c in hard.get("rsi_reuse", [])[:6])
        lines.append(f"🔴 **Hard RSI reuse** with: {names}. Same RSI within the 14 km rule window is a hard conflict.")
    mod3_adj = hard.get("mod3_adjacent") or hard.get("mod3_violation") or []
    if mod3_adj:
        names = ", ".join(f"{c['sibling']} (mod3={c['mod3']})" for c in mod3_adj)
        lines.append(f"🔴 **Hard Mod3 adjacent** with co-located sibling(s): {names}. Ring-adjacent sectors on the same site must not share Mod3.")
    if hard.get("mod4_intra_site"):
        names = ", ".join(f"{c['sibling']} (mod4={c['mod4']})" for c in hard.get("mod4_intra_site", []))
        lines.append(f"🔴 **Hard Mod4 intra-site** with co-located sibling(s): {names}. Ring-adjacent sectors on the same site must not share Mod4.")

    soft = exp.get("soft", {})
    mod4_inter = soft.get("mod4_inter_site") or soft.get("mod4_clash") or []
    if mod4_inter:
        names = ", ".join(f"{c['neighbor']} ({round(c['distance_m']/1000,1)} km)" for c in mod4_inter[:6])
        more = f" and {len(mod4_inter)-6} more" if len(mod4_inter) > 6 else ""
        lines.append(f"🟠 **Soft Mod4 inter-site** with: {names}{more}. Nearest inter-site neighbor in sector direction shares Mod4.")
    mod3_non_adj = soft.get("mod3_non_adj") or soft.get("mod3_soft") or []
    if mod3_non_adj:
        names = ", ".join(f"{c['sibling']} (mod3={c['mod3']})" for c in mod3_non_adj)
        lines.append(f"🟠 **Soft Mod3 non-adj reuse** with co-located sibling(s): {names}. Non-adjacent co-site reuse is tracked as informational.")
    if soft.get("mod4_non_adj"):
        names = ", ".join(f"{c['sibling']} (mod4={c['mod4']})" for c in soft.get("mod4_non_adj", []))
        lines.append(f"🟠 **Soft Mod4 non-adj intra-site** with co-located sibling(s): {names}. Non-adjacent co-site reuse is tracked as informational.")

    if exp.get("clean"):
        lines.append("🟢 No hard-rule violations on this sector.")
    return "\n\n".join(lines)


def _call_llm(system: str, user_content: str, max_tokens: int = 400) -> str | None:
    """Blank for now - always returns None, so narrate() and answer() both
    just use the deterministic template everywhere. To connect a model
    later, replace the `return None` below with a real request. Example:

        api_url = "http://localhost:8000/v1/chat/completions"
        model_name = "your-model-name"
        api_key = os.environ.get("LLM_API_KEY", "")
        headers = {"content-type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_name, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        }
        try:
            import requests
            resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip() or None
        except Exception:
            return None
    """
    return None


def narrate(exp: dict) -> str:
    """Template narration by default; if _call_llm() is configured, ask
    your model to phrase the SAME facts more conversationally. The facts
    themselves never come from the model - only the wording does."""
    template = _template_narration(exp)
    reply = _call_llm(
        system=(
            "You explain NR5G PCI/RSI planning conflicts to a network engineer. "
            "You are given a JSON object of ALREADY-COMPUTED facts about one sector's conflicts. "
            "Rephrase them clearly and concisely in plain language. "
            "Do not invent, estimate, or alter any number, ID, or distance - use only what's given. "
            "If there are no conflicts, say so briefly."
        ),
        user_content=json.dumps(exp),
    )
    return reply or template
