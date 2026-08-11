"""
Stage 14: reduced ml anomaly logic
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 4622-4924). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 24. Reduced ML anomaly logic: production models vs validation/context models
# =========================

actual_ml = pd.to_numeric(ml_audit[TARGET_COL], errors="coerce")
actual_log_ml = np.log1p(actual_ml)

# Only these predictive models participate in final ML anomaly decisions.
MODEL_COLUMNS = {
    "hgb_resource": "expected_tp_ml_hgb_resource_q50",
    "hgb_temporal": "expected_tp_ml_hgb_temporal_q50",
    "q75_resource": "expected_tp_ml_q75_resource",
    # LSTM is validation/context only but receives residual diagnostics.
    "lstm_q50": "expected_tp_ml_lstm_q50",
}

residual_threshold_rows = []
for model_key, expected_col in MODEL_COLUMNS.items():
    expected = pd.to_numeric(ml_audit.get(expected_col, np.nan), errors="coerce")
    ml_audit[f"ml_{model_key}_gap_mbps"] = expected - actual_ml
    ml_audit[f"ml_{model_key}_ratio"] = actual_ml / expected.replace(0, np.nan)
    ml_audit[f"ml_{model_key}_log_residual"] = actual_log_ml - np.log1p(expected)
    valid_resid = ml_audit[f"ml_{model_key}_log_residual"].dropna()
    residual_threshold_rows.append({
        "model": model_key, "valid_rows": len(valid_resid),
        "residual_q10": valid_resid.quantile(0.10) if len(valid_resid) else np.nan,
        "residual_q05": valid_resid.quantile(0.05) if len(valid_resid) else np.nan,
        "residual_q01": valid_resid.quantile(0.01) if len(valid_resid) else np.nan,
    })
    ml_audit[f"ml_{model_key}_residual_percentile"] = ml_audit[f"ml_{model_key}_log_residual"].rank(pct=True, method="average")

ml_residual_thresholds = pd.DataFrame(residual_threshold_rows)
save_table(ml_residual_thresholds, "ml_residual_thresholds_oof.csv", category="anomaly")
threshold_lookup = ml_residual_thresholds.set_index("model").to_dict("index")

ml_audit["ml_resource_expected_tp"] = ml_audit[["expected_tp_ml_q75_resource", "expected_tp_ml_hgb_resource_q50"]].median(axis=1, skipna=True)
ml_audit["ml_temporal_expected_tp"] = ml_audit[["expected_tp_ml_hgb_temporal_q50", "expected_tp_ml_lstm_q50"]].median(axis=1, skipna=True)
# Production-only expected reference excludes LSTM.
ml_audit["ml_best_expected_tp"] = ml_audit[["expected_tp_ml_q75_resource", "expected_tp_ml_hgb_resource_q50", "expected_tp_ml_hgb_temporal_q50"]].max(axis=1, skipna=True)
ml_audit["ml_best_gap_mbps"] = ml_audit["ml_best_expected_tp"] - actual_ml
ml_audit["ml_best_ratio"] = actual_ml / ml_audit["ml_best_expected_tp"].replace(0, np.nan)
ml_audit["ml_low_expected_context_flag"] = ml_audit["ml_best_expected_tp"] < ML_LOW_EXPECTED_CONTEXT_MBPS

rb_reliable = ml_audit.get("rb_usage_evidence_reliable_flag", pd.Series(False, index=ml_audit.index)).fillna(False).astype(bool)
rb_medium_high = ml_audit.get("rb_medium_or_high_usage_flag", pd.Series(True, index=ml_audit.index)).fillna(False).astype(bool)
rb_final_gate = (~rb_reliable) | rb_medium_high

ratio_gates = {
    "q75_resource": ML_Q75_RESOURCE_RATIO_GATE,
    "hgb_resource": ML_HGB_RATIO_GATE,
    "hgb_temporal": ML_LSTM_RATIO_GATE,
    "lstm_q50": ML_LSTM_RATIO_GATE,
}

for model_key, ratio_gate in ratio_gates.items():
    expected = pd.to_numeric(ml_audit[MODEL_COLUMNS[model_key]], errors="coerce")
    gap = ml_audit[f"ml_{model_key}_gap_mbps"]
    ratio = ml_audit[f"ml_{model_key}_ratio"]
    residual = ml_audit[f"ml_{model_key}_log_residual"]
    q05 = threshold_lookup[model_key]["residual_q05"]
    q01 = threshold_lookup[model_key]["residual_q01"]
    valid = expected.notna() & residual.notna()
    magnitude = valid & (expected >= ML_MIN_EXPECTED_TP_MBPS) & rb_final_gate & (ratio <= ratio_gate) & (gap >= ML_MIN_GAP_MBPS)
    residual_tail = valid & (residual <= q05)
    strict = magnitude & residual_tail
    severe = strict & (residual <= q01) & (actual_ml <= VERY_LOW_TP_MBPS) & (gap >= 30.0)
    ml_audit[f"ml_{model_key}_magnitude_flag"] = magnitude
    ml_audit[f"ml_{model_key}_residual_evidence_flag"] = residual_tail
    ml_audit[f"ml_{model_key}_underperformance_flag"] = strict
    ml_audit[f"ml_{model_key}_severe_underperformance_flag"] = severe

# Production families. Q75+HGB resource are correlated and count as ONE resource family.
ml_audit["ml_resource_family_flag"] = (
    ml_audit["ml_q75_resource_underperformance_flag"] | ml_audit["ml_hgb_resource_underperformance_flag"]
)
ml_audit["ml_temporal_family_flag"] = ml_audit["ml_hgb_temporal_underperformance_flag"]

# -------------------------
# Cross-fitted IsolationForest — validation/context only
# -------------------------
iforest_feature_cols = [
    TARGET_COL, "expected_tp_ml_hgb_resource_q50", "expected_tp_ml_hgb_temporal_q50",
    "expected_tp_ml_q75_resource", "expected_tp_ml_lstm_q50",
    "ml_hgb_resource_gap_mbps", "ml_hgb_resource_ratio", "ml_hgb_resource_log_residual",
    "ml_hgb_temporal_gap_mbps", "ml_hgb_temporal_ratio", "ml_hgb_temporal_log_residual",
    "ml_q75_resource_gap_mbps", "ml_q75_resource_ratio", "ml_q75_resource_log_residual",
    "ml_lstm_q50_gap_mbps", "ml_lstm_q50_ratio", "ml_lstm_q50_log_residual",
    "lte_rsrp", "lte_rsrq", "lte_sinr", "lte_bler", "lte_cqi", "lte_mcs", "rb_usage_value", "carrier_count",
]
iforest_feature_cols = [c for c in iforest_feature_cols if c in ml_audit.columns]
iforest_raw = np.zeros(len(ml_audit), dtype=bool)
iforest_decision = np.full(len(ml_audit), np.nan, dtype=float)

if ML_SKIP_TRAINING:
    _if_art = joblib.load(MODEL_ARTIFACT_DIR / "isolation_forest_context_only.joblib")
    iforest_preprocessor = _if_art["preprocessor"]
    iforest_model = _if_art["model"]
    X_if = iforest_preprocessor.transform(ml_audit[iforest_feature_cols].replace([np.inf, -np.inf], np.nan))
    iforest_raw = iforest_model.predict(X_if) == -1
    iforest_decision = iforest_model.decision_function(X_if)
    print("Inference mode: loaded saved IsolationForest model.")
else:
    for plan in outer_fold_plan:
        train_idx = np.asarray(plan["train_idx"], dtype=int)
        valid_idx = np.asarray(plan["valid_idx"], dtype=int)
        prep = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
        X_train_if = prep.fit_transform(ml_audit.iloc[train_idx][iforest_feature_cols].replace([np.inf, -np.inf], np.nan))
        X_valid_if = prep.transform(ml_audit.iloc[valid_idx][iforest_feature_cols].replace([np.inf, -np.inf], np.nan))
        model_if = IsolationForest(n_estimators=400, contamination=ML_IFOREST_CONTAMINATION, random_state=ML_RANDOM_SEED + int(plan["fold"]), n_jobs=-1)
        with threadpool_limits(limits=1):
            model_if.fit(X_train_if)
            iforest_raw[valid_idx] = model_if.predict(X_valid_if) == -1
            iforest_decision[valid_idx] = model_if.decision_function(X_valid_if)

    iforest_preprocessor = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    X_iforest_all = iforest_preprocessor.fit_transform(ml_audit[iforest_feature_cols].replace([np.inf, -np.inf], np.nan))
    iforest_model = IsolationForest(n_estimators=400, contamination=ML_IFOREST_CONTAMINATION, random_state=ML_RANDOM_SEED, n_jobs=-1)
    with threadpool_limits(limits=1):
        iforest_model.fit(X_iforest_all)

ml_audit["ml_iforest_raw_flag"] = iforest_raw
ml_audit["ml_iforest_anomaly_strength"] = np.clip(-iforest_decision, 0, None)
ml_audit["ml_iforest_context_flag"] = (
    ml_audit["ml_iforest_raw_flag"] & (ml_audit["ml_best_gap_mbps"] > 0)
    & ((actual_ml < LOW_TP_FIXED_MBPS) | (ml_audit["ml_best_ratio"] <= 0.70))
)
ml_audit["ml_iforest_confirmed_underperformance_flag"] = (
    ml_audit["ml_iforest_context_flag"] & (ml_audit["ml_best_expected_tp"] >= ML_MIN_EXPECTED_TP_MBPS)
    & (ml_audit["ml_best_gap_mbps"] >= ML_MIN_GAP_MBPS) & (ml_audit["ml_best_ratio"] <= ML_IFOREST_RATIO_GATE) & rb_final_gate
)


def model_evidence_score(frame, model_key, ratio_gate):
    ratio = frame[f"ml_{model_key}_ratio"]
    gap = frame[f"ml_{model_key}_gap_mbps"]
    percentile = frame[f"ml_{model_key}_residual_percentile"]
    expected = frame[MODEL_COLUMNS[model_key]]
    ratio_sev = np.clip((ratio_gate - ratio) / max(ratio_gate, 1e-6), 0, 1)
    gap_sev = np.clip((gap - ML_MIN_GAP_MBPS) / (80.0 - ML_MIN_GAP_MBPS), 0, 1)
    tail_sev = np.clip((0.10 - percentile) / 0.10, 0, 1)
    return (0.35*ratio_sev + 0.35*gap_sev + 0.30*tail_sev).where((expected >= ML_LOW_EXPECTED_CONTEXT_MBPS) & (gap > 0), 0).fillna(0)

ml_audit["ml_q75_resource_evidence_0_1"] = model_evidence_score(ml_audit, "q75_resource", ML_Q75_RESOURCE_RATIO_GATE)
ml_audit["ml_hgb_resource_evidence_0_1"] = model_evidence_score(ml_audit, "hgb_resource", ML_HGB_RATIO_GATE)
ml_audit["ml_hgb_temporal_evidence_0_1"] = model_evidence_score(ml_audit, "hgb_temporal", ML_LSTM_RATIO_GATE)
ml_audit["ml_lstm_evidence_0_1"] = model_evidence_score(ml_audit, "lstm_q50", ML_LSTM_RATIO_GATE)

iforest_strength = ml_audit["ml_iforest_anomaly_strength"].fillna(0)
if iforest_strength.max() > 0:
    iforest_strength = iforest_strength / max(float(iforest_strength.quantile(0.99)), 1e-6)
ml_audit["ml_iforest_evidence_0_1"] = np.clip(iforest_strength, 0, 1).where(ml_audit["ml_iforest_confirmed_underperformance_flag"], 0)

# Production evidence only. LSTM and IsolationForest are exported as context validation.
ml_audit["ml_resource_family_evidence_0_1"] = pd.concat([
    ML_RELIABILITY_Q75_RESOURCE * ml_audit["ml_q75_resource_evidence_0_1"],
    ML_RELIABILITY_HGB_RESOURCE * ml_audit["ml_hgb_resource_evidence_0_1"],
], axis=1).max(axis=1)
ml_audit["ml_temporal_family_evidence_0_1"] = ML_RELIABILITY_HGB_TEMPORAL * ml_audit["ml_hgb_temporal_evidence_0_1"]
ml_audit["ml_lstm_context_evidence_0_1"] = ML_RELIABILITY_LSTM * ml_audit["ml_lstm_evidence_0_1"]
ml_audit["ml_iforest_context_evidence_0_1"] = ML_RELIABILITY_IFOREST * ml_audit["ml_iforest_evidence_0_1"]
ml_audit["ml_capability_family_flag"] = False  # compatibility alias; capability models removed
ml_audit["ml_capability_family_evidence_0_1"] = 0.0
ml_audit["ml_residual_space_family_flag"] = False  # context-only, never a final production family
ml_audit["ml_residual_family_evidence_0_1"] = 0.0

family_flag_cols = ["ml_resource_family_flag", "ml_temporal_family_flag"]
ml_audit["ml_independent_trigger_count"] = ml_audit[family_flag_cols].fillna(False).astype(int).sum(axis=1)

confidence_product = (1 - ml_audit["ml_resource_family_evidence_0_1"].clip(0,1)) * (1 - ml_audit["ml_temporal_family_evidence_0_1"].clip(0,1))
ml_confidence = 1 - confidence_product
ml_confidence += 0.08 * (ml_audit["ml_independent_trigger_count"] >= 2).astype(float)
ml_confidence += 0.03 * rb_medium_high.astype(float)
ml_audit["ml_detection_confidence_0_100"] = (100 * np.clip(ml_confidence, 0, 1)).round(2)


def family_impact(expected, include_drop=False):
    exp = pd.to_numeric(expected, errors="coerce")
    gap = exp - actual_ml
    ratio = actual_ml / exp.replace(0, np.nan)
    low = np.clip((20.0 - actual_ml) / 20.0, 0, 1)
    gap_sev = np.clip(gap / 80.0, 0, 1).fillna(0)
    ratio_sev = np.clip((0.60 - ratio) / 0.60, 0, 1).fillna(0)
    score = 0.25*low + 0.40*gap_sev + 0.35*ratio_sev
    return score.clip(0,1)

res_impact = family_impact(ml_audit["ml_resource_expected_tp"])
tmp_impact = family_impact(ml_audit["expected_tp_ml_hgb_temporal_q50"])
family_impacts = pd.concat([
    res_impact.where(ml_audit["ml_resource_family_flag"], 0),
    tmp_impact.where(ml_audit["ml_temporal_family_flag"], 0),
], axis=1)
ml_audit["ml_impact_score_0_100"] = (100 * family_impacts.max(axis=1)).round(2)
ml_audit["ml_anomaly_score_raw_0_100"] = np.clip(0.55*ml_audit["ml_impact_score_0_100"] + 0.45*ml_audit["ml_detection_confidence_0_100"], 0, 100).round(2)

severe_production_any = pd.concat([
    ml_audit["ml_q75_resource_severe_underperformance_flag"],
    ml_audit["ml_hgb_resource_severe_underperformance_flag"],
    ml_audit["ml_hgb_temporal_severe_underperformance_flag"],
], axis=1).any(axis=1)
max_prod_evidence = pd.concat([
    ml_audit["ml_resource_family_evidence_0_1"], ml_audit["ml_temporal_family_evidence_0_1"]
], axis=1).max(axis=1)
strong_single_family = (
    (ml_audit["ml_independent_trigger_count"] == 1)
    & severe_production_any
    & (ml_audit["ml_detection_confidence_0_100"] >= max(80.0, ML_SINGLE_FAMILY_MIN_CONFIDENCE))
    & (ml_audit["ml_best_gap_mbps"] >= max(40.0, ML_SINGLE_FAMILY_MIN_GAP_MBPS))
    & (ml_audit["ml_best_ratio"] <= min(0.20, ML_SINGLE_FAMILY_MAX_RATIO))
    & (max_prod_evidence >= max(0.80, ML_SINGLE_FAMILY_MIN_EVIDENCE))
)
ml_audit["ml_anomaly_candidate_flag"] = ml_audit[family_flag_cols].any(axis=1)
ml_audit["ml_single_family_strong_flag"] = strong_single_family
ml_audit["is_ml_throughput_anomaly"] = (ml_audit["ml_independent_trigger_count"] >= 2) | strong_single_family
ml_audit["ml_requires_human_review_flag"] = ml_audit["is_ml_throughput_anomaly"]

catastrophic_ml = (
    (actual_ml <= CATASTROPHIC_ACTUAL_TP_MBPS) & (ml_audit["ml_best_expected_tp"] >= CATASTROPHIC_EXPECTED_TP_MBPS)
    & rb_medium_high & (ml_audit["ml_independent_trigger_count"] >= 2)
)
ml_priority = ml_audit["ml_anomaly_score_raw_0_100"].where(ml_audit["is_ml_throughput_anomaly"], 0.0).copy()
high = ml_priority > 85.0
ml_priority.loc[high] = 85.0 + (ML_NON_CATASTROPHIC_CAP - 85.0) * (1.0 - np.exp(-(ml_priority.loc[high] - 85.0)/10.0))
ml_priority = ml_priority.where(~catastrophic_ml, 100.0)
ml_audit["ml_anomaly_score_0_100"] = np.round(np.clip(ml_priority, 0, 100), 2)
ml_audit["ml_catastrophic_flag"] = catastrophic_ml

conditions = [
    ml_audit["ml_q75_resource_severe_underperformance_flag"],
    ml_audit["ml_q75_resource_underperformance_flag"],
    ml_audit["ml_hgb_temporal_severe_underperformance_flag"],
    ml_audit["ml_hgb_temporal_underperformance_flag"],
    ml_audit["ml_hgb_resource_severe_underperformance_flag"],
    ml_audit["ml_hgb_resource_underperformance_flag"],
]
choices = [
    "ml_severe_quantile_p75_resource_underperformance", "ml_quantile_p75_resource_underperformance",
    "ml_severe_hgb_strict_causal_temporal_underperformance", "ml_hgb_strict_causal_temporal_underperformance",
    "ml_severe_hgb_resource_conditioned_underperformance", "ml_hgb_resource_conditioned_underperformance",
]
ml_audit["ml_anomaly_type"] = np.select(conditions, choices, default="normal")

# LSTM/IsolationForest validation context is never used as the primary final anomaly type.
ml_audit["ml_validation_context_flags"] = np.select(
    [ml_audit["ml_lstm_q50_underperformance_flag"] & ml_audit["ml_iforest_confirmed_underperformance_flag"],
     ml_audit["ml_lstm_q50_underperformance_flag"], ml_audit["ml_iforest_confirmed_underperformance_flag"]],
    ["lstm_and_iforest_context_agree", "lstm_context_support", "iforest_context_support"], default="none"
)

ml_audit["ml_anomaly_severity"] = np.select(
    [~ml_audit["is_ml_throughput_anomaly"], ml_audit["ml_anomaly_score_0_100"] >= ML_SCORE_CRITICAL,
     ml_audit["ml_anomaly_score_0_100"] >= ML_SCORE_HIGH, ml_audit["ml_anomaly_score_0_100"] >= ML_SCORE_MEDIUM],
    ["Normal", "Critical", "High", "Medium"], default="Low"
)


def bool_col(df, col):
    if col not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0).ne(0)
    return s.astype("string").str.strip().str.lower().isin({"true","1","yes","y","t"})

method_specs = [
    ("ml_q75_resource_underperformance_flag", "PRODUCTION_resource_trigger"),
    ("ml_hgb_resource_underperformance_flag", "PRODUCTION_resource_trigger"),
    ("ml_hgb_temporal_underperformance_flag", "PRODUCTION_temporal_trigger"),
    ("ml_lstm_q50_underperformance_flag", "CONTEXT_validation_only"),
    ("ml_iforest_raw_flag", "CONTEXT_unsupervised_validation_only"),
    ("ml_iforest_confirmed_underperformance_flag", "CONTEXT_validation_only"),
    ("ml_anomaly_candidate_flag", "candidate_gate"),
    ("is_ml_throughput_anomaly", "strict_production_final_gate"),
]
ml_anomaly_method_summary = pd.DataFrame([{
    "method_or_case": col, "flag_role": role,
    "flagged_rows": int(bool_col(ml_audit, col).sum()), "flagged_pct": float(bool_col(ml_audit, col).mean()*100),
} for col,role in method_specs])
save_table(ml_anomaly_method_summary, "ml_anomaly_method_summary.csv", category="anomaly")

flagged_ml = ml_audit[ml_audit["is_ml_throughput_anomaly"]].copy()
ml_anomaly_score_qc = pd.DataFrame([{
    "rows": len(ml_audit), "ml_candidate_rows": int(ml_audit["ml_anomaly_candidate_flag"].sum()),
    "ml_final_anomaly_rows": len(flagged_ml), "ml_final_anomaly_pct": float(len(flagged_ml)/max(len(ml_audit),1)*100),
    "single_family_final_rows": int((ml_audit["is_ml_throughput_anomaly"] & (ml_audit["ml_independent_trigger_count"]==1)).sum()),
    "lstm_oof_available_pct": float(ml_audit["expected_tp_ml_lstm_q50"].notna().mean()*100),
    "lstm_context_overlap_with_final_pct": float((ml_audit["ml_lstm_q50_underperformance_flag"] & ml_audit["is_ml_throughput_anomaly"]).sum()/max(int(ml_audit["is_ml_throughput_anomaly"].sum()),1)*100),
    "iforest_context_overlap_with_final_pct": float((ml_audit["ml_iforest_confirmed_underperformance_flag"] & ml_audit["is_ml_throughput_anomaly"]).sum()/max(int(ml_audit["is_ml_throughput_anomaly"].sum()),1)*100),
}])
save_table(ml_anomaly_score_qc, "ml_anomaly_score_distribution_qc.csv", category="anomaly")

ml_model_agreement_summary = ml_audit.groupby("ml_independent_trigger_count", dropna=False).agg(
    rows=(TARGET_COL,"size"), final_ml_anomalies=("is_ml_throughput_anomaly","sum"),
    median_ml_score=("ml_anomaly_score_0_100","median"), median_confidence=("ml_detection_confidence_0_100","median"),
    median_actual_tp=(TARGET_COL,"median"),
).reset_index()
save_table(ml_model_agreement_summary, "ml_model_agreement_summary.csv", category="anomaly")

# Validation-only context file explicitly contains LSTM/IF evidence; final JSON excludes these fields.
ml_review_context = ml_audit[(~ml_audit["is_ml_throughput_anomaly"]) & (
    ml_audit["ml_anomaly_candidate_flag"] | ml_audit["ml_lstm_q50_underperformance_flag"] |
    ml_audit["ml_iforest_context_flag"] | ml_audit["ml_low_expected_context_flag"]
)].copy()
save_table(ml_review_context, "lte_throughput_ml_review_context_not_final.csv", category="anomaly")
save_parquet_or_csv(ml_audit, "lte_dl_anomaly_audit_table_with_ml", category="anomaly")
save_table(flagged_ml, "lte_throughput_anomalies_ml.csv", category="anomaly")

display(ml_anomaly_method_summary)
display(ml_anomaly_score_qc.round(4))
display(ml_model_agreement_summary.round(3))

# =========================
