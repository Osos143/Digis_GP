"""
ThresholdEvaluationService: Phase 2's first step. Takes the thresholds the
user configured (or the defaults, if they haven't edited any) and produces a
poor/acceptable/good label for every KPI on every anomaly already sitting in
the session -- no database read of the anomaly collections happens here,
Phase 1's `session.anomalies` is the only input, which is what makes this
step (and everything after it) re-runnable purely in-memory/against the
session document.

Threshold comparison logic itself (`label_value`) and the default threshold
values for the 9 base KPIs are reused from ran-kpi-labeling-service via
rules/condition_catalog.py, not re-implemented -- see that module's
docstring for exactly what's reused vs. added.
"""

from __future__ import annotations

from typing import Any, Optional

from netfix_backend.rules.condition_catalog import default_thresholds, get_kpi_value, label_value
from netfix_backend.services.common import anomaly_id


class ThresholdEvaluationService:
    def get_default_thresholds(self) -> dict[str, Any]:
        return default_thresholds()

    def evaluate(
        self,
        anomalies: list[dict[str, Any]],
        thresholds: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Returns {anomaly_id: {kpi_id: {value, label}}}. `thresholds`
        defaults to the built-in set if the caller hasn't configured/edited
        any yet (mirrors ran-kpi-labeling-service's own "seed if empty"
        behavior, just in-memory instead of Mongo-seeded)."""
        thresholds = thresholds or self.get_default_thresholds()

        evaluated: dict[str, Any] = {}
        for doc in anomalies:
            doc_id = anomaly_id(doc)
            kpi_labels: dict[str, Any] = {}
            for kpi_id, threshold_doc in thresholds.items():
                value = get_kpi_value(doc, kpi_id)
                if value is None:
                    continue
                label = label_value(value, threshold_doc)
                if label is None:
                    continue  # boolean/unlabelable KPI (e.g. rb_medium_or_high_usage) -- same rule as kpi-labeling-service
                kpi_labels[kpi_id] = {"value": value, "label": label}
            evaluated[doc_id] = kpi_labels
        return evaluated
