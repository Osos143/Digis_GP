"""
The Analysis Session: one object, created when a dataset is uploaded, that
every pipeline stage reads from and writes into -- instead of each stage
producing its own disconnected files/collections. This is what makes Phase 2
(thresholds -> labels -> causes -> explanations) re-runnable on its own,
as many times as the user likes, without ever re-triggering Phase 1's
expensive cleaning + anomaly-detection work: Phase 2 only ever reads
`session.anomalies` (already sitting in the session from Phase 1) and writes
`session.evaluated_kpis` / `session.matched_causes` / `session.llm_explanations`.

Matches the structure requested in the architecture brief:

    {
      "session_id": "...",
      "dataset": {},
      "statistics": {},
      "anomalies": [],
      "thresholds": {},
      "evaluated_kpis": {},
      "matched_causes": {},
      "llm_explanations": {}
    }

plus a `status`/`error` pair so callers (CLI/API) can tell what stage a
session is actually in and whether Phase 1 or Phase 2 failed partway.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SessionStatus(str, Enum):
    CREATED = "created"
    PHASE1_RUNNING = "phase1_running"
    PHASE1_DONE = "phase1_done"           # ready for the user to configure thresholds
    PHASE2_RUNNING = "phase2_running"
    PHASE2_DONE = "phase2_done"           # causes matched + explanations generated
    FAILED = "failed"


def new_session_id() -> str:
    return f"session_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class AnalysisSession:
    session_id: str = field(default_factory=new_session_id)
    status: SessionStatus = SessionStatus.CREATED
    current_stage: Optional[str] = "ready"
    stage_message: Optional[str] = "System ready. Waiting for drive-test dataset upload."
    error: Optional[str] = None

    # Phase 1 outputs -- written once, never touched again by Phase 2.
    dataset: dict[str, Any] = field(default_factory=dict)          # uploaded file info
    statistics: dict[str, Any] = field(default_factory=dict)       # aggregate stats over the run
    anomalies: list[dict[str, Any]] = field(default_factory=list)  # full anomaly documents

    # Phase 2 outputs -- overwritten every time Phase 2 re-runs.
    thresholds: dict[str, Any] = field(default_factory=dict)              # kpi_id -> {poor, acceptable, good, direction}
    evaluated_kpis: dict[str, Any] = field(default_factory=dict)          # anomaly_id -> {kpi_id: {value, label}}
    matched_causes: dict[str, Any] = field(default_factory=dict)          # anomaly_id -> {matched: [...]}
    excluded_reasons: list[dict[str, Any]] = field(default_factory=list)  # taxonomy reasons with no evaluable condition, and why
    llm_explanations: dict[str, Any] = field(default_factory=dict)        # anomaly_id -> {text, key_evidence, model, ...}

    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_doc(self) -> dict[str, Any]:
        """Mongo/JSON-serializable representation."""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "stage_message": self.stage_message,
            "error": self.error,
            "dataset": self.dataset,
            "statistics": self.statistics,
            "anomalies": self.anomalies,
            "thresholds": self.thresholds,
            "evaluated_kpis": self.evaluated_kpis,
            "matched_causes": self.matched_causes,
            "excluded_reasons": self.excluded_reasons,
            "llm_explanations": self.llm_explanations,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AnalysisSession":
        return cls(
            session_id=doc["session_id"],
            status=SessionStatus(doc.get("status", "created")),
            current_stage=doc.get("current_stage", "ready"),
            stage_message=doc.get("stage_message", ""),
            error=doc.get("error"),
            dataset=doc.get("dataset", {}),
            statistics=doc.get("statistics", {}),
            anomalies=doc.get("anomalies", []),
            thresholds=doc.get("thresholds", {}),
            evaluated_kpis=doc.get("evaluated_kpis", {}),
            matched_causes=doc.get("matched_causes", {}),
            excluded_reasons=doc.get("excluded_reasons", []),
            llm_explanations=doc.get("llm_explanations", {}),
            created_at=doc.get("created_at", utcnow()),
            updated_at=doc.get("updated_at", utcnow()),
        )

    def summary(self) -> dict[str, Any]:
        """Lightweight view for list endpoints -- no anomaly payload."""
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "current_stage": self.current_stage or self.status.value,
            "stage_message": self.stage_message or "",
            "error": self.error,
            "dataset": self.dataset,
            "anomaly_count": len(self.anomalies),
            "matched_cause_count": sum(1 for v in self.matched_causes.values() if v.get("matched")),
            "explained_count": len(self.llm_explanations),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
