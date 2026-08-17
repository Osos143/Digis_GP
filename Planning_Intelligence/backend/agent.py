"""
agent.py - the Assistant tab's AI agent: an LLM used purely as a router
that reads the user's text, picks ZERO OR MORE of the tools below, and
then phrases their (already-computed) output back in plain language.

Hard rule, same one core/explain.py and core/assistant_chat.py already
followed: the model never computes a PCI/RSI/Mod4 value or a clash fact
itself. Every number in TOOL_IMPLS comes straight out of the real
pipeline (neighbor_graph.py / constraints.py / validator.py /
explain.py) - the model only chooses which function to call and how to
word the result.

Two interchangeable backends, switchable per-request from the UI:
    - "claude"  -> Anthropic Messages API, native `tools` param
    - "ollama"  -> local Ollama server (default model qwen2.5:7b),
                   OpenAI-style `tools` param - Ollama translates the
                   same JSON-schema shape for tool-calling models.

Both backends run the exact same tool loop against the exact same
TOOL_IMPLS, so switching models never changes what a tool call can
compute - only how the final sentence is phrased.
"""

from __future__ import annotations

import os
import json
from typing import Any, Callable

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
MAX_TOOL_ITERATIONS = 4

REGION_NAMES = {"ALX": "Alexandria", "SIN": "Sinai", "UPP": "Upper Egypt", "DEL": "Delta"}

# ---- helpers for the UI to show what the backend is actually configured with ----
def get_agent_info() -> dict:
    """What the Assistant tab should display - always the real values the
    backend is actually configured with, so the UI can never show a model
    name that doesn't match what a request actually hits."""
    return {"model": OLLAMA_MODEL, "url": OLLAMA_URL}

# ---------------------------------------------------------------------------
# Clash-type reference (static facts, not model-generated) - powers both the
# `clash_type_info` tool AND the Clashes tab's "what is this clash?" panel.
# ---------------------------------------------------------------------------
CLASH_DEFINITIONS = {
    "collision": {
        "label": "PCI collision", "severity": "hard - must be 0",
        "threshold": "Within 7 km",
        "rule": "Two sectors within 7 km must never share the same PCI - a device can't tell them apart during cell search.",
        "source": "Planning rules",
    },
    "confusion": {
        "label": "PCI confusion", "severity": "hard - must be 0",
        "threshold": "Within 14 km",
        "rule": "Two sectors within 14 km must never share the same PCI - a device could report the wrong handover target.",
        "source": "Planning rules",
    },
    "mod4": {
        "label": "Mod4 inter-site", "severity": "soft - informational",
        "threshold": "Within 7 km, different sites",
        "rule": "A sector and its nearest inter-site neighbor in its antenna direction share the same Mod4. This is tracked as a soft KPI.",
        "source": "Planning rules",
    },
    "rsi": {
        "label": "RSI reuse", "severity": "hard - must be 0",
        "threshold": "Within 14 km",
        "rule": "Two sectors within 14 km must not share the same RSI under the hard KPI rule.",
        "source": "Planning rules",
    },
    "mod3": {
        "label": "Mod3 adjacent", "severity": "hard - must be 0",
        "threshold": "Ring-adjacent sectors on the same site",
        "rule": "Ring-adjacent co-site sectors must not share the same Mod3 under the hard KPI rule.",
        "source": "Planning rules",
    },
    "mod4_intra": {
        "label": "Mod4 intra-site", "severity": "hard - must be 0",
        "threshold": "Ring-adjacent sectors on the same site",
        "rule": "Ring-adjacent co-site sectors must not share the same Mod4 under the hard KPI rule.",
        "source": "Planning rules",
    },
    "mod3_non_adj": {
        "label": "Mod3 non-adj reuse", "severity": "soft - informational",
        "threshold": "Non-adjacent sectors on the same site",
        "rule": "Non-adjacent co-site sectors sharing Mod3 are tracked as an informational soft KPI.",
        "source": "Planning rules",
    },
    "mod4_non_adj": {
        "label": "Mod4 non-adj intra-site", "severity": "soft - informational",
        "threshold": "Non-adjacent sectors on the same site",
        "rule": "Non-adjacent co-site sectors sharing Mod4 are tracked as an informational soft KPI.",
        "source": "Planning rules",
    },
    "clear": {
        "label": "Clear", "severity": "n/a",
        "threshold": "n/a", "rule": "No conflicts on this sector.",
        "source": "n/a",
    },
}


# ---------------------------------------------------------------------------
# Tool implementations - every one takes (args: dict, workbook_path: str)
# and returns a small JSON-safe dict. No tool ever decides a PCI/RSI/Mod4
# value; they only read what the real pipeline already computed.
# ---------------------------------------------------------------------------
def _pipeline(workbook_path: str):
    import cache
    return cache.get_pipeline_state(workbook_path)


def _network(workbook_path: str):
    import cache
    return cache.get_network_json(workbook_path)


def tool_explain_sector(args: dict, workbook_path: str) -> dict:
    from explain import explain_sector
    sectors, graph, assignments = _pipeline(workbook_path)
    return explain_sector(args["sector_id"], sectors, graph, assignments)


def tool_region_summary(args: dict, workbook_path: str) -> dict:
    data = _network(workbook_path)
    region = args["region"].upper()
    r = data["kpi"]["regions"].get(region)
    if not r:
        return {"error": f"unknown region '{region}'. Valid: {list(REGION_NAMES)}"}
    return {"region": region, "name": REGION_NAMES.get(region, region), **r}


def tool_overall_summary(args: dict, workbook_path: str) -> dict:
    data = _network(workbook_path)
    k = data["kpi"]
    return {
        "total_sectors": k["total_sectors"], "total_sites": k["total_sites"],
        "validation": k.get("validation"), "mod4_clash_count": k["mod4_clash_count"],
        "rsi_clash_count": k["rsi_clash_count"], "mod3_soft_count": k["mod3_soft_count"],
        "pci_collision_count": k["pci_collision_count"], "pci_confusion_count": k["pci_confusion_count"],
        "pci_range_used": k["pci_range_used"], "rsi_range_used": k["rsi_range_used"],
    }


def tool_worst_sites(args: dict, workbook_path: str) -> dict:
    data = _network(workbook_path)
    n = int(args.get("n", 5))
    region = (args.get("region") or "").upper() or None

    def clash_count(site):
        return sum(1 for sec in site["sec"] if sec["c4"] or sec["cc"] or sec["cr"] or sec["cf"])

    sites = [s for s in data["sites"] if region is None or s["g"] == region]
    ranked = sorted(sites, key=clash_count, reverse=True)
    top = [s for s in ranked if clash_count(s) > 0][:n]
    return {"sites": [{"site": s["s"], "region": s["g"], "clashing_sectors": clash_count(s), "total_sectors": s["n"]} for s in top]}


def tool_find_sites(args: dict, workbook_path: str) -> dict:
    data = _network(workbook_path)
    q = args["query"].strip().upper()
    matches = [s["s"] for s in data["sites"] if q in s["s"].upper()][:25]
    return {"query": q, "matches": matches, "count": len(matches)}


def tool_distance_between(args: dict, workbook_path: str) -> dict:
    from utils import haversine_m
    data = _network(workbook_path)
    by_id = {s["s"]: s for s in data["sites"]}
    a, b = by_id.get(args["site_a"].upper()), by_id.get(args["site_b"].upper())
    if not a or not b:
        return {"error": f"site not found: {'a' if not a else b}"}
    d_km = haversine_m(a["y"], a["x"], b["y"], b["x"]) / 1000.0
    return {
        "site_a": a["s"], "site_b": b["s"], "distance_km": round(d_km, 3),
        "tier1_collision_range": d_km <= 7.0, "tier2_confusion_range": d_km <= 14.0,
    }


def tool_neighbors_within_radius(args: dict, workbook_path: str) -> dict:
    from utils import haversine_m
    data = _network(workbook_path)
    by_id = {s["s"]: s for s in data["sites"]}
    center = by_id.get(args["site_id"].upper())
    if not center:
        return {"error": f"site '{args['site_id']}' not found"}
    radius_km = float(args.get("radius_km", 7.0))
    out = []
    for s in data["sites"]:
        if s["s"] == center["s"]:
            continue
        d_km = haversine_m(center["y"], center["x"], s["y"], s["x"]) / 1000.0
        if d_km <= radius_km:
            out.append({"site": s["s"], "region": s["g"], "distance_km": round(d_km, 2)})
    out.sort(key=lambda n: n["distance_km"])
    return {"center": center["s"], "radius_km": radius_km, "neighbors": out[:40], "count": len(out)}


def tool_clash_type_info(args: dict, workbook_path: str) -> dict:
    clash_type = (args.get("clash_type") or "").lower().strip()
    sector_id = args.get("sector_id")
    out: dict = {}
    if clash_type:
        out["definition"] = CLASH_DEFINITIONS.get(clash_type, {"error": f"unknown clash type '{clash_type}'"})
    if sector_id:
        from explain import explain_sector
        sectors, graph, assignments = _pipeline(workbook_path)
        out["live_explanation"] = explain_sector(sector_id, sectors, graph, assignments)
    if not out:
        out["definitions"] = CLASH_DEFINITIONS
    return out

def tool_plan_health_score(args: dict, workbook_path: str) -> dict:
    """Single composite score (0-100) summarizing overall plan quality -
    100 = zero hard violations and minimal soft conflict rate."""
    data = _network(workbook_path)
    k = data["kpi"]
    region = (args.get("region") or "").upper() or None
    if region:
        r = k["regions"].get(region)
        if not r:
            return {"error": f"unknown region '{region}'"}
        sectors = r["sectors"] or 1
        soft_rate = (r["mod4_clash"] + r["rsi_clash"] + r["mod3_soft"]) / (3 * sectors)
        hard = 0  # region breakdown doesn't carry hard counts separately; network-wide only
    else:
        sectors = k["total_sectors"] or 1
        soft_rate = (k["mod4_clash_count"] + k["rsi_clash_count"] + k["mod3_soft_count"]) / (3 * sectors)
        hard = k["pci_collision_count"] + k["pci_confusion_count"]

    score = 100.0
    score -= min(60, hard * 5)          # each hard violation costs heavily, capped
    score -= min(40, soft_rate * 100)   # soft conflict rate costs proportionally, capped
    score = max(0, round(score))

    return {
        "region": region or "network-wide",
        "score": score,
        "hard_violations": hard,
        "soft_conflict_rate_pct": round(soft_rate * 100, 1),
    }


def tool_compare_regions(args: dict, workbook_path: str) -> dict:
    """Side-by-side stats for two regions in a single call."""
    data = _network(workbook_path)
    a, b = (args.get("region_a") or "").upper(), (args.get("region_b") or "").upper()
    regions = data["kpi"]["regions"]
    if a not in regions or b not in regions:
        return {"error": f"unknown region(s): {[r for r in (a, b) if r not in regions]}. Valid: {list(REGION_NAMES)}"}
    ra, rb = regions[a], regions[b]
    return {
        a: {"name": REGION_NAMES.get(a, a), **ra},
        b: {"name": REGION_NAMES.get(b, b), **rb},
        "sector_count_diff": ra["sectors"] - rb["sectors"],
        "mod4_clash_rate_diff_pct": round((ra["mod4_clash"] / max(ra["sectors"], 1) - rb["mod4_clash"] / max(rb["sectors"], 1)) * 100, 2),
    }

TOOL_IMPLS: dict[str, Callable[[dict, str], dict]] = {
    "explain_sector": tool_explain_sector,
    "region_summary": tool_region_summary,
    "overall_summary": tool_overall_summary,
    "worst_sites": tool_worst_sites,
    "find_sites": tool_find_sites,
    "distance_between": tool_distance_between,
    "neighbors_within_radius": tool_neighbors_within_radius,
    "clash_type_info": tool_clash_type_info,
    "plan_health_score": tool_plan_health_score,
    "compare_regions": tool_compare_regions,
}

# JSON-schema tool specs - shared shape, adapted per backend below.
TOOL_SPECS = [
    {
        "name": "explain_sector",
        "description": "Get the full, real conflict breakdown for ONE sector (e.g. 'ALX2014-1') - PCI/Mod4/RSI/Mod3 values and every hard/soft clash with its neighbors, re-derived live from the neighbor graph.",
        "input_schema": {"type": "object", "properties": {"sector_id": {"type": "string"}}, "required": ["sector_id"]},
    },
    {
        "name": "region_summary",
        "description": "Sector/site counts and clash totals for one region (ALX, SIN, UPP, or DEL).",
        "input_schema": {"type": "object", "properties": {"region": {"type": "string", "enum": ["ALX", "SIN", "UPP", "DEL"]}}, "required": ["region"]},
    },
    {
        "name": "overall_summary",
        "description": "Network-wide totals: sectors, sites, PASS/FAIL, hard-rule counts, soft-conflict counts, PCI/RSI ranges used.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "worst_sites",
        "description": "Rank sites by how many of their sectors carry a hard or Mod4/RSI clash flag - use for 'worst', 'top offenders', 'which sites are bad' style questions.",
        "input_schema": {"type": "object", "properties": {"n": {"type": "integer", "default": 5}, "region": {"type": "string"}}},
    },
    {
        "name": "find_sites",
        "description": "Find site IDs containing a substring - use when the user gives a partial or fuzzy site/sector name.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "distance_between",
        "description": "Real haversine distance in km between two sites, plus whether they fall in the 7km collision / 14km confusion range.",
        "input_schema": {"type": "object", "properties": {"site_a": {"type": "string"}, "site_b": {"type": "string"}}, "required": ["site_a", "site_b"]},
    },
    {
        "name": "neighbors_within_radius",
        "description": "List every other site within a given radius (km) of one site - use for 'what's near X' or 'measure around this site' questions.",
        "input_schema": {"type": "object", "properties": {"site_id": {"type": "string"}, "radius_km": {"type": "number", "default": 7.0}}, "required": ["site_id"]},
    },
    {
        "name": "clash_type_info",
        "description": "Explain what a clash TYPE means (collision/confusion/mod4/rsi/mod3) - its rule, hard/soft severity, and distance threshold. Pass sector_id too for that sector's live, specific cause (which neighbor, what distance).",
        "input_schema": {"type": "object", "properties": {
            "clash_type": {"type": "string", "enum": ["collision", "confusion", "mod4", "rsi", "mod3"]},
            "sector_id": {"type": "string"},
        }},
    },
    {
        "name": "plan_health_score",
        "description": "One composite 0-100 score summarizing overall plan quality for the whole network or one region - use for 'how good is this plan overall' style questions.",
        "input_schema": {"type": "object", "properties": {"region": {"type": "string", "enum": ["ALX", "SIN", "UPP", "DEL"]}}},
    },
    {
        "name": "compare_regions",
        "description": "Side-by-side stats for two regions in one call - use for 'compare X and Y' style questions instead of calling region_summary twice.",
        "input_schema": {"type": "object", "properties": {
            "region_a": {"type": "string", "enum": ["ALX", "SIN", "UPP", "DEL"]},
            "region_b": {"type": "string", "enum": ["ALX", "SIN", "UPP", "DEL"]},
        }, "required": ["region_a", "region_b"]},
    },
]

TOOL_DESCRIPTIONS = [{"name": t["name"], "description": t["description"]} for t in TOOL_SPECS]

SYSTEM_PROMPT = (
    "You are the Network Pulse assistant, helping a network-planning engineer explore an "
    "NR5G PCI/RSI/Mod4 planning workbook. Use the tools available to you to look up REAL facts "
    "before answering - never invent a PCI, RSI, Mod4, distance, or count. If a tool returns an "
    "error (e.g. site not found), say so plainly instead of guessing. Keep answers concise and "
    "use bold for concrete numbers/IDs. If the user asks something no tool can answer, say what "
    "you *can* help with instead of making something up."
)


# ---------------------------------------------------------------------------
# Claude backend
# ---------------------------------------------------------------------------
def _run_claude(message: str, workbook_path: str, history: list[dict]) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "reply": "Claude isn't configured yet - set the `ANTHROPIC_API_KEY` environment variable on the backend "
                      "(and optionally `CLAUDE_MODEL`, default `claude-sonnet-5`) and restart the server.",
            "tool_calls": [], "model": "claude (not configured)",
        }
    try:
        import anthropic
    except ImportError:
        return {"reply": "The `anthropic` package isn't installed on the backend - run `pip install anthropic`.",
                "tool_calls": [], "model": "claude (not installed)"}

    client = anthropic.Anthropic(api_key=api_key)
    messages = [*history, {"role": "user", "content": message}]
    tool_calls_made = []

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=800, system=SYSTEM_PROMPT,
            tools=TOOL_SPECS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"reply": text or "(no response)", "tool_calls": tool_calls_made, "model": f"claude:{CLAUDE_MODEL}"}

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            impl = TOOL_IMPLS.get(block.name)
            result = impl(block.input, workbook_path) if impl else {"error": f"unknown tool '{block.name}'"}
            tool_calls_made.append({"name": block.name, "input": block.input, "result": result})
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)[:4000]})
        messages.append({"role": "user", "content": tool_results})

    return {"reply": "Stopped after several tool calls without a final answer - try rephrasing.",
            "tool_calls": tool_calls_made, "model": f"claude:{CLAUDE_MODEL}"}


# ---------------------------------------------------------------------------
# Ollama backend (local qwen2.5:7b, or whatever OLLAMA_MODEL is set to)
# ---------------------------------------------------------------------------
def _ollama_tool_specs() -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in TOOL_SPECS]


def _run_ollama(message: str, workbook_path: str, history: list[dict]) -> dict:
    try:
        import requests
    except ImportError:
        return {"reply": "The `requests` package isn't installed on the backend.", "tool_calls": [], "model": "ollama (not installed)"}

    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": message}]
    tool_calls_made = []

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "tools": _ollama_tool_specs(), "stream": False},
                timeout=180,
            )
            resp.raise_for_status()
        except Exception as e:
            return {
                "reply": f"Couldn't reach Ollama at {OLLAMA_URL} (is `ollama serve` running, and is `{OLLAMA_MODEL}` pulled?). Error: {e}",
                "tool_calls": tool_calls_made, "model": f"ollama:{OLLAMA_MODEL} (unreachable)",
            }

        msg = resp.json().get("message", {})
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"reply": msg.get("content") or "(no response)", "tool_calls": tool_calls_made, "model": f"ollama:{OLLAMA_MODEL}"}

        messages.append(msg)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            raw_args = fn.get("arguments") or {}
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
            impl = TOOL_IMPLS.get(name)
            result = impl(args, workbook_path) if impl else {"error": f"unknown tool '{name}'"}
            tool_calls_made.append({"name": name, "input": args, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result)[:4000]})

    return {"reply": "Stopped after several tool calls without a final answer - try rephrasing.",
            "tool_calls": tool_calls_made, "model": f"ollama:{OLLAMA_MODEL}"}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def run_agent(message: str, workbook_path: str, model: str, history: list[dict] | None = None) -> dict:
    """Ollama only - Claude backend removed. `model` param is accepted for
    call-site compatibility but ignored."""
    history = history or []
    return _run_ollama(message, workbook_path, history)