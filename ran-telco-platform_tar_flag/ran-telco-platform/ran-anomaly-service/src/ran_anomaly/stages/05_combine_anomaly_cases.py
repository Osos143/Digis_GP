"""
Stage 05: combine anomaly cases
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 1712-2558). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

import plotly.graph_objects as go

# 14. Combine anomaly cases, severity, and scores
# =========================

# The broader bad_session_flag is context only. A sample inside a bad session is not automatically
# a sample-level anomaly unless a direct sample-level detector also fires.
lte_dl["bad_session_sample_flag"] = lte_dl["bad_session_sample_flag"] | (
    lte_dl["bad_session_flag"] & (lte_dl["underperform_vs_p75_flag"] | lte_dl.get("underperform_vs_rb_p75_flag", False))
)

# -------------------------
# A) Independent trigger families
# -------------------------
# Several flags are correlated. For example, fixed low throughput, P10, IQR, and robust-z
# all describe the same broad idea: "throughput is low". They should not stack as four
# independent pieces of evidence. We first create family-level triggers, then score the
# number of independent families.
lte_dl["low_tp_family_flag"] = (
    lte_dl["low_tp_fixed_flag"] |
    lte_dl["low_tp_global_p10_flag"] |
    lte_dl["low_tp_session_p10_flag"] |
    lte_dl["low_tp_robust_z_flag"] |
    lte_dl["low_tp_iqr_flag"]
)
lte_dl["temporal_drop_family_flag"] = lte_dl["rolling_drop_flag"] | lte_dl["sudden_drop_flag"]
lte_dl["sustained_window_family_flag"] = lte_dl["rolling_sustained_degradation_flag"]  # persistence modifier, not independent family
lte_dl["expected_tp_family_flag"] = lte_dl["underperform_vs_p75_flag"] | lte_dl.get("underperform_vs_rb_p75_flag", False)


# RB-efficiency method.
# RB usage tells us that resources were allocated. Throughput per RB tells us whether
# the allocated resources were converted efficiently into throughput. This is a strong
# candidate anomaly when RB demand is medium/high but throughput-per-RB is extremely low.
rb_values_for_eff = pd.to_numeric(lte_dl.get("rb_usage_value", pd.Series(np.nan, index=lte_dl.index)), errors="coerce")
lte_dl["throughput_per_rb"] = lte_dl["actual_lte_dl_throughput"] / rb_values_for_eff.replace(0, np.nan)
rb_eff_reference_mask = (
    lte_dl.get("rb_usage_evidence_reliable_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    lte_dl.get("rb_medium_or_high_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    lte_dl["throughput_per_rb"].notna()
)
rb_eff_p10 = lte_dl.loc[rb_eff_reference_mask, "throughput_per_rb"].quantile(RB_EFFICIENCY_REFERENCE_QUANTILE) if rb_eff_reference_mask.any() else np.nan
lte_dl["rb_efficiency_p10_threshold"] = rb_eff_p10
lte_dl["low_rb_efficiency_high_rb_flag"] = (
    rb_eff_reference_mask &
    pd.notna(rb_eff_p10) &
    (lte_dl["throughput_per_rb"] <= rb_eff_p10) &
    (lte_dl["actual_lte_dl_throughput"] <= max(LOW_TP_FIXED_MBPS, VERY_LOW_TP_MBPS))
)
lte_dl["rb_efficiency_family_flag"] = lte_dl["low_rb_efficiency_high_rb_flag"]
lte_dl["score_rb_efficiency"] = ((rb_eff_p10 - lte_dl["throughput_per_rb"]) / max(float(rb_eff_p10) if pd.notna(rb_eff_p10) else 1e-9, 1e-9)).clip(lower=0, upper=1).fillna(0)
lte_dl["score_rb_efficiency"] = lte_dl["score_rb_efficiency"].where(lte_dl["low_rb_efficiency_high_rb_flag"], 0.0)

# Low throughput with low RB is still useful, but it means demand/resource uncertainty,
# not confirmed unexpected underperformance. It remains a case/context label and is score-capped later.
lte_dl["low_tp_low_rb_flag"] = (
    lte_dl["low_tp_family_flag"] &
    lte_dl.get("rb_usage_evidence_reliable_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    lte_dl.get("rb_low_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool)
)

# RSRQ is useful evidence but noisy in the current plots. RSRQ alone should not dominate
# the radio-limited flag; it contributes strongly when SINR is also poor.
radio_bad_evidence = (
    lte_dl["poor_rsrp_flag"] |
    lte_dl["poor_sinr_flag"] |
    lte_dl["high_bler_flag"] |
    (lte_dl["poor_rsrq_flag"] & lte_dl["poor_sinr_flag"])
)

# Low throughput caused by clearly bad radio is still an anomaly, but it is radio-limited,
# not unexpected underperformance.
lte_dl["radio_limited_degradation_flag"] = (
    (lte_dl["low_tp_family_flag"] | lte_dl["temporal_drop_family_flag"] | lte_dl["sustained_window_family_flag"] | lte_dl["expected_tp_family_flag"]) &
    radio_bad_evidence
)
lte_dl["radio_limited_family_flag"] = lte_dl["radio_limited_degradation_flag"]  # case/context alias, not independent family

radio_ok_for_unexpected = ~radio_bad_evidence
lte_dl["unexpected_underperformance_flag"] = lte_dl["expected_tp_family_flag"] & radio_ok_for_unexpected

lte_dl["ca_active_flag"] = (
    (lte_dl["carrier_count"] >= 2) |
    lte_dl[["scell1_rsrp", "scell1_sinr", "scell1_cqi", "scell1_rb_count"]].notna().any(axis=1)
)

radio_ok_for_ca = ~(
    lte_dl["poor_rsrp_flag"] |
    lte_dl["poor_sinr_flag"] |
    lte_dl["high_bler_flag"]
)
if REQUIRE_RB_DEMAND_FOR_CA_UNDERPERFORMANCE and bool(lte_dl.get("rb_usage_evidence_reliable_flag", pd.Series(False, index=lte_dl.index)).fillna(False).any()):
    rb_demand_ok_for_ca = lte_dl.get("rb_medium_or_high_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool)
else:
    rb_demand_ok_for_ca = pd.Series(True, index=lte_dl.index)

# CA underperformance is strict: CA is active, radio is not obviously poor, RB demand exists,
# and either radio-P75 or RB-conditioned P75 says throughput is far lower than expected.
lte_dl["ca_underperformance_flag"] = (
    lte_dl["anomaly_analysis_window_flag"].fillna(True).astype(bool) &
    lte_dl["ca_active_flag"] &
    radio_ok_for_ca &
    rb_demand_ok_for_ca &
    (
        (
            lte_dl["expected_tp_reliable_flag"] &
            (lte_dl["expected_tp_radio_p75"] >= CA_UNDERPERF_MIN_EXPECTED_MBPS) &
            (lte_dl["actual_lte_dl_throughput"] <= CA_UNDERPERF_MAX_ACTUAL_MBPS) &
            (lte_dl["throughput_ratio_p75"] <= CA_UNDERPERF_RATIO_THRESHOLD)
        ) |
        (
            lte_dl.get("expected_tp_rb_reliable_flag", False) &
            (lte_dl.get("expected_tp_rb_conditioned_p75", np.nan) >= CA_UNDERPERF_MIN_EXPECTED_MBPS) &
            (lte_dl["actual_lte_dl_throughput"] <= CA_UNDERPERF_MAX_ACTUAL_MBPS) &
            (lte_dl.get("throughput_ratio_rb_p75", np.nan) <= CA_UNDERPERF_RATIO_THRESHOLD)
        )
    )
)
lte_dl["ca_underperformance_family_flag"] = lte_dl["ca_underperformance_flag"]  # case/context alias, not independent family

# Event evidence is contextual only. It does not create an anomaly by itself.
lte_dl["event_related_degradation_flag"] = (
    (lte_dl["low_tp_family_flag"] | lte_dl["temporal_drop_family_flag"] | lte_dl["sustained_window_family_flag"] | lte_dl["expected_tp_family_flag"]) &
    (
        lte_dl.get("near_handover_mobility_flag", False) |
        lte_dl.get("near_rach_failure_flag", False) |
        lte_dl.get("rach_failure_direct_flag", False)
    )
)

# Only genuinely distinct detector families count toward independence/fusion confidence.
# P10/IQR/MAD/fixed/session-P10 stay visible as details inside LOW_LEVEL.
# Sustained-window, radio-limited, and CA labels are persistence/case/context modifiers.
trigger_family_cols = [
    "low_tp_family_flag",
    "temporal_drop_family_flag",
    "expected_tp_family_flag",
    "rb_efficiency_family_flag",
]
context_family_alias_cols = [
    "sustained_window_family_flag",
    "radio_limited_family_flag",
    "ca_underperformance_family_flag",
]
trigger_detail_cols = [
    "low_tp_fixed_flag",
    "low_tp_global_p10_flag",
    "low_tp_session_p10_flag",
    "low_tp_robust_z_flag",
    "low_tp_iqr_flag",
    "rolling_drop_flag",
    "rolling_sustained_degradation_flag",
    "sudden_drop_flag",
    "underperform_vs_p75_flag",
    "underperform_vs_rb_p75_flag",
    "low_rb_efficiency_high_rb_flag",
    "ca_underperformance_flag",
]
context_flag_cols = [
    "radio_limited_degradation_flag",
    "unexpected_underperformance_flag",
    "event_related_degradation_flag",
    "bad_session_flag",
    "bad_session_sample_flag",
    "underperform_vs_p75_context_flag",
    "underperform_vs_rb_p75_context_flag",
    "p75_underperformance_demand_unknown_context_flag",
    "low_tp_low_rb_flag",
    "rb_low_usage_flag",
]
for col in trigger_family_cols + context_family_alias_cols + trigger_detail_cols + context_flag_cols:
    if col not in lte_dl.columns:
        lte_dl[col] = False

lte_dl["independent_trigger_count"] = lte_dl[trigger_family_cols].fillna(False).astype(bool).sum(axis=1)
lte_dl["is_throughput_anomaly"] = lte_dl["independent_trigger_count"] > 0
lte_dl["anomaly_method_count"] = lte_dl["independent_trigger_count"]
lte_dl["context_flag_count"] = lte_dl[context_flag_cols].fillna(False).astype(bool).sum(axis=1)
lte_dl["trigger_family_flags"] = lte_dl[trigger_family_cols].fillna(False).astype(bool).apply(
    lambda row: ";".join([col.replace("_flag", "") for col, active in row.items() if active]) if row.any() else "none",
    axis=1,
)

# -------------------------
# B) Continuous evidence-based score
# -------------------------
score_cols = [
    "score_fixed_low_tp",
    "score_global_p10_low_tp",
    "score_session_p10_low_tp",
    "score_robust_z_low_tp",
    "score_iqr_low_tp",
    "score_rolling_drop",
    "score_rolling_bad_window",
    "score_bad_session",
    "score_sudden_drop",
    "score_group_p75_gap",
    "score_group_rb_p75_gap",
    "score_rb_efficiency",
]
for col in score_cols:
    if col not in lte_dl.columns:
        lte_dl[col] = 0.0

# Strongest trigger base. These are interpretable minimum anchors, not the full score.
severe_radio_p75_condition = (
    lte_dl["underperform_vs_p75_flag"].fillna(False).astype(bool) &
    (lte_dl["actual_lte_dl_throughput"] <= VERY_LOW_TP_MBPS) &
    (lte_dl["expected_tp_radio_p75"] >= 40) &
    (lte_dl["throughput_ratio_p75"] <= 0.20)
)
severe_rb_p75_condition = (
    lte_dl.get("underperform_vs_rb_p75_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    (lte_dl["actual_lte_dl_throughput"] <= VERY_LOW_TP_MBPS) &
    (lte_dl.get("expected_tp_rb_conditioned_p75", np.nan) >= 40) &
    (lte_dl.get("throughput_ratio_rb_p75", np.nan) <= 0.20)
)
severe_p75_condition = severe_radio_p75_condition | severe_rb_p75_condition
reliable_p75_condition = lte_dl["expected_tp_family_flag"].fillna(False).astype(bool)
rb_efficiency_condition = lte_dl.get("rb_efficiency_family_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool)
local_drop_condition = lte_dl["temporal_drop_family_flag"].fillna(False).astype(bool)
sustained_condition = lte_dl["sustained_window_family_flag"].fillna(False).astype(bool)
radio_limited_condition = lte_dl["radio_limited_family_flag"].fillna(False).astype(bool)
low_tp_condition = lte_dl["low_tp_family_flag"].fillna(False).astype(bool)

base_score_candidates = pd.concat([
    pd.Series(np.where(severe_p75_condition, MIN_SCORE_SEVERE_P75_UNDERPERF, 0), index=lte_dl.index),
    pd.Series(np.where(reliable_p75_condition, MIN_SCORE_P75_UNDERPERF, 0), index=lte_dl.index),
    pd.Series(np.where(rb_efficiency_condition, MIN_SCORE_P75_UNDERPERF, 0), index=lte_dl.index),
    pd.Series(np.where(local_drop_condition, MIN_SCORE_LOCAL_DROP, 0), index=lte_dl.index),
    pd.Series(np.where(sustained_condition, MIN_SCORE_SUSTAINED_LOW_WINDOW, 0), index=lte_dl.index),
    pd.Series(np.where(radio_limited_condition, MIN_SCORE_RADIO_LIMITED, 0), index=lte_dl.index),
    pd.Series(np.where(low_tp_condition, MIN_SCORE_FIXED_LOW_TP, 0), index=lte_dl.index),
    pd.Series(np.where(lte_dl["is_throughput_anomaly"], MIN_SCORE_ANY_TRIGGER, 0), index=lte_dl.index),
], axis=1)
lte_dl["score_base_from_strongest_trigger"] = base_score_candidates.max(axis=1)

# Continuous anomaly magnitude. This avoids artificial score piles caused by floors alone.
best_ratio = pd.concat([
    lte_dl["throughput_ratio_p75"],
    lte_dl.get("throughput_ratio_rb_p75", pd.Series(np.nan, index=lte_dl.index)),
], axis=1).min(axis=1)
best_gap = pd.concat([
    lte_dl["throughput_gap_p75"],
    lte_dl.get("throughput_gap_rb_p75", pd.Series(np.nan, index=lte_dl.index)),
], axis=1).max(axis=1)

lte_dl["score_magnitude_ratio_severity"] = ((0.60 - best_ratio) / 0.60).clip(lower=0, upper=1).fillna(0)
lte_dl["score_magnitude_gap_severity"] = (best_gap / MAGNITUDE_GAP_DENOMINATOR_MBPS).clip(lower=0, upper=1).fillna(0)
lte_dl["score_magnitude_low_tp_severity"] = ((MAGNITUDE_LOW_TP_REFERENCE_MBPS - lte_dl["actual_lte_dl_throughput"]) / MAGNITUDE_LOW_TP_REFERENCE_MBPS).clip(lower=0, upper=1).fillna(0)
rolling_gap_for_score = pd.concat([
    lte_dl.get("rolling_tp_gap", pd.Series(0, index=lte_dl.index)),
    lte_dl.get("tp_drop_from_prev", pd.Series(0, index=lte_dl.index)),
], axis=1).max(axis=1)
lte_dl["score_magnitude_drop_severity"] = (rolling_gap_for_score / MAGNITUDE_DROP_DENOMINATOR_MBPS).clip(lower=0, upper=1).fillna(0)

lte_dl["score_continuous_magnitude"] = 100 * (
    0.35 * lte_dl["score_magnitude_ratio_severity"] +
    0.25 * lte_dl["score_magnitude_gap_severity"] +
    0.25 * lte_dl["score_magnitude_low_tp_severity"] +
    0.15 * lte_dl["score_magnitude_drop_severity"]
)

# RB-efficiency severity is used as an additional continuous evidence dimension.
lte_dl["score_magnitude_rb_efficiency"] = lte_dl.get("score_rb_efficiency", pd.Series(0, index=lte_dl.index)).fillna(0)
lte_dl["score_continuous_magnitude"] = np.maximum(
    lte_dl["score_continuous_magnitude"],
    75 * lte_dl["score_magnitude_rb_efficiency"],
)

# Independent-trigger bonus. Count trigger families, not raw correlated flags.
lte_dl["score_independent_trigger_bonus"] = (
    MULTI_TRIGGER_BONUS_PER_LOG_STEP * np.log1p(np.maximum(lte_dl["independent_trigger_count"] - 1, 0))
).clip(lower=0, upper=MULTI_TRIGGER_BONUS_CAP)

# Capped evidence bonus. Context supports confidence but does not create anomalies by itself.
poor_radio_context_flag = radio_bad_evidence
near_event_context_flag = lte_dl["event_related_degradation_flag"].fillna(False).astype(bool)
# P10/IQR/robust-MAD remain individually visible detectors, but their agreement contributes
# only ONE bounded low-tail evidence term so correlated methods cannot inflate confidence.
low_tail_consensus_strength = pd.to_numeric(
    lte_dl.get("low_tail_robust_consensus_strength_0_1", pd.Series(0.0, index=lte_dl.index)), errors="coerce"
).fillna(0).clip(0, 1)
lte_dl["score_evidence_bonus"] = (
    3.0 * low_tail_consensus_strength +
    4 * lte_dl.get("rb_high_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool).astype(int) +
    2 * lte_dl["ca_active_flag"].fillna(False).astype(bool).astype(int) +
    2 * near_event_context_flag.astype(int) +
    2 * poor_radio_context_flag.fillna(False).astype(bool).astype(int)
).clip(lower=0, upper=EVIDENCE_BONUS_CAP)

score_before_cap = np.maximum(lte_dl["score_base_from_strongest_trigger"], lte_dl["score_continuous_magnitude"])
score_before_cap = score_before_cap + lte_dl["score_independent_trigger_bonus"] + lte_dl["score_evidence_bonus"]
lte_dl["score_raw_before_caps"] = score_before_cap

# Preserve an uncapped analytical score for ranking/fusion. Operational uncertainty is
# applied smoothly so many rows do not collapse to exactly 45 or 95.
lte_dl["anomaly_score_raw_0_100"] = pd.Series(score_before_cap, index=lte_dl.index).clip(lower=0, upper=100)

low_rb_cap_mask = (
    lte_dl.get("rb_usage_evidence_reliable_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    lte_dl.get("rb_low_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    ~lte_dl["radio_limited_family_flag"].fillna(False).astype(bool) &
    ~lte_dl["temporal_drop_family_flag"].fillna(False).astype(bool)
)
lte_dl["score_low_rb_cap_applied_flag"] = low_rb_cap_mask
# Smooth asymptotic uncertainty compression: approaches LOW_RB_DEMAND_SCORE_CAP without
# producing a pile of rows at the exact cap.
low_rb_smoothed = LOW_RB_DEMAND_SCORE_CAP * (
    1.0 - np.exp(-1.5 * pd.Series(score_before_cap, index=lte_dl.index) / max(LOW_RB_DEMAND_SCORE_CAP, 1e-6))
)
score_after_cap = pd.Series(score_before_cap, index=lte_dl.index).where(~low_rb_cap_mask, low_rb_smoothed)
lte_dl["score_after_low_rb_cap"] = score_after_cap

best_expected_for_score = pd.concat([
    lte_dl.get("expected_tp_radio_p75", pd.Series(np.nan, index=lte_dl.index)),
    lte_dl.get("expected_tp_rb_conditioned_p75", pd.Series(np.nan, index=lte_dl.index)),
], axis=1).max(axis=1)
lte_dl["catastrophic_score_allowed_flag"] = (
    (lte_dl["actual_lte_dl_throughput"] <= CATASTROPHIC_ACTUAL_TP_MBPS) &
    (best_expected_for_score >= CATASTROPHIC_EXPECTED_TP_MBPS) &
    lte_dl.get("rb_medium_or_high_usage_flag", pd.Series(False, index=lte_dl.index)).fillna(False).astype(bool) &
    (lte_dl["independent_trigger_count"] >= 2)
)
# Smooth high-end saturation toward the non-catastrophic cap while retaining ordering.
score_operational = score_after_cap.copy()
high_mask = score_operational > 85.0
score_operational.loc[high_mask] = 85.0 + (SCORE_SOFT_CAP_NON_CATASTROPHIC - 85.0) * (
    1.0 - np.exp(-(score_operational.loc[high_mask] - 85.0) / 10.0)
)
score_operational = score_operational.where(~lte_dl["catastrophic_score_allowed_flag"], 100.0)

lte_dl["anomaly_score_0_100"] = score_operational.clip(lower=0, upper=100)
lte_dl["anomaly_score_0_100"] = lte_dl["anomaly_score_0_100"].where(lte_dl["is_throughput_anomaly"], 0.0).round(1)

score_component_cols = [
    "score_base_from_strongest_trigger",
    "score_continuous_magnitude",
    "score_independent_trigger_bonus",
    "score_evidence_bonus",
    "score_low_rb_cap_applied_flag",
    "score_magnitude_ratio_severity",
    "score_magnitude_gap_severity",
    "score_magnitude_low_tp_severity",
    "score_magnitude_drop_severity",
    "score_magnitude_rb_efficiency",
    "score_raw_before_caps",
    "anomaly_score_raw_0_100",
    "score_after_low_rb_cap",
    "catastrophic_score_allowed_flag",
]

# -------------------------
# C) Case labels and severity
# -------------------------
CASE_FLAG_MAP = {
    "unexpected_underperformance": "unexpected_underperformance_flag",
    "radio_limited_degradation": "radio_limited_degradation_flag",
    "ca_underperformance": "ca_underperformance_flag",
    "rb_efficiency_underperformance": "low_rb_efficiency_high_rb_flag",
    "rb_conditioned_underperformance": "underperform_vs_rb_p75_flag",
    "resource_limited_or_demand_uncertain_low_throughput": "low_tp_low_rb_flag",
    "radio_p75_underperformance": "underperform_vs_p75_flag",
    "sudden_drop": "sudden_drop_flag",
    "rolling_local_drop": "rolling_drop_flag",
    "sustained_low_throughput_window": "rolling_sustained_degradation_flag",
    "fixed_low_throughput": "low_tp_fixed_flag",
    "global_percentile_low_throughput": "low_tp_global_p10_flag",
    "session_percentile_low_throughput": "low_tp_session_p10_flag",
    "iqr_extreme_low_throughput": "low_tp_iqr_flag",
    "robust_z_extreme_low_throughput": "low_tp_robust_z_flag",
}

case_df = pd.DataFrame(index=lte_dl.index)
for label, col in CASE_FLAG_MAP.items():
    case_df[label] = lte_dl[col].fillna(False).astype(bool) if col in lte_dl.columns else False

lte_dl["anomaly_type_flags"] = case_df.apply(
    lambda row: ";".join([label for label, active in row.items() if active]) if row.any() else "not_flagged",
    axis=1,
)

# Specific-first priority. Generic unexpected-underperformance should not hide
# CA, RB-conditioned, RB-efficiency, or radio-P75-specific cases.
priority_labels = [
    "ca_underperformance",
    "rb_efficiency_underperformance",
    "rb_conditioned_underperformance",
    "radio_p75_underperformance",
    "unexpected_underperformance",
    "radio_limited_degradation",
    "sudden_drop",
    "rolling_local_drop",
    "sustained_low_throughput_window",
    "resource_limited_or_demand_uncertain_low_throughput",
    "fixed_low_throughput",
    "global_percentile_low_throughput",
    "session_percentile_low_throughput",
    "iqr_extreme_low_throughput",
    "robust_z_extreme_low_throughput",
]
conditions = [case_df[label].values for label in priority_labels]
lte_dl["anomaly_type"] = np.select(conditions, priority_labels, default="not_flagged")
lte_dl.loc[~lte_dl["is_throughput_anomaly"], "anomaly_type"] = "not_flagged"
lte_dl.loc[~lte_dl["is_throughput_anomaly"], "anomaly_type_flags"] = "not_flagged"

# Severity combines score thresholds with technical severity criteria.
SEVERITY_ORDER = {"Normal": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}
REVERSE_SEVERITY_ORDER = {v: k for k, v in SEVERITY_ORDER.items()}


def max_severity(a: str, b: str) -> str:
    return REVERSE_SEVERITY_ORDER[max(SEVERITY_ORDER.get(a, 0), SEVERITY_ORDER.get(b, 0))]


def cap_severity(severity: str, max_allowed: str) -> str:
    return REVERSE_SEVERITY_ORDER[min(SEVERITY_ORDER.get(severity, 0), SEVERITY_ORDER.get(max_allowed, 0))]


def assign_severity_v3(row: pd.Series) -> str:
    if not bool(row.get("is_throughput_anomaly", False)):
        return "Normal"

    actual = row.get("actual_lte_dl_throughput", np.nan)
    expected_radio = row.get("expected_tp_radio_p75", np.nan)
    expected_rb = row.get("expected_tp_rb_conditioned_p75", np.nan)
    expected = np.nanmax([expected_radio, expected_rb])
    ratio_radio = row.get("throughput_ratio_p75", np.nan)
    ratio_rb = row.get("throughput_ratio_rb_p75", np.nan)
    ratio = np.nanmin([ratio_radio, ratio_rb])
    reliable = bool(row.get("expected_tp_reliable_flag", False)) or bool(row.get("expected_tp_rb_reliable_flag", False))
    score = row.get("anomaly_score_0_100", 0)
    families = int(row.get("independent_trigger_count", 0))

    catastrophic = bool(row.get("catastrophic_score_allowed_flag", False))
    rb_confirmed = bool(row.get("rb_medium_or_high_usage_flag", False))
    radio_limited = bool(row.get("radio_limited_degradation_flag", False)) or bool(row.get("radio_limited_family_flag", False))
    temporal_drop = bool(row.get("temporal_drop_family_flag", False))

    severity = "Low"
    if reliable and pd.notna(actual) and pd.notna(expected) and pd.notna(ratio):
        if catastrophic and score >= 85:
            severity = "Critical"
        elif actual <= 2.0 and expected >= 50 and ratio <= 0.15 and rb_confirmed and score >= 85:
            severity = "Critical"
        elif actual <= LOW_TP_FIXED_MBPS and expected >= 25 and ratio <= 0.35:
            # Low-RB/demand-uncertain rows should not become High only because the
            # radio-P75 reference is high. Require RB confirmation or direct radio/temporal evidence.
            severity = "High" if (rb_confirmed or radio_limited or temporal_drop) else "Medium"

    if severity != "Critical":
        if score >= 85 and families >= 3 and rb_confirmed:
            severity = max_severity(severity, "High")
        if score >= 60 or families >= 4:
            severity = max_severity(severity, "High")
        elif score >= 35 or families >= 2:
            severity = max_severity(severity, "Medium")

    # Final cap for demand-uncertain low-RB rows unless there is radio or temporal evidence.
    if bool(row.get("score_low_rb_cap_applied_flag", False)) and not radio_limited and not temporal_drop:
        severity = cap_severity(severity, "Medium")

    return severity


lte_dl["anomaly_severity"] = lte_dl.apply(assign_severity_v3, axis=1)

# Candidate-vs-handoff split. The candidate flag remains broad for monitoring/QC. The
# RCA handoff flag is stricter and suppresses weak low-RB-only candidates.
lte_dl["weak_low_rb_only_candidate_flag"] = (
    lte_dl["low_tp_low_rb_flag"].fillna(False).astype(bool) &
    ~lte_dl["radio_limited_family_flag"].fillna(False).astype(bool) &
    ~lte_dl["temporal_drop_family_flag"].fillna(False).astype(bool) &
    ~lte_dl["expected_tp_family_flag"].fillna(False).astype(bool) &
    ~lte_dl["rb_efficiency_family_flag"].fillna(False).astype(bool)
)
lte_dl["rca_handoff_flag"] = (
    lte_dl["is_throughput_anomaly"].fillna(False).astype(bool) &
    (lte_dl["anomaly_score_0_100"] >= RCA_HANDOFF_MIN_SCORE) &
    (
        lte_dl["expected_tp_family_flag"].fillna(False).astype(bool) |
        lte_dl["rb_efficiency_family_flag"].fillna(False).astype(bool) |
        lte_dl["radio_limited_family_flag"].fillna(False).astype(bool) |
        lte_dl["temporal_drop_family_flag"].fillna(False).astype(bool) |
        lte_dl["sustained_window_family_flag"].fillna(False).astype(bool)
    ) &
    ~lte_dl["weak_low_rb_only_candidate_flag"].fillna(False).astype(bool)
)

# -------------------------
# D) Summary tables and QC
# -------------------------
flag_roles = {c: "trigger_detail" for c in trigger_detail_cols}
flag_roles.update({c: "trigger_family_independent" for c in trigger_family_cols})
flag_roles.update({c: "context_or_case_family_alias" for c in context_family_alias_cols})
flag_roles.update({
    "radio_limited_degradation_flag": "case_context",
    "unexpected_underperformance_flag": "case_context",
    "event_related_degradation_flag": "context_only",
    "bad_session_flag": "context_only",
    "bad_session_sample_flag": "context_only",
    "underperform_vs_p75_context_flag": "context_only",
    "underperform_vs_rb_p75_context_flag": "context_only",
    "p75_underperformance_demand_unknown_context_flag": "context_only",
    "low_tp_low_rb_flag": "case_context",
    "low_rb_efficiency_high_rb_flag": "trigger_detail",
    "rb_efficiency_family_flag": "trigger_family",
    "rb_low_usage_flag": "context_only",
    "weak_low_rb_only_candidate_flag": "context_only",
    "is_throughput_anomaly": "candidate_gate",
    "rca_handoff_flag": "handoff_gate",
})
summary_cols = list(dict.fromkeys(trigger_family_cols + context_family_alias_cols + trigger_detail_cols + context_flag_cols + ["low_tail_robust_consensus_flag", "weak_low_rb_only_candidate_flag", "is_throughput_anomaly", "rca_handoff_flag"]))
analysis_denominator = int(lte_dl["anomaly_analysis_window_flag"].fillna(True).astype(bool).sum()) if "anomaly_analysis_window_flag" in lte_dl.columns else len(lte_dl)
method_summary = pd.DataFrame([
    {
        "method_or_case": col,
        "flag_role": flag_roles.get(col, "unknown"),
        "flagged_rows": int(lte_dl[col].fillna(False).astype(bool).sum()),
        "flagged_pct": round(float(lte_dl[col].fillna(False).astype(bool).sum() / max(analysis_denominator, 1) * 100), 3),
        "flagged_pct_of_all_lte_dl_rows": round(float(lte_dl[col].fillna(False).astype(bool).mean() * 100), 3),
    }
    for col in summary_cols
    if col in lte_dl.columns
])
save_table(method_summary, "anomaly_method_summary.csv")
display(method_summary)

flag_overlap_summary = (
    lte_dl.groupby(["independent_trigger_count", "context_flag_count"], dropna=False)
    .agg(
        rows=("actual_lte_dl_throughput", "count"),
        anomaly_rows=("is_throughput_anomaly", "sum"),
        mean_score=("anomaly_score_0_100", "mean"),
        median_score=("anomaly_score_0_100", "median"),
        median_tp=("actual_lte_dl_throughput", "median"),
    )
    .reset_index()
    .sort_values(["independent_trigger_count", "context_flag_count"])
)
for c in ["mean_score", "median_score", "median_tp"]:
    flag_overlap_summary[c] = flag_overlap_summary[c].astype(float).round(3)
save_table(flag_overlap_summary, "anomaly_flag_overlap_summary.csv")
display(flag_overlap_summary)

# Score distribution QC. These warnings help tune whether scores are too compressed or too severe.
flagged_scores = lte_dl.loc[lte_dl["is_throughput_anomaly"], "anomaly_score_0_100"].dropna()
score_qc_rows = []
if not flagged_scores.empty:
    score_qc_rows.append({"metric": "flagged_rows", "value": len(flagged_scores), "qc_note": "Number of anomaly rows used for score-distribution checks."})
    for q in [0.10, 0.25, 0.50, 0.75, 0.80, 0.90, 0.95, 0.99]:
        score_qc_rows.append({"metric": f"score_p{int(q*100):02d}", "value": float(flagged_scores.quantile(q)), "qc_note": "Flagged-score percentile."})
    severity_pct = lte_dl.loc[lte_dl["is_throughput_anomaly"], "anomaly_severity"].value_counts(normalize=True) * 100
    for sev, pct in severity_pct.items():
        score_qc_rows.append({"metric": f"severity_pct_{sev}", "value": float(pct), "qc_note": "Share of flagged rows by severity."})

    if float(flagged_scores.quantile(0.95)) < 60:
        score_qc_rows.append({"metric": "warning_score_compressed", "value": 1, "qc_note": "P95 flagged score is below 60; scoring may still be too compressed."})
    if float((lte_dl.loc[lte_dl["is_throughput_anomaly"], "anomaly_severity"] == "Critical").mean() * 100) > 10:
        score_qc_rows.append({"metric": "warning_critical_pct_high", "value": 1, "qc_note": "Critical percentage is above 10%; review severity/score scaling."})
    if float(flagged_scores.quantile(0.50)) < 35:
        score_qc_rows.append({"metric": "warning_median_score_low", "value": 1, "qc_note": "Median flagged score is below 35; many anomalies may be weak candidates."})
    low_rb_cap_pile_pct = float((flagged_scores == LOW_RB_DEMAND_SCORE_CAP).mean() * 100)
    soft_cap_pile_pct = float((flagged_scores == SCORE_SOFT_CAP_NON_CATASTROPHIC).mean() * 100)
    score_qc_rows.append({"metric": "pct_exact_low_rb_cap", "value": low_rb_cap_pile_pct, "qc_note": "Share of flagged scores exactly at the low-RB cap."})
    score_qc_rows.append({"metric": "pct_exact_soft_cap", "value": soft_cap_pile_pct, "qc_note": "Share of flagged scores exactly at the non-catastrophic soft cap."})
    if low_rb_cap_pile_pct > 10:
        score_qc_rows.append({"metric": "warning_low_rb_cap_pileup", "value": 1, "qc_note": "Many anomalies sit exactly at the low-RB cap; ranking may be compressed."})
    if soft_cap_pile_pct > 5:
        score_qc_rows.append({"metric": "warning_soft_cap_pileup", "value": 1, "qc_note": "Many anomalies sit exactly at the soft cap; high-end ranking may be compressed."})
score_qc = pd.DataFrame(score_qc_rows)
if not score_qc.empty:
    score_qc["value"] = pd.to_numeric(score_qc["value"], errors="coerce").round(3)
save_table(score_qc, "anomaly_score_distribution_qc.csv")
display(score_qc)

# Percentage sanity review. These are not hard pass/fail rules; they flag methods that deserve a look.
expected_pct_ranges = {
    "low_tp_fixed_flag": (10, 25, "10 Mbps should capture the lower tail, not half the route."),
    "low_tp_global_p10_flag": (9, 11, "Global P10 should be almost exactly 10% by construction."),
    "low_tp_session_p10_flag": (3, 12, "Session P10 should be lower than 10% overall after the low-session-threshold guard."),
    "low_tp_robust_z_flag": (1, 6, "Robust z is an extreme lower-tail method; 0% usually means the threshold is too strict."),
    "low_tp_iqr_flag": (1, 6, "Log-IQR should catch only extreme low-throughput outliers."),
    "rolling_drop_flag": (3, 15, "Rolling drop should capture local collapses, not every low segment."),
    "rolling_sustained_degradation_flag": (5, 18, "Sustained window degradation can be broader than extreme outlier methods."),
    "sudden_drop_flag": (3, 15, "Sudden one-sample drops are common in drive tests but should stay bounded."),
    "underperform_vs_p75_flag": (1, 10, "Reliable radio-P75 underperformance should be narrower after RB-demand gating."),
    "underperform_vs_rb_p75_flag": (1, 10, "RB-conditioned P75 underperformance should be narrow and high confidence."),
    "low_rb_efficiency_high_rb_flag": (0.5, 8, "Low throughput-per-RB under medium/high RB should be narrow and high confidence."),
    "rb_efficiency_family_flag": (0.5, 8, "RB-efficiency family should not dominate; it confirms inefficient use of allocated RBs."),
    "expected_tp_family_flag": (2, 15, "Expected-throughput family combines radio-P75 and RB-conditioned P75."),
    "unexpected_underperformance_flag": (2, 12, "Unexpected underperformance should be narrower than broad P75 context."),
    "radio_limited_degradation_flag": (3, 18, "With calibrated poor-radio thresholds, this should focus on clearly bad radio evidence."),
    "ca_underperformance_flag": (1, 8, "Tightened CA underperformance should not dominate the anomaly table."),
    "event_related_degradation_flag": (3, 18, "Event evidence is contextual and should not use near_any_event."),
    "is_throughput_anomaly": (8, 26, "Broad statistical candidate gate. The stricter RCA handoff is controlled separately."),
    "rca_handoff_flag": (8, 22, "Practical RCA handoff subset after weak low-RB-only suppression."),
}
qc_rows = []
for _, row in method_summary.iterrows():
    method = row["method_or_case"]
    pct = float(row["flagged_pct"])
    lo, hi, note = expected_pct_ranges.get(method, (0, 100, "No fixed review band configured."))
    status = "OK"
    if pct < lo:
        status = "LOW_REVIEW"
    elif pct > hi:
        status = "HIGH_REVIEW"
    qc_rows.append({
        "method_or_case": method,
        "flag_role": row.get("flag_role", "unknown"),
        "flagged_pct": pct,
        "expected_low_pct": lo,
        "expected_high_pct": hi,
        "qc_status": status,
        "interpretation": note,
    })
percentage_qc_review = pd.DataFrame(qc_rows)
save_table(percentage_qc_review, "anomaly_percentage_qc_review.csv")
display(percentage_qc_review)

leaked_default_rows = int(((lte_dl["is_throughput_anomaly"]) & (lte_dl["anomaly_type"] == "not_flagged")).sum())
if leaked_default_rows:
    print(f"WARNING: {leaked_default_rows} anomaly rows still have anomaly_type='not_flagged'. Review CASE_FLAG_MAP.")
else:
    print("Sanity check passed: every anomaly row has a non-default anomaly_type.")


# -------------------------
# E) Empirical fusion-weight validation
# -------------------------
# This does not auto-tune weights on the same data. It diagnoses whether a component dominates
# the fused score, whether independent families are actually redundant, and whether the robust
# low-tail trio is being treated as one bounded evidence source as intended.
fusion_validation_mask = lte_dl["is_throughput_anomaly"].fillna(False).astype(bool)
fusion_component_cols = [
    "score_base_from_strongest_trigger", "score_continuous_magnitude",
    "score_independent_trigger_bonus", "score_evidence_bonus",
]
fusion_component_rows = []
for col in fusion_component_cols:
    vals = pd.to_numeric(lte_dl.loc[fusion_validation_mask, col], errors="coerce")
    fusion_component_rows.append({
        "component": col,
        "mean": vals.mean(), "median": vals.median(), "p90": vals.quantile(0.90),
        "nonzero_pct": 100 * vals.gt(0).mean() if len(vals) else np.nan,
    })
fusion_component_validation = pd.DataFrame(fusion_component_rows)

# Pairwise Jaccard among the four independent families. High overlap is a warning that
# independence assumptions should be reviewed, not a reason to silently retune weights.
family_overlap_rows = []
for a in trigger_family_cols:
    A = lte_dl[a].fillna(False).astype(bool)
    for b in trigger_family_cols:
        B = lte_dl[b].fillna(False).astype(bool)
        union = int((A | B).sum()); inter = int((A & B).sum())
        family_overlap_rows.append({
            "family_a": a, "family_b": b, "intersection_rows": inter,
            "union_rows": union, "jaccard": inter / union if union else np.nan,
        })
fusion_family_overlap = pd.DataFrame(family_overlap_rows)

# Weight-health flags: evidence/bonus terms should support—not dominate—the main base/magnitude.
base_mag = pd.concat([
    pd.to_numeric(lte_dl.loc[fusion_validation_mask, "score_base_from_strongest_trigger"], errors="coerce"),
    pd.to_numeric(lte_dl.loc[fusion_validation_mask, "score_continuous_magnitude"], errors="coerce"),
], axis=1).max(axis=1)
bonus_total = (
    pd.to_numeric(lte_dl.loc[fusion_validation_mask, "score_independent_trigger_bonus"], errors="coerce").fillna(0) +
    pd.to_numeric(lte_dl.loc[fusion_validation_mask, "score_evidence_bonus"], errors="coerce").fillna(0)
)
fusion_weight_health = pd.DataFrame([{
    "anomaly_rows": int(fusion_validation_mask.sum()),
    "median_base_or_magnitude": float(base_mag.median()) if len(base_mag) else np.nan,
    "median_total_bonus": float(bonus_total.median()) if len(bonus_total) else np.nan,
    "p90_total_bonus": float(bonus_total.quantile(0.90)) if len(bonus_total) else np.nan,
    "pct_rows_bonus_exceeds_base_or_magnitude": float(100 * (bonus_total > base_mag).mean()) if len(base_mag) else np.nan,
    "verdict": "REVIEW_IF_BONUS_DOMINATES" if len(base_mag) and (bonus_total > base_mag).mean() > 0.10 else "BONUS_IS_SUPPORTING_EVIDENCE",
}])

save_table(fusion_component_validation, "fusion_component_empirical_validation.csv", category="key")
save_table(fusion_family_overlap, "fusion_independent_family_overlap.csv", category="key")
save_table(fusion_weight_health, "fusion_weight_health_check.csv", category="key")
print("Empirical fusion component validation:")
display(fusion_component_validation.round(3))
display(fusion_weight_health.round(3))

if len(fusion_component_validation):
    plt.figure(figsize=(10,5))
    plt.bar(fusion_component_validation["component"], fusion_component_validation["median"].fillna(0))
    plt.ylabel("Median contribution among statistical anomaly rows")
    plt.title("Fusion contribution audit — main evidence should dominate bonuses")
    plt.xticks(rotation=25, ha="right")
    save_current_plot("stat_28_fusion_component_contribution_audit.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=fusion_component_validation["component"],
            y=fusion_component_validation["median"].fillna(0)
        )])
        fig.update_layout(
            template='plotly_white',
            title="Fusion contribution audit — main evidence should dominate bonuses",
            yaxis_title="Median contribution among statistical anomaly rows",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        fig.write_html(str(PLOTS_DIR / "stat_28_fusion_component_contribution_audit.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

# =========================
# 14B. Worst-performing cell / PCI ranking for RCA investigation
# =========================

# PCI can be reused across the network, so the primary ranking uses a cell key:
# ECI when available; otherwise EARFCN+PCI. A separate PCI-only ranking is exported as
# a secondary view and should be interpreted with reuse caution.

def _mode_or_nan(s: pd.Series):
    m = s.dropna().mode()
    return m.iloc[0] if len(m) else np.nan


def build_cell_key(frame: pd.DataFrame) -> pd.Series:
    eci = frame.get("serving_eci", pd.Series(np.nan, index=frame.index))
    earfcn = frame.get("serving_earfcn", pd.Series(np.nan, index=frame.index))
    pci = frame.get("serving_pci", pd.Series(np.nan, index=frame.index))
    out = pd.Series(index=frame.index, dtype="object")
    has_eci = eci.notna()
    out.loc[has_eci] = "ECI:" + eci.loc[has_eci].astype(str)
    fallback = ~has_eci & pci.notna()
    out.loc[fallback] = "EARFCN:" + earfcn.loc[fallback].astype(str) + "|PCI:" + pci.loc[fallback].astype(str)
    return out

lte_dl["serving_cell_key"] = build_cell_key(lte_dl)

def rank_bad_entities(frame: pd.DataFrame, group_col: str, entity_label: str, min_rows: int) -> pd.DataFrame:
    valid = frame[frame[group_col].notna()].copy()
    if valid.empty:
        return pd.DataFrame()

    agg_spec = {
        "rows": (TARGET_COL, "size"),
        "sessions": ("id", "nunique"),
        "median_tp_mbps": (TARGET_COL, "median"),
        "p10_tp_mbps": (TARGET_COL, lambda s: pd.to_numeric(s, errors="coerce").quantile(0.10)),
        "mean_tp_mbps": (TARGET_COL, "mean"),
        "low_tp_pct": ("low_tp_family_flag", lambda s: 100 * pd.Series(s).fillna(False).astype(bool).mean()),
        "stat_anomaly_pct": ("is_throughput_anomaly", lambda s: 100 * pd.Series(s).fillna(False).astype(bool).mean()),
        "rca_handoff_pct": ("rca_handoff_flag", lambda s: 100 * pd.Series(s).fillna(False).astype(bool).mean()),
        "median_p75_gap_mbps": ("throughput_gap_p75", "median"),
        "p90_p75_gap_mbps": ("throughput_gap_p75", lambda s: pd.to_numeric(s, errors="coerce").quantile(0.90)),
        "median_rsrp_dbm": ("lte_rsrp", "median"),
        "median_rsrq_db": ("lte_rsrq", "median"),
        "median_sinr_db": ("lte_sinr", "median"),
        "median_cqi": ("lte_cqi", "median"),
        "median_mcs": ("lte_mcs", "median"),
        "median_bler_pct": ("lte_bler", "median"),
        "p90_bler_pct": ("lte_bler", lambda s: pd.to_numeric(s, errors="coerce").quantile(0.90)),
        "median_rb_usage": ("rb_usage_value", "median"),
        "median_tp_per_rb": ("throughput_per_rb", "median"),
    }
    # Only retain aggregations whose source columns exist.
    agg_spec = {k:v for k,v in agg_spec.items() if v[0] in valid.columns}
    ranked = valid.groupby(group_col, dropna=False).agg(**agg_spec).reset_index()
    ranked = ranked[(ranked["rows"] >= min_rows) & (ranked["sessions"] >= CELL_RANK_MIN_SESSIONS)].copy()
    if ranked.empty:
        return ranked

    # Percentile badness is fully data-driven. Higher = worse.
    # Low throughput/CQI/MCS/SINR => bad; high BLER/anomaly/gap => bad.
    components = {
        # Throughput remains the primary definition of bad performance. Radio/PHY KPIs explain
        # whether that poor performance is accompanied by coverage/interference/link-quality evidence.
        "median_tp_badness": ("median_tp_mbps", "low", 0.25),
        "p10_tp_badness": ("p10_tp_mbps", "low", 0.12),
        "anomaly_rate_badness": ("stat_anomaly_pct", "high", 0.13),
        "p75_gap_badness": ("median_p75_gap_mbps", "high", 0.10),
        "cqi_badness": ("median_cqi", "low", 0.10),
        "mcs_badness": ("median_mcs", "low", 0.08),
        "bler_badness": ("median_bler_pct", "high", 0.10),
        "sinr_badness": ("median_sinr_db", "low", 0.06),
        "rsrq_badness": ("median_rsrq_db", "low", 0.04),
        "rsrp_badness": ("median_rsrp_dbm", "low", 0.02),
    }
    weighted_sum = pd.Series(0.0, index=ranked.index)
    available_weight = pd.Series(0.0, index=ranked.index)
    for out_col, (source_col, direction, weight) in components.items():
        if source_col not in ranked.columns:
            ranked[out_col] = np.nan
            continue
        s = pd.to_numeric(ranked[source_col], errors="coerce")
        if direction == "low":
            bad = s.rank(pct=True, ascending=False, method="average")
        else:
            bad = s.rank(pct=True, ascending=True, method="average")
        ranked[out_col] = bad
        valid_comp = bad.notna()
        weighted_sum.loc[valid_comp] += weight * bad.loc[valid_comp]
        available_weight.loc[valid_comp] += weight
    ranked["bad_entity_score_0_100"] = (100 * weighted_sum / available_weight.replace(0, np.nan)).round(2)
    ranked["entity_label"] = entity_label
    ranked = ranked.sort_values(["bad_entity_score_0_100", "rows"], ascending=[False, False]).reset_index(drop=True)
    ranked["bad_entity_rank"] = np.arange(1, len(ranked) + 1)
    ranked["bad_entity_percentile"] = (100 * (1 - (ranked["bad_entity_rank"] - 1) / max(len(ranked), 1))).round(2)
    ranked["bad_entity_candidate_flag"] = ranked["bad_entity_rank"] <= max(1, int(np.ceil(0.10 * len(ranked))))
    # Ranking reliability is reported, not used to hide entities. This prevents a cell seen in only
    # one short route segment from looking equally certain as a cell observed repeatedly.
    ranked["rank_reliability"] = np.select(
        [(ranked["sessions"] >= 3) & (ranked["rows"] >= 100), (ranked["sessions"] >= 2) & (ranked["rows"] >= 50)],
        ["HIGH", "MEDIUM"], default="LOW",
    )
    return ranked

cell_rank = rank_bad_entities(lte_dl, "serving_cell_key", "cell_key", CELL_RANK_MIN_ROWS)
pci_rank = rank_bad_entities(lte_dl, "serving_pci", "pci_only_reuse_caution", CELL_RANK_MIN_ROWS)

# Add identity/context columns to cell ranking.
if not cell_rank.empty:
    cell_identity = (
        lte_dl[lte_dl["serving_cell_key"].notna()]
        .groupby("serving_cell_key", dropna=False)
        .agg(
            serving_pci=("serving_pci", _mode_or_nan),
            serving_eci=("serving_eci", _mode_or_nan),
            serving_earfcn=("serving_earfcn", _mode_or_nan),
            serving_band=("serving_band", _mode_or_nan),
        ).reset_index()
    )
    cell_rank = cell_rank.merge(cell_identity, on="serving_cell_key", how="left")

save_table(cell_rank, "worst_performing_cells_ranked.csv", category="rca")
save_table(pci_rank, "worst_performing_pci_ranked.csv", category="rca")

# RCA-friendly JSON for the top cells/PCIs.
def _json_safe_records(frame: pd.DataFrame, n: int):
    if frame.empty:
        return []
    part = frame.head(n).copy().replace({np.nan: None})
    return part.to_dict(orient="records")

with open(RCA_HANDOFF_DIR / "worst_performing_cells_rca_handoff.json", "w", encoding="utf-8") as f:
    _worst_cells_records = _json_safe_records(cell_rank, BAD_CELL_TOP_N)
    json.dump(_worst_cells_records, f, ensure_ascii=False, indent=2, default=str)
from ran_anomaly.mongo_writer import write_json_to_mongo
write_json_to_mongo("worst_performing_cells_rca_handoff", _worst_cells_records)
with open(RCA_HANDOFF_DIR / "worst_performing_pci_rca_handoff.json", "w", encoding="utf-8") as f:
    _worst_pci_records = _json_safe_records(pci_rank, BAD_PCI_TOP_N)
    json.dump(_worst_pci_records, f, ensure_ascii=False, indent=2, default=str)
write_json_to_mongo("worst_performing_pci_rca_handoff", _worst_pci_records)

# Plot the highest-ranked cells. This is a ranking aid, not a root-cause conclusion.
if not cell_rank.empty:
    top = cell_rank.head(min(BAD_CELL_TOP_N, 20)).sort_values("bad_entity_score_0_100")
    plt.figure(figsize=(12, max(5, 0.35 * len(top))))
    labels = top["serving_cell_key"].astype(str)
    plt.barh(labels, top["bad_entity_score_0_100"])
    plt.xlabel("Data-driven bad-cell score (0-100; higher = worse)")
    plt.ylabel("Serving cell key")
    plt.title("Worst-performing LTE cells — multi-KPI percentile ranking")
    save_current_plot("14b_worst_performing_cells_ranked.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=top["bad_entity_score_0_100"],
            y=labels,
            orientation='h'
        )])
        fig.update_layout(
            template='plotly_white',
            title="Worst-performing LTE cells — multi-KPI percentile ranking",
            xaxis_title="Data-driven bad-cell score (0-100; higher = worse)",
            yaxis_title="Serving cell key",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        fig.write_html(str(PLOTS_DIR / "14b_worst_performing_cells_ranked.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

print("Ranked cells:", len(cell_rank), "| Ranked PCI-only groups:", len(pci_rank))
display(cell_rank.head(25))

# =========================
