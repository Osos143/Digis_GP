"""
core/assistant_chat.py - query translation for the Assistant tab's chat
box. This is intentionally simple keyword/regex routing, not a general
NL-to-SQL system: every branch below pulls a real number out of `data`
(the same dict the Overview/Assignments tabs use) or calls
core/explain.py for a specific sector. An LLM is only ever used to
rephrase what this function already retrieved - see explain._call_llm.

If you outgrow keyword routing later, this is the one function to
replace; every other file stays the same.
"""

from __future__ import annotations

import re

from explain import explain_sector, narrate, _call_llm
from utils import pct

REGION_NAMES = {"ALX": "Alexandria", "SIN": "Sinai", "UPP": "Upper Egypt", "DEL": "Delta"}
SECTOR_RE = re.compile(r"\b([A-Za-z]{3}\d{3,5})(-\d)?\b")


def _region_summary(data: dict, region: str) -> str:
    r = data["kpi"]["regions"][region]
    return (f"**{region} · {REGION_NAMES[region]}** - {r['sectors']:,} sectors across {r['sites']:,} sites. "
            f"Mod4 clashes: {r['mod4_clash']:,} ({pct(r['mod4_clash'], r['sectors'])}%). "
            f"RSI reuse: {r['rsi_clash']:,}. Mod3 soft violations: {r['mod3_soft']:,}.")


def _overall_summary(data: dict) -> str:
    k = data["kpi"]
    t = k["total_sectors"]
    v = k.get("validation", {})
    lines = [
        f"**{t:,} sectors** across **{k['total_sites']:,} sites**, 4 regions.",
        f"Hard rules (validator.py): {v.get('hard', {}).get('pci_collisions', 0)} PCI collisions, "
        f"{v.get('hard', {}).get('pci_confusions', 0)} PCI confusions, "
        f"{v.get('hard', {}).get('mod3_violations', 0)} Mod3 violations - "
        f"{'**PASS**' if v.get('pass') else '**FAIL**'}.",
        f"Soft: {k['mod4_clash_count']:,} Mod4 clashes ({pct(k['mod4_clash_count'], t)}%), "
        f"{k['rsi_clash_count']:,} RSI reuse ({pct(k['rsi_clash_count'], t)}%), "
        f"{k['mod3_soft_count']:,} Mod3 soft violations ({pct(k['mod3_soft_count'], t)}%).",
        f"PCI values used: {k['pci_range_used'][0]}–{k['pci_range_used'][1]} of 0–1007. "
        f"RSI values used: {k['rsi_range_used'][0]}–{k['rsi_range_used'][1]} of 0–830.",
    ]
    return "\n\n".join(lines)


def _worst_sites(data: dict, n: int = 5) -> str:
    ranked = sorted(data["sites"], key=lambda s: sum(1 for sec in s["sec"] if sec["c4"] or sec["cc"] or sec["cr"] or sec["cf"]), reverse=True)
    top = [s for s in ranked if any(sec["c4"] or sec["cc"] or sec["cr"] or sec["cf"] for sec in s["sec"])][:n]
    if not top:
        return "No sites have hard or Mod4/RSI clashes."
    lines = [f"Top {len(top)} sites by clashing sector count:"]
    for s in top:
        n_clash = sum(1 for sec in s["sec"] if sec["c4"] or sec["cc"] or sec["cr"] or sec["cf"])
        lines.append(f"- **{s['s']}** ({s['g']}): {n_clash}/{s['n']} sectors flagged")
    return "\n".join(lines)


def answer(message: str, data: dict, sectors: list, graph: dict, assignments: dict) -> str:
    msg_upper = message.upper()

    m = SECTOR_RE.search(msg_upper)
    if m:
        token = m.group(0)
        if token in assignments:
            exp = explain_sector(token, sectors, graph, assignments)
            return narrate(exp)
        candidates = sorted(sid for sid in assignments if sid.startswith(token + "-"))
        if candidates:
            exp = explain_sector(candidates[0], sectors, graph, assignments)
            return f"'{token}' is a site, not a sector - showing its first sector, **{candidates[0]}**:\n\n" + narrate(exp)

    lower = message.lower()
    for code, name in REGION_NAMES.items():
        if code.lower() in lower or name.lower() in lower:
            return _region_summary(data, code)

    if "worst" in lower or "top" in lower:
        return _worst_sites(data)

    if any(k in lower for k in ["pass", "fail", "valid"]):
        v = data["kpi"].get("validation", {})
        return f"Validation status: {'**PASS**' if v.get('pass') else '**FAIL**'}. " + _overall_summary(data)

    if any(k in lower for k in ["mod4", "clash"]):
        k = data["kpi"]
        return f"Mod4 clashes: **{k['mod4_clash_count']:,}** of {k['total_sectors']:,} sectors ({pct(k['mod4_clash_count'], k['total_sectors'])}%). This is expected to be high - see the structural note in the KPI bar."
    if "rsi" in lower:
        k = data["kpi"]
        return f"RSI reuse clashes: **{k['rsi_clash_count']:,}** of {k['total_sectors']:,} sectors ({pct(k['rsi_clash_count'], k['total_sectors'])}%)."
    if "mod3" in lower:
        k = data["kpi"]
        return f"Mod3 soft violations: **{k['mod3_soft_count']:,}** ({pct(k['mod3_soft_count'], k['total_sectors'])}%), all on sites with 4-5 co-located sectors (pigeonhole-impossible to fully avoid)."

    # Fallback: let the LLM phrase a general answer, but ONLY over the
    # retrieved summary text - never given free rein over the raw data.
    summary = _overall_summary(data)
    reply = _call_llm(
        system=(
            "You are a network-planning assistant for an NR5G PCI/RSI dashboard. "
            "Answer the user's question using ONLY the facts in the summary provided. "
            "If the summary doesn't contain the answer, say what information is available instead of guessing."
        ),
        user_content=f"Question: {message}\n\nAvailable facts:\n{summary}",
        max_tokens=300,
    )
    return reply or (
        "I can answer questions about a specific sector/site ID, a region (ALX/SIN/UPP/DEL), "
        "worst-clashing sites, or overall Mod4/RSI/Mod3 stats. Here's the overall picture:\n\n" + summary
    )