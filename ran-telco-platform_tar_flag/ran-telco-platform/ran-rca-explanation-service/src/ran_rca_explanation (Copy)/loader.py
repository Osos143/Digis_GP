"""
Loads the input JSON and normalizes it into a list of ExplanationRequest,
regardless of which of three shapes it's in (auto-detected):

1. **Single anomaly** -- the simplest case, one anomaly per file:
    {
      "anomaly_id": "INC-0017",              // optional, derived from anomaly.incident_id / anomaly._id if omitted
      "anomaly": { ...KPI/evidence fields... },
      "reasons": [ {"title": "...", "category": "...", "description": "..."}, ... ],
      "solutions": [ {"title": "...", "description": "..."}, ... ]   // optional
    }

2. **Batch** -- a JSON array of objects in shape 1.

3. **A full netfix-backend Analysis Session document** (or any document
   with the same `anomalies` + `matched_causes` shape) -- auto-detected by
   the presence of both keys. Every anomaly in the session becomes one
   ExplanationRequest, using that anomaly's own `matched_causes` entry as
   its reasons. Sessions have no `solutions` field (this platform's
   architecture deliberately excludes solution retrieval), so `solutions`
   is empty for every request built this way -- add a `solutions` field
   per anomaly yourself first if you want it included (or per-anomaly in a
   custom shape-1/2 file instead).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ran_rca_explanation.schema import ExplanationRequest


def _anomaly_id(doc: dict[str, Any]) -> str:
    if doc.get("incident_id"):
        return str(doc["incident_id"])
    return str(doc.get("_id", "unknown"))


def _is_session_shape(raw: Any) -> bool:
    return isinstance(raw, dict) and "anomalies" in raw and "matched_causes" in raw


def _from_session(raw: dict[str, Any]) -> list[ExplanationRequest]:
    matched_causes = raw.get("matched_causes", {})
    requests = []
    for anomaly in raw.get("anomalies", []):
        aid = _anomaly_id(anomaly)
        matched = matched_causes.get(aid, {}).get("matched", [])
        requests.append(ExplanationRequest(anomaly_id=aid, anomaly=anomaly, reasons=matched, solutions=[]))
    return requests


def _from_single(raw: dict[str, Any]) -> ExplanationRequest:
    anomaly = raw.get("anomaly", {})
    anomaly_id = raw.get("anomaly_id") or _anomaly_id(anomaly)
    return ExplanationRequest(
        anomaly_id=anomaly_id,
        anomaly=anomaly,
        reasons=raw.get("reasons", []),
        solutions=raw.get("solutions", []),
    )


def load_requests(path: str) -> list[ExplanationRequest]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    if _is_session_shape(raw):
        return _from_session(raw)

    if isinstance(raw, list):
        return [_from_single(item) for item in raw]

    if isinstance(raw, dict):
        return [_from_single(raw)]

    raise ValueError(
        "Input JSON must be a single-anomaly object, a JSON array of them, "
        "or a netfix-backend Analysis Session document (with 'anomalies' + 'matched_causes')."
    )
