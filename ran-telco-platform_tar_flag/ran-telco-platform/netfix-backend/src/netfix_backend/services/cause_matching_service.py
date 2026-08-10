"""
CauseMatchingService: Phase 2's second step. Replaces the previous
RAG/embedding-similarity matcher entirely -- a reason now "matches" an
anomaly purely by a deterministic rule: does the anomaly's evaluated KPI
label (or, for boolean conditions, its raw value) satisfy that reason's
condition. No embeddings, no LLM call, no Ollama dependency for this step
at all.

Reasons are loaded the same way the old RAG-based service loaded them (see
ran-reason-matching-service's reasons_store.py / graph_reasons.py, reused
here unchanged -- both the flat-list and taxonomy-graph reasons file formats
are still supported) since that loading/flattening logic has nothing to do
with how matching itself works. What changed is only *how* a reason gets
tested against an anomaly.
"""

from __future__ import annotations

from typing import Any

from netfix_backend.rules.condition_catalog import (
    REASON_CONDITIONS,
    BooleanCondition,
    Condition,
    evaluability_report,
    get_kpi_value,
)


class CauseMatchingService:
    def __init__(self, reasons: list[dict[str, Any]]):
        """`reasons` is whatever ran_reason_matching.reasons_store.load_reasons_file()
        (or upload_reasons's stored MongoDB documents) returns -- a flat list
        of {reason_id, title, category, description, ...} dicts, regardless
        of whether the source file was a flat list or a taxonomy graph."""
        self.reasons_by_id = {r["reason_id"]: r for r in reasons}
        self.excluded_reasons = evaluability_report(list(self.reasons_by_id))["excluded"]

    def _reason_fires(self, condition, anomaly_doc: dict[str, Any], kpi_labels: dict[str, Any]) -> bool:
        if isinstance(condition, Condition):
            entry = kpi_labels.get(condition.kpi_id)
            return entry is not None and entry.get("label") == condition.requires_label
        if isinstance(condition, BooleanCondition):
            raw = get_kpi_value(anomaly_doc, condition.kpi_id)
            return raw is not None and bool(raw) == condition.requires_value
        return False

    def match_one(self, anomaly_doc: dict[str, Any], kpi_labels: dict[str, Any]) -> dict[str, Any]:
        matched = []
        for reason_id, condition in REASON_CONDITIONS.items():
            reason = self.reasons_by_id.get(reason_id)
            if reason is None:
                continue  # this reason isn't in the currently-uploaded reasons file
            if self._reason_fires(condition, anomaly_doc, kpi_labels):
                matched.append({
                    "reason_id": reason_id,
                    "title": reason.get("title", reason_id),
                    "category": reason.get("category"),
                    "description": reason.get("description"),
                })
        return {"matched": matched}

    def match_all(self, anomalies: list[dict[str, Any]], evaluated_kpis: dict[str, Any]) -> dict[str, Any]:
        """anomaly_id -> {"matched": [...]}. Callers should also persist
        `self.excluded_reasons` into `session.excluded_reasons` -- it's the
        same list for every anomaly (which reasons are structurally
        impossible to evaluate given current fields), so it's exposed once
        here rather than repeated per anomaly."""
        from netfix_backend.services.common import anomaly_id as get_anomaly_id

        results: dict[str, Any] = {}
        for doc in anomalies:
            doc_id = get_anomaly_id(doc)
            kpi_labels = evaluated_kpis.get(doc_id, {})
            results[doc_id] = self.match_one(doc, kpi_labels)
        return results
