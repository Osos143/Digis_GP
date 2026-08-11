"""
Stage 09: feature construction
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 3363-3736). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 19. Leakage-safe feature construction and feature-view audits
# =========================

ML_EXCLUDE_EXACT = {
    "source_index", "id", "timestamp", "date", TARGET_COL,
    "LTE.LTE_Data_KPI.Agg_Throughput_DL",
    "LTE.DownlinkMeasurements.Throughput_DL",
    "Throughput.Physical_DL",
    "Throughput.HTTP_DL",
    "Activity.Throughput",
    "LTE - PrimaryCell - PCell_Throughput",
    "LTE - SecondaryCell 1 - SCell1_Throughput",
}

ML_EXCLUDE_PATTERNS = [
    r"throughput", r"expected", r"p75", r"anomaly", r"score", r"severity",
    r"underperform", r"low_tp_", r"rolling_", r"prev_tp", r"tp_drop",
    r"tp_ratio", r"log_residual", r"rca", r"candidate", r"handoff",
    r"remote ip", r"remote address", r"private ip", r"public ip", r"source ports",
    r"_count_pm\d+s",  # symmetric ± event windows are forbidden in causal forecasting
]


def make_ml_working_table(df: pd.DataFrame) -> pd.DataFrame:
    """Create only target-safe helper features for ML and sequence modeling."""
    out = df.copy()

    # Cyclical hour representation is more meaningful than treating 23 and 0 as far apart.
    if "hour" in out.columns:
        hour_num = pd.to_numeric(out["hour"], errors="coerce")
        out["ml_hour_sin"] = np.sin(2 * np.pi * hour_num / 24.0)
        out["ml_hour_cos"] = np.cos(2 * np.pi * hour_num / 24.0)

    # Some aggregate-CA RB denominators underestimate available RB and produce >100%.
    if "rb_utilization_pct" in out.columns:
        out["rb_utilization_pct_clipped"] = (
            pd.to_numeric(out["rb_utilization_pct"], errors="coerce")
            .clip(lower=0, upper=100)
        )

    if "rb_demand_confidence" in out.columns:
        out["rb_demand_confidence_ml"] = out["rb_demand_confidence"].astype(str)
        if "rb_usage_bucket" in out.columns:
            below_med = out["rb_usage_bucket"].astype(str).eq("below_median_rb_usage")
            out.loc[below_med, "rb_demand_confidence_ml"] = "below_median_or_uncertain"
        out["rb_demand_confidence_ml"] = out["rb_demand_confidence_ml"].replace({
            "unknown": "unknown_or_not_reliable",
        })

    # CAUSAL event features only: counts at/before the target sample.
    # Symmetric *_count_pmXs fields are offline RCA context and are banned from predictors.
    event_count_cols = [
        "measurement_report_event_count_prev5s",
        "handover_execution_count_prev5s",
        "handover_failure_count_prev10s",
        "rach_attempt_count_prev10s",
        "rach_failure_count_prev10s",
        "ca_activation_change_count_prev10s",
        "failure_other_count_prev10s",
    ]
    for col in event_count_cols:
        if col in out.columns:
            values = pd.to_numeric(out[col], errors="coerce").clip(lower=0)
            cap = values.quantile(0.99)
            if pd.notna(cap):
                values = values.clip(upper=cap)
            out[f"ml_log1p_{col}"] = np.log1p(values)

    return out


def add_past_only_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal lag/trend features for the boosted-tree temporal benchmark.

    Every throughput lag is shifted within session before rolling, so the current target is
    never present in the current row's predictors. These features intentionally define a
    forecasting objective and are kept out of capability/resource models.
    """
    out = df.copy()
    sort_cols = [GROUP_COL] + ([TIME_COL] if TIME_COL in out.columns else [])
    out = out.sort_values(sort_cols).copy()
    group = out.groupby(GROUP_COL, sort=False, group_keys=False)

    tp_log = np.log1p(pd.to_numeric(out[TARGET_COL], errors="coerce"))
    for lag in [1, 2, 3, 5, 10]:
        out[f"ml_tp_log_lag_{lag}"] = group[TARGET_COL].shift(lag).pipe(lambda x: np.log1p(pd.to_numeric(x, errors="coerce")))

    out["ml_tp_log_past_median_5"] = group[TARGET_COL].transform(
        lambda s: np.log1p(pd.to_numeric(s, errors="coerce")).shift(1).rolling(5, min_periods=2).median()
    )
    out["ml_tp_log_past_mean_10"] = group[TARGET_COL].transform(
        lambda s: np.log1p(pd.to_numeric(s, errors="coerce")).shift(1).rolling(10, min_periods=3).mean()
    )
    out["ml_tp_log_past_slope_5"] = group[TARGET_COL].transform(
        lambda s: np.log1p(pd.to_numeric(s, errors="coerce")).shift(1).diff(4) / 4.0
    )

    for source_col, short in [
        ("lte_rsrp", "rsrp"), ("lte_sinr", "sinr"), ("rb_usage_value", "rb"),
        ("lte_bler", "bler"), ("lte_cqi", "cqi"),
    ]:
        if source_col in out.columns:
            values = pd.to_numeric(out[source_col], errors="coerce")
            out[f"ml_{short}_lag_1"] = values.groupby(out[GROUP_COL], sort=False).shift(1)
            out[f"ml_{short}_past_mean_5"] = values.groupby(out[GROUP_COL], sort=False).transform(
                lambda s: s.shift(1).rolling(5, min_periods=2).mean()
            )

    out["ml_temporal_history_count"] = group.cumcount().clip(upper=20)
    return out.sort_index()


def _existing(df: pd.DataFrame, columns: Sequence[str]) -> List[str]:
    return [c for c in columns if c in df.columns]


def _drop_leakage_and_constants(
    df: pd.DataFrame,
    columns: Sequence[str],
    view_name: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    kept, audit = [], []
    for col in dict.fromkeys(columns):
        reason = "kept"
        keep = True
        lower = str(col).lower()
        if col not in df.columns:
            keep, reason = False, "missing"
        elif col in ML_EXCLUDE_EXACT:
            keep, reason = False, "exact leakage/id exclusion"
        elif any(re.search(pattern, lower) for pattern in ML_EXCLUDE_PATTERNS):
            keep, reason = False, "pattern leakage/post-anomaly exclusion"
        elif df[col].nunique(dropna=True) <= 1:
            keep, reason = False, "constant or single-value feature"
        if keep:
            kept.append(col)
        audit.append({
            "view": view_name,
            "column": col,
            "kept_for_ml": keep,
            "reason": reason,
            "dtype": str(df[col].dtype) if col in df.columns else "missing",
            "non_null_pct": float(df[col].notna().mean() * 100) if col in df.columns else np.nan,
            "unique_values": int(df[col].nunique(dropna=True)) if col in df.columns else 0,
        })
    return kept, audit


def build_ml_feature_views(df: pd.DataFrame) -> Tuple[Dict[str, Dict[str, List[str]]], pd.DataFrame]:
    """Build pure/contextual capability, resource, temporal, cell-aware, and LSTM views."""
    capability_numeric = [
        "ml_hour_sin", "ml_hour_cos", "session_elapsed_seconds",
        "speed", "location_accuracy", "altitude", "distance_from_prev_m",
        "lte_rsrp", "lte_rsrq", "lte_sinr", "lte_rssi",
        "carrier_count", "lte_agg_bandwidth_dl", "lte_bandwidth_dl",
        "scell1_rsrp", "scell1_rsrq", "scell1_sinr",
        "neighbor_count", "best_neighbor_rsrp", "strong_neighbor_count",
        "serving_minus_best_neighbor_rsrp", "neighbor_pci_count",
        "ml_log1p_measurement_report_event_count_prev5s",
        "ml_log1p_handover_execution_count_prev5s",
        "ml_log1p_handover_failure_count_prev10s",
        "ml_log1p_rach_attempt_count_prev10s",
        "ml_log1p_rach_failure_count_prev10s",
        "ml_log1p_ca_activation_change_count_prev10s",
        "ml_log1p_failure_other_count_prev10s",
    ]
    capability_bool = [
        "near_measurement_report_event_prev_flag", "near_handover_execution_prev_flag",
        "near_handover_failure_prev_flag", "near_rach_failure_prev_flag",
        "near_ca_activation_change_prev_flag", "near_failure_other_prev_flag",
        "download_activity_window_raw_flag", "download_analysis_window_flag",
        "inactive_download_context_flag", "ca_active_flag",
    ]
    capability_categorical = [
        "serving_earfcn", "serving_band", "id_test_type",
        "download_context_label", "ca_condition_label",
    ]

    resource_numeric = capability_numeric + [
        "lte_cqi", "lte_mcs", "lte_bler", "lte_rank",
        "lte_rb_count", "lte_agg_rb_dl", "rb_usage_value",
        "rb_utilization_pct_clipped", "estimated_available_rb",
        "scell1_cqi", "scell1_mcs", "scell1_bler", "scell1_rank", "scell1_rb_count",
    ]
    resource_bool = capability_bool + [
        "rb_low_usage_flag", "rb_medium_or_high_usage_flag", "rb_high_usage_flag",
    ]
    resource_categorical = capability_categorical + [
        "rb_usage_bucket", "rb_demand_confidence_ml", "rb_capacity_estimation_method",
    ]

    augmented_numeric = capability_numeric
    augmented_bool = capability_bool + [
        "poor_rsrp_flag", "poor_rsrq_flag", "poor_sinr_flag",
        "high_bler_flag", "low_cqi_flag", "low_rb_allocation_flag",
    ]
    augmented_categorical = capability_categorical + ["rsrp_bin", "rsrq_bin", "sinr_bin"]

    cell_aware_categorical = capability_categorical + ["serving_pci", "serving_eci"]

    # Pure capability intentionally excludes activity/event context so the model does not
    # learn to explain away a mobility/access disturbance that we later want to detect.
    pure_capability_numeric = [
        c for c in capability_numeric
        if not c.startswith("ml_log1p_")
    ]
    pure_capability_bool = [
        c for c in capability_bool
        if c not in {
            "near_measurement_report_event_prev_flag", "near_handover_execution_prev_flag",
            "near_handover_failure_prev_flag", "near_rach_failure_prev_flag",
            "near_ca_activation_change_prev_flag", "near_failure_other_prev_flag",
            "download_activity_window_raw_flag", "download_analysis_window_flag",
            "inactive_download_context_flag",
        }
    ]
    pure_capability_categorical = [
        c for c in capability_categorical if c != "download_context_label"
    ]

    # Temporal LSTM uses numeric technical features only. Past throughput is added later
    # as a lagged sequence channel, never as the current target row.
    lstm_numeric = [
        "ml_hour_sin", "ml_hour_cos", "session_elapsed_seconds", "speed",
        "distance_from_prev_m", "lte_rsrp", "lte_rsrq", "lte_sinr", "lte_rssi",
        "lte_cqi", "lte_mcs", "lte_bler", "lte_rank",
        "lte_rb_count", "lte_agg_rb_dl", "rb_usage_value", "rb_utilization_pct_clipped",
        "carrier_count", "lte_agg_bandwidth_dl", "lte_bandwidth_dl",
        "scell1_rsrp", "scell1_rsrq", "scell1_sinr", "scell1_cqi",
        "scell1_mcs", "scell1_bler", "scell1_rank", "scell1_rb_count",
        "best_neighbor_rsrp", "serving_minus_best_neighbor_rsrp",
        "ml_log1p_handover_execution_count_prev5s",
        "ml_log1p_handover_failure_count_prev10s",
        "ml_log1p_rach_failure_count_prev10s",
        "ml_log1p_ca_activation_change_count_prev10s",
    ]

    temporal_lag_numeric = resource_numeric + resource_bool + [
        "ml_tp_log_lag_1", "ml_tp_log_lag_2", "ml_tp_log_lag_3",
        "ml_tp_log_lag_5", "ml_tp_log_lag_10",
        "ml_tp_log_past_median_5", "ml_tp_log_past_mean_10", "ml_tp_log_past_slope_5",
        "ml_rsrp_lag_1", "ml_rsrp_past_mean_5",
        "ml_sinr_lag_1", "ml_sinr_past_mean_5",
        "ml_rb_lag_1", "ml_rb_past_mean_5",
        "ml_bler_lag_1", "ml_bler_past_mean_5",
        "ml_cqi_lag_1", "ml_cqi_past_mean_5",
        "ml_temporal_history_count",
    ]

    raw_views = {
        "capability_pure": {"numeric": pure_capability_numeric + pure_capability_bool, "categorical": pure_capability_categorical},
        "capability": {"numeric": capability_numeric + capability_bool, "categorical": capability_categorical},
        "resource": {"numeric": resource_numeric + resource_bool, "categorical": resource_categorical},
        "capability_augmented": {"numeric": augmented_numeric + augmented_bool, "categorical": augmented_categorical},
        "cell_aware": {"numeric": capability_numeric + capability_bool, "categorical": cell_aware_categorical},
        "temporal_lag": {"numeric": temporal_lag_numeric, "categorical": resource_categorical},
        "lstm_temporal": {"numeric": lstm_numeric, "categorical": []},
    }

    views, audit_records = {}, []
    for name, spec in raw_views.items():
        numeric, audit_num = _drop_leakage_and_constants(df, spec["numeric"], name)
        categorical, audit_cat = _drop_leakage_and_constants(df, spec["categorical"], name)
        views[name] = {"numeric": numeric, "categorical": categorical}
        audit_records.extend(audit_num + audit_cat)

    audit_df = pd.DataFrame(audit_records).drop_duplicates(["view", "column"], keep="last")
    return views, audit_df


# Reload the clean table so ML never consumes columns created by the statistical section.
ml_base = make_ml_working_table(load_pre_anomaly_feature_table())
ml_base = ml_base.loc[
    ml_base[TARGET_COL].notna() & (pd.to_numeric(ml_base[TARGET_COL], errors="coerce") >= 0)
].copy()
ml_base = ml_base.sort_values([GROUP_COL, TIME_COL] if TIME_COL in ml_base.columns else [GROUP_COL]).reset_index(drop=True)
ml_base = add_past_only_lag_features(ml_base)

if ML_MAX_ROWS_DEBUG is not None and len(ml_base) > ML_MAX_ROWS_DEBUG:
    # Debug sampling is session aware to preserve sequences and group validation.
    session_sizes = ml_base.groupby(GROUP_COL).size().sort_values(ascending=False)
    selected_sessions, rows = [], 0
    for sid, n_rows in session_sizes.items():
        selected_sessions.append(sid)
        rows += int(n_rows)
        if rows >= ML_MAX_ROWS_DEBUG:
            break
    ml_base = ml_base[ml_base[GROUP_COL].isin(selected_sessions)].copy().reset_index(drop=True)

ml_feature_views, ml_feature_audit = build_ml_feature_views(ml_base)

# Hard causal guard: no symmetric ± event-window column may enter any ML view.
for _view_name, _spec in ml_feature_views.items():
    _all = _spec["numeric"] + _spec["categorical"]
    _bad = [c for c in _all if "_count_pm" in c or (c.startswith("near_") and not c.endswith("_prev_flag") and "download" not in c and "ca_active" not in c)]
    if _bad:
        raise AssertionError(f"Non-causal symmetric event context leaked into {_view_name}: {_bad}")

# Final hard guard against direct target-like names in any tabular view.
for view_name, spec in ml_feature_views.items():
    for col in spec["numeric"] + spec["categorical"]:
        assert col != TARGET_COL, f"Target leaked into {view_name}: {col}"
        assert not any(re.search(p, str(col).lower()) for p in ML_EXCLUDE_PATTERNS), f"Leak-like feature in {view_name}: {col}"

save_table(ml_feature_audit, "ml_feature_leakage_audit.csv", category="anomaly")

feature_view_rows = []
for view_name, spec in ml_feature_views.items():
    for feature_type in ["numeric", "categorical"]:
        for col in spec[feature_type]:
            feature_view_rows.append({"view": view_name, "feature_type": feature_type, "column": col})
ml_feature_view_table = pd.DataFrame(feature_view_rows)
save_table(ml_feature_view_table, "ml_safe_feature_views.csv", category="anomaly")

# Backward-compatible flat safe list for the resource-conditioned view.
ml_safe_feature_list = ml_feature_view_table.loc[
    ml_feature_view_table["view"].eq("resource"), ["column", "feature_type"]
].drop_duplicates()
save_table(ml_safe_feature_list, "ml_safe_feature_list.csv", category="anomaly")

# Export explicit feature lists per objective so future reviewers know exactly which model
# consumed each feature view.
feature_file_map = {
    "capability_pure": "ml_capability_pure_feature_list.csv",
    "capability": "ml_capability_contextual_feature_list.csv",
    "resource": "ml_resource_feature_list.csv",
    "temporal_lag": "ml_temporal_hgb_feature_list.csv",
    "lstm_temporal": "ml_lstm_feature_list.csv",
    "cell_aware": "ml_cell_aware_ablation_feature_list.csv",
}
for view_name, filename in feature_file_map.items():
    part = ml_feature_view_table.loc[
        ml_feature_view_table["view"].eq(view_name), ["column", "feature_type"]
    ].drop_duplicates()
    save_table(part, filename, category="anomaly")

# Full-schema leakage audit: every column from the clean pre-anomaly table receives an
# explicit used/not-used decision, not only columns that appeared in curated candidate lists.
used_by = {}
for view_name, spec in ml_feature_views.items():
    for col in spec["numeric"] + spec["categorical"]:
        used_by.setdefault(col, []).append(view_name)
full_schema_rows = []
for col in ml_base.columns:
    lower = str(col).lower()
    direct_target_like = col in ML_EXCLUDE_EXACT or any(re.search(p, lower) for p in ML_EXCLUDE_PATTERNS)
    views_using = used_by.get(col, [])
    full_schema_rows.append({
        "column": col,
        "dtype": str(ml_base[col].dtype),
        "used_by_any_model": bool(views_using),
        "models_using_column": ";".join(sorted(views_using)),
        "decision": "USED" if views_using else "NOT_USED",
        "exclusion_reason": (
            "target/throughput/post-anomaly name guard" if (not views_using and direct_target_like)
            else "not selected for any model objective" if not views_using
            else "objective-safe curated feature"
        ),
        "target_or_post_anomaly_pattern_flag": bool(direct_target_like),
        "non_null_pct": float(ml_base[col].notna().mean() * 100),
        "unique_values": int(ml_base[col].nunique(dropna=True)),
    })
ml_full_schema_leakage_audit = pd.DataFrame(full_schema_rows)
save_table(ml_full_schema_leakage_audit, "ml_full_schema_leakage_audit.csv", category="anomaly")

print("ML rows:", len(ml_base))
print("Sessions:", ml_base[GROUP_COL].nunique())
for view_name, spec in ml_feature_views.items():
    print(f"{view_name}: {len(spec['numeric'])} numeric + {len(spec['categorical'])} categorical")
display(ml_feature_audit[~ml_feature_audit["kept_for_ml"]].head(30))
display(ml_feature_view_table.groupby(["view", "feature_type"]).size().rename("features").reset_index())


# =========================
