"""
Stage 06: rca handoff table
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 2559-3050). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 15. Build final RCA-ready anomaly handoff table
# =========================

# Canonical handoff columns expected by the next RCA module.
handoff_cols = [
    "source_index",
    "id",
    "timestamp",
    "date",
    "hour",
    "minute",
    "id_route_test_label",
    "id_location_label",
    "id_test_type",
    "session_elapsed_seconds",
    "sample_gap_seconds",
    "anomaly_analysis_window_flag",
    "download_activity_window_raw_flag",
    "download_analysis_window_flag",
    "inactive_download_context_flag",
    "download_context_label",
    "latitude",
    "longitude",
    "speed",
    "location_accuracy",
    "altitude",
    "distance_from_prev_m",
    "serving_pci",
    "serving_earfcn",
    "serving_band",
    "serving_eci",
    "serving_enodebid",
    "serving_lci",
    "actual_lte_dl_throughput",
    "expected_tp_p75",
    "expected_tp_source_level",
    "expected_tp_group_n",
    "expected_tp_group_cols",
    "expected_tp_p75_ci_low",
    "expected_tp_p75_ci_high",
    "expected_tp_p75_ci_width",
    "expected_tp_reliable_flag",
    "expected_tp_confidence",
    "expected_tp_radio_p75",
    "expected_tp_radio_source_level",
    "expected_tp_radio_group_n",
    "expected_tp_radio_group_cols",
    "expected_tp_radio_p75_ci_low",
    "expected_tp_radio_p75_ci_high",
    "expected_tp_radio_p75_ci_width",
    "throughput_gap_p75_ci_low",
    "throughput_ratio_p75_ci_low",
    "expected_tp_rb_conditioned_p75",
    "expected_tp_rb_source_level",
    "expected_tp_rb_group_n",
    "expected_tp_rb_group_cols",
    "expected_tp_rb_p75_ci_low",
    "expected_tp_rb_p75_ci_high",
    "expected_tp_rb_p75_ci_width",
    "expected_tp_rb_reliable_flag",
    "expected_tp_rb_confidence",
    "throughput_gap_rb_p75",
    "throughput_ratio_rb_p75",
    "log_residual_rb_p75",
    "throughput_gap_rb_p75_ci_low",
    "throughput_ratio_rb_p75_ci_low",
    "underperform_vs_rb_p75_context_flag",
    "underperform_vs_rb_p75_flag",
    "independent_trigger_count",
    "trigger_family_flags",
    "score_base_from_strongest_trigger",
    "score_continuous_magnitude",
    "score_independent_trigger_bonus",
    "score_evidence_bonus",
    "throughput_gap_p75",
    "throughput_ratio_p75",
    "log_residual_p75",
    "rolling_median_tp",
    "rolling_p25_tp",
    "rolling_count",
    "rolling_tp_gap",
    "rolling_tp_ratio",
    "prev_tp",
    "tp_drop_from_prev",
    "tp_ratio_to_prev",
    "session_rows",
    "session_mean_tp",
    "session_median_tp",
    "session_p10_tp_threshold",
    "session_p25_tp",
    "session_low_tp_ratio",
    "anomaly_score_0_100",
    "anomaly_severity",
    "anomaly_type",
    "anomaly_type_flags",
    "anomaly_method_count",
    "context_flag_count",
    "weak_low_rb_only_candidate_flag",
    "rca_handoff_flag",
    "lte_rsrp",
    "lte_rsrq",
    "lte_sinr",
    "lte_rssi",
    "lte_cqi",
    "lte_mcs",
    "lte_bler",
    "lte_rank",
    "lte_rb_count",
    "lte_agg_rb_dl",
    "lte_agg_rb_dl_bin",
    "lte_bandwidth_dl",
    "lte_agg_bandwidth_dl",
    "rb_usage_evidence_reliable_flag",
    "reliable_rb_columns",
    "rb_reference_column",
    "rb_usage_value",
    "rb_usage_bucket",
    "rb_demand_confidence",
    "estimated_available_rb",
    "rb_capacity_estimation_method",
    "rb_utilization_pct",
    "rb_low_usage_threshold",
    "rb_medium_usage_threshold",
    "rb_high_usage_threshold",
    "rb_low_usage_flag",
    "rb_medium_or_high_usage_flag",
    "rb_high_usage_flag",
    "throughput_per_rb",
    "rb_efficiency_p10_threshold",
    "low_rb_efficiency_high_rb_flag",
    "rb_efficiency_family_flag",
    "low_tp_low_rb_flag",
    "p75_demand_confirmed_flag",
    "p75_underperformance_demand_unknown_context_flag",
    "score_floor_from_rules",
    "score_low_rb_cap_applied_flag",
    "catastrophic_score_allowed_flag",
    "carrier_count",
    "ca_condition_label",
    "scell1_rsrp",
    "scell1_rsrq",
    "scell1_sinr",
    "scell1_cqi",
    "scell1_mcs",
    "scell1_bler",
    "scell1_rb_count",
    "neighbor_count",
    "best_neighbor_rsrp",
    "strong_neighbor_count",
    "serving_minus_best_neighbor_rsrp",
    "poor_rsrp_flag",
    "poor_rsrq_flag",
    "poor_sinr_flag",
    "high_bler_flag",
    "low_cqi_flag",
    "low_rb_allocation_flag",
    "low_tp_fixed_flag",
    "low_tp_global_p10_flag",
    "low_tp_session_p10_flag",
    "low_tp_robust_z_flag",
    "low_tp_iqr_flag",
    "rolling_drop_flag",
    "rolling_bad_window_flag",
    "rolling_sustained_degradation_flag",
    "bad_session_flag",
    "bad_session_sample_flag",
    "sudden_drop_flag",
    "underperform_vs_p75_context_flag",
    "underperform_vs_p75_flag",
    "unexpected_underperformance_flag",
    "radio_limited_degradation_flag",
    "ca_active_flag",
    "ca_underperformance_flag",
    "event_related_degradation_flag",
    "rach_failure_direct_flag",
    "rach_result",
    "rach_reason",
    "rach_latency",
]

# Add event-window columns dynamically.
for name, window in EVENT_WINDOWS_SECONDS.items():
    handoff_cols.extend([f"{name}_count_pm{window}s", f"near_{name}_flag"])

# Add all trigger-family and score columns so reviewers can compare methods.
if "trigger_family_cols" in globals():
    handoff_cols.extend(trigger_family_cols)
handoff_cols.extend(score_cols)
if "score_component_cols" in globals():
    handoff_cols.extend(score_component_cols)

# Important: score_cols, score_component_cols, and manually listed handoff columns can
# overlap. If duplicate column names are passed to DataFrame selection, pandas returns
# duplicate-labelled columns. Later, anomaly_handoff[col] becomes a DataFrame instead
# of a Series, which breaks schema generation because DataFrame has .dtypes, not .dtype.
def unique_existing_columns(columns, source_df):
    """Keep columns that exist in source_df, remove duplicates, and preserve order."""
    seen = set()
    out = []
    for c in columns:
        if c in source_df.columns and c not in seen:
            out.append(c)
            seen.add(c)
    return out

handoff_cols = unique_existing_columns(handoff_cols, lte_dl)

# Post-scoring audit export. The leakage-safe clean modeling table is produced by Notebook 01.
modeling_export_cols = list(dict.fromkeys(handoff_cols + ["is_throughput_anomaly", "rca_handoff_flag"]))
modeling_export_cols = [c for c in modeling_export_cols if c in lte_dl.columns]
lte_dl_modeling_export = lte_dl[modeling_export_cols].copy()
save_parquet_or_csv(lte_dl_modeling_export, "lte_dl_anomaly_audit_table_post_scoring", category="anomaly")

anomalies = lte_dl[lte_dl["is_throughput_anomaly"]].copy()
# Drop old IDs if an analyst accidentally used a previous post-scoring table as input.
anomalies = anomalies.drop(columns=["anomaly_id", "anomaly_episode_id", "rca_status", "rca_decision_placeholder"], errors="ignore")
anomalies = anomalies.sort_values(["id" if "id" in anomalies.columns else "timestamp", "timestamp"]).reset_index(drop=True)
anomalies.insert(0, "anomaly_id", [f"LTE-TP-{i:06d}" for i in range(1, len(anomalies) + 1)])
anomalies["rca_status"] = "pending_rca"
anomalies["rca_decision_placeholder"] = ""

# Episode grouping: consecutive anomaly samples in the same session are grouped into one
# degradation episode. This prevents long P75 runs from being interpreted as unrelated events.
def add_anomaly_episode_ids(anomaly_df: pd.DataFrame) -> pd.DataFrame:
    if anomaly_df.empty:
        anomaly_df["anomaly_episode_id"] = []
        return anomaly_df
    out = anomaly_df.copy()
    out["timestamp_utc_episode"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    out["_episode_new"] = False
    episode_ids = []
    episode_counter = 0
    group_col = "id" if "id" in out.columns else None
    groups = out.groupby(group_col, dropna=False, sort=False) if group_col else [(None, out)]
    for _, g in groups:
        prev_ts = None
        prev_source = None
        for idx, row in g.sort_values("timestamp_utc_episode").iterrows():
            ts = row.get("timestamp_utc_episode")
            source = row.get("source_index", np.nan)
            new_episode = False
            if prev_ts is None:
                new_episode = True
            else:
                gap_sec = (ts - prev_ts).total_seconds() if pd.notna(ts) and pd.notna(prev_ts) else np.inf
                source_gap = source - prev_source if pd.notna(source) and pd.notna(prev_source) else np.nan
                if (pd.notna(gap_sec) and gap_sec > MAX_SECONDS_GAP_SAME_ANOMALY_EPISODE) or (pd.notna(source_gap) and source_gap > 1):
                    new_episode = True
            if new_episode:
                episode_counter += 1
            episode_ids.append((idx, f"LTE-TP-EP-{episode_counter:06d}"))
            prev_ts = ts
            prev_source = source
    for idx, ep in episode_ids:
        out.loc[idx, "anomaly_episode_id"] = ep
    return out.drop(columns=["timestamp_utc_episode", "_episode_new"], errors="ignore")

anomalies = add_anomaly_episode_ids(anomalies)

# Save broad candidate table first. This preserves every statistical anomaly candidate.
handoff_output_cols = ["anomaly_id", "anomaly_episode_id"] + handoff_cols + ["rca_status", "rca_decision_placeholder"]
handoff_output_cols = unique_existing_columns(handoff_output_cols, anomalies)
anomaly_candidates_all = anomalies[handoff_output_cols].copy()
anomaly_candidates_all = anomaly_candidates_all.loc[:, ~anomaly_candidates_all.columns.duplicated()].copy()
save_table(anomaly_candidates_all, "lte_throughput_anomaly_candidates_all.csv")

# Main RCA-ready baseline handoff table: stricter subset for practical review.
# This still contains anomaly evidence only; no final RCA cause is assigned here.
if "rca_handoff_flag" in anomalies.columns:
    anomalies = anomalies[anomalies["rca_handoff_flag"].fillna(False).astype(bool)].copy()

handoff_output_cols = unique_existing_columns(handoff_output_cols, anomalies)
anomaly_handoff = anomalies[handoff_output_cols].copy()

# Extra guard: if duplicate column labels still exist because the source dataframe itself
# contained duplicate labels, keep the first occurrence for the handoff output.
anomaly_handoff = anomaly_handoff.loc[:, ~anomaly_handoff.columns.duplicated()].copy()

save_table(anomaly_handoff, "lte_throughput_anomalies_baseline.csv")
# Main anomaly handoff is intentionally saved as CSV for easy RCA handoff/review.

# Episode-level summary for RCA review.
if not anomaly_handoff.empty and "anomaly_episode_id" in anomaly_handoff.columns:
    severity_rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    tmp_ep = anomaly_handoff.copy()
    tmp_ep["severity_rank"] = tmp_ep["anomaly_severity"].map(severity_rank).fillna(0)
    episode_summary = (
        tmp_ep.groupby("anomaly_episode_id", dropna=False)
        .agg(
            id=("id", "first"),
            route_label=("id_route_test_label", "first"),
            test_type=("id_test_type", "first"),
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            rows=("anomaly_id", "count"),
            dominant_type=("anomaly_type", lambda s: s.value_counts().index[0] if len(s) else np.nan),
            max_score=("anomaly_score_0_100", "max"),
            mean_score=("anomaly_score_0_100", "mean"),
            max_severity_rank=("severity_rank", "max"),
            min_actual_tp=("actual_lte_dl_throughput", "min"),
            median_actual_tp=("actual_lte_dl_throughput", "median"),
            median_expected_tp=("expected_tp_p75", "median"),
            median_expected_radio_p75=("expected_tp_radio_p75", "median"),
            median_expected_rb_conditioned_p75=("expected_tp_rb_conditioned_p75", "median"),
            expected_radio_confidence_mode=("expected_tp_confidence", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            expected_rb_confidence_mode=("expected_tp_rb_confidence", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            min_ratio=("throughput_ratio_p75", "min"),
            min_rb_ratio=("throughput_ratio_rb_p75", "min"),
            median_rb_usage=("rb_usage_value", "median"),
            rb_usage_bucket_mode=("rb_usage_bucket", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            rb_demand_confidence_mode=("rb_demand_confidence", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            median_throughput_per_rb=("throughput_per_rb", "median"),
            primary_serving_pci=("serving_pci", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            primary_earfcn=("serving_earfcn", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            primary_band=("serving_band", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            mean_rsrp=("lte_rsrp", "mean"),
            mean_sinr=("lte_sinr", "mean"),
            serving_pci_count=("serving_pci", "nunique"),
        )
        .reset_index()
    )

    # Episode duration and event/route aggregates for RCA handoff.
    episode_summary["duration_seconds"] = (
        pd.to_datetime(episode_summary["end_time"], errors="coerce", utc=True) -
        pd.to_datetime(episode_summary["start_time"], errors="coerce", utc=True)
    ).dt.total_seconds()

    ep_group = tmp_ep.groupby("anomaly_episode_id", dropna=False)
    for name, window in EVENT_WINDOWS_SECONDS.items():
        flag_col = f"near_{name}_flag"
        count_col = f"{name}_count_pm{window}s"
        if flag_col in tmp_ep.columns:
            episode_summary[f"{name}_near_rows"] = episode_summary["anomaly_episode_id"].map(ep_group[flag_col].sum()).fillna(0).astype(int)
            episode_summary[f"{name}_near_rows_pct"] = (episode_summary[f"{name}_near_rows"] / episode_summary["rows"].replace(0, np.nan) * 100).round(3)
        if count_col in tmp_ep.columns:
            episode_summary[f"{name}_event_count_sum"] = episode_summary["anomaly_episode_id"].map(ep_group[count_col].sum()).fillna(0).astype(int)
    for legacy_flag in ["near_handover_mobility_flag", "near_rach_failure_flag", "near_ca_change_flag", "near_any_event_flag"]:
        if legacy_flag in tmp_ep.columns:
            out_col = legacy_flag.replace("near_", "").replace("_flag", "_near_rows")
            episode_summary[out_col] = episode_summary["anomaly_episode_id"].map(ep_group[legacy_flag].sum()).fillna(0).astype(int)
            episode_summary[out_col + "_pct"] = (episode_summary[out_col] / episode_summary["rows"].replace(0, np.nan) * 100).round(3)
    if "speed" in tmp_ep.columns:
        episode_summary["max_speed"] = episode_summary["anomaly_episode_id"].map(ep_group["speed"].max())
    if "distance_from_prev_m" in tmp_ep.columns:
        episode_summary["min_distance_from_prev_m"] = episode_summary["anomaly_episode_id"].map(ep_group["distance_from_prev_m"].min())
        episode_summary["max_distance_from_prev_m"] = episode_summary["anomaly_episode_id"].map(ep_group["distance_from_prev_m"].max())

    rev_severity_rank = {v: k for k, v in severity_rank.items()}
    episode_summary["max_severity"] = episode_summary["max_severity_rank"].map(rev_severity_rank)
    for c in ["duration_seconds", "max_score", "mean_score", "min_actual_tp", "median_actual_tp", "median_expected_tp", "median_expected_radio_p75", "median_expected_rb_conditioned_p75", "min_ratio", "min_rb_ratio", "median_rb_usage", "median_throughput_per_rb", "mean_rsrp", "mean_sinr", "max_speed", "min_distance_from_prev_m", "max_distance_from_prev_m"]:
        if c in episode_summary.columns:
            episode_summary[c] = episode_summary[c].astype(float).round(3)
    episode_summary = episode_summary.drop(columns=["max_severity_rank"]).sort_values(["max_score", "rows"], ascending=[False, False])
    save_table(episode_summary, "throughput_anomaly_episode_summary.csv")
else:
    episode_summary = pd.DataFrame()
    save_table(episode_summary, "throughput_anomaly_episode_summary.csv")

# Compact summaries for quick review.
summary_by_type_sev = (
    anomaly_handoff.groupby(["anomaly_type", "anomaly_severity"], dropna=False)
    .agg(
        anomalies=("anomaly_id", "count"),
        episodes=("anomaly_episode_id", "nunique") if "anomaly_episode_id" in anomaly_handoff.columns else ("anomaly_id", "count"),
        mean_score=("anomaly_score_0_100", "mean"),
        mean_actual_tp=("actual_lte_dl_throughput", "mean"),
        mean_expected_tp=("expected_tp_p75", "mean"),
        mean_expected_radio_p75=("expected_tp_radio_p75", "mean"),
        mean_expected_rb_conditioned_p75=("expected_tp_rb_conditioned_p75", "mean"),
        mean_rb_usage=("rb_usage_value", "mean"),
        mean_throughput_per_rb=("throughput_per_rb", "mean"),
        mean_gap=("throughput_gap_p75", "mean"),
    )
    .reset_index()
    .sort_values(["anomalies", "mean_score"], ascending=[False, False])
)
for c in ["mean_score", "mean_actual_tp", "mean_expected_tp", "mean_expected_radio_p75", "mean_expected_rb_conditioned_p75", "mean_rb_usage", "mean_throughput_per_rb", "mean_gap"]:
    summary_by_type_sev[c] = summary_by_type_sev[c].astype(float).round(3)
save_table(summary_by_type_sev, "anomaly_summary_by_type_severity.csv")

if "serving_pci" in anomaly_handoff.columns:
    pci_exposure = (
        lte_dl.groupby("serving_pci", dropna=False)
        .agg(
            total_lte_dl_rows_on_pci=("actual_lte_dl_throughput", "count"),
            analysis_rows_on_pci=("anomaly_analysis_window_flag", "sum"),
            median_tp_all_rows_on_pci=("actual_lte_dl_throughput", "median"),
            median_rb_usage_on_pci=("rb_usage_value", "median"),
            ca_median_carrier_count_on_pci=("carrier_count", "median"),
        )
        .reset_index()
    )
    summary_by_pci = (
        anomaly_handoff.groupby("serving_pci", dropna=False)
        .agg(
            anomalies=("anomaly_id", "count"),
            episodes=("anomaly_episode_id", "nunique") if "anomaly_episode_id" in anomaly_handoff.columns else ("anomaly_id", "count"),
            mean_score=("anomaly_score_0_100", "mean"),
            mean_actual_tp=("actual_lte_dl_throughput", "mean"),
            mean_expected_tp=("expected_tp_p75", "mean"),
            mean_expected_rb_p75=("expected_tp_rb_conditioned_p75", "mean"),
            mean_rb_usage=("rb_usage_value", "mean"),
            mean_throughput_per_rb=("throughput_per_rb", "mean"),
            mean_rsrp=("lte_rsrp", "mean"),
            mean_sinr=("lte_sinr", "mean"),
        )
        .reset_index()
        .merge(pci_exposure, on="serving_pci", how="left")
    )
    summary_by_pci["anomaly_rate_on_pci_pct"] = (summary_by_pci["anomalies"] / summary_by_pci["total_lte_dl_rows_on_pci"].replace(0, np.nan) * 100).round(3)
    summary_by_pci["episode_rate_on_pci_pct"] = (summary_by_pci["episodes"] / summary_by_pci["total_lte_dl_rows_on_pci"].replace(0, np.nan) * 100).round(3)

    def wilson_ci(successes, total, z=1.96):
        if pd.isna(successes) or pd.isna(total) or total <= 0:
            return (np.nan, np.nan)
        p = successes / total
        denom = 1 + z**2 / total
        center = (p + z**2 / (2 * total)) / denom
        half = (z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)) / denom
        return max(0.0, center - half), min(1.0, center + half)

    pci_rate_ci = summary_by_pci.apply(lambda r: wilson_ci(r["anomalies"], r["total_lte_dl_rows_on_pci"]), axis=1)
    summary_by_pci["anomaly_rate_ci_low_pct"] = [round(lo * 100, 3) for lo, hi in pci_rate_ci]
    summary_by_pci["anomaly_rate_ci_high_pct"] = [round(hi * 100, 3) for lo, hi in pci_rate_ci]
    for c in ["mean_score", "mean_actual_tp", "mean_expected_tp", "mean_expected_rb_p75", "mean_rb_usage", "mean_throughput_per_rb", "mean_rsrp", "mean_sinr", "median_tp_all_rows_on_pci", "median_rb_usage_on_pci", "ca_median_carrier_count_on_pci"]:
        if c in summary_by_pci.columns:
            summary_by_pci[c] = summary_by_pci[c].astype(float).round(3)
    summary_by_pci = summary_by_pci.sort_values(["anomaly_rate_on_pci_pct", "anomalies"], ascending=[False, False])
    save_table(summary_by_pci, "anomaly_summary_by_serving_pci.csv")

# Session-level anomaly context. This is important because a bad session is not the same
# as every sample in that session being individually anomalous.
if "id" in lte_dl.columns:
    session_anomaly_summary = (
        lte_dl.groupby("id", dropna=False)
        .agg(
            route_label=("id_route_test_label", "first"),
            test_type=("id_test_type", "first"),
            rows=("actual_lte_dl_throughput", "count"),
            time_start=("timestamp", "min"),
            time_end=("timestamp", "max"),
            mean_tp=("actual_lte_dl_throughput", "mean"),
            median_tp=("actual_lte_dl_throughput", "median"),
            p25_tp=("actual_lte_dl_throughput", lambda s: s.quantile(0.25)),
            p10_tp=("actual_lte_dl_throughput", lambda s: s.quantile(0.10)),
            low_tp_ratio=("low_tp_fixed_flag", "mean"),
            anomaly_sample_ratio=("is_throughput_anomaly", "mean"),
            bad_session_flag=("bad_session_flag", "max"),
            median_rb_usage=("rb_usage_value", "median"),
            median_throughput_per_rb=("throughput_per_rb", "median"),
            rb_demand_confidence_mode=("rb_demand_confidence", lambda s: s.value_counts().index[0] if len(s.dropna()) else np.nan),
            mean_rsrp=("lte_rsrp", "mean"),
            mean_sinr=("lte_sinr", "mean"),
            unique_pci_count=("serving_pci", "nunique"),
        )
        .reset_index()
        .sort_values(["bad_session_flag", "low_tp_ratio", "anomaly_sample_ratio"], ascending=[False, False, False])
    )
    save_table(session_anomaly_summary, "lte_dl_session_anomaly_summary.csv")

# Schema file for integration.
# Guard against accidental duplicate columns before schema generation.
if anomaly_handoff.columns.duplicated().any():
    duplicate_cols = anomaly_handoff.columns[anomaly_handoff.columns.duplicated()].tolist()
    print("Warning: duplicate handoff columns removed before schema generation:", duplicate_cols)
    anomaly_handoff = anomaly_handoff.loc[:, ~anomaly_handoff.columns.duplicated()].copy()

schema_rows = []
for col in anomaly_handoff.columns:
    series = anomaly_handoff[col]
    # If a duplicate-column situation ever slips through, pandas returns a DataFrame.
    # Use the first duplicate safely rather than crashing.
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    schema_rows.append({
        "column": col,
        "dtype": str(series.dtype),
        "non_null": int(series.notna().sum()),
        "missing_pct": round(float(series.isna().mean() * 100), 3),
        "description": "RCA handoff / anomaly evidence column",
    })
anomaly_schema = pd.DataFrame(schema_rows)
save_table(anomaly_schema, "lte_throughput_anomaly_output_schema.csv")

print("Anomaly handoff shape:", anomaly_handoff.shape)
print("Episode summary shape:", episode_summary.shape)
display(summary_by_type_sev)
preview_cols = [c for c in ["anomaly_id", "anomaly_episode_id", "timestamp", "id", "actual_lte_dl_throughput", "expected_tp_p75", "throughput_ratio_p75", "anomaly_score_0_100", "anomaly_severity", "anomaly_type", "lte_rsrp", "lte_sinr", "serving_pci"] if c in anomaly_handoff.columns]
display(anomaly_handoff[preview_cols].head(20))

# =========================
