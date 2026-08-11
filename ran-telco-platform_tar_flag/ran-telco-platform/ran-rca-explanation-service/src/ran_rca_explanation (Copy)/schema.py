"""
Input and output schemas.

Input is deliberately permissive: real anomaly JSON (from this platform's
netfix-backend, from the earlier reason-matching service, or from anything
else) varies in exact shape, so every model here accepts extra fields
without rejecting the document -- `formatter.py` flattens whatever's
present into readable text for the prompt rather than requiring an exact
schema match.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReasonInput(BaseModel):
    """One matched root-cause reason. Matches the shape netfix-backend's
    CauseMatchingService produces (`{"reason_id", "title", "category",
    "description"}`), but only `title` is actually required -- everything
    else is optional/best-effort."""
    model_config = ConfigDict(extra="allow")

    reason_id: Optional[str] = None
    title: str
    category: Optional[str] = None
    description: Optional[str] = None


class SolutionInput(BaseModel):
    """One suggested solution, supplied by the caller -- this service never
    generates these itself, only explains/echoes what's given."""
    model_config = ConfigDict(extra="allow")

    solution_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    priority: Optional[str] = None


class ExplanationRequest(BaseModel):
    """One fully-assembled request: one anomaly, its evidence, its matched
    reason(s), and any suggested solutions. This is what `explainer.py`
    actually consumes -- `loader.py` is responsible for turning either
    supported input JSON shape (see loader.py's docstring) into a list of
    these."""
    model_config = ConfigDict(extra="allow")

    anomaly_id: str
    anomaly: dict[str, Any] = Field(default_factory=dict)   # raw evidence/KPI data, any shape
    reasons: list[ReasonInput] = Field(default_factory=list)
    solutions: list[SolutionInput] = Field(default_factory=list)


class RcaExplanationReport(BaseModel):
    """LLM output schema. Kept to a small number of fields deliberately --
    fewer fields means more reliable json_schema-constrained output from a
    local model (see explainer.py's docstring)."""
    executive_summary: str = Field(
        description="1-3 sentences: what happened and its practical impact, in plain language for a "
                    "non-specialist stakeholder.",
    )
    root_cause_narrative: str = Field(
        description="The full root-cause explanation, written the way a senior RAN/RF optimization engineer "
                    "would explain it to a colleague -- technically precise, but readable. Must be grounded "
                    "only in the evidence and matched reason(s) given; never invent KPI values or causes not "
                    "present in the input.",
    )
    supporting_evidence: list[str] = Field(
        default_factory=list,
        description="The specific evidence fields/values (as given, not invented) that most directly support "
                    "the root cause narrative, e.g. 'RSRP -118 dBm (median)'.",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="If suggested solutions were provided in the input, explain/expand on them here in the "
                    "engineer's own words. If none were provided, leave this empty -- do not invent new "
                    "recommendations.",
    )
