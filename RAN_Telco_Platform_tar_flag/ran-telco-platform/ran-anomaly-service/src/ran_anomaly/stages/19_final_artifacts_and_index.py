"""
Stage 19: final artifacts and index
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 6056-6121). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 29. Fit/save final future-inference artifacts and refreshed output index
# =========================

if ML_SAVE_FINAL_MODELS and not ML_SKIP_TRAINING:
    final_model_manifest = []
    final_fit_idx = np.where(final_reference_train_mask)[0]
    if len(final_fit_idx) < 100:
        final_fit_idx = np.arange(len(ml_audit))

    def fit_save_model(view_name, factory, filename, model_role, extra_metadata=None):
        view = ml_feature_views[view_name]
        cols = view["numeric"] + view["categorical"]
        model = factory(view)
        X = ml_audit.iloc[final_fit_idx][cols]
        y = np.log1p(pd.to_numeric(ml_audit.iloc[final_fit_idx][TARGET_COL], errors="coerce"))
        with threadpool_limits(limits=1):
            model.fit(X, y)
        path = MODEL_ARTIFACT_DIR / filename
        payload = {"model": model, "features": view, "target": TARGET_COL, "role": model_role}
        if extra_metadata:
            payload.update(extra_metadata)
        joblib.dump(payload, path)
        final_model_manifest.append({"artifact": filename, "role": model_role, "rows_fit": len(final_fit_idx), "feature_view": view_name})

    fit_save_model("temporal_lag", make_hgb_pipeline, "hgb_strict_causal_temporal_q50.joblib", "PRODUCTION")
    fit_save_model("resource", make_hgb_pipeline, "hgb_resource_q50.joblib", "PRODUCTION")
    q75_resource_calibration_correction_log = float(pd.to_numeric(
        nested_reference_summary.get("q75_resource_correction_log", pd.Series(dtype=float)), errors="coerce"
    ).median()) if len(nested_reference_summary) else 0.0
    if not np.isfinite(q75_resource_calibration_correction_log):
        q75_resource_calibration_correction_log = 0.0
    fit_save_model(
        "resource", make_q75_pipeline, "gb_resource_q75_calibrated_base.joblib", "PRODUCTION",
        extra_metadata={
            "q75_calibration_correction_log": q75_resource_calibration_correction_log,
            "prediction_transform": "expm1(raw_log_prediction + q75_calibration_correction_log)",
        },
    )

    # IsolationForest stays validation/context only.
    joblib.dump({"preprocessor": iforest_preprocessor, "model": iforest_model, "features": iforest_feature_cols, "role": "CONTEXT_VALIDATION_ONLY"}, MODEL_ARTIFACT_DIR / "isolation_forest_context_only.joblib")
    final_model_manifest.append({"artifact":"isolation_forest_context_only.joblib","role":"CONTEXT_VALIDATION_ONLY","rows_fit":len(ml_audit),"feature_view":"residual_space"})

    # LSTM final artifact, when available, remains validation/context only.
    if TORCH_AVAILABLE and 'lstm_final_model' in globals() and lstm_final_model is not None:
        lstm_path = MODEL_ARTIFACT_DIR / "lstm_q50_context_validation_only.pt"
        torch.save({"state_dict": lstm_final_model.state_dict(), "role":"CONTEXT_VALIDATION_ONLY", "sequence_length":LSTM_SEQUENCE_LENGTH}, lstm_path)
        final_model_manifest.append({"artifact":lstm_path.name,"role":"CONTEXT_VALIDATION_ONLY","rows_fit":len(ml_audit),"feature_view":"lstm_temporal"})

    final_model_manifest = pd.DataFrame(final_model_manifest)
    save_table(final_model_manifest, "ml_final_model_artifact_manifest.csv", category="key")
    display(final_model_manifest)

# Final output index focused on the production/RCA-facing artifacts.
final_output_index = []
for folder,label in [
    (PREPROCESSING_DIR,"preprocessing"),(ANOMALY_DIR,"anomaly_audit"),(PLOTS_DIR,"plots"),
    (RCA_HANDOFF_DIR,"final_rca_handoff"),(RCA_KEY_FILES_DIR,"key_review_files"),(RCA_CASE_PLOTS_DIR,"top_case_plots")
]:
    if folder.exists():
        for p in sorted(folder.glob('*')):
            if p.is_file(): final_output_index.append({"category":label,"file":p.name,"path":str(p)})
final_output_index = pd.DataFrame(final_output_index)
save_table(final_output_index, "final_output_file_index.csv", category="key")
print("Final optimized pipeline artifacts indexed:", len(final_output_index))
display(final_output_index.tail(100))
