"""
Stage 13: execute lstm crossfit
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 4584-4621). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 23. Execute LSTM-Q50 cross-fitting and save temporal diagnostics
# =========================

lstm_temporal_features = ml_feature_views["lstm_temporal"]["numeric"]

if ML_RUN_LSTM_Q50 and TORCH_AVAILABLE and len(lstm_temporal_features) > 0:
    start_time_lstm = time.time()
    lstm_oof_log, lstm_fold_metrics, lstm_training_history, lstm_comparison = cross_fit_lstm_q50(
        ml_audit,
        lstm_temporal_features,
        LSTM_OOF_N_SPLITS,
    )
    ml_audit["expected_tp_ml_lstm_q50"] = np.where(
        np.isfinite(lstm_oof_log), np.maximum(np.expm1(lstm_oof_log), 0), np.nan
    )
    print(f"LSTM cross-fitting finished in {(time.time() - start_time_lstm) / 60:.2f} minutes")
else:
    lstm_oof_log = np.full(len(ml_audit), np.nan)
    lstm_fold_metrics = pd.DataFrame()
    lstm_training_history = pd.DataFrame()
    lstm_comparison = {}
    ml_audit["expected_tp_ml_lstm_q50"] = np.nan

save_table(lstm_fold_metrics, "ml_lstm_q50_fold_evaluation_report.csv", category="anomaly")
save_table(lstm_training_history, "ml_lstm_q50_training_history.csv", category="anomaly")

# Append LSTM metrics to the unified OOF report.
all_oof_model_metrics = pd.concat([
    boosted_fold_metrics,
    lstm_fold_metrics,
], ignore_index=True, sort=False)
save_table(all_oof_model_metrics, "ml_model_evaluation_report.csv", category="anomaly")

lstm_valid_pct = float(ml_audit["expected_tp_ml_lstm_q50"].notna().mean() * 100)
print(f"LSTM OOF prediction availability: {lstm_valid_pct:.2f}% of rows")
display(lstm_fold_metrics.round(4))

# =========================
