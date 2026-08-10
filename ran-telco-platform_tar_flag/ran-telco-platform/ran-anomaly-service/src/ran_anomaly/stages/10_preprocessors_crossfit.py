"""
Stage 10: preprocessors crossfit
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 3737-4132). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 20. Preprocessors, cross-fitting, repeated validation, and ablation helpers
# =========================


def make_preprocessor(numeric_cols: Sequence[str], categorical_cols: Sequence[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])
    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(
            handle_unknown="ignore",
            min_frequency=5,
            sparse_output=False,
        )),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, list(numeric_cols)),
        ("cat", categorical_pipe, list(categorical_cols)),
    ], remainder="drop", verbose_feature_names_out=False)


def make_hgb_pipeline(view: Dict[str, List[str]]) -> Pipeline:
    return Pipeline([
        ("preprocess", make_preprocessor(view["numeric"], view["categorical"])),
        ("model", HistGradientBoostingRegressor(**HGB_COMMON_PARAMS)),
    ])


def make_q75_pipeline(view: Dict[str, List[str]]) -> Pipeline:
    return Pipeline([
        ("preprocess", make_preprocessor(view["numeric"], view["categorical"])),
        ("model", GradientBoostingRegressor(**Q75_GB_PARAMS)),
    ])


def regression_metrics(
    y_true_log: np.ndarray,
    y_pred_log: np.ndarray,
    model_name: str,
    split_name: str,
    fold: Optional[int] = None,
    alpha: Optional[float] = None,
) -> Dict[str, Any]:
    mask = np.isfinite(y_true_log) & np.isfinite(y_pred_log)
    yt_log = np.asarray(y_true_log)[mask]
    yp_log = np.asarray(y_pred_log)[mask]
    yt = np.expm1(yt_log)
    yp = np.maximum(np.expm1(yp_log), 0)
    row = {
        "model": model_name,
        "split": split_name,
        "fold": fold,
        "rows": int(mask.sum()),
        "mae_mbps": mean_absolute_error(yt, yp),
        "rmse_mbps": mean_squared_error(yt, yp) ** 0.5,
        "r2_mbps": r2_score(yt, yp),
        "mae_log": mean_absolute_error(yt_log, yp_log),
        "rmse_log": mean_squared_error(yt_log, yp_log) ** 0.5,
        "r2_log": r2_score(yt_log, yp_log),
    }
    if alpha is not None:
        row["pinball_loss_log"] = mean_pinball_loss(yt_log, yp_log, alpha=alpha)
        row["empirical_coverage"] = float((yt_log <= yp_log).mean())
        row["coverage_error_from_target"] = row["empirical_coverage"] - alpha
    return row


def cross_fit_sklearn(
    df: pd.DataFrame,
    view: Dict[str, List[str]],
    model_factory,
    model_name: str,
    n_splits: int,
    quantile_alpha: Optional[float] = None,
    train_reference_mask: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, pd.DataFrame, Dict[str, Any]]:
    feature_cols = view["numeric"] + view["categorical"]
    X = df[feature_cols].copy()
    y_log = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()

    oof_pred = np.full(len(df), np.nan, dtype=float)
    metrics, fold_models = [], []
    comparison_bundle = {}
    splitter = GroupKFold(n_splits=n_splits)

    for fold, (train_idx, valid_idx) in enumerate(splitter.split(X, y_log, groups=groups), start=1):
        fit_idx = train_idx
        if train_reference_mask is not None:
            fit_idx = train_idx[np.asarray(train_reference_mask, dtype=bool)[train_idx]]
            if len(fit_idx) < max(100, int(0.50 * len(train_idx))):
                fit_idx = train_idx
        pipeline = model_factory(view)
        pipeline.fit(X.iloc[fit_idx], y_log[fit_idx])
        pred_train = pipeline.predict(X.iloc[fit_idx])
        pred_valid = pipeline.predict(X.iloc[valid_idx])
        oof_pred[valid_idx] = pred_valid

        metrics.append(regression_metrics(
            y_log[fit_idx], pred_train, model_name, "fold_reference_train", fold, quantile_alpha
        ))
        metrics.append(regression_metrics(
            y_log[valid_idx], pred_valid, model_name, "fold_validation", fold, quantile_alpha
        ))
        fold_models.append(pipeline)

        # Fold 1 is retained for transparent train-vs-held-out comparison plots.
        if fold == 1:
            comparison_bundle = {
                "pipeline": pipeline,
                "train_idx": fit_idx,
                "test_idx": valid_idx,
                "pred_train_log": pred_train,
                "pred_test_log": pred_valid,
                "feature_cols": feature_cols,
            }

    assert np.isfinite(oof_pred).all(), f"OOF predictions incomplete for {model_name}"
    return oof_pred, pd.DataFrame(metrics), comparison_bundle


def repeated_group_validation(
    df: pd.DataFrame,
    view: Dict[str, List[str]],
    model_factory,
    model_name: str,
    runs: int,
    test_size: float,
    quantile_alpha: Optional[float] = None,
    train_reference_mask: Optional[np.ndarray] = None,
) -> pd.DataFrame:
    feature_cols = view["numeric"] + view["categorical"]
    X = df[feature_cols].copy()
    y_log = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()
    rows = []
    for run in range(runs):
        splitter = GroupShuffleSplit(
            n_splits=1,
            test_size=test_size,
            random_state=ML_RANDOM_SEED + run,
        )
        train_idx, test_idx = next(splitter.split(X, y_log, groups=groups))
        fit_idx = train_idx
        if train_reference_mask is not None:
            fit_idx = train_idx[np.asarray(train_reference_mask, dtype=bool)[train_idx]]
            if len(fit_idx) < max(100, int(0.50 * len(train_idx))):
                fit_idx = train_idx
        model = model_factory(view)
        model.fit(X.iloc[fit_idx], y_log[fit_idx])
        pred = model.predict(X.iloc[test_idx])
        row = regression_metrics(
            y_log[test_idx], pred, model_name, "repeated_group_test", run + 1, quantile_alpha
        )
        row["train_sessions"] = int(pd.Series(groups[fit_idx]).nunique())
        row["test_sessions"] = int(pd.Series(groups[test_idx]).nunique())
        rows.append(row)
    return pd.DataFrame(rows)


def run_feature_ablation(df: pd.DataFrame, feature_views: Dict[str, Dict[str, List[str]]]) -> pd.DataFrame:
    """One held-out group split compares raw, augmented, resource, and cell-aware views."""
    y_log = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()
    split = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=ML_RANDOM_SEED)
    train_idx, test_idx = next(split.split(df, y_log, groups=groups))
    rows = []
    for view_name in ["capability", "capability_augmented", "resource", "cell_aware"]:
        view = feature_views[view_name]
        cols = view["numeric"] + view["categorical"]
        model = make_hgb_pipeline(view)
        model.fit(df.iloc[train_idx][cols], y_log[train_idx])
        pred = model.predict(df.iloc[test_idx][cols])
        row = regression_metrics(y_log[test_idx], pred, f"HGB_{view_name}", "ablation_test", 1)
        row["numeric_features"] = len(view["numeric"])
        row["categorical_features"] = len(view["categorical"])
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_repeated_metrics(repeated_df: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "mae_mbps", "rmse_mbps", "r2_mbps", "mae_log", "rmse_log", "r2_log",
        "pinball_loss_log", "empirical_coverage", "coverage_error_from_target",
    ]
    rows = []
    for model_name, group in repeated_df.groupby("model"):
        row = {"model": model_name, "runs": len(group)}
        for metric in metrics:
            if metric in group.columns and group[metric].notna().any():
                values = pd.to_numeric(group[metric], errors="coerce")
                row[f"{metric}_mean"] = values.mean()
                row[f"{metric}_std"] = values.std(ddof=1)
                row[f"{metric}_min"] = values.min()
                row[f"{metric}_max"] = values.max()
        rows.append(row)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Nested outer-fold reference filtering and quantile calibration helpers
# -----------------------------------------------------------------------------
def _safe_inner_group_splits(groups: np.ndarray, requested: int) -> int:
    n_groups = int(pd.Series(groups).nunique())
    if n_groups < 2:
        return 0
    return max(2, min(int(requested), n_groups))


def _inner_oof_predictions(
    df: pd.DataFrame,
    train_idx: np.ndarray,
    view: Dict[str, List[str]],
    model_factory,
    n_splits: int,
) -> np.ndarray:
    """OOF predictions only inside an outer-training population."""
    feature_cols = view["numeric"] + view["categorical"]
    X = df.iloc[train_idx][feature_cols].copy()
    y = np.log1p(pd.to_numeric(df.iloc[train_idx][TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df.iloc[train_idx][GROUP_COL].astype(str).to_numpy()
    splits = _safe_inner_group_splits(groups, n_splits)
    if splits < 2:
        return np.full(len(train_idx), np.nan)
    pred = np.full(len(train_idx), np.nan, dtype=float)
    splitter = GroupKFold(n_splits=splits)
    for inner_train_local, inner_valid_local in splitter.split(X, y, groups=groups):
        model = model_factory(view)
        model.fit(X.iloc[inner_train_local], y[inner_train_local])
        pred[inner_valid_local] = model.predict(X.iloc[inner_valid_local])
    return pred


def _derive_reference_and_q75_calibration_for_train(
    df: pd.DataFrame,
    train_idx: np.ndarray,
) -> Dict[str, Any]:
    """Derive robust-reference exclusions and Q75 corrections using outer-train only.

    This is intentionally nested: no outer-test session contributes to reference-row
    selection or quantile calibration.
    """
    y_train = np.log1p(pd.to_numeric(df.iloc[train_idx][TARGET_COL], errors="coerce")).to_numpy(dtype=float)

    resource_inner = _inner_oof_predictions(
        df, train_idx, ml_feature_views["resource"], make_hgb_pipeline,
        ML_REFERENCE_INNER_N_SPLITS,
    )
    q75_resource_inner = _inner_oof_predictions(
        df, train_idx, ml_feature_views["resource"], make_q75_pipeline,
        ML_REFERENCE_INNER_N_SPLITS,
    )

    valid_resource = np.isfinite(resource_inner)
    valid_q75_resource = np.isfinite(q75_resource_inner)
    resource_resid = y_train - resource_inner
    q75_resource_resid = y_train - q75_resource_inner

    resource_cut = np.nanquantile(resource_resid[valid_resource], ML_REFERENCE_REFIT_EXTREME_QUANTILE) if valid_resource.any() else -np.inf
    q75_resource_cut = np.nanquantile(q75_resource_resid[valid_q75_resource], ML_REFERENCE_REFIT_EXTREME_QUANTILE) if valid_q75_resource.any() else -np.inf
    keep_local = np.ones(len(train_idx), dtype=bool)
    if ML_RUN_ROBUST_REFERENCE_REFIT and ML_NESTED_REFERENCE_FILTERING:
        keep_local &= ~(valid_resource & (resource_resid <= resource_cut))
        keep_local &= ~(valid_q75_resource & (q75_resource_resid <= q75_resource_cut))
        if int(keep_local.sum()) < max(100, int(0.50 * len(train_idx))):
            keep_local[:] = True

    def quantile_correction(inner_pred: np.ndarray) -> float:
        valid = np.isfinite(inner_pred) & np.isfinite(y_train)
        if not valid.any() or not ML_CALIBRATE_Q75_WITH_INNER_OOF:
            return 0.0
        # Additive correction in log space so P(actual <= calibrated Q75) ~= 0.75.
        return float(np.nanquantile(y_train[valid] - inner_pred[valid], 0.75))

    return {
        "fit_idx": train_idx[keep_local],
        "reference_keep_local": keep_local,
        "resource_residual_cut": float(resource_cut),
        "q75_resource_residual_cut": float(q75_resource_cut),
        "q75_resource_correction_log": quantile_correction(q75_resource_inner),
    }


def build_nested_outer_fold_plan(df: pd.DataFrame, n_splits: int) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    y = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()
    splitter = GroupKFold(n_splits=n_splits)
    plans, summary = [], []
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(df, y, groups=groups), start=1):
        nested = _derive_reference_and_q75_calibration_for_train(df, train_idx)
        plan = {"fold": fold, "train_idx": train_idx, "valid_idx": valid_idx, **nested}
        plans.append(plan)
        summary.append({
            "fold": fold,
            "outer_train_rows": len(train_idx),
            "outer_test_rows": len(valid_idx),
            "reference_rows_kept": len(nested["fit_idx"]),
            "reference_rows_removed": len(train_idx) - len(nested["fit_idx"]),
            "reference_removed_pct": (len(train_idx) - len(nested["fit_idx"])) / max(len(train_idx), 1) * 100,
            "resource_residual_cut": nested["resource_residual_cut"],
            "q75_resource_residual_cut": nested["q75_resource_residual_cut"],
            "q75_resource_correction_log": nested["q75_resource_correction_log"],
        })
    return plans, pd.DataFrame(summary)


def cross_fit_sklearn_with_plan(
    df: pd.DataFrame,
    view: Dict[str, List[str]],
    model_factory,
    model_name: str,
    fold_plan: Sequence[Dict[str, Any]],
    quantile_alpha: Optional[float] = None,
    q75_correction_key: Optional[str] = None,
) -> Tuple[np.ndarray, pd.DataFrame, Dict[str, Any]]:
    feature_cols = view["numeric"] + view["categorical"]
    X = df[feature_cols].copy()
    y_log = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    oof = np.full(len(df), np.nan, dtype=float)
    metrics, comparison = [], {}
    for plan in fold_plan:
        fold = int(plan["fold"])
        fit_idx = np.asarray(plan["fit_idx"], dtype=int)
        valid_idx = np.asarray(plan["valid_idx"], dtype=int)
        model = model_factory(view)
        model.fit(X.iloc[fit_idx], y_log[fit_idx])
        pred_train = model.predict(X.iloc[fit_idx])
        pred_valid = model.predict(X.iloc[valid_idx])
        correction = float(plan.get(q75_correction_key, 0.0)) if q75_correction_key else 0.0
        pred_train = pred_train + correction
        pred_valid = pred_valid + correction
        oof[valid_idx] = pred_valid
        metrics.append(regression_metrics(y_log[fit_idx], pred_train, model_name, "fold_reference_train", fold, quantile_alpha))
        metrics.append(regression_metrics(y_log[valid_idx], pred_valid, model_name, "fold_validation", fold, quantile_alpha))
        if fold == 1:
            comparison = {
                "pipeline": model,
                "train_idx": fit_idx,
                "test_idx": valid_idx,
                "pred_train_log": pred_train,
                "pred_test_log": pred_valid,
                "feature_cols": feature_cols,
                "q75_correction_log": correction,
            }
    assert np.isfinite(oof).all(), f"OOF predictions incomplete for {model_name}"
    return oof, pd.DataFrame(metrics), comparison


def build_repeated_nested_plan(df: pd.DataFrame, runs: int, test_size: float) -> List[Dict[str, Any]]:
    y = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()
    plans = []
    for run in range(runs):
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=ML_RANDOM_SEED + run)
        train_idx, test_idx = next(splitter.split(df, y, groups=groups))
        nested = _derive_reference_and_q75_calibration_for_train(df, train_idx)
        plans.append({"fold": run + 1, "train_idx": train_idx, "valid_idx": test_idx, **nested})
    return plans


def repeated_group_validation_with_plan(
    df: pd.DataFrame,
    view: Dict[str, List[str]],
    model_factory,
    model_name: str,
    plans: Sequence[Dict[str, Any]],
    quantile_alpha: Optional[float] = None,
    q75_correction_key: Optional[str] = None,
) -> pd.DataFrame:
    cols = view["numeric"] + view["categorical"]
    X = df[cols].copy()
    y = np.log1p(pd.to_numeric(df[TARGET_COL], errors="coerce")).to_numpy(dtype=float)
    groups = df[GROUP_COL].astype(str).to_numpy()
    rows = []
    for plan in plans:
        fit_idx = np.asarray(plan["fit_idx"], dtype=int)
        test_idx = np.asarray(plan["valid_idx"], dtype=int)
        model = model_factory(view)
        model.fit(X.iloc[fit_idx], y[fit_idx])
        pred = model.predict(X.iloc[test_idx])
        if q75_correction_key:
            pred = pred + float(plan.get(q75_correction_key, 0.0))
        row = regression_metrics(y[test_idx], pred, model_name, "repeated_group_test", int(plan["fold"]), quantile_alpha)
        row["train_sessions"] = int(pd.Series(groups[fit_idx]).nunique())
        row["test_sessions"] = int(pd.Series(groups[test_idx]).nunique())
        rows.append(row)
    return pd.DataFrame(rows)

# =========================
