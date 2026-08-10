"""
The rule-based matching core: for every reason in the taxonomy, either a
concrete, testable condition against a specific evidence field, or an
explicit, honest exclusion because no such field exists in the anomaly data
this platform actually produces.

This replaces the RAG/embedding-similarity matcher entirely, per the
architecture change -- matching is now a deterministic lookup: "does this
anomaly's evaluated KPI label satisfy this reason's condition", nothing more.

Field availability and threshold values were checked against the real
pipeline code, not assumed:
- The 9 base KPIs (RSRP/RSRQ/SINR/CQI/MCS/BLER/RB usage/throughput-per-RB/
  RB-medium-or-high-usage) and their default poor/acceptable/good thresholds
  are exactly `ran-kpi-labeling-service`'s existing, already-shipped schema
  -- reused here via import, not re-typed, so there's one source of truth
  for those numbers.
- 5 more fields (secondary-carrier RSRP/SINR/CQI/MCS/BLER) and a boolean
  `ca_active` flag were verified present in
  `ran-anomaly-service/stages/17_episodes_and_incidents.py` under
  `doc["ca_context"]` (see CA_EXTRA_FIELD_CANDIDATES below) -- these have no
  threshold in ran-kpi-labeling-service's existing schema, so default
  thresholds for them are defined locally in this module, mirroring the
  logic/reasoning style of the existing ones.
- Every other leaf in the 34-reason taxonomy (RACH, handover, MIMO rank,
  neighbor-RSRP comparison, SCell RB count) was checked against the same
  pipeline source and has NO corresponding field anywhere in the anomaly
  documents this platform produces. Those are listed in
  NOT_EVALUABLE_REASON_IDS with the reason why, and CauseMatchingService
  excludes them from matching rather than silently never firing them.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Optional

_BASE_FIELD_CANDIDATES: dict[str, list[str]] = {}
_label_value: Any = lambda v, t: None
_flatten_base_defaults: Any = lambda: {}
_infer_direction: Any = lambda p, a, g: "higher_is_better"

def _load_kpi_labeling():
    global _BASE_FIELD_CANDIDATES, _label_value, _flatten_base_defaults, _infer_direction
    try:
        mod = importlib.import_module("ran_kpi_labeling")
        _BASE_FIELD_CANDIDATES = mod.field_mapping.FIELD_CANDIDATES
        _label_value = mod.labeler.label_value
        _flatten_base_defaults = mod.thresholds.flatten_defaults
        _infer_direction = mod.thresholds.infer_direction
    except ModuleNotFoundError:
        pass

_load_kpi_labeling()

# --------------------------------------------------------------------------
# Field lookup: base 9 KPIs (reused from ran-kpi-labeling-service) + the 5
# secondary-carrier fields + ca_active, verified present under ca_context.
# --------------------------------------------------------------------------

CA_EXTRA_FIELD_CANDIDATES: dict[str, list[str]] = {
    "scell1_rsrp_median_dbm": ["ca_context.scell1_rsrp_median_dbm"],
    "scell1_sinr_median_db": ["ca_context.scell1_sinr_median_db"],
    "scell1_cqi_median": ["ca_context.scell1_cqi_median"],
    "scell1_mcs_median": ["ca_context.scell1_mcs_median"],
    "scell1_bler_median_pct": ["ca_context.scell1_bler_median_pct"],
    "ca_active": ["ca_context.ca_active"],
}
FIELD_CANDIDATES: dict[str, list[str]] = {**_BASE_FIELD_CANDIDATES, **CA_EXTRA_FIELD_CANDIDATES}

# Default thresholds for the CA fields -- same poor/acceptable/good shape as
# ran-kpi-labeling-service's existing schema, not currently part of that
# service's own default set (it only ever thresholded serving-cell KPIs).
# `ca_active` is intentionally absent here: it's a boolean flag, evaluated
# directly (True/False), never thresholded like a continuous KPI.
CA_EXTRA_DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "scell1_rsrp_median_dbm": {
        "category": "ca_context", "poor_threshold": -95, "acceptable_threshold": -85, "good_threshold": -75,
        "logic": "Same coverage logic as serving-cell RSRP, applied to the secondary carrier: a weak SCell "
                 "link limits the throughput gain carrier aggregation is supposed to provide.",
    },
    "scell1_sinr_median_db": {
        "category": "ca_context", "poor_threshold": 0.0, "acceptable_threshold": 10.0, "good_threshold": 20.0,
        "logic": "Secondary-carrier signal-to-noise quality, same scale as serving-cell SINR.",
    },
    "scell1_cqi_median": {
        "category": "ca_context", "poor_threshold": 6.0, "acceptable_threshold": 10.0, "good_threshold": 13.0,
        "logic": "Secondary-carrier channel quality indicator, same scale as serving-cell CQI.",
    },
    "scell1_mcs_median": {
        "category": "ca_context", "poor_threshold": 9.0, "acceptable_threshold": 18.0, "good_threshold": 24.0,
        "logic": "Secondary-carrier modulation/coding index, same scale as serving-cell MCS.",
    },
    "scell1_bler_median_pct": {
        "category": "ca_context", "poor_threshold": 15.0, "acceptable_threshold": 10.0, "good_threshold": 5.0,
        "logic": "Secondary-carrier block error rate, same scale as serving-cell BLER.",
    },
}


def default_thresholds() -> dict[str, dict[str, Any]]:
    """The full default threshold set this service seeds new Sessions
    with: ran-kpi-labeling-service's 9 base KPIs (imported, not
    re-declared) plus this module's 5 CA additions. Each entry also gets
    `direction` computed once via the same `infer_direction` the base
    service uses, so labeling logic never has to re-derive it."""
    flat = dict(_flatten_base_defaults())
    flat.update(CA_EXTRA_DEFAULT_THRESHOLDS)
    for kpi_id, cfg in flat.items():
        cfg["direction"] = _infer_direction(cfg["poor_threshold"], cfg["acceptable_threshold"], cfg["good_threshold"])
    return flat


def _get_path(doc: dict[str, Any], path: str):
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def get_kpi_value(anomaly_doc: dict[str, Any], kpi_id: str):
    """Same lookup strategy as ran-kpi-labeling-service's field_mapping.py,
    over the merged (base + CA) field candidate list."""
    for path in FIELD_CANDIDATES.get(kpi_id, []):
        value = _get_path(anomaly_doc, path)
        if value is not None:
            return value
    return None


def label_value(value, threshold_doc: dict[str, Any]) -> Optional[str]:
    """Re-exported from ran-kpi-labeling-service -- one source of truth for
    the poor/acceptable/good comparison logic, not duplicated here."""
    return _label_value(value, threshold_doc)


# --------------------------------------------------------------------------
# Reason -> condition mapping
# --------------------------------------------------------------------------

@dataclass
class Condition:
    kpi_id: str
    requires_label: str = "poor"   # a reason "fires" when this KPI's evaluated label equals this


@dataclass
class BooleanCondition:
    kpi_id: str
    requires_value: bool = False


# reason_id (from the taxonomy graph) -> Condition. Only reasons with a real,
# testable evidence field are listed here; everything else is intentionally
# absent and handled by NOT_EVALUABLE_REASON_IDS below.
REASON_CONDITIONS: dict[str, Any] = {
    "low_rsrp": Condition("rsrp_median_dbm"),
    "low_rsrq": Condition("rsrq_median_db"),
    "low_sinr": Condition("sinr_median_db"),
    "low_cqi": Condition("cqi_median"),
    "low_mcs": Condition("mcs_median"),
    "high_bler": Condition("bler_median_pct"),
    "low_rb_efficiency": Condition("throughput_per_rb_median"),
    "high_rb_utilization": Condition("rb_usage_median"),
    # Carrier aggregation -- same underlying SCell fields, reached from two
    # different branches of the taxonomy (Coverage/weak_scell and
    # Carrier Aggregation/weak_secondary_cell), which is legitimate: the
    # taxonomy graph itself represents "Low SCell RSRP" as a concept
    # reachable multiple ways (see graph_reasons.py's handling of `ref` nodes
    # for the analogous case in the RAG version of this service).
    "low_scell_rsrp_coverage": Condition("scell1_rsrp_median_dbm"),
    "low_scell_rsrp": Condition("scell1_rsrp_median_dbm"),
    "low_scell_sinr": Condition("scell1_sinr_median_db"),
    "low_scell_cqi": Condition("scell1_cqi_median"),
    "high_scell_bler": Condition("scell1_bler_median_pct"),
    "ca_inactive": BooleanCondition("ca_active", requires_value=False),
}

# Every other leaf reason_id in the taxonomy, with why it's excluded --
# checked against the actual pipeline code (ran-anomaly-service's stages),
# not assumed. Shown to the user/caller explicitly rather than silently
# never matching.
NOT_EVALUABLE_REASON_IDS: dict[str, str] = {
    "low_rb_allocation": "No distinct 'RB allocation' field exists separately from RB usage/efficiency "
                          "in the anomaly data.",
    "neighbor_rsrp_gt_serving_rsrp": "No neighbor-cell RSRP field is carried into the anomaly documents "
                                      "to compare against serving RSRP.",
    "low_rank_indicator": "No MIMO rank indicator field exists anywhere in the anomaly pipeline's output.",
    "poor_spatial_multiplexing": "No MIMO spatial-multiplexing field exists anywhere in the anomaly "
                                  "pipeline's output.",
    "low_scell_rb_count": "No secondary-carrier RB count field exists in the anomaly data "
                           "(only carrier_count_median, which counts active carriers, not RBs).",
    "rach_access_delay": "No RACH access-delay field is carried into the final anomaly documents "
                          "(RACH counters only exist as intermediate ML features, not exposed per-anomaly).",
    "high_rach_attempts": "No RACH attempt-count field is carried into the final anomaly documents.",
    "radio_link_failure": "No radio-link-failure event field exists in the anomaly data.",
    "early_ho": "No handover-type classification field exists in the anomaly data.",
    "late_ho": "No handover-type classification field exists in the anomaly data.",
    "ping_pong_ho": "No handover-type classification field exists in the anomaly data.",
    "wrong_neighbor_relation": "No neighbor-relation field exists in the anomaly data.",
}


def is_evaluable(reason_id: str) -> bool:
    return reason_id in REASON_CONDITIONS


def evaluability_report(all_reason_ids: list[str]) -> dict[str, list[str]]:
    """For transparency: split any given list of reason_ids into evaluable
    vs. excluded, with the excluded ones' reasons. Intermediate/category
    taxonomy nodes (which were never given conditions -- only true leaves
    are, see graph_reasons.py's level field) show up as 'excluded: no
    condition defined' too, which is correct: this service only ever
    proposes the most specific reason, consistent with the taxonomy's own
    "prefer a more specific child" guidance."""
    evaluable, excluded = [], []
    for reason_id in all_reason_ids:
        if is_evaluable(reason_id):
            evaluable.append(reason_id)
        else:
            excluded.append({
                "reason_id": reason_id,
                "why": NOT_EVALUABLE_REASON_IDS.get(reason_id, "No condition defined for this reason "
                                                                 "(likely a taxonomy grouping node, not a "
                                                                 "specific measurable symptom)."),
            })
    return {"evaluable": evaluable, "excluded": excluded}
