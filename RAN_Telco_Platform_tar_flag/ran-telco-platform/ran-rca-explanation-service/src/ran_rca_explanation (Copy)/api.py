"""
Minimal FastAPI app. One endpoint -- this service does one thing.

Run with:
    uvicorn ran_rca_explanation.api:app --host 0.0.0.0 --port 8010
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
    anomaly_id: Optional[str] = None
    anomaly: dict[str, Any] = {}
    reasons: list[dict[str, Any]] = []
    solutions: list[dict[str, Any]] = []


@app.post("/explain", response_model=RcaExplanationReport)
async def explain(body: ExplainApiRequest):
    anomaly_id = body.anomaly_id or str(body.anomaly.get("incident_id") or body.anomaly.get("_id") or "unknown")
    request = ExplanationRequest(
        anomaly_id=anomaly_id, anomaly=body.anomaly, reasons=body.reasons, solutions=body.solutions,
    )
    try:
        return get_explainer().explain(request)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}
