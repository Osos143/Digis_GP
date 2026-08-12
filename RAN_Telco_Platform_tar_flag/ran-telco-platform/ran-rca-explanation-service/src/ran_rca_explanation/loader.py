"""
Loads input JSON from a file and normalizes it into a list of
ExplanationRequest objects. Supports three shapes:

1. **Full reason-matching result** -- a single object with `incident_id`,
   `diagnosis`, `key_kpi_evidence`, `recommended_solution`, etc.
   (the primary shape sent by netfix-backend after reason matching).

2. **Batch** -- a JSON array of objects in shape 1.

3. **Legacy single-anomaly** -- the older `{anomaly_id, anomaly, reasons,
   solutions}` shape (backward compatibility).

4. **Full session document** -- a netfix-backend session with `anomalies`
   and `matched_causes` keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ran_rca_explanation.schema import ExplanationRequest


def _anomaly_id(doc: dict[str, Any]) -> str:
    if doc.get("incident_id"):
        return str(doc["incident_id"])
    if doc.get("anomaly_id"):
        return str(doc["anomaly_id"])
    return str(doc.get("_id", "unknown"))


def _is_session_shape(raw: Any) -> bool:
    return isinstance(raw, dict) and "anomalies" in raw and "matched_causes" in raw


def _is_rca_result_shape(raw: Any) -> bool:
    """Detect the full reason-matching result shape (has diagnosis + key_kpi_evidence)."""
    return isinstance(raw, dict) and "diagnosis" in raw and "key_kpi_evidence" in raw


def _from_rca_result(raw: dict[str, Any]) -> ExplanationRequest:
    """Build an ExplanationRequest from a full reason-matching result JSON."""
    aid = _anomaly_id(raw)
    return ExplanationRequest(anomaly_id=aid, rca_result_json=raw)


def _from_session(raw: dict[str, Any]) -> list[ExplanationRequest]:
    matched_causes = raw.get("matched_causes", {})
    requests = []
    for anomaly in raw.get("anomalies", []):
        aid = _anomaly_id(anomaly)
        matched = matched_causes.get(aid, {}).get("matched", [])
        # Build a lightweight result-like structure for the LLM
        result_json = {
            "incident_id": aid,
            "anomaly": anomaly,
            "reasons": matched,
        }
        requests.append(ExplanationRequest(anomaly_id=aid, rca_result_json=result_json))
    return requests


def _from_legacy_single(raw: dict[str, Any]) -> ExplanationRequest:
    """Legacy format: {anomaly_id, anomaly, reasons, solutions}."""
    anomaly = raw.get("anomaly", {})
    anomaly_id = raw.get("anomaly_id") or _anomaly_id(anomaly)
    return ExplanationRequest(anomaly_id=anomaly_id, rca_result_json=raw)


def load_requests(path: str) -> list[ExplanationRequest]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    if _is_session_shape(raw):
        return _from_session(raw)

    if isinstance(raw, list):
        return [
            _from_rca_result(item) if _is_rca_result_shape(item) else _from_legacy_single(item)
            for item in raw
        ]

    if isinstance(raw, dict):
        if _is_rca_result_shape(raw):
            return [_from_rca_result(raw)]
        return [_from_legacy_single(raw)]

    raise ValueError(
        "Input JSON must be a reason-matching result, a single-anomaly object, "
        "a JSON array of them, or a session document (with 'anomalies' + 'matched_causes')."
    )
