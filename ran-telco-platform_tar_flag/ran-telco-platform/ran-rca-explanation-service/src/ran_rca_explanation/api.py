"""
Minimal FastAPI app. One endpoint -- this service does one thing.

Run with:
    uvicorn ran_rca_explanation.api:app --host 0.0.0.0 --port 8010
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from ran_rca_explanation.explainer import RcaExplainerLLM
from ran_rca_explanation.schema import ExplanationRequest, RcaExplanationReport

app = FastAPI(title="RAN RCA Explanation Service", version="1.0.0")

_explainer: Optional[RcaExplainerLLM] = None


def get_explainer() -> RcaExplainerLLM:
    global _explainer
    if _explainer is None:
        _explainer = RcaExplainerLLM(
            provider=os.environ.get("LLM_PROVIDER", "ollama"),
            model=os.environ.get("LLM_MODEL"),
            base_url=os.environ.get("OLLAMA_BASE_URL"),
        )
    return _explainer


class ExplainApiRequest(BaseModel):
    """Accept the full reason-matching result JSON. All fields are optional
    so the service never rejects a request due to schema mismatch -- it
    reads whatever is present and passes the full JSON to the LLM."""
    model_config = ConfigDict(extra="allow")

    # Fields from the full reason-matching result
    incident_id: Optional[str] = None
    diagnosis: Optional[dict[str, Any]] = None
    key_kpi_evidence: Optional[dict[str, Any]] = None
    recommended_solution: Optional[dict[str, Any]] = None
    supporting_evidence: Optional[list[dict[str, Any]]] = None

    # Legacy fields (backward compatibility with old partial payload format)
    anomaly_id: Optional[str] = None
    anomaly: Optional[dict[str, Any]] = None
    reasons: Optional[list[dict[str, Any]]] = None
    solutions: Optional[list[dict[str, Any]]] = None


@app.post("/explain", response_model=RcaExplanationReport)
async def explain(body: ExplainApiRequest):
    # Resolve anomaly ID from whichever field is present
    anomaly_id = (
        body.incident_id
        or body.anomaly_id
        or (body.anomaly.get("incident_id") if body.anomaly else None)
        or "unknown"
    )

    # Build the full JSON dict that the LLM will read
    full_json: dict[str, Any] = body.model_dump(exclude_none=True)

    request = ExplanationRequest(
        anomaly_id=str(anomaly_id),
        rca_result_json=full_json,
    )
    try:
        return get_explainer().explain(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}
