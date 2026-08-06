"""
main.py - Network Pulse API (FastAPI edition).

This file is the ONLY place that turns HTTP requests into calls against
the real pipeline (pipeline/loader.py -> neighbor_graph.py ->
constraints.py -> assignment_engine.py -> bulk_plan.py -> validator.py ->
exporter.py -> add_site.py). Every pipeline module is byte-for-byte the
same file that ran under Streamlit - this replaces core/state.py's
st.cache_resource with a plain dict cache keyed on (path, mtime), and
replaces st.session_state["active_xlsx"] with an explicit `workbook` id
the React client passes on every call (see core/workbooks.py).

No planning decision is made here - this file only wires requests to
functions that already exist, exactly like core/*_ops.py did for
Streamlit.
"""

from __future__ import annotations

import os
import sys
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.join(BASE_DIR, "pipeline")
DATA_DIR = os.path.join(BASE_DIR, "data")
LIVE_DIR = os.path.join(DATA_DIR, "live")
os.makedirs(LIVE_DIR, exist_ok=True)
sys.path.insert(0, PIPELINE_DIR)

from workbooks import (  # noqa: E402  (path must be resolved first)
    resolve_workbook, register_live_workbook, list_workbooks, RAW_ID, FINAL_ID,
)
import cache  # noqa: E402

app = FastAPI(title="Network Pulse API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileNotFoundError)
async def _handle_missing_workbook_file(request, exc: FileNotFoundError):
    """A registered workbook id can outlive its file (deleted upload,
    server restart, manual cleanup). Surface that as a clean 404 instead
    of a 500 crash, so the client can drop the stale id and send the
    user back to Upload & Plan."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=404,
        content={"detail": "This workbook's file is no longer available. Please upload it again."},
    )


@app.exception_handler(ValueError)
async def _handle_unknown_workbook_id(request, exc: ValueError):
    """`resolve_workbook()` raises ValueError for an id it doesn't know
    about (e.g. a "live:xxxxxxxx" id from before a backend restart, or a
    stale id from localStorage). Treat that the same way as a missing
    file rather than a raw 500."""
    from fastapi.responses import JSONResponse

    if "unknown workbook id" in str(exc):
        return JSONResponse(
            status_code=404,
            content={"detail": "This workbook's file is no longer available. Please upload it again."},
        )
    raise exc


def _kpi_summary_from_sheet(path: str) -> dict | None:
    """Read the exported KPI_Report sheet when present and convert it to a compact summary for the UI."""
    if not path or not os.path.exists(path):
        return None
    try:
        import openpyxl  # type: ignore
    except Exception:
        return None

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return None

    if "KPI_Report" not in workbook.sheetnames:
        return None

    sheet = workbook["KPI_Report"]
    rows = list(sheet.iter_rows(values_only=True))
    section = None
    hard: dict[str, int] = {}
    soft: dict[str, int] = {}
    coverage: dict[str, int] = {}
    status = "READY"

    for row in rows:
        if not row or len(row) < 2:
            continue
        metric = row[0]
        value = row[1]
        if not isinstance(metric, str):
            continue
        label = metric.strip()
        low = label.lower()
        if low == "overall result":
            status = str(value).upper() if value is not None else "READY"
        elif low == "hard rules (must be 0)":
            section = "hard"
        elif low == "soft conflicts (informational)":
            section = "soft"
        elif low == "full kpi breakdown (all granularities)":
            section = "breakdown"
        elif low == "coverage":
            section = "coverage"
        elif section == "hard" and label:
            hard[label] = int(value) if isinstance(value, (int, float)) else 0
        elif section == "soft" and label:
            soft[label] = int(value) if isinstance(value, (int, float)) else 0
        elif section == "coverage" and label:
            coverage[label] = int(value) if isinstance(value, (int, float)) else 0

    if not hard and not soft and not coverage:
        return None

    hard_total = sum(hard.values())
    soft_total = sum(soft.values())
    return {
        "source": "kpi-sheet",
        "status": status,
        "hard_issues": hard_total,
        "soft_issues": soft_total,
        "hard": hard,
        "soft": soft,
        "coverage": coverage,
    }


def _enrich_kpi_summary(path: str, payload: dict) -> dict:
    kpi = payload.setdefault("kpi", {})
    if kpi.get("summary"):
        return payload

    validation = kpi.get("validation") or {}
    if validation:
        hard_total = sum(int(validation.get("hard", {}).get(key, 0)) for key in validation.get("hard", {}))
        soft_total = sum(int(validation.get("soft", {}).get(key, 0)) for key in validation.get("soft", {}))
        kpi["summary"] = {
            "source": "validator",
            "status": "PASS" if validation.get("pass") else "FAIL",
            "hard_issues": hard_total,
            "soft_issues": soft_total,
            "hard": validation.get("hard", {}),
            "soft": validation.get("soft", {}),
        }
        return payload

    sheet_summary = _kpi_summary_from_sheet(path)
    if sheet_summary:
        kpi["summary"] = sheet_summary
        return payload

    else:
        kpi["summary"] = {
            "source": "raw",
            "status": "READY",
            "hard_issues": 0,
            "soft_issues": 0,
            "hard": {},
            "soft": {},
        }
    return payload


# --------------------------------------------------------------------------
# request/response models
# --------------------------------------------------------------------------
class ReplanRequest(BaseModel):
    pass


class NewSitePreviewRequest(BaseModel):
    site_id: str
    lat: float
    lon: float
    azimuths: list[float]


class NewSiteCommitRequest(BaseModel):
    tmp_id: str
    assignments: dict


class ExistingReplanPreviewRequest(BaseModel):
    workbook: str
    target_site: str


class ExistingReplanOptionsRequest(BaseModel):
    workbook: str
    target_site: str
    assignments: dict
    mod3_choices: dict[str, int] | None = None


class ExistingReplanCommitRequest(BaseModel):
    workbook: str
    assignments: dict


class ChatRequest(BaseModel):
    workbook: str
    message: str


class AgentChatRequest(BaseModel):
    workbook: str
    message: str
    model: str = "claude"  # "claude" | "ollama"
    history: list[dict] = []


# --------------------------------------------------------------------------
# workbook / kpi / map endpoints
# --------------------------------------------------------------------------
@app.get("/api/workbooks")
def api_workbooks():
    """Every workbook the client can select: the shipped raw + planned
    files, plus anything produced by a replan/commit this session."""
    return list_workbooks()


@app.get("/api/network")
def api_network(workbook: str = FINAL_ID):
    path = resolve_workbook(workbook)
    return _enrich_kpi_summary(path, cache.get_network_json(path))


@app.get("/api/raw")
def api_raw(workbook: str = RAW_ID):
    path = resolve_workbook(workbook)
    return _enrich_kpi_summary(path, cache.get_raw_json(path))

@app.get("/api/sectors_raw")
def api_sectors_raw(workbook: str = FINAL_ID):
    """Flat per-sector rows including UNPLANNED sectors (pci/rsi/mod4 may
    be null), and does NOT run validate() or require a full plan. Used by
    the Voronoi Compare tab so an old, partially-planned, or differently-
    shaped workbook never throws - it just returns whatever exists."""
    from loader import load_sectors

    path = resolve_workbook(workbook)
    sectors = load_sectors(path, plan_all=False)
    return [
        {
            "id": s["site_sector_id"], "site": s["site_id"],
            "lat": s["lat"], "lon": s["lon"], "az": s["azimuth"],
            "pci": s["pci"], "mod4": s["mod4"], "rsi": s["rsi"],
        }
        for s in sectors
    ]

@app.get("/api/sectors")
def api_sectors(workbook: str = FINAL_ID):
    """Flat per-sector rows for the Assignments table - one dict per sector."""
    data = cache.get_network_json(resolve_workbook(workbook))
    rows = []
    for site in data["sites"]:
        for sec in site["sec"]:
            rows.append({
                "id": sec["i"], "site": site["s"], "region": site["g"],
                "lat": site["y"], "lon": site["x"], "az": sec["a"],
                "pci": sec.get("p"), "mod4": sec.get("m"), "rsi": sec.get("r"), "mod3": sec.get("t"),
                "c4": sec.get("c4", False), "cc": sec.get("cc", False),
                "cr": sec.get("cr", False), "c3": sec.get("c3", False), "cf": sec.get("cf", False),
                "c3n": sec.get("c3n", False), "c4i": sec.get("c4i", False), "c4n": sec.get("c4n", False),
            })
    return rows


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    """The base tab: accept a raw (unplanned) .xlsx, validate its shape
    with the real loader, and register it as a new selectable workbook.
    Nothing is planned yet - call POST /api/replan?workbook=<id> next."""
    from loader import load_sectors, LoaderError

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload an .xlsx workbook.")

    upload_dir = os.path.join(LIVE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, f"{uuid.uuid4().hex[:8]}_{file.filename}")
    with open(dest, "wb") as f:
        f.write(await file.read())

    try:
        sectors = load_sectors(dest, plan_all=True)
    except LoaderError as e:
        os.remove(dest)
        raise HTTPException(400, f"Invalid workbook: {e}")

    assignments = {
        s["site_sector_id"]: {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
        for s in sectors
    }
    final_like = sum(1 for a in assignments.values() if a["pci"] is not None and a["rsi"] is not None and a["mod4"] is not None)
    if final_like == len(assignments):
        os.remove(dest)
        raise HTTPException(
            400,
            "This workbook already looks fully planned. Use the 'Final' upload option instead of 'Raw'.",
        )

    workbook_id = register_live_workbook(dest, f"Uploaded: {file.filename}")
    return {"workbook": workbook_id, "label": file.filename, "sectors": len(sectors),
            "sites": len({s["site_id"] for s in sectors})}


# main.py — add near api_upload

@app.post("/api/upload_final")
async def api_upload_final(file: UploadFile = File(...)):
    """Accept an ALREADY-PLANNED .xlsx (has PCI/RSI/Mod4 filled in) and
    register it directly as a usable workbook — no planning run, no
    demo data involved. This becomes the active workbook immediately."""
    from loader import load_sectors, LoaderError
    from validator import validate
    from neighbor_graph import build_neighbor_graph

    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload an .xlsx workbook.")

    upload_dir = os.path.join(LIVE_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, f"{uuid.uuid4().hex[:8]}_{file.filename}")
    with open(dest, "wb") as f:
        f.write(await file.read())

    try:
        sectors = load_sectors(dest, plan_all=False)  # read as-is, don't force replanning
    except LoaderError as e:
        os.remove(dest)
        raise HTTPException(400, f"Invalid workbook: {e}")

    assignments = {
        s["site_sector_id"]: {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
        for s in sectors
    }
    n_missing = sum(1 for a in assignments.values() if a["pci"] is None)
    if n_missing > 0:
        os.remove(dest)
        raise HTTPException(
            400,
            f"{n_missing} sector(s) have no PCI assigned yet — this looks like a raw "
            f"workbook, not a final one. Use the 'Raw (needs planning)' option instead.",
        )

    graph = build_neighbor_graph(sectors, use_cache=True)
    report = validate(sectors, graph, assignments)

    workbook_id = register_live_workbook(dest, f"Uploaded final: {file.filename}")
    cache.invalidate(dest)
    hard = report.get("hard", {})
    return {
        "workbook": workbook_id, "label": file.filename,
        "sectors": len(sectors), "sites": len({s["site_id"] for s in sectors}),
        "pass": report["pass"],
        "collisions": hard.get("pci_collision", 0),
        "confusions": hard.get("pci_confusion", 0),
        "mod3": hard.get("mod3_adjacent", 0) + hard.get("mod3_rule_violations", 0),
    }

@app.post("/api/replan")
def api_replan(workbook: str = RAW_ID):
    """Runs the real bulk_plan.py from scratch on `workbook` (any raw,
    unplanned workbook - the shipped RAW_ID or one just uploaded via
    /api/upload), then validator.py + exporter.py, and registers the
    result as a new selectable workbook - mirrors run_planning_ops.py.
    This is the ONLY place a full replan happens; every other tab just
    reads whichever workbook the client currently has active."""
    from bulk_plan import bulk_plan
    from validator import validate
    from exporter import export_results

    src_path = resolve_workbook(workbook)
    src_label = os.path.basename(src_path)
    sectors, graph, assignments = bulk_plan(src_path)
    report = validate(sectors, graph, assignments)
    out_path = os.path.join(LIVE_DIR, f"NR5G_PCI_RSI_Planning_planned_{uuid.uuid4().hex[:8]}.xlsx")
    export_results(src_path, out_path, assignments, report)
    cache.invalidate(out_path)
    workbook_id = register_live_workbook(out_path, f"Planned: {src_label}")
    hard = report.get("hard", {})
    return {
        "workbook": workbook_id,
        "written": len(assignments),
        "pass": report["pass"],
        "collisions": hard.get("pci_collision", 0),
        "confusions": hard.get("pci_confusion", 0),
        "mod3": hard.get("mod3_adjacent", 0) + hard.get("mod3_rule_violations", 0),
    }


# --------------------------------------------------------------------------
# clash explainer + chat  (core/explain.py + core/assistant_chat.py, verbatim logic)
# --------------------------------------------------------------------------
@app.get("/api/explain/{sector_id}")
def api_explain(sector_id: str, workbook: str = FINAL_ID):
    from explain import explain_sector, narrate

    sectors, graph, assignments = cache.get_pipeline_state(resolve_workbook(workbook))
    exp = explain_sector(sector_id, sectors, graph, assignments)
    if "error" in exp:
        raise HTTPException(404, exp["error"])
    exp["narration"] = narrate(exp)
    return exp


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    from assistant_chat import answer

    sectors, graph, assignments = cache.get_pipeline_state(resolve_workbook(req.workbook))
    data = cache.get_network_json(resolve_workbook(req.workbook))
    reply = answer(req.message, data, sectors, graph, assignments)
    return {"reply": reply}


# --------------------------------------------------------------------------
# AI agent - the LLM picks tools from text, tools compute real facts, the
# LLM only phrases the result. Switchable per-request between Claude
# (cloud, ANTHROPIC_API_KEY) and Ollama (local, qwen2.5:7b by default).
# --------------------------------------------------------------------------
@app.get("/api/agent/tools")
def api_agent_tools():
    from agent import TOOL_DESCRIPTIONS
    return TOOL_DESCRIPTIONS

@app.get("/api/agent/info")
def api_agent_info():
    from agent import get_agent_info
    return get_agent_info()

@app.post("/api/agent/chat")
def api_agent_chat(req: AgentChatRequest):
    from agent import run_agent
    return run_agent(req.message, resolve_workbook(req.workbook), req.model, req.history)


@app.get("/api/clash_info")
def api_clash_info():
    """Static clash-type reference (hard/soft, threshold, rule, source) -
    the Clashes tab's 'what is this clash?' panel, no LLM involved."""
    from agent import CLASH_DEFINITIONS
    return CLASH_DEFINITIONS


@app.get("/api/clash_info/{sector_id}")
def api_clash_info_sector(sector_id: str, workbook: str = FINAL_ID):
    """Same reference, plus the live, real reason THIS sector clashes (or
    doesn't) - re-derived from explain.py, same as the Assistant tab."""
    from agent import tool_clash_type_info
    return tool_clash_type_info({"sector_id": sector_id}, resolve_workbook(workbook))


# --------------------------------------------------------------------------
# Add Site: brand-new site  (core/add_site_ops.py, verbatim logic)
# --------------------------------------------------------------------------
@app.post("/api/addsite/new/preview")
def api_addsite_new_preview(req: NewSitePreviewRequest, workbook: str = FINAL_ID):
    from add_site import add_site
    from neighbor_graph import direct_neighbors, build_neighbor_graph
    from loader import load_sectors

    base_path = resolve_workbook(workbook)
    existing_ids = {s["site_id"] for s in cache.get_pipeline_state(base_path)[0]}
    if req.site_id in existing_ids:
        raise HTTPException(400, f"'{req.site_id}' already exists - use the re-plan flow instead.")

    tmp_path = os.path.join(LIVE_DIR, f"_preview_{req.site_id}.xlsx")
    _append_new_site_rows(base_path, tmp_path, req.site_id, req.lat, req.lon, req.azimuths)

    _, _, existing_assignments = cache.get_pipeline_state(base_path)
    new_assignments = add_site(tmp_path, existing_assignments, req.site_id)

    sectors = load_sectors(tmp_path, plan_all=True)
    graph = build_neighbor_graph(sectors, use_cache=True)
    new_ids = set(new_assignments.keys())
    neighbors = []
    for sid in new_ids:
        for nb in direct_neighbors(graph, sid):
            if nb not in new_ids:
                a = existing_assignments.get(nb)
                if a:
                    neighbors.append({"sector": sid, "neighbor": nb, "pci": a["pci"], "mod4": a["mod4"], "rsi": a["rsi"]})

    tmp_id = register_live_workbook(tmp_path, f"preview:{req.site_id}", selectable=False)
    return {"tmp_id": tmp_id, "assignments": new_assignments, "neighbors": neighbors}


@app.post("/api/addsite/new/commit")
def api_addsite_new_commit(req: NewSiteCommitRequest):
    from loader import load_sectors
    from neighbor_graph import build_neighbor_graph
    from validator import validate
    from exporter import export_results

    tmp_path = resolve_workbook(req.tmp_id)
    sectors = load_sectors(tmp_path)
    full_assignments = {
        s["site_sector_id"]: (
            req.assignments[s["site_sector_id"]] if s["site_sector_id"] in req.assignments
            else {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
        )
        for s in sectors
    }
    graph = build_neighbor_graph(sectors, use_cache=True)
    report = validate(sectors, graph, full_assignments)

    out_path = os.path.join(LIVE_DIR, "NR5G_PCI_RSI_Planning_live.xlsx")
    export_results(tmp_path, out_path, req.assignments, report)
    cache.invalidate(out_path)
    workbook_id = register_live_workbook(out_path, "Live (after Add Site)")
    return {"workbook": workbook_id, "report": report}


def _append_new_site_rows(src_path, out_path, site_id, lat, lon, azimuths, band="N41",
                           cell_radius=7000.0, base_sector_id=91):
    import openpyxl
    shutil.copy(src_path, out_path)
    wb = openpyxl.load_workbook(out_path)
    ws = wb["Planning"]
    n = len(azimuths)
    for i, az in enumerate(azimuths):
        sid = f"{site_id}-{i + 1}"
        ws.append([sid, site_id, n, base_sector_id + i, True, az, lat, lon, band, cell_radius, None, None, None])
    wb.save(out_path)
    return out_path


def _rank_pci_suggestions(candidates: list[int], current_pci: int | None, limit: int = 16) -> list[int]:
    if not candidates:
        return []

    ranked = sorted(
        candidates,
        key=lambda pci: (
            0 if current_pci is not None and pci == current_pci else 1,
            abs(pci - current_pci) if current_pci is not None else pci,
            pci,
        ),
    )
    return ranked[:limit]


def _replan_site_editor_options(base_path: str, target_site: str, draft_assignments: dict, mod3_choices: dict | None = None) -> dict:
    from constraints import compute_forbidden_sets, valid_pci_candidates, group_sectors_by_site, mod4_co_site_siblings

    sectors, graph, existing_assignments = cache.get_pipeline_state(base_path)
    target_sectors = [s for s in sectors if s["site_id"] == target_site]
    if not target_sectors:
        raise HTTPException(404, f"site '{target_site}' not found")

    target_ids = {s["site_sector_id"] for s in target_sectors}
    locked_assignments = {sid: a for sid, a in existing_assignments.items() if sid not in target_ids}
    merged_assignments = {**locked_assignments, **draft_assignments}
    sectors_by_site = group_sectors_by_site(sectors)
    mod3_choices = mod3_choices or {}

    options = {}
    for sector in sorted(target_sectors, key=lambda s: s["azimuth"]):
        sid = sector["site_sector_id"]
        assignment = draft_assignments.get(sid, {})
        current_pci = assignment.get("pci")
        current_mod4 = assignment.get("mod4")
        current_mod3 = mod3_choices.get(sid)
        if current_mod3 is None and current_pci is not None:
            current_mod3 = int(current_pci) % 3

        local_assignments = dict(merged_assignments)
        local_assignments.pop(sid, None)
        forbidden = compute_forbidden_sets(sector, graph, local_assignments, sectors_by_site)
        valid_pci = valid_pci_candidates(forbidden)

        sibling_forbidden = set()
        for sibling_id in mod4_co_site_siblings(sector, sectors_by_site):
            sibling_assignment = local_assignments.get(sibling_id)
            if sibling_assignment and sibling_assignment.get("mod4") is not None:
                sibling_forbidden.add(int(sibling_assignment["mod4"]))
        valid_mod4 = [color for color in range(4) if color not in sibling_forbidden]
        valid_mod3 = sorted({pci % 3 for pci in valid_pci})

        filtered_pci = [pci for pci in valid_pci if (current_mod4 is None or pci % 4 == current_mod4) and (current_mod3 is None or pci % 3 == current_mod3)]

        if current_mod4 is not None and current_mod4 not in valid_mod4:
            valid_mod4 = sorted({current_mod4, *valid_mod4})
        if current_mod3 is not None and current_mod3 not in valid_mod3:
            valid_mod3 = sorted({current_mod3, *valid_mod3})

        options[sid] = {
            "valid_pci": filtered_pci,
            "suggested_pci": _rank_pci_suggestions(filtered_pci, current_pci),
            "valid_mod4": valid_mod4 or [0, 1, 2, 3],
            "valid_mod3": valid_mod3 or [0, 1, 2],
        }

    return options


# --------------------------------------------------------------------------
# Add Site: re-plan an existing site  (core/add_site_ops.py, verbatim logic)
# --------------------------------------------------------------------------
@app.post("/api/replan_site/preview")
def api_replan_site_preview(req: ExistingReplanPreviewRequest):
    from add_site import add_site
    from neighbor_graph import direct_neighbors

    base_path = resolve_workbook(req.workbook)
    sectors, graph, assignments = cache.get_pipeline_state(base_path)
    old = {sid: a for sid, a in assignments.items() if sid.rsplit("-", 1)[0] == req.target_site}
    if not old:
        raise HTTPException(404, f"site '{req.target_site}' not found")

    new_assignments = add_site(base_path, assignments, req.target_site)

    new_ids = set(new_assignments.keys())
    neighbors = []
    for sid in new_ids:
        for nb in direct_neighbors(graph, sid):
            if nb not in new_ids:
                a = assignments.get(nb)
                if a:
                    neighbors.append({"sector": sid, "neighbor": nb, "pci": a["pci"], "mod4": a["mod4"], "rsi": a["rsi"]})

    editor_options = _replan_site_editor_options(base_path, req.target_site, new_assignments)
    return {"old": old, "assignments": new_assignments, "neighbors": neighbors, "editor_options": editor_options}


@app.post("/api/replan_site/options")
def api_replan_site_options(req: ExistingReplanOptionsRequest):
    base_path = resolve_workbook(req.workbook)
    return {"editor_options": _replan_site_editor_options(base_path, req.target_site, req.assignments, req.mod3_choices)}


@app.post("/api/replan_site/commit")
def api_replan_site_commit(req: ExistingReplanCommitRequest):
    from loader import load_sectors
    from neighbor_graph import build_neighbor_graph
    from validator import validate
    from exporter import export_results

    base_path = resolve_workbook(req.workbook)
    sectors = load_sectors(base_path)
    full_assignments = {
        s["site_sector_id"]: (
            req.assignments[s["site_sector_id"]] if s["site_sector_id"] in req.assignments
            else {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
        )
        for s in sectors
    }
    graph = build_neighbor_graph(sectors, use_cache=True)
    report = validate(sectors, graph, full_assignments)

    out_path = os.path.join(LIVE_DIR, "NR5G_PCI_RSI_Planning_live.xlsx")
    export_results(base_path, out_path, req.assignments, report)
    cache.invalidate(out_path)
    workbook_id = register_live_workbook(out_path, "Live (after re-plan)")
    return {"workbook": workbook_id, "report": report}


# --------------------------------------------------------------------------
# export / download
# --------------------------------------------------------------------------
@app.get("/api/download")
def api_download(workbook: str = FINAL_ID):
    path = resolve_workbook(workbook)
    return FileResponse(path, filename=os.path.basename(path))


@app.get("/api/health")
def api_health():
    return {"status": "ok"}
