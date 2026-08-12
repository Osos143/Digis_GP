"""
Stage 11: execute predictive models
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 4133-4300). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 21. Execute reduced final predictive model set
# =========================

ml_audit = ml_base.copy()
y_log_all = np.log1p(pd.to_numeric(ml_audit[TARGET_COL], errors="coerce")).to_numpy(dtype=float)

# One shared group-aware outer-fold plan ensures fair comparisons and no session leakage.
outer_fold_plan, nested_reference_summary = build_nested_outer_fold_plan(ml_audit, ML_OOF_N_SPLITS)
save_table(nested_reference_summary, "ml_nested_reference_refit_by_fold.csv", category="anomaly")

reference_refit_summary = pd.DataFrame([{
    "rows_total": len(ml_audit),
    "outer_folds": len(outer_fold_plan),
    "mean_reference_removed_pct": nested_reference_summary["reference_removed_pct"].mean(),
    "max_reference_removed_pct": nested_reference_summary["reference_removed_pct"].max(),
    "median_resource_residual_cut": nested_reference_summary["resource_residual_cut"].median(),
    "median_q75_resource_residual_cut": nested_reference_summary["q75_resource_residual_cut"].median(),
    "median_q75_resource_correction_log": nested_reference_summary["q75_resource_correction_log"].median(),
    "refit_enabled": ML_RUN_ROBUST_REFERENCE_REFIT,
    "nested_outer_fold_filtering": ML_NESTED_REFERENCE_FILTERING,
}])
save_table(reference_refit_summary, "ml_robust_reference_refit_summary.csv", category="anomaly")

import sys

# 1) Resource-conditioned HGB Q50/central predictor.
print("  -> Training HGB Resource Q50 model (5 folds)...", flush=True)
hgb_resource_oof_log, hgb_resource_fold_metrics, hgb_resource_comparison = cross_fit_sklearn_with_plan(
    ml_audit, ml_feature_views["resource"], make_hgb_pipeline,
    "HGB_resource_conditioned_Q50", outer_fold_plan,
)
ml_audit["expected_tp_ml_hgb_resource_q50"] = np.maximum(np.expm1(hgb_resource_oof_log), 0)

# 2) Calibrated resource-conditioned Q75 achievable-throughput reference.
print("  -> Training GradientBoosting Q75 model (5 folds)...", flush=True)
q75_resource_oof_log, q75_resource_fold_metrics, q75_resource_comparison = cross_fit_sklearn_with_plan(
    ml_audit, ml_feature_views["resource"], make_q75_pipeline,
    "GradientBoosting_resource_conditioned_Q75_calibrated", outer_fold_plan,
    quantile_alpha=0.75, q75_correction_key="q75_resource_correction_log",
)
ml_audit["expected_tp_ml_q75_resource"] = np.maximum(np.expm1(q75_resource_oof_log), 0)

# 3) Strongest causal predictor: past-only temporal HGB Q50.
print("  -> Training HGB Strict Causal Temporal Q50 model (5 folds)...", flush=True)
hgb_temporal_oof_log, hgb_temporal_fold_metrics, hgb_temporal_comparison = cross_fit_sklearn_with_plan(
    ml_audit, ml_feature_views["temporal_lag"], make_hgb_pipeline,
    "HGB_strict_causal_temporal_Q50", outer_fold_plan,
)
ml_audit["expected_tp_ml_hgb_temporal_q50"] = np.maximum(np.expm1(hgb_temporal_oof_log), 0)

boosted_fold_metrics = pd.concat([
    hgb_resource_fold_metrics, q75_resource_fold_metrics, hgb_temporal_fold_metrics,
], ignore_index=True)
save_table(boosted_fold_metrics, "ml_oof_fold_evaluation_report.csv", category="anomaly")

# Repeated held-out-session validation only for the reduced final predictive set.
repeated_plans = build_repeated_nested_plan(ml_audit, ML_REPEATED_GROUP_RUNS, ML_REPEATED_TEST_SIZE) if ML_RUN_REPEATED_VALIDATION else []
repeated_parts = []
if repeated_plans:
    repeated_parts.extend([
        repeated_group_validation_with_plan(
            ml_audit, ml_feature_views["resource"], make_hgb_pipeline,
            "HGB_resource_conditioned_Q50", repeated_plans,
        ),
        repeated_group_validation_with_plan(
            ml_audit, ml_feature_views["resource"], make_q75_pipeline,
            "GradientBoosting_resource_conditioned_Q75_calibrated", repeated_plans,
            quantile_alpha=0.75, q75_correction_key="q75_resource_correction_log",
        ),
        repeated_group_validation_with_plan(
            ml_audit, ml_feature_views["temporal_lag"], make_hgb_pipeline,
            "HGB_strict_causal_temporal_Q50", repeated_plans,
        ),
    ])
ml_repeated_validation = pd.concat(repeated_parts, ignore_index=True) if repeated_parts else pd.DataFrame()
save_table(ml_repeated_validation, "ml_repeated_group_validation_runs.csv", category="anomaly")
ml_repeated_validation_summary = summarize_repeated_metrics(ml_repeated_validation) if not ml_repeated_validation.empty else pd.DataFrame()
save_table(ml_repeated_validation_summary, "ml_repeated_group_validation_summary.csv", category="anomaly")

# Final notebook does not rerun broad feature ablation by default; the chosen model set is fixed.
ml_feature_ablation = pd.DataFrame()
save_table(ml_feature_ablation, "ml_feature_objective_ablation.csv", category="anomaly")


def build_q75_calibration_outputs(frame, pred_log, expected_col, prefix):
    global_metric = pd.DataFrame([regression_metrics(y_log_all, pred_log, prefix, "OOF_all_rows", None, 0.75)])
    condition_rows = []
    for condition_col in ["rb_usage_bucket", "ca_condition_label", "sinr_bin", "rsrp_bin", "serving_band", "serving_earfcn"]:
        if condition_col not in frame.columns:
            continue
        for value, idx_labels in frame.groupby(condition_col, dropna=False).groups.items():
            idx = np.asarray(list(idx_labels), dtype=int)
            if len(idx) < 30:
                continue
            actual_log = y_log_all[idx]
            p = pred_log[idx]
            coverage = float((actual_log <= p).mean())
            condition_rows.append({
                "condition": condition_col, "value": value, "rows": len(idx),
                "empirical_q75_coverage": coverage,
                "coverage_error_from_0_75": coverage - 0.75,
                "calibration_status": "REVIEW" if abs(coverage - 0.75) > 0.05 else "OK",
                "pinball_loss_log": mean_pinball_loss(actual_log, p, alpha=0.75),
                "median_actual_mbps": float(np.median(np.expm1(actual_log))),
                "median_q75_expected_mbps": float(np.median(np.expm1(p))),
            })
    condition_df = pd.DataFrame(condition_rows)
    decile_col = f"{prefix}_prediction_decile"
    decile_df = pd.DataFrame()
    try:
        frame[decile_col] = pd.qcut(frame[expected_col], q=10, duplicates="drop")
        decile_df = frame.groupby(decile_col, observed=True, dropna=False).agg(
            rows=(TARGET_COL, "size"), min_predicted_q75=(expected_col, "min"),
            median_predicted_q75=(expected_col, "median"), max_predicted_q75=(expected_col, "max"),
            median_actual=(TARGET_COL, "median"),
        ).reset_index()
        coverages = []
        for category in decile_df[decile_col]:
            mask = frame[decile_col].eq(category).to_numpy()
            coverages.append(float((y_log_all[mask] <= pred_log[mask]).mean()))
        decile_df["empirical_q75_coverage"] = coverages
        decile_df["coverage_error_from_0_75"] = decile_df["empirical_q75_coverage"] - 0.75
        decile_df["calibration_status"] = np.where(decile_df["coverage_error_from_0_75"].abs() > 0.05, "REVIEW", "OK")
    except Exception as exc:
        print("Q75 decile calibration skipped:", exc)
    return global_metric, condition_df, decile_df

q75_resource_global_metrics_df, ml_q75_resource_condition_calibration, ml_q75_resource_decile_calibration = build_q75_calibration_outputs(
    ml_audit, q75_resource_oof_log, "expected_tp_ml_q75_resource", "q75_resource"
)
save_table(q75_resource_global_metrics_df, "ml_q75_resource_global_calibration.csv", category="anomaly")
save_table(ml_q75_resource_condition_calibration, "ml_q75_resource_calibration_by_condition.csv", category="anomaly")
save_table(ml_q75_resource_decile_calibration, "ml_q75_resource_calibration_by_prediction_decile.csv", category="anomaly")

ml_audit["ml_q75_resource_below_hgb_resource_flag"] = (
    ml_audit["expected_tp_ml_q75_resource"] < ml_audit["expected_tp_ml_hgb_resource_q50"]
)
ml_q75_inversion_summary = pd.DataFrame([{
    "reference": "resource_conditioned",
    "rows": len(ml_audit),
    "q75_below_q50_rows": int(ml_audit["ml_q75_resource_below_hgb_resource_flag"].sum()),
    "q75_below_q50_pct": float(ml_audit["ml_q75_resource_below_hgb_resource_flag"].mean() * 100),
    "median_q75_minus_q50_mbps": float((ml_audit["expected_tp_ml_q75_resource"] - ml_audit["expected_tp_ml_hgb_resource_q50"]).median()),
}])
save_table(ml_q75_inversion_summary, "ml_q75_vs_hgb_inversion_summary.csv", category="anomaly")

# OOF-only reference mask for final future-inference artifact fitting.
initial_resource_log, _, _ = cross_fit_sklearn(
    ml_audit, ml_feature_views["resource"], make_hgb_pipeline,
    "HGB_resource_final_reference_mask", ML_OOF_N_SPLITS,
)
initial_q75_resource_log, _, _ = cross_fit_sklearn(
    ml_audit, ml_feature_views["resource"], make_q75_pipeline,
    "Q75_resource_final_reference_mask", ML_OOF_N_SPLITS, quantile_alpha=0.75,
)
resid_resource_final = y_log_all - initial_resource_log
resid_q75_resource_final = y_log_all - initial_q75_resource_log
resource_cut_final = np.nanquantile(resid_resource_final, ML_REFERENCE_REFIT_EXTREME_QUANTILE)
q75_resource_cut_final = np.nanquantile(resid_q75_resource_final, ML_REFERENCE_REFIT_EXTREME_QUANTILE)
final_reference_train_mask = ~((resid_resource_final <= resource_cut_final) | (resid_q75_resource_final <= q75_resource_cut_final))
if not ML_RUN_ROBUST_REFERENCE_REFIT:
    final_reference_train_mask[:] = True

print("Reduced causal predictive model set completed.")
display(reference_refit_summary.round(4))
display(boosted_fold_metrics.round(4))
display(ml_repeated_validation_summary.round(4))
display(q75_resource_global_metrics_df.round(4))
display(ml_q75_inversion_summary.round(4))



# =========================
