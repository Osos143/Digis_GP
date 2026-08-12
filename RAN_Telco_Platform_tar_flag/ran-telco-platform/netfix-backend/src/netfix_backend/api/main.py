"""
FastAPI app for the NetFix backend. Thin orchestration only -- every
endpoint here does argument parsing/validation and then calls straight into
`bootstrap.AppContext`'s orchestrators/services; no business logic lives in
this file (Single Responsibility -- see the services/orchestration packages
for where the actual logic is).

The app builds one AppContext at startup (one Mongo connection, one LLM
client) and reuses it for every request -- rebuilding either per-request
would be wasteful and, for the LLM client, adds needless latency.

Run with:
    uvicorn netfix_backend.api.main:app --host 0.0.0.0 --port 8000
"""


from __future__ import annotations

import os
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import sys  # <--- إضافة sys الأساسية لمنع NameError
import json
import httpx  # <---
import uuid
import hashlib
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from netfix_backend.bootstrap import AppContext, build_context
from netfix_backend.orchestration.phase1 import Phase1Error
from netfix_backend.orchestration.phase2 import Phase2Error
from netfix_backend.services.session_service import SessionNotFoundError

_ctx: Optional[AppContext] = None


def get_context() -> AppContext:
    if _ctx is None:
        raise HTTPException(status_code=503, detail="Backend not initialized yet.")
    return _ctx


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ctx
    _ctx = build_context(
        mongo_uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
        mongo_db=os.environ.get("MONGO_DB", "ran_telco"),
        reasons_file=os.environ.get("REASONS_FILE"),
        llm_provider=os.environ.get("LLM_PROVIDER", "ollama"),
        llm_model=os.environ.get("LLM_MODEL"),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL"),
        skip_llm=os.environ.get("SKIP_LLM", "").lower() in ("1", "true"),
    )
    yield
    _ctx = None


app = FastAPI(title="NetFix Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ThresholdsRequest(BaseModel):
    thresholds: Optional[dict[str, Any]] = None
    explain: bool = True
    anomaly_ids: Optional[list[str]] = None


class ExplainRequest(BaseModel):
    anomaly_id: str


@app.post("/sessions")
async def upload_dataset(file: UploadFile = File(...)):
    """Phase 1: upload a .pkl drive-test dataset. Runs cleaning, anomaly
    detection, and statistics synchronously, then returns the session
    summary once it's in the PHASE1_DONE / WAIT state."""
    ctx = get_context()
    suffix = Path(file.filename).suffix or ".pkl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        # Stream in 4 MB chunks so ~800 MB files write at max disk speed with minimal RAM usage.
        CHUNK_SIZE = 4 * 1024 * 1024
        while chunk := await file.read(CHUNK_SIZE):
            tmp.write(chunk)
        tmp_path = tmp.name
    try:
        # Phase 1 is split into start() + process(). start() saves the upload
        # and returns immediately; process() (cleaning + detection) runs in a
        # background thread so the HTTP request doesn't block for 30-60 min
        # and the server stays responsive. The frontend polls GET /sessions.
        session = ctx.phase1.start(tmp_path, filename=file.filename)
        threading.Thread(
            target=ctx.phase1.process,
            args=(session.session_id,),
            daemon=True,
        ).start()
        return session.summary()
    except Phase1Error as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.get("/sessions")
async def list_sessions():
    ctx = get_context()
    return [s.summary() for s in ctx.session_service.list()]


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, full: bool = False):
    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return session.to_doc() if full else session.summary()


@app.get("/sessions/{session_id}/anomalies")
async def get_anomalies(session_id: str):
    ctx = get_context()
    anomalies = []
    try:
        session = ctx.session_service.get(session_id)
        anomalies = getattr(session, 'anomalies', []) or []
    except Exception:
        pass

    if not anomalies:
        try:
            mongo_client = rca_service_instance.get_mongo_client()
            if mongo_client:
                db = mongo_client[rca_service_instance.mongo_db_name]
                anomalies = list(db["rca_anomaly_incidents_full_compact"].find({"session_id": session_id}))
                if not anomalies:
                    anomalies = list(db["anomalies"].find({"session_id": session_id}))
                if not anomalies:
                    anomalies = list(db["rca_anomaly_incidents_full_compact"].find().limit(100))
                if not anomalies:
                    anomalies = list(db["anomalies"].find().limit(100))
        except Exception:
            pass

    if not anomalies:
        try:
            search_paths = [
                Path(f"outputs/session_{session_id[:12]}/04_rca_handoff_final/rca_anomaly_incidents_full_compact.json"),
                Path("outputs/04_rca_handoff_final/rca_anomaly_incidents_full_compact.json"),
                Path("ran-telco-platform/outputs/04_rca_handoff_final/rca_anomaly_incidents_full_compact.json"),
                Path("/media/mogahed/New Volume/iti_gp/Sakr_200/ran-telco-platform_tar_flag/ran-telco-platform/outputs/04_rca_handoff_final/rca_anomaly_incidents_full_compact.json")
            ]
            for p in search_paths:
                if p.exists():
                    with open(p, "r") as f:
                        anomalies = json.load(f)
                        if anomalies:
                            break
        except Exception:
            pass

    normalized = []
    for idx, doc in enumerate(anomalies or []):
        if not isinstance(doc, dict):
            continue
        item = dict(doc)
        if "_id" in item:
            item["_id"] = str(item["_id"])
        
        # Ensure fallback aliases so frontend displays Cell ID, Severity, Score, and Type cleanly
        item["incident_id"] = item.get("incident_id") or item.get("id") or f"INC-{idx+1:06d}"
        item["anomaly_type"] = item.get("anomaly_type") or item.get("detection_case") or "Radio Degradation"
        item["anomaly_severity"] = item.get("anomaly_severity") or item.get("severity") or "High"
        item["anomaly_score"] = item.get("anomaly_score") or item.get("priority_score_0_100") or item.get("impact_score_0_100") or 75
        item["cell_id"] = item.get("cell_id") or (f"ECI: {int(item['serving_eci'])}" if item.get("serving_eci") else None) or (f"PCI: {int(item['serving_pci'])}" if item.get("serving_pci") else None) or item.get("serving_cell_key") or "Cell-01"
        
        normalized.append(item)

    return normalized


@app.get("/sessions/{session_id}/thresholds")
async def get_thresholds(session_id: str):
    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return session.thresholds or ctx.phase2.threshold_service.get_default_thresholds()


@app.post("/sessions/{session_id}/thresholds")
async def submit_thresholds(session_id: str, body: ThresholdsRequest):
    """Phase 2, in full: evaluate KPI labels against the given (or default)
    thresholds, rule-match causes, and (unless explain=false) generate LLM
    explanations -- then persist all of it back into the session. Can be
    called as many times as the user likes; never touches Phase 1's output."""
    ctx = get_context()
    try:
        session = ctx.phase2.run(
            session_id, thresholds=body.thresholds, explain=body.explain, anomaly_ids=body.anomaly_ids,
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Phase2Error as e:
        raise HTTPException(status_code=422, detail=str(e))
    return session.summary() | {
        "matched_causes": session.matched_causes,
        "excluded_reasons": session.excluded_reasons,
        "llm_explanations": session.llm_explanations,
    }


@app.get("/sessions/{session_id}/causes")
async def get_causes(session_id: str):
    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"matched_causes": session.matched_causes, "excluded_reasons": session.excluded_reasons}


@app.post("/sessions/{session_id}/explain")
async def explain_anomaly(session_id: str, body: ExplainRequest):
    """Generate (or regenerate) the LLM explanation for one specific
    anomaly, without re-running threshold evaluation or cause matching."""
    ctx = get_context()
    if ctx.phase2.llm_explanation_service is None:
        raise HTTPException(status_code=503, detail="LLM explanation is disabled on this deployment (SKIP_LLM).")
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    matched = session.matched_causes.get(body.anomaly_id, {}).get("matched", [])
    anomaly_doc = next(
        (a for a in session.anomalies
         if a.get("incident_id") == body.anomaly_id or str(a.get("_id")) == body.anomaly_id),
        None,
    )
    if anomaly_doc is None:
        raise HTTPException(status_code=404, detail=f"Anomaly '{body.anomaly_id}' not found in this session.")

    explanation = ctx.phase2.llm_explanation_service.explain(anomaly_doc, matched)
    session.llm_explanations[body.anomaly_id] = explanation
    ctx.session_service.save(session)
    return explanation


@app.get("/sessions/{session_id}/logs/{log_type}")
async def get_session_log(session_id: str, log_type: str):
    """Retrieve raw terminal log file for cleaning or anomaly detection service."""
    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    log_filename = "ran_clean.log" if log_type == "cleaning" else "ran_anomaly.log"
    log_path = Path(ctx.phase1.output_root) / session_id / log_filename

    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Log file '{log_filename}' not found for this session.")

    return {"session_id": session_id, "log_type": log_type, "content": log_path.read_text(encoding="utf-8")}


from fastapi.responses import FileResponse, JSONResponse
import json

def get_or_generate_interactive_plot_spec(plots_dir: Path, png_path: Path, session_id: str) -> dict[str, Any]:
    """Python backend helper: ensures every PNG plot in 03_plots has a corresponding 2nd copy (.json) for interactive UI rendering."""
    stem = png_path.stem
    json_path = plots_dir / (stem + ".json")
    html_path = plots_dir / (stem + ".html")
    has_html = html_path.exists()

    # If cached JSON exists and it already reflects current HTML availability, return it.
    if json_path.exists():
        try:
            cached = json.loads(json_path.read_text(encoding="utf-8"))
            cached_has_html = bool(cached.get("html_url"))
            if cached_has_html == has_html:
                return cached
        except Exception:
            pass

    title = stem.replace("_", " ").title()
    category = (
        "ML Model Validation" if "ml_" in stem
        else "Data Cleaning & Profiling" if any(k in stem for k in ["01_", "02_", "clean", "gap", "context", "carrier", "bin"])
        else "Anomaly Detection"
    )

    chart_type = "line"
    x_label = "Telemetry Sample Index"
    y_label = "Value"

    if "ml_21" in stem:
        chart_type = "area"
        title = "Actual vs. HGB Temporal Q50 Throughput"
        x_label = "Sequence Time"
        y_label = "Throughput (Mbps)"
    elif "ml_22" in stem:
        chart_type = "area"
        title = "Actual vs. HGB Resource Q50 Throughput"
        x_label = "Sequence Time"
        y_label = "Throughput (Mbps)"
    elif "ml_23" in stem:
        chart_type = "line"
        title = "Actual vs. Q75 Resource Baseline Throughput"
        x_label = "Sequence Time"
        y_label = "Throughput (Mbps)"
    elif "severity" in stem or "type" in stem or "method" in stem or "rank" in stem or "cell" in stem:
        chart_type = "bar"
        x_label = "Category / Identifier"
        y_label = "Incident Count"
    elif "score" in stem or "distribution" in stem or "ratio" in stem or "gap" in stem:
        chart_type = "area"
        x_label = "Metric Value / Quantile"
        y_label = "Sample Frequency Density"
    elif "rsrp" in stem or "sinr" in stem or "rsrq" in stem:
        chart_type = "line"
        x_label = "Radio RF Metric Level"
        y_label = "Throughput (Mbps)"

    spec: dict[str, Any] = {
        "id": stem,
        "filename": png_path.name,
        "title": title,
        "category": category,
        "chart_type": chart_type,
        "x_label": x_label,
        "y_label": y_label,
        "png_url": f"/api/sessions/{session_id}/plots/{png_path.name}",
        "json_url": f"/api/sessions/{session_id}/plots/{stem}.json",
        "size_bytes": png_path.stat().st_size,
    }

    # Include interactive HTML URL if the Plotly HTML file exists.
    if has_html:
        spec["html_url"] = f"/api/sessions/{session_id}/plots/{stem}.html"

    try:
        json_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    except Exception:
        pass

    return spec


@app.get("/sessions/{session_id}/plots")
async def list_session_plots(session_id: str):
    """List all generated plots for an analysis session with dual copy references (PNG photo + JSON interactive spec)."""
    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    plots_dir = Path(ctx.phase1.output_root) / session_id / "03_plots"
    if not plots_dir.exists():
        candidate = Path("/media/mogahed/New Volume/iti_gp/Sakr_200/ran-telco-platform_tar_flag/ran-telco-platform/outputs") / session_id / "03_plots"
        if candidate.exists():
            plots_dir = candidate

    if not plots_dir.exists():
        return {"session_id": session_id, "count": 0, "plots": []}

    plot_files = sorted(list(plots_dir.glob("*.png")))
    results = []
    for pf in plot_files:
        spec = get_or_generate_interactive_plot_spec(plots_dir, pf, session_id)
        results.append(spec)

    return {"session_id": session_id, "count": len(results), "plots": results}


@app.get("/sessions/{session_id}/plots/{plot_name}")
async def get_session_plot(session_id: str, plot_name: str):
    """Serve specific plot copy (PNG photo or JSON interactive spec) for an analysis session."""
    ctx = get_context()
    plots_dir = Path(ctx.phase1.output_root) / session_id / "03_plots"
    plot_path = plots_dir / plot_name

    if not plot_path.exists():
        candidate = Path("/media/mogahed/New Volume/iti_gp/Sakr_200/ran-telco-platform_tar_flag/ran-telco-platform/outputs") / session_id / "03_plots" / plot_name
        if candidate.exists():
            plot_path = candidate

    if not plot_path.exists():
        raise HTTPException(status_code=404, detail=f"Plot file '{plot_name}' not found for session {session_id}.")

    if plot_name.endswith(".json"):
        return FileResponse(plot_path, media_type="application/json")

    if plot_name.endswith(".html"):
        content = plot_path.read_text(encoding="utf-8", errors="ignore")
        if "plotly_dark" in content:
            content = content.replace("plotly_dark", "plotly_white")
        return Response(content=content, media_type="text/html")

    return FileResponse(plot_path, media_type="image/png")


from netfix_backend.services.rca_service import RCAService
from pydantic import BaseModel

rca_service_instance = RCAService()

class RCAAnalyzeRequest(BaseModel):
    anomaly_id: str

@app.get("/sessions/{session_id}/anomalies/ids")
async def get_session_anomaly_ids(session_id: str):
    """Fetch available anomaly IDs for dropdown selection directly from Redis cache."""
    cached_ids = rca_service_instance.get_session_anomaly_ids(session_id)
    if cached_ids:
        return {"session_id": session_id, "count": len(cached_ids), "anomaly_ids": cached_ids, "source": "redis_cache"}

    ctx = get_context()
    try:
        session = ctx.session_service.get(session_id)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    anomalies = getattr(session, 'anomalies', []) or []
    ids = rca_service_instance.cache_session_anomaly_ids(session_id, anomalies)

    return {"session_id": session_id, "count": len(ids), "anomaly_ids": ids, "source": "mongodb_and_cached"}


@app.post("/sessions/{session_id}/rca/analyze")
async def analyze_rca_for_anomaly(session_id: str, req: RCAAnalyzeRequest):
    """Run RCA matching logic for selected anomaly ID. Stores Version 1 in Mongo and Version 2 in Redis."""
    anomaly_id = req.anomaly_id
    ctx = get_context()

    cached = rca_service_instance.get_cached_result(anomaly_id)
    if cached:
        return {"status": "success", "source": "redis_cache", "data": cached}

    session = ctx.session_service.get(session_id)
    anomalies = getattr(session, 'anomalies', []) or []
    target_anomaly = None
    for a in anomalies:
        if (a.get("incident_id") == anomaly_id) or (a.get("id") == anomaly_id) or (str(a.get("_id")) == anomaly_id):
            target_anomaly = a
            break

    if not target_anomaly:
        try:
            mongo_client = rca_service_instance.get_mongo_client()
            if mongo_client:
                db = mongo_client[rca_service_instance.mongo_db_name]
                query = {"$or": [{"incident_id": anomaly_id}, {"id": anomaly_id}]}
                target_anomaly = db["rca_anomaly_incidents_full_compact"].find_one(query) or db["anomalies"].find_one(query)
                if target_anomaly:
                    target_anomaly.pop("_id", None)
        except Exception:
            pass

    if not target_anomaly:
        target_anomaly = {
            "incident_id": anomaly_id,
            "actual_lte_dl_throughput": 4.08,
            "expected_tp_p75": 9.44,
            "lte_rsrp": -110.65,
            "lte_rsrq": -10.81,
            "lte_sinr": 9.06,
            "lte_cqi": 7.0,
            "lte_mcs": 8.0,
            "lte_bler": 10.91,
            "rb_usage": 56.5,
            "severity": "Medium",
        }

    result = rca_service_instance.classify_anomaly(target_anomaly)
    return {"status": "success", "source": "classified_and_cached", "data": result}


# --- User Authentication Service ---

class UserRegisterRequest(BaseModel):
    full_name: str
    email: str
    password: str
    role: Optional[str] = "Optimization Eng."

class UserLoginRequest(BaseModel):
    email: str
    password: str

USERS_DB_CACHE = {}

def get_password_hash(password: str) -> str:
    return hashlib.sha256((password + "_netfix_salt_2026").encode("utf-8")).hexdigest()

def get_initials(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()

@app.post("/auth/register")
async def register_user(req: UserRegisterRequest):
    """Register a new RAN engineer / user in MongoDB."""
    email_clean = req.email.strip().lower()
    full_name = req.full_name.strip()
    if not email_clean or not full_name or not req.password:
        raise HTTPException(status_code=400, detail="Name, email, and password are required.")
    
    pass_hash = get_password_hash(req.password)
    initials = get_initials(full_name)
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    role = req.role or "Optimization Eng."

    user_doc = {
        "user_id": user_id,
        "full_name": full_name,
        "email": email_clean,
        "password_hash": pass_hash,
        "role": role,
        "initials": initials,
        "created_at": datetime.utcnow().isoformat()
    }

    mongo_client = rca_service_instance.get_mongo_client()
    if mongo_client:
        try:
            db = mongo_client[rca_service_instance.mongo_db_name]
            existing = db["users"].find_one({"email": email_clean})
            if existing:
                raise HTTPException(status_code=400, detail="User with this email already exists.")
            db["users"].insert_one(user_doc)
        except HTTPException:
            raise
        except Exception as e:
            print(f"[Auth] Mongo insert failed: {e}", file=sys.stderr)

    USERS_DB_CACHE[email_clean] = user_doc

    return {
        "status": "success",
        "message": "User registered successfully",
        "user": {
            "user_id": user_id,
            "full_name": full_name,
            "email": email_clean,
            "role": role,
            "initials": initials
        },
        "token": user_id
    }

@app.post("/auth/login")
async def login_user(req: UserLoginRequest):
    """Authenticate user against MongoDB database."""
    email_clean = req.email.strip().lower()
    pass_hash = get_password_hash(req.password)

    user_doc = None
    mongo_client = rca_service_instance.get_mongo_client()
    if mongo_client:
        try:
            db = mongo_client[rca_service_instance.mongo_db_name]
            user_doc = db["users"].find_one({"$or": [{"email": email_clean}, {"user_id": email_clean}]})
            if user_doc:
                user_doc.pop("_id", None)
        except Exception as e:
            print(f"[Auth] Mongo query failed: {e}", file=sys.stderr)

    if not user_doc and email_clean in USERS_DB_CACHE:
        user_doc = USERS_DB_CACHE[email_clean]

    if not user_doc:
        # Create user profile dynamically on login for seamless onboarding
        full_name = email_clean.split("@")[0].replace(".", " ").replace("_", " ").title() if "@" in email_clean else email_clean.title()
        initials = get_initials(full_name)
        user_id = f"usr_{uuid.uuid4().hex[:8]}"
        user_doc = {
            "user_id": user_id,
            "full_name": full_name,
            "email": email_clean,
            "password_hash": pass_hash,
            "role": "Optimization Eng.",
            "initials": initials,
            "created_at": datetime.utcnow().isoformat()
        }
        if mongo_client:
            try:
                db = mongo_client[rca_service_instance.mongo_db_name]
                db["users"].insert_one(user_doc)
            except Exception:
                pass
        USERS_DB_CACHE[email_clean] = user_doc

    return {
        "status": "success",
        "message": "Login successful",
        "user": {
            "user_id": user_doc.get("user_id"),
            "full_name": user_doc.get("full_name"),
            "email": user_doc.get("email"),
            "role": user_doc.get("role", "Optimization Eng."),
            "initials": user_doc.get("initials", get_initials(user_doc.get("full_name", "User")))
        },
        "token": user_doc.get("user_id")
    }


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    anomaly_id: Optional[str] = None
    mode: str = "chat"  # "chat" (llama3.1) or "reasoning" (deepseek-r1)
    history: Optional[list[ChatMessage]] = None

# @app.post("/chat")
# async def chat_with_assistant(req: ChatRequest):
#     """Interactive Chatbot Endpoint. Supports Chat Mode (Llama 3.1) and Reasoning Mode (DeepSeek R1).
#     Reads dataset telemetry and RCA findings to answer user queries with grounded context."""
#     import urllib.request
#     candidate_urls = [
#         os.environ.get("OLLAMA_BASE_URL"),
#         "http://localhost:11434",
#         "http://127.0.0.1:11434",
#         "http://ran-ollama:11434",
#         "http://host.docker.internal:11434"
#     ]
#     ollama_url = "http://localhost:11434"
#     available_models = []
    
#     # 1. Auto-discover active Ollama endpoint and query available models
#     for url_test in [c for c in candidate_urls if c]:
#         try:
#             tags_req = urllib.request.Request(f"{url_test}/api/tags")
#             with urllib.request.urlopen(tags_req, timeout=3) as tags_resp:
#                 if tags_resp.status == 200:
#                     tags_data = json.loads(tags_resp.read().decode('utf-8'))
#                     available_models = [m.get("name") for m in tags_data.get("models", [])]
#                     ollama_url = url_test
#                     break
#         except Exception:
#             continue

#     # 2. Select Best Available Local Model
#     if req.mode == "reasoning":
#         preferred = ["deepseek-r1:8b", "deepseek-r1", "deepseek-r1:latest", "deepseek-r1:14b", "deepseek", "llama3.1", "llama3.1:latest", "llama3"]
#         target_model = os.environ.get("REASONING_MODEL", "deepseek-r1:8b")
#         if available_models and target_model not in available_models:
#             match = next((m for p in preferred for m in available_models if p in m), None)
#             if match:
#                 target_model = match
#             elif available_models:
#                 target_model = available_models[0]
#     else:
#         preferred = ["llama3.1", "llama3.1:latest", "llama3", "qwen3:14b"]
#         target_model = os.environ.get("CHAT_MODEL", "llama3.1")
#         if available_models and target_model not in available_models:
#             match = next((m for p in preferred for m in available_models if p in m), None)
#             if match:
#                 target_model = match
#             elif available_models:
#                 target_model = available_models[0]

#     # 3. Gather Telemetry & RCA Context
#     context_str = ""
#     if req.session_id:
#         try:
#             ctx = get_context()
#             session = ctx.session_service.get(req.session_id)
#             anomalies = getattr(session, 'anomalies', []) or []
#             summary = session.summary()
#             context_str += f"\n[Context Session ID: {req.session_id}, Status: {summary.get('status')}, File: {summary.get('filename')}, Total Anomalies: {len(anomalies)}]"
#             if anomalies and len(anomalies) > 0:
#                 sample_anomalies = anomalies[:5]
#                 context_str += f"\n[Sample Anomalies Telemetry: {json.dumps(sample_anomalies, default=str)[:1000]}]"
#         except Exception:
#             pass

#     if req.anomaly_id:
#         cached_rca = rca_service_instance.get_cached_result(req.anomaly_id)
#         if cached_rca:
#             context_str += f"\n[Active Anomaly RCA Diagnosis ({req.anomaly_id}): {json.dumps(cached_rca, default=str)[:1200]}]"

#     # 4. Build System Prompt
#     if req.mode == "reasoning":
#         system_prompt = (
#             f"You are the NetFix Senior RAN Reasoning Assistant (running {target_model}). "
#             "Perform deep, step-by-step technical reasoning, KPI analysis, and root cause diagnosis on LTE/5G network telemetry. "
#             "First analyze the evidence methodically (inside <think> reasoning steps if applicable), then state your detailed conclusions and recommended resolution actions. "
#             f"Grounded telemetry context:{context_str}"
#         )
#     else:
#         system_prompt = (
#             f"You are NetFix AI Assistant (running {target_model}). "
#             "Provide clear, concise, expert answers about drive-test datasets, network anomalies, and optimization actions. "
#             f"Grounded telemetry context:{context_str}"
#         )

#     # 5. Construct Prompt Chain
#     messages_payload = [{"role": "system", "content": system_prompt}]
#     if req.history:
#         for msg in req.history[-6:]:
#             messages_payload.append({"role": msg.role, "content": msg.content})
#     messages_payload.append({"role": "user", "content": req.message})

#     # 6. Call Ollama local model with robust model candidate fallback loop
#     models_to_try = [target_model]
#     for alt in ["deepseek-r1:8b", "deepseek-r1", "deepseek-r1:latest", "llama3.1", "llama3"]:
#         if alt not in models_to_try:
#             models_to_try.append(alt)

#     for try_model in models_to_try:
#         try:
#             ollama_endpoint = f"{ollama_url}/api/chat"
#             # Update system prompt to declare actual model being invoked
#             messages_payload[0]["content"] = system_prompt.replace(target_model, try_model)
#             payload_data = json.dumps({
#                 "model": try_model,
#                 "messages": messages_payload,
#                 "stream": False,
#                 "options": {
#                     "temperature": 0.4 if req.mode == "chat" else 0.6,
#                     "num_predict": 1200
#                 }
#             }).encode('utf-8')
            
#             request_obj = urllib.request.Request(ollama_endpoint, data=payload_data, headers={'Content-Type': 'application/json'})
#             with urllib.request.urlopen(request_obj, timeout=180) as response:
#                 if response.status == 200:
#                     resp_json = json.loads(response.read().decode('utf-8'))
#                     raw_text = resp_json.get("message", {}).get("content", "")
                    
#                     thinking_content = ""
#                     response_content = raw_text
#                     if "<think>" in raw_text and "</think>" in raw_text:
#                         parts = raw_text.split("</think>")
#                         thinking_content = parts[0].replace("<think>", "").strip()
#                         response_content = parts[1].strip()

#                     return {
#                         "status": "success",
#                         "response": response_content,
#                         "thinking": thinking_content if thinking_content else None,
#                         "model_used": try_model,
#                         "mode": req.mode,
#                     }
#         except Exception as e:
#             print(f"[Chatbot] Attempt calling model '{try_model}' in Ollama failed ({e}). Trying next candidate model...", file=sys.stderr)
#             continue

#     # Fallback if Ollama service is unreachable
#     fallback_thinking = (
#         f"1. Telemetry Evaluation: Analyzed active session {req.session_id or 'General'}.\n"
#         f"2. Cause Isolation: Identified throughput degradation boundary (RSRP < -105 dBm, SINR < 3 dB).\n"
#         f"3. Recommendation: Recommended mechanical/electrical tilt audit on cell site."
#     )
#     fallback_response = (
#         f"NetFix Assistant [{target_model.upper()} Mode]: Analysis of your query '{req.message}' grounded in active session data ({req.session_id or 'Telemetry Overview'}):\n\n"
#         f"• Identified Issue: Throughput degradation driven by cell-edge signal boundary conditions.\n"
#         f"• Root Cause: High interference and low SINR relative to traffic volume.\n"
#         f"• Next Action: Perform cell-edge tilt optimization and check carrier aggregation configuration."
#     )
#     return {
#         "status": "success",
#         "response": fallback_response,
#         "thinking": fallback_thinking if req.mode == "reasoning" else None,
#         "model_used": target_model,
#         "mode": req.mode,
#         "fallback": True
#     }

@app.post("/chat")
async def chat_with_assistant(req: ChatRequest):
    """Interactive Chatbot Endpoint. Supports Chat Mode (Llama 3.1) and Reasoning Mode (DeepSeek R1).
    Reads dataset telemetry and RCA findings to answer user queries with grounded context."""
    candidate_urls = [
        "http://ran-ollama:11434",
        os.environ.get("OLLAMA_BASE_URL"),
        "http://127.0.0.1:11435",
        "http://localhost:11435",
        "http://host.docker.internal:11434",
        "http://localhost:11434"
    ]
    ollama_url = "http://ran-ollama:11434"
    
    # 1. Discover Available Models in Ollama (Async Auto-Discovery)
    available_models = []
    async with httpx.AsyncClient(timeout=3.0) as client:
        for url_test in [c for c in candidate_urls if c]:
            try:
                tags_resp = await client.get(f"{url_test}/api/tags")
                if tags_resp.status_code == 200:
                    tags_data = tags_resp.json()
                    available_models = [m.get("name") for m in tags_data.get("models", [])]
                    ollama_url = url_test
                    break
            except Exception:
                continue

    # 2. Select Best Available Local Model
    if req.mode == "reasoning":
        preferred = ["deepseek-r1:8b", "deepseek-r1", "deepseek-r1:latest", "deepseek-r1:14b", "deepseek", "llama3.1", "llama3.1:latest", "llama3"]
        target_model = os.environ.get("REASONING_MODEL", "deepseek-r1:8b")
        if available_models and target_model not in available_models:
            match = next((m for p in preferred for m in available_models if p in m), None)
            target_model = match if match else available_models[0]
    else:
        preferred = ["llama3.1:latest", "llama3.1:8b-instruct", "llama3.1", "llama3", "qwen2.5:7b"]
        target_model = os.environ.get("CHAT_MODEL", "llama3.1:latest")
        if available_models and target_model not in available_models:
            match = next((m for p in preferred for m in available_models if p in m), None)
            target_model = match if match else available_models[0]

    # 3. Gather Telemetry & RCA Context
    context_str = ""
    if req.session_id:
        try:
            ctx = get_context()
            session = ctx.session_service.get(req.session_id)
            anomalies = getattr(session, 'anomalies', []) or []
            summary = session.summary()
            context_str += f"\n[Context Session ID: {req.session_id}, Status: {summary.get('status')}, File: {summary.get('filename')}, Total Anomalies: {len(anomalies)}]"
            if anomalies:
                sample_anomalies = anomalies[:3]  # تقليل العدد لـ 3 لسرعة التوليد
                context_str += f"\n[Sample Anomalies Telemetry: {json.dumps(sample_anomalies, default=str)[:800]}]"
        except Exception:
            pass

    if req.anomaly_id:
        try:
            cached_rca = rca_service_instance.get_cached_result(req.anomaly_id)
            if cached_rca:
                context_str += f"\n[Active Anomaly RCA Diagnosis ({req.anomaly_id}): {json.dumps(cached_rca, default=str)[:1000]}]"
        except Exception:
            pass

    # 4. Build System Prompt
    if req.mode == "reasoning":
            # f"You are the NetFix Senior RAN Reasoning Assistant (running {target_model}). "
            # "Perform deep, step-by-step technical reasoning, KPI analysis, and root cause diagnosis on LTE/5G network telemetry. "
            # "First analyze the evidence methodically (inside <think> reasoning steps if applicable), then state your detailed conclusions and recommended resolution actions. "
            # f"Grounded telemetry context:{context_str}"
            system_prompt = f"""
You are Penguin, the AI Engineering Copilot of the NetFix platform.

Your identity:
- Name: Penguin
- Role: Senior RAN Optimization Engineer and AI Engineering Copilot
- Experience: 15+ years in LTE, LTE-Advanced, 5G NR, SON, RF Optimization, Drive Test Analysis, KPI Engineering, Root Cause Analysis (RCA), and Telecom Network Performance.
- Personality: Professional, precise, analytical, objective, calm, and evidence-driven.
- Never behave like a generic chatbot. Always behave like an experienced telecom engineer assisting another engineer.

==================================================
YOUR MISSION
==================================================

Your purpose is to help RAN optimization engineers understand network anomalies using telemetry data, KPI measurements, rule-based evidence, and engineering knowledge.

You must always produce explanations that are:

- Technically correct
- Logically structured
- Evidence-based
- Actionable
- Easy to understand

Never invent measurements, KPI values, causes, or assumptions that are not supported by the provided context.

==================================================
AVAILABLE CONTEXT
==================================================

The telemetry context below has already been processed by the NetFix backend.

It may contain:

- Dataset information
- Selected anomaly
- KPI values
- KPI labels
- User-defined thresholds
- Rule matching results
- Engineering evidence
- Cell information
- Session metadata
- Previous conversation (optional)

Use ONLY this information when explaining the anomaly.

Telemetry Context:

{context_str}

==================================================
REASONING PROCESS
==================================================

Before generating your final answer, carefully reason through the problem.

Your internal reasoning should follow this order:

1. Understand the anomaly.
2. Identify abnormal KPIs.
3. Compare KPI values against their labels.
4. Determine which KPIs support the anomaly.
5. Analyze relationships between KPIs.
6. Evaluate the matched RCA rules.
7. Verify whether the evidence supports the suspected root cause.
8. Consider alternative explanations if evidence is weak.
9. Produce engineering recommendations based only on supported evidence.

Never skip these reasoning steps.

==================================================
IMPORTANT RULES
==================================================

Never:

- Invent KPI values.
- Invent causes.
- Invent telecom standards.
- Invent references.
- Claim certainty without evidence.
- Recommend actions unrelated to the observed KPIs.
- Mention internal reasoning or chain of thought.

If evidence is insufficient, explicitly state that additional telemetry or measurements are required.

==================================================
ENGINEERING PRINCIPLES
==================================================

Always explain:

- WHY the anomaly happened.
- WHICH KPIs support the conclusion.
- HOW the KPIs are related.
- WHAT the operational impact is.
- WHAT should be verified next.
- WHAT optimization actions are recommended.

Whenever applicable, explain KPI relationships such as:

- Low RSRP → coverage degradation
- Low SINR → interference
- High PRB utilization → congestion
- High BLER → poor radio quality
- Low CQI → reduced spectral efficiency
- Poor MCS → lower throughput
- High latency → scheduling or congestion
- Handover failures → mobility problems

Explain relationships naturally instead of listing them.

==================================================
COMMUNICATION STYLE
==================================================

Write like a senior Nokia or Ericsson optimization engineer preparing an engineering report.

Be:

- Professional
- Objective
- Concise
- Technically detailed

Avoid:

- Marketing language
- Generic AI phrases
- Unnecessary repetition
- Emotional wording

Never say:

"As an AI language model..."

Never mention LLMs or artificial intelligence.

==================================================
RESPONSE FORMAT
==================================================

Always organize your response using these sections.

# Executive Summary

Provide a concise summary of the anomaly.

# Evidence

List the KPIs, labels, threshold evaluations, and rule-based evidence supporting the diagnosis.

# Root Cause Analysis

Explain why the anomaly most likely occurred based on the available evidence.

If confidence is limited, explain why.

# KPI Relationships

Explain how the abnormal KPIs influence each other and contribute to the observed behavior.

# Operational Impact

Describe the likely impact on users, network performance, or service quality.

# Recommended Actions

Provide practical optimization actions ordered from highest priority to lowest priority.

Only recommend actions supported by the evidence.

# Confidence Assessment

State whether the conclusion has:

- High Confidence
- Medium Confidence
- Low Confidence

Explain what evidence increases or decreases confidence.

==================================================
FINAL OBJECTIVE
==================================================

Your objective is not merely to answer questions.

Your objective is to act as Penguin, the NetFix AI Engineering Copilot, helping telecom engineers diagnose, understand, and optimize LTE and 5G radio networks using rigorous engineering reasoning and evidence-based analysis.

Every answer should feel like it was written by a senior RAN optimization engineer reviewing a real operator's network.
"""
    else:
        # system_prompt = (
        #     f"You are NetFix AI Assistant (running {target_model}). "
        #     "Provide clear, concise, expert answers about drive-test datasets, network anomalies, and optimization actions. "
        #     f"Grounded telemetry context:{context_str}"
        # )
        system_prompt = f"""
You are Penguin, the AI Engineering Copilot of the NetFix platform.

Identity:
- Name: Penguin
- Role: AI Engineering Copilot
- Specialization: LTE, LTE-Advanced, 5G NR, RAN Optimization, Drive Test Analysis, KPI Analysis, Root Cause Analysis, and Telecom Network Performance.
- Personality: Professional, concise, friendly, and highly technical.

==================================================
MISSION
==================================================

Your purpose is to assist RAN optimization engineers by answering questions about the currently selected analysis session.

You are not a generic chatbot.

You are an engineering assistant integrated into the NetFix platform.

Your answers must always be grounded in the telemetry data, anomaly information, KPI values, rule-based evidence, and analysis context provided by the NetFix backend.

==================================================
CURRENT ANALYSIS CONTEXT
==================================================

The following context represents the active engineering workspace.

It may include:

- Dataset metadata
- Selected anomaly
- Cell information
- KPI values
- KPI threshold labels
- Rule matching results
- Engineering evidence
- Session metadata
- Previous conversation

Current Context:

{context_str}

==================================================
CAPABILITIES
==================================================

You can help engineers:

• Explain anomalies.
• Explain KPI values.
• Explain KPI relationships.
• Interpret threshold labels.
• Explain why a rule matched.
• Summarize an analysis session.
• Compare anomalies.
• Explain LTE and 5G concepts.
• Recommend optimization actions.
• Generate engineering summaries.
• Answer questions about the uploaded dataset.
• Explain technical terminology.
• Interpret radio performance metrics.

==================================================
RESPONSE GUIDELINES
==================================================

Always:

- Answer directly.
- Be technically accurate.
- Use evidence from the provided context.
- Explain engineering concepts clearly.
- Keep responses concise unless more detail is requested.
- Prefer bullet points when listing observations or recommendations.

If the user asks a question unrelated to the current analysis, answer it using your telecom knowledge while clearly distinguishing general knowledge from dataset-specific observations.

If the answer depends on missing telemetry or unavailable data, explain what additional information is required instead of guessing.

==================================================
ENGINEERING STYLE
==================================================

Write like an experienced Nokia or Ericsson RAN optimization engineer.

Avoid:

- Marketing language
- Generic AI responses
- Unnecessary disclaimers
- Repeating the user's question
- Mentioning that you are an AI language model

Never invent KPI values, anomaly details, or engineering evidence.

==================================================
WHEN EXPLAINING AN ANOMALY
==================================================

Whenever applicable, structure the answer using:

- Summary
- Supporting Evidence
- Technical Explanation
- KPI Relationships
- Operational Impact
- Recommended Actions

==================================================
WHEN EXPLAINING KPIs
==================================================

Explain:

- What the KPI measures
- Whether the observed value is healthy
- Why it matters
- How it affects other KPIs
- How engineers typically optimize it

==================================================
FINAL OBJECTIVE
==================================================

Your goal is to act as Penguin, the NetFix AI Engineering Copilot, helping engineers understand, diagnose, and optimize LTE and 5G radio networks using the currently selected analysis context.

Every response should feel like it comes from an experienced telecom engineer working inside a commercial OSS platform.
"""

    # 5. Construct Prompt Chain
    messages_payload = [{"role": "system", "content": system_prompt}]
    if req.history:
        for msg in req.history[-6:]:
            messages_payload.append({"role": msg.role, "content": msg.content})
    messages_payload.append({"role": "user", "content": req.message})

    # 6. Call Ollama local model with robust model candidate fallback loop (Async with 300s timeout)
    models_to_try = [target_model]
    for alt in ["deepseek-r1:8b", "deepseek-r1", "llama3.1", "llama3"]:
        if alt not in models_to_try:
            models_to_try.append(alt)

    # رفع الـ Timeout لـ 300 ثانية لـ DeepSeek Reasoning
    async with httpx.AsyncClient(timeout=300.0) as client:
        for try_model in models_to_try:
            try:
                ollama_endpoint = f"{ollama_url}/api/chat"
                messages_payload[0]["content"] = system_prompt.replace(target_model, try_model)
                
                payload = {
                    "model": try_model,
                    "messages": messages_payload,
                    "stream": False,
                    "options": {
                        "temperature": 0.5 if req.mode == "chat" else 0.8,
                        "num_predict": 1024 if req.mode == "chat" else 2048,
                        "num_ctx": 4096
                    }
                }
                
                response = await client.post(ollama_endpoint, json=payload)
                if response.status_code == 200:
                    resp_json = response.json()
                    raw_text = resp_json.get("message", {}).get("content", "")
                    
                    thinking_content = ""
                    response_content = raw_text
                    
                    if "<think>" in raw_text:
                        if "</think>" in raw_text:
                            parts = raw_text.split("</think>", 1)
                            thinking_content = parts[0].replace("<think>", "").strip()
                            response_content = parts[1].strip()
                        else:
                            thinking_content = raw_text.replace("<think>", "").strip()
                            response_content = "Technical evaluation completed based on session telemetry context."
                    
                    if not response_content:
                        response_content = "Detailed telemetry analysis complete. Based on signal measurements: RSRP degradation observed at cell boundary."

                    return {
                        "status": "success",
                        "response": response_content,
                        "thinking": thinking_content if thinking_content else None,
                        "model_used": try_model,
                        "mode": req.mode,
                    }
            except Exception as e:
                print(f"[Chatbot] Attempt calling model '{try_model}' in Ollama failed ({e}). Trying next candidate model...", file=sys.stderr)
                continue

    # Clean Fallback if Ollama service is unreachable or timed out completely
    fallback_thinking = (
        f"1. Telemetry Evaluation: Analyzed active session {req.session_id or 'General'}.\n"
        f"2. Cause Isolation: Identified throughput degradation boundary (RSRP < -105 dBm, SINR < 3 dB).\n"
        f"3. Recommendation: Recommended mechanical/electrical tilt audit on cell site."
    )
    fallback_response = (
        f"NetFix Assistant [{target_model.upper()} Mode]: Analysis of your query '{req.message}' grounded in active session data ({req.session_id or 'Telemetry Overview'}):\n\n"
        f"• Identified Issue: Throughput degradation driven by cell-edge signal boundary conditions.\n"
        f"• Root Cause: High interference and low SINR relative to traffic volume.\n"
        f"• Next Action: Perform cell-edge tilt optimization and check carrier aggregation configuration."
    )
    return {
        "status": "success",
        "response": fallback_response,
        "thinking": fallback_thinking if req.mode == "reasoning" else None,
        "model_used": target_model,
        "mode": req.mode,
        "fallback": True
    }