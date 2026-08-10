"""
Stage 16: fusion layer
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 5103-5396). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 26. Row-level statistical–ML–LSTM fusion — strict final RCA decision layer
# =========================

if "source_index" not in lte_dl.columns or "source_index" not in ml_audit.columns:
    raise KeyError("source_index is required for safe statistical–ML fusion")

ml_fusion_cols = [c for c in ml_audit.columns if c.startswith("ml_") or c.startswith("expected_tp_ml_") or c == "is_ml_throughput_anomaly"]
ml_fusion_export = ml_audit[["source_index"] + ml_fusion_cols].drop_duplicates("source_index")
fused = lte_dl.merge(ml_fusion_export, on="source_index", how="left", validate="one_to_one")


def bool_col(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return frame[name].fillna(False).astype(bool)
    return pd.Series(False, index=frame.index)

# -------------------------
# Statistical evidence
# -------------------------
stat_score = pd.to_numeric(fused.get("anomaly_score_0_100", 0), errors="coerce").fillna(0)
stat_raw_score = pd.to_numeric(fused.get("anomaly_score_raw_0_100", stat_score), errors="coerce").fillna(stat_score)
stat_handoff = bool_col(fused, "rca_handoff_flag")
stat_reliable_p75 = bool_col(fused, "underperform_vs_p75_flag") | bool_col(fused, "underperform_vs_rb_p75_flag")
stat_rb_efficiency = bool_col(fused, "low_rb_efficiency_high_rb_flag")
stat_ca = bool_col(fused, "ca_underperformance_flag")
stat_radio = bool_col(fused, "radio_limited_degradation_flag")
stat_temporal = bool_col(fused, "rolling_drop_flag") | bool_col(fused, "sudden_drop_flag")
stat_sustained = bool_col(fused, "rolling_sustained_degradation_flag")
stat_low_only = bool_col(fused, "low_tp_family_flag") & ~(stat_reliable_p75 | stat_rb_efficiency | stat_ca | stat_radio | stat_temporal | stat_sustained)

stat_reliability = np.select(
    [stat_reliable_p75 | stat_rb_efficiency | stat_ca, stat_radio, stat_temporal, stat_sustained, stat_low_only],
    [1.00, 0.92, 0.90, 0.82, 0.55],
    default=0.65,
)
stat_strength = np.clip(stat_raw_score / 100.0, 0, 1)
fused["fused_statistical_strength_0_1"] = stat_strength
fused["fused_statistical_reliability_0_1"] = stat_reliability
fused["fused_statistical_evidence_0_1"] = stat_strength * stat_reliability

# -------------------------
# ML evidence by independent family
# -------------------------
ml_score = pd.to_numeric(fused.get("ml_anomaly_score_0_100", 0), errors="coerce").fillna(0)
ml_raw_score = pd.to_numeric(fused.get("ml_anomaly_score_raw_0_100", ml_score), errors="coerce").fillna(ml_score)
ml_final = bool_col(fused, "is_ml_throughput_anomaly")

# Production ML confidence uses ONLY resource + strict-causal temporal families.
# LSTM and IsolationForest are validation/context and cannot inflate final confidence.
res_ev = pd.to_numeric(fused.get("ml_resource_family_evidence_0_1", 0), errors="coerce").fillna(0).clip(0, 1)
tmp_ev = pd.to_numeric(fused.get("ml_temporal_family_evidence_0_1", 0), errors="coerce").fillna(0).clip(0, 1)
ml_family_confidence = 1 - (1-res_ev) * (1-tmp_ev)
fused["fused_ml_strength_0_1"] = np.clip(ml_raw_score / 100.0, 0, 1)
fused["fused_ml_reliability_0_1"] = np.maximum(res_ev, tmp_ev)
fused["fused_ml_evidence_0_1"] = ml_family_confidence

fused["fused_stat_ml_agreement_flag"] = stat_handoff & ml_final
ml_family_count = pd.to_numeric(fused.get("ml_independent_trigger_count", 0), errors="coerce").fillna(0)

# Detection confidence combines statistical evidence with FOUR independent ML families.
stat_evidence = fused["fused_statistical_evidence_0_1"]
confidence = 1 - (1 - 0.80 * stat_evidence) * (1 - 0.90 * ml_family_confidence)
confidence += 0.08 * fused["fused_stat_ml_agreement_flag"].astype(float)
confidence += 0.04 * bool_col(fused, "rb_medium_or_high_usage_flag").astype(float)
confidence += 0.04 * (ml_family_count >= 2).astype(float)
fused["fused_detection_confidence_0_100"] = (100 * np.clip(confidence, 0, 1)).round(2)

# -------------------------
# Objective-aware expected-throughput references
# -------------------------
def robust_median(frame: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    existing = [c for c in cols if c in frame.columns]
    return frame[existing].median(axis=1, skipna=True) if existing else pd.Series(np.nan, index=frame.index)

fused["fused_capability_expected_tp"] = robust_median(fused, [
    "expected_tp_radio_p75",
])
fused["fused_resource_expected_tp"] = robust_median(fused, [
    "expected_tp_rb_conditioned_p75", "expected_tp_ml_q75_resource", "expected_tp_ml_hgb_resource_q50",
])
fused["fused_temporal_expected_tp"] = robust_median(fused, [
    "expected_tp_ml_hgb_temporal_q50", "rolling_median_tp",
])

actual_fused = pd.to_numeric(fused[TARGET_COL], errors="coerce")

def impact_from_expected(expected: pd.Series, include_drop: bool = False) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    gap = expected - actual_fused
    ratio = actual_fused / expected.replace(0, np.nan)
    low = np.clip((20.0 - actual_fused) / 20.0, 0, 1)
    gap_comp = np.clip(gap / 80.0, 0, 1).fillna(0)
    ratio_comp = np.clip((0.60 - ratio) / 0.60, 0, 1).fillna(0)
    impact = 0.25 * low + 0.40 * gap_comp + 0.35 * ratio_comp
    if include_drop:
        rolling_gap = pd.to_numeric(fused.get("rolling_tp_gap", 0), errors="coerce").fillna(0)
        prev_gap = pd.to_numeric(fused.get("tp_drop_from_prev", 0), errors="coerce").fillna(0)
        drop = np.clip(pd.concat([rolling_gap, prev_gap], axis=1).max(axis=1) / 40.0, 0, 1)
        impact = 0.80 * impact + 0.20 * drop
    return impact.clip(0, 1), gap, ratio, low

cap_impact, cap_gap, cap_ratio, _ = impact_from_expected(fused["fused_capability_expected_tp"])
res_impact, res_gap, res_ratio, _ = impact_from_expected(fused["fused_resource_expected_tp"])
tmp_impact, tmp_gap, tmp_ratio, _ = impact_from_expected(fused["fused_temporal_expected_tp"], include_drop=True)

cap_active = stat_reliable_p75 | bool_col(fused, "ml_capability_family_flag")
res_active = stat_rb_efficiency | stat_ca | bool_col(fused, "underperform_vs_rb_p75_flag") | bool_col(fused, "ml_resource_family_flag")
tmp_active = stat_temporal | bool_col(fused, "ml_temporal_family_flag")
radio_active = stat_radio

# Radio-limited impact is based on actual degradation and persistence, not an inflated
# capability maximum.
low_tp_component = np.clip((20.0 - actual_fused) / 20.0, 0, 1)
persistence_proxy = (0.70 * stat_sustained.astype(float) + 0.30 * bool_col(fused, "bad_session_sample_flag").astype(float)).clip(0, 1)
radio_impact = (0.70 * low_tp_component + 0.30 * persistence_proxy).clip(0, 1)

family_impact_df = pd.DataFrame({
    "capability": cap_impact.where(cap_active, 0),
    "resource": res_impact.where(res_active, 0),
    "temporal": tmp_impact.where(tmp_active, 0),
    "radio": radio_impact.where(radio_active, 0),
}, index=fused.index)
fused["fused_dominant_impact_family"] = family_impact_df.idxmax(axis=1)
fused["fused_impact_score_0_100"] = (100 * family_impact_df.max(axis=1)).round(2)

# Backward-compatible expected/gap fields now refer to the DOMINANT impact family rather
# than the maximum expected value across unrelated models.
fused["fused_best_expected_tp"] = np.select(
    [
        fused["fused_dominant_impact_family"].eq("capability"),
        fused["fused_dominant_impact_family"].eq("resource"),
        fused["fused_dominant_impact_family"].eq("temporal"),
    ],
    [fused["fused_capability_expected_tp"], fused["fused_resource_expected_tp"], fused["fused_temporal_expected_tp"]],
    default=np.nan,
)
fused["fused_expected_gap_mbps"] = fused["fused_best_expected_tp"] - actual_fused
fused["fused_actual_expected_ratio"] = actual_fused / pd.Series(fused["fused_best_expected_tp"], index=fused.index).replace(0, np.nan)

fused_priority_raw = (
    FUSION_IMPACT_WEIGHT * fused["fused_impact_score_0_100"]
    + FUSION_CONFIDENCE_WEIGHT * fused["fused_detection_confidence_0_100"]
)
fused["final_rca_priority_raw_0_100"] = np.clip(fused_priority_raw, 0, 100).round(2)

# -------------------------
# Strict final keep rules
# -------------------------
rolling_gap = pd.to_numeric(fused.get("rolling_tp_gap", 0), errors="coerce").fillna(0)
prev_gap = pd.to_numeric(fused.get("tp_drop_from_prev", 0), errors="coerce").fillna(0)
drop_component = np.clip(pd.concat([rolling_gap, prev_gap], axis=1).max(axis=1) / 40.0, 0, 1)
very_low_tp = actual_fused <= VERY_LOW_TP_MBPS
rb_medium_high = bool_col(fused, "rb_medium_or_high_usage_flag")

catastrophic_fused = (
    (actual_fused <= CATASTROPHIC_ACTUAL_TP_MBPS)
    & (
        (fused["fused_capability_expected_tp"] >= CATASTROPHIC_EXPECTED_TP_MBPS)
        | (fused["fused_resource_expected_tp"] >= CATASTROPHIC_EXPECTED_TP_MBPS)
    )
    & (fused["fused_stat_ml_agreement_flag"] | (ml_family_count >= 2))
)

consensus_keep = stat_handoff & ml_final & (
    (fused["final_rca_priority_raw_0_100"] >= FUSION_CONSENSUS_MIN_SCORE) | catastrophic_fused
)

stat_expected_keep = (
    (stat_reliable_p75 | stat_rb_efficiency | stat_ca)
    & (fused["final_rca_priority_raw_0_100"] >= FUSION_STAT_EXPECTED_MIN_SCORE)
)
stat_radio_keep = (
    stat_radio
    & (stat_sustained | very_low_tp)
    & (fused["final_rca_priority_raw_0_100"] >= FUSION_STAT_RADIO_TEMPORAL_MIN_SCORE)
)
stat_temporal_keep = (
    stat_temporal
    & (drop_component >= 0.40)
    & (fused["final_rca_priority_raw_0_100"] >= FUSION_STAT_RADIO_TEMPORAL_MIN_SCORE)
)
stat_only_keep = stat_handoff & (~ml_final) & (stat_expected_keep | stat_radio_keep | stat_temporal_keep)

ml_severe_any = pd.concat([
    bool_col(fused, c) for c in [
        "ml_q75_resource_severe_underperformance_flag", "ml_hgb_resource_severe_underperformance_flag",
        "ml_hgb_temporal_severe_underperformance_flag",
    ]
], axis=1).any(axis=1)
ml_only_keep = (
    ml_final & (~stat_handoff)
    & (
        (
            fused["fused_detection_confidence_0_100"] >= FUSION_ML_ONLY_MIN_CONFIDENCE
        )
        & (
            fused["final_rca_priority_raw_0_100"] >= FUSION_ML_ONLY_MIN_SCORE
        )
        | ml_severe_any
    )
)

fused["fused_consensus_flag"] = consensus_keep
fused["fused_statistical_only_flag"] = stat_only_keep
fused["fused_ml_only_flag"] = ml_only_keep
fused["final_rca_handoff_flag"] = consensus_keep | stat_only_keep | ml_only_keep
fused["requires_human_review_flag"] = ml_only_keep
fused["human_review_reason"] = np.where(ml_only_keep, "strict_ml_only_anomaly_requires_supervised_verification", "not_required_by_ml_only_rule")

# Preserve continuous raw priority. Non-handoff rows get zero only in the handoff-facing
# score column; no minimum score is forced onto retained rows.
fused["fusion_selected_impact_confidence_score_0_100"] = fused["final_rca_priority_raw_0_100"]
fused["final_rca_priority_score_0_100"] = fused["final_rca_priority_raw_0_100"].where(fused["final_rca_handoff_flag"], 0.0)
fused["fused_catastrophic_flag"] = catastrophic_fused

# Diagnostic comparison methods only.
fused["fusion_naive_average_score_0_100"] = ((stat_score + ml_score) / 2.0).round(2)
fused["fusion_weighted_max_score_0_100"] = np.maximum(0.80 * stat_score, 0.90 * ml_score).round(2)

fused["impact_severity"] = np.select(
    [fused["fused_impact_score_0_100"] >= 80, fused["fused_impact_score_0_100"] >= 55, fused["fused_impact_score_0_100"] >= 30],
    ["Critical", "High", "Medium"], default="Low",
)
fused["detection_confidence"] = np.select(
    [fused["fused_detection_confidence_0_100"] >= 80, fused["fused_detection_confidence_0_100"] >= 60, fused["fused_detection_confidence_0_100"] >= 40],
    ["Very High", "High", "Medium"], default="Low",
)
fused["final_priority_severity"] = np.select(
    [
        ~fused["final_rca_handoff_flag"],
        catastrophic_fused | (fused["final_rca_priority_score_0_100"] >= FUSION_CRITICAL),
        fused["final_rca_priority_score_0_100"] >= FUSION_HIGH,
        fused["final_rca_priority_score_0_100"] >= FUSION_MEDIUM,
    ],
    ["Normal", "Critical", "High", "Medium"], default="Low",
)
fused["fusion_source"] = np.select(
    [consensus_keep, stat_only_keep, ml_only_keep],
    ["statistical_and_ml_consensus", "statistical_only_retained", "ml_only_retained"],
    default="not_handed_off",
)

save_parquet_or_csv(fused, "lte_throughput_anomalies_fused_row_level", category="anomaly")
fused_handoff_rows = fused[fused["final_rca_handoff_flag"]].copy()
save_table(fused_handoff_rows, "lte_throughput_anomalies_final_fused_row_level.csv", category="anomaly")

# Overlap diagnostics.
overlap_rows = []
for stat_name, stat_flag in [
    ("broad_statistical_candidate", bool_col(fused, "is_throughput_anomaly")),
    ("statistical_rca_handoff", stat_handoff),
    ("statistical_high_or_critical", fused.get("anomaly_severity", "Normal").isin(["High", "Critical"]) if "anomaly_severity" in fused.columns else pd.Series(False, index=fused.index)),
]:
    for stat_value in [False, True]:
        for ml_value in [False, True]:
            mask = (stat_flag == stat_value) & (ml_final == ml_value)
            overlap_rows.append({
                "statistical_definition": stat_name, "statistical_flag": stat_value,
                "ml_final_flag": ml_value, "rows": int(mask.sum()), "pct_all_rows": float(mask.mean() * 100),
            })
ml_vs_statistical_overlap = pd.DataFrame(overlap_rows)
save_table(ml_vs_statistical_overlap, "ml_vs_statistical_overlap_summary.csv", category="anomaly")

fusion_summary = (
    fused.groupby(["fusion_source", "final_priority_severity", "detection_confidence"], dropna=False)
    .agg(
        rows=(TARGET_COL, "size"), median_actual_tp=(TARGET_COL, "median"),
        median_final_priority=("final_rca_priority_score_0_100", "median"),
        median_raw_priority=("final_rca_priority_raw_0_100", "median"),
        median_impact=("fused_impact_score_0_100", "median"),
        median_confidence=("fused_detection_confidence_0_100", "median"),
    ).reset_index()
)
save_table(fusion_summary, "final_score_fusion_distribution_summary.csv", category="anomaly")

fusion_method_comparison = pd.DataFrame([{
    "method": col,
    "median_all_rows": fused[col].median(),
    "median_final_handoff_rows": fused.loc[fused["final_rca_handoff_flag"], col].median(),
    "p90_final_handoff_rows": fused.loc[fused["final_rca_handoff_flag"], col].quantile(0.90),
    "statistical_only_median": fused.loc[stat_only_keep, col].median(),
    "ml_only_median": fused.loc[ml_only_keep, col].median(),
    "consensus_median": fused.loc[consensus_keep, col].median(),
} for col in [
    "fusion_naive_average_score_0_100", "fusion_weighted_max_score_0_100",
    "fusion_selected_impact_confidence_score_0_100",
]])
save_table(fusion_method_comparison, "score_fusion_method_comparison.csv", category="anomaly")

display(ml_vs_statistical_overlap)
display(fusion_summary.round(3))
print("Final fused row handoff:", len(fused_handoff_rows), "rows")


# =========================
