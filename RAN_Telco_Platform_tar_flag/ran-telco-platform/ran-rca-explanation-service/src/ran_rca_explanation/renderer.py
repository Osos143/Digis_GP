"""
Renders an RcaExplanationReport into a single markdown document.
"""

from __future__ import annotations

from ran_rca_explanation.schema import ExplanationRequest, RcaExplanationReport


def render_markdown(request: ExplanationRequest, report: RcaExplanationReport) -> str:
    lines = [
        f"# RCA Explanation -- {request.anomaly_id}",
        "",
        "## Explanation",
        report.explanation,
        "",
    ]
    return "\n".join(lines)
