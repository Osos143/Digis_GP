"""
Inference-only stage: loads pre-trained model artifacts and generates predictions.
Replaces stages 11-13 when ML_SKIP_TRAINING is True.
"""

import joblib

ml_audit = ml_base.copy()

_INFERENCE_MODELS = [
    ("hgb_resource_q50.joblib", "resource", "expected_tp_ml_hgb_resource_q50", False),
    ("hgb_strict_causal_temporal_q50.joblib", "temporal_lag", "expected_tp_ml_hgb_temporal_q50", False),
    ("gb_resource_q75_calibrated_base.joblib", "resource", "expected_tp_ml_q75_resource", True),
]

for _fname, _vname, _col, _is_q75 in _INFERENCE_MODELS:
    _art = joblib.load(MODEL_ARTIFACT_DIR / _fname)
    _model = _art["model"]
    _view = _art["features"]
    _cols = _view["numeric"] + _view["categorical"]
    _pred = _model.predict(ml_audit[_cols].copy())
    if _is_q75:
        _pred = _pred + _art.get("q75_calibration_correction_log", 0.0)
    ml_audit[_col] = np.maximum(np.expm1(_pred), 0)
    print(f"  Loaded {_fname} -> {_col}")

outer_fold_plan = []
final_reference_train_mask = np.ones(len(ml_audit), dtype=bool)
hgb_resource_comparison = hgb_temporal_comparison = q75_resource_comparison = {}
boosted_fold_metrics = ml_repeated_validation = ml_repeated_validation_summary = pd.DataFrame()
ml_feature_ablation = pd.DataFrame()
lstm_oof_log = np.full(len(ml_audit), np.nan)
lstm_fold_metrics = pd.DataFrame()
lstm_training_history = pd.DataFrame()
lstm_comparison = {}
ml_audit["expected_tp_ml_lstm_q50"] = np.nan

y_log_all = np.log1p(pd.to_numeric(ml_audit[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
ml_q75_resource_decile_calibration = pd.DataFrame()

print("Inference mode: loaded 3 production models and generated predictions.")
print("Reduced causal predictive model set completed (inference).")
