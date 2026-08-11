"""
Renders an RcaExplanationReport into a single markdown document. Kept
separate from the LLM call itself (explainer.py) -- assembling markdown in
Python is more reliable than asking the model to format it, and keeps the
LLM's structured-output schema simple (see schema.py's docstring on why
fewer fields is better for local-model reliability).
"""

from __future__ import annotations

from ran_rca_explanation.schema import ExplanationRequest, RcaExplanationReport


def render_markdown(request: ExplanationRequest, report: RcaExplanationReport) -> str:
    lines = [
        f"# RCA Explanation -- {request.anomaly_id}",
        "",
        "## Executive Summary",
        report.executive_summary,
        "",
        "## Root Cause Analysis",
        report.root_cause_narrative,
        "",
    ]
    if report.supporting_evidence:
        lines += ["## Supporting Evidence", *[f"- {e}" for e in report.supporting_evidence], ""]
    if report.recommended_actions:
        lines += ["## Recommended Actions", *[f"- {a}" for a in report.recommended_actions], ""]
    return "\n".join(lines)
