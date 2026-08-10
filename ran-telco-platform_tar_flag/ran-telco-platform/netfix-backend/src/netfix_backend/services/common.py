"""
Small helpers shared by more than one service -- kept here instead of
duplicated, per the "avoid duplicated logic" requirement.
"""

from __future__ import annotations

from typing import Any


def anomaly_id(doc: dict[str, Any]) -> str:
    """The one place that decides how an anomaly document maps to the string
    key used everywhere in the session (`evaluated_kpis`, `matched_causes`,
    `llm_explanations`). `incident_id` is always present on
    `rca_anomaly_incidents_full_compact` documents; `_id` is the fallback so
    this never raises even on an unexpected document shape."""
    if doc.get("incident_id"):
        return str(doc["incident_id"])
    return str(doc.get("_id", "unknown"))
