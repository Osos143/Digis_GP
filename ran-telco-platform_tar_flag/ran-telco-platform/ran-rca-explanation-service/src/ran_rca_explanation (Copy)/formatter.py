"""
Turns an ExplanationRequest into the text blocks that go into the prompt.
The evidence-flattening approach (dot-path any nested dict, drop
internal/bookkeeping fields) is the same one this platform used elsewhere
for anomaly documents -- proven to work across differently-shaped anomaly
JSON without needing an exact schema match.
"""

from __future__ import annotations

from typing import Any

from ran_rca_explanation.schema import ExplanationRequest, ReasonInput, SolutionInput

_EXCLUDED_KEYS = {"_id", "_run_id", "_ingested_at", "kpi_labels", "rca_matched_reasons", "incident_id"}


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not prefix and k in _EXCLUDED_KEYS:
                continue
            key = f"{prefix}.{k}" if prefix else k
            out.update(_flatten(v, key))
    else:
        out[prefix] = obj
    return out


def evidence_text(anomaly: dict[str, Any]) -> str:
    flat = _flatten(anomaly)
    lines = [f"{k}: {v}" for k, v in sorted(flat.items()) if v is not None and v != ""]
    return "\n".join(lines) if lines else "(no evidence fields provided)"


def reasons_text(reasons: list[ReasonInput]) -> str:
    if not reasons:
        return "(no root cause was matched for this anomaly)"
    lines = []
    for r in reasons:
        parts = [r.title]
        if r.category:
            parts.append(f"category: {r.category}")
        lines.append(f"- {' | '.join(parts)}")
        if r.description:
            lines.append(f"  {r.description}")
    return "\n".join(lines)


def solutions_text(solutions: list[SolutionInput]) -> str:
    if not solutions:
        return "(none provided -- do not invent any)"
    lines = []
    for s in solutions:
        parts = [s.title]
        if s.priority:
            parts.append(f"priority: {s.priority}")
        lines.append(f"- {' | '.join(parts)}")
        if s.description:
            lines.append(f"  {s.description}")
    return "\n".join(lines)


def build_prompt_context(request: ExplanationRequest) -> dict[str, str]:
    return {
        "anomaly_id": request.anomaly_id,
        "evidence": evidence_text(request.anomaly),
        "reasons": reasons_text(request.reasons),
        "solutions": solutions_text(request.solutions),
    }
