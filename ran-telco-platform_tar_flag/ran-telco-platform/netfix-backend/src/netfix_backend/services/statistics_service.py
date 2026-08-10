"""
StatisticsService: pure computation over the anomaly documents Phase 1
already has in memory (from DetectionService) -- no I/O, no subprocess, no
re-reading anything. This satisfies "Statistics Generation" as its own
distinct pipeline step without needing to split ran-anomaly-service's
internal stages (which aren't independently invocable -- see
CleaningService/DetectionService's docstrings): the actual expensive
computation runs once, inside the single `ran-anomaly` subprocess call;
this service is what turns that output into the summary the session stores.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from netfix_backend.rules.condition_catalog import get_kpi_value

_SUMMARY_KPIS = [
    "rsrp_median_dbm", "rsrq_median_db", "sinr_median_db",
    "cqi_median", "mcs_median", "bler_median_pct", "rb_usage_median",
]


class StatisticsService:
    def compute(self, anomalies: list[dict[str, Any]]) -> dict[str, Any]:
        if not anomalies:
            return {"total_anomalies": 0}

        by_severity = Counter(str(a.get("severity", "unknown")) for a in anomalies)
        by_detection_case = Counter(str(a.get("detection_case", "unknown")) for a in anomalies)

        kpi_stats: dict[str, Any] = {}
        for kpi_id in _SUMMARY_KPIS:
            values = [v for a in anomalies if isinstance((v := get_kpi_value(a, kpi_id)), (int, float))
                      and not isinstance(v, bool)]
            if values:
                kpi_stats[kpi_id] = {
                    "count": len(values),
                    "mean": round(mean(values), 3),
                    "median": round(median(values), 3),
                    "min": round(min(values), 3),
                    "max": round(max(values), 3),
                }

        return {
            "total_anomalies": len(anomalies),
            "by_severity": dict(by_severity),
            "by_detection_case": dict(by_detection_case),
            "kpi_summary": kpi_stats,
        }
