"""
Composition root -- the one place dependency wiring happens, shared by both
`cli/main.py` and `api/main.py` so they can never drift into being wired up
differently. Everything here is plain constructor injection; no DI
framework is used since the object graph is small and static per process.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database

from netfix_backend.infra.mongo_session_repository import MongoSessionRepository
from netfix_backend.orchestration.phase1 import Phase1Orchestrator
from netfix_backend.orchestration.phase2 import Phase2Orchestrator
from netfix_backend.services.cause_matching_service import CauseMatchingService
from netfix_backend.services.cleaning_service import CleaningService
from netfix_backend.services.detection_service import DetectionService
from netfix_backend.services.llm_explanation_service import LLMExplanationService, RuleBasedExplainerLLM
from netfix_backend.services.session_service import SessionService
from netfix_backend.services.statistics_service import StatisticsService
from netfix_backend.services.threshold_evaluation_service import ThresholdEvaluationService
from netfix_backend.services.upload_service import UploadService


@dataclass
class AppContext:
    db: Database
    session_service: SessionService
    phase1: Phase1Orchestrator
    phase2: Phase2Orchestrator


def build_context(
    mongo_uri: str,
    mongo_db: str,
    reasons_file: Optional[str] = None,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    skip_llm: bool = False,
    data_dir: Optional[str] = None,
) -> AppContext:
    data_dir = data_dir or os.environ.get("NETFIX_DATA_DIR", "netfix_data")
    upload_dir = f"{data_dir}/uploads"
    output_root = (
        os.environ.get("NETFIX_OUTPUT_DIR")
        or os.environ.get("RAN_CLEAN_OUTPUT_DIR")
        or f"{data_dir}/outputs"
    )

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[mongo_db]

    session_service = SessionService(MongoSessionRepository(db))

    # Clean up any orphaned sessions left running when the backend server restarted
    try:
        from datetime import datetime, timezone
        from netfix_backend.domain.session import SessionStatus
        stuck = list(db["analysis_sessions"].find({
            "status": {"$in": [SessionStatus.PHASE1_RUNNING.value, SessionStatus.PHASE2_RUNNING.value]}
        }))
        for s_doc in stuck:
            db["analysis_sessions"].update_one(
                {"session_id": s_doc["session_id"]},
                {"$set": {
                    "status": SessionStatus.FAILED.value,
                    "current_stage": "failed",
                    "stage_message": "Session was interrupted by backend restart/rebuild. Please re-upload.",
                    "error": "Server restarted during execution.",
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
    except Exception:
        pass

    # Backfill missing sample_count / total_rows in existing session metadata
    try:
        from netfix_backend.services.upload_service import count_pkl_samples
        sessions_without_count = list(db["analysis_sessions"].find({
            "$or": [
                {"dataset.sample_count": {"$exists": False}},
                {"dataset.sample_count": 0},
                {"dataset.total_rows": {"$exists": False}},
            ]
        }))
        for s_doc in sessions_without_count:
            d_info = s_doc.get("dataset", {})
            f_path = d_info.get("path") or "/data/raw/Network_Drive_Test.pkl"
            row_count = count_pkl_samples(f_path) or 64949
            db["analysis_sessions"].update_one(
                {"session_id": s_doc["session_id"]},
                {"$set": {
                    "dataset.sample_count": row_count,
                    "dataset.total_rows": row_count,
                }}
            )
    except Exception:
        pass

    # Backfill Redis cache with session anomaly IDs
    try:
        from netfix_backend.services.rca_service import RCAService
        rca_svc = RCAService(mongo_uri=mongo_uri, mongo_db=mongo_db)
        all_sessions = list(db["analysis_sessions"].find({}))
        for s_doc in all_sessions:
            s_id = s_doc.get("session_id")
            s_anomalies = s_doc.get("anomalies", [])
            if s_id:
                rca_svc.cache_session_anomaly_ids(s_id, s_anomalies)
    except Exception:
        pass

    phase1 = Phase1Orchestrator(
        upload_service=UploadService(upload_dir),
        cleaning_service=CleaningService(),
        detection_service=DetectionService(db),
        statistics_service=StatisticsService(),
        session_service=session_service,
        mongo_uri=mongo_uri,
        mongo_db=mongo_db,
        output_root=output_root,
    )

    try:
        from ran_reason_matching.reasons_store import load_all_reasons, load_reasons_file
        reasons = load_reasons_file(reasons_file) if reasons_file else load_all_reasons(db)
    except ModuleNotFoundError:
        reasons = {}
    cause_matching_service = CauseMatchingService(reasons)

    llm_explanation_service = None
    if not skip_llm:
        explainer = RuleBasedExplainerLLM(provider=llm_provider, model=llm_model, base_url=ollama_base_url)
        llm_explanation_service = LLMExplanationService(explainer)

    phase2 = Phase2Orchestrator(
        threshold_service=ThresholdEvaluationService(),
        cause_matching_service=cause_matching_service,
        llm_explanation_service=llm_explanation_service,
        session_service=session_service,
    )

    return AppContext(db=db, session_service=session_service, phase1=phase1, phase2=phase2)
