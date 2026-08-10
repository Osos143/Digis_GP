"""
Stage 11: quality bins flags neighbor features
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1698-2268). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 11. Quality bins, flags, neighbor aggregates, and event-window features
# =========================

def bin_rsrp(x):
    """Bin LTE RSRP using the calibrated drive-test thresholds."""
    if pd.isna(x): return np.nan
    if x >= RSRP_EXCELLENT_MIN_DBM: return "Excellent"
    if x >= RSRP_GOOD_MIN_DBM: return "Good"
    if x >= RSRP_FAIR_MIN_DBM: return "Fair"
    return "Poor"


def bin_rsrq(x):
    """Bin LTE RSRQ using the calibrated drive-test thresholds."""
    if pd.isna(x): return np.nan
    if x >= RSRQ_EXCELLENT_MIN_DB: return "Excellent"
    if x >= RSRQ_GOOD_MIN_DB: return "Good"
    if x >= RSRQ_FAIR_MIN_DB: return "Fair"
    return "Poor"


def bin_sinr(x):
    """Bin LTE SINR using the calibrated drive-test thresholds."""
    if pd.isna(x): return np.nan
    if x >= SINR_EXCELLENT_MIN_DB: return "Excellent"
    if x >= SINR_GOOD_MIN_DB: return "Good"
    if x >= SINR_FAIR_MIN_DB: return "Fair"
    return "Poor"


# Quality bins.
lte_dl["rsrp_bin"] = lte_dl["lte_rsrp"].map(bin_rsrp)
lte_dl["rsrq_bin"] = lte_dl["lte_rsrq"].map(bin_rsrq)
lte_dl["sinr_bin"] = lte_dl["lte_sinr"].map(bin_sinr)

radio_bin_summary = pd.concat(
    {
        "RSRP": lte_dl["rsrp_bin"].value_counts(dropna=False, normalize=True).mul(100).round(2),
        "RSRQ": lte_dl["rsrq_bin"].value_counts(dropna=False, normalize=True).mul(100).round(2),
        "SINR": lte_dl["sinr_bin"].value_counts(dropna=False, normalize=True).mul(100).round(2),
    },
    axis=1,
).fillna(0).sort_index()
print("Radio-quality bin distribution (% of LTE-DL samples):")
display(radio_bin_summary)

# Evidence flags used by the anomaly labels. These are not final RCA causes.
# Poor flags use the lower edge of the Fair bin.
# This means Fair radio is preserved as warning/context, while Poor radio is reserved
# for clearly bad field conditions.
lte_dl["poor_rsrp_flag"] = lte_dl["lte_rsrp"] < RSRP_FAIR_MIN_DBM
lte_dl["poor_rsrq_flag"] = lte_dl["lte_rsrq"] < RSRQ_FAIR_MIN_DB
lte_dl["poor_sinr_flag"] = lte_dl["lte_sinr"] < SINR_FAIR_MIN_DB
lte_dl["high_bler_flag"] = lte_dl["lte_bler"] > 10
lte_dl["low_cqi_flag"] = lte_dl["lte_cqi"] < 7

# Low RB allocation is relative because RB values depend on bandwidth and export semantics.
rb_q25 = lte_dl["lte_rb_count"].quantile(0.25) if lte_dl["lte_rb_count"].notna().any() else np.nan
lte_dl["low_rb_allocation_flag"] = lte_dl["lte_rb_count"].notna() & (lte_dl["lte_rb_count"] <= rb_q25)

# Neighbor aggregates from wide LTE NeighborCells(n) columns.
def add_lte_neighbor_aggregates(df_samples: pd.DataFrame) -> pd.DataFrame:
    out = df_samples.copy()
    rsrp_cols = [c for c in out.columns if re.match(r"LTE - NeighborCells\(\d+\) - RSRP$", str(c))]
    pci_cols = [c for c in out.columns if re.match(r"LTE - NeighborCells\(\d+\) - PCI$", str(c))]
    if rsrp_cols:
        rsrp_numeric = out[rsrp_cols].apply(pd.to_numeric, errors="coerce")
        out["neighbor_count"] = rsrp_numeric.notna().sum(axis=1)
        out["best_neighbor_rsrp"] = rsrp_numeric.max(axis=1)
        out["strong_neighbor_count"] = (rsrp_numeric >= -100).sum(axis=1)
        out["serving_minus_best_neighbor_rsrp"] = out["lte_rsrp"] - out["best_neighbor_rsrp"]
    else:
        out["neighbor_count"] = 0
        out["best_neighbor_rsrp"] = np.nan
        out["strong_neighbor_count"] = 0
        out["serving_minus_best_neighbor_rsrp"] = np.nan

    # PCI count is useful for overlap/mobility context.
    if pci_cols:
        out["neighbor_pci_count"] = out[pci_cols].notna().sum(axis=1)
    else:
        out["neighbor_pci_count"] = 0
    return out


lte_dl = add_lte_neighbor_aggregates(lte_dl)

# Event-window features.
# IMPORTANT CAUSALITY RULE:
# - *_count_prevXs / near_*_prev_flag use ONLY events at or before the sample timestamp and
#   are safe candidates for causal forecasting.
# - legacy *_count_pmXs / near_*_flag are symmetric ±X-second OFFLINE RCA CONTEXT ONLY.
#   Notebook 02 explicitly excludes them from causal model predictors.
def add_event_window_features(samples: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Add both causal past-only and symmetric offline event context efficiently."""
    out = samples.copy()

    def _init_empty(frame: pd.DataFrame) -> pd.DataFrame:
        for name, window in EVENT_WINDOWS_SECONDS.items():
            frame[f"{name}_count_prev{window}s"] = 0
            frame[f"near_{name}_prev_flag"] = False
            # Legacy/offline context only.
            frame[f"{name}_count_pm{window}s"] = 0
            frame[f"near_{name}_flag"] = False
        return frame

    if events.empty or "event_timestamp" not in events.columns or "timestamp" not in out.columns:
        return _init_empty(out)

    ev = events.copy()
    ev["event_timestamp_utc"] = pd.to_datetime(ev["event_timestamp"], errors="coerce", utc=True)
    out["timestamp_utc_for_event_window"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=True)
    ev = ev.dropna(subset=["event_timestamp_utc"])
    if ev.empty:
        return _init_empty(out).drop(columns=["timestamp_utc_for_event_window"], errors="ignore")

    id_col = "id" if "id" in out.columns and "id" in ev.columns else None
    ev["event_time_ns"] = ev["event_timestamp_utc"].astype("int64")

    any_event_times, family_event_times = {}, {}
    if id_col:
        for sid, group in ev.groupby(id_col, dropna=False):
            any_event_times[sid] = np.sort(group["event_time_ns"].values)
        for (sid, family), group in ev.groupby([id_col, "event_family"], dropna=False):
            family_event_times[(sid, family)] = np.sort(group["event_time_ns"].values)
    else:
        any_event_times[None] = np.sort(ev["event_time_ns"].values)
        for family, group in ev.groupby("event_family", dropna=False):
            family_event_times[(None, family)] = np.sort(group["event_time_ns"].values)

    out = _init_empty(out)
    sample_groups = out.groupby(id_col, dropna=False) if id_col else [(None, out)]

    for sid, sample_group in sample_groups:
        sample_idx = sample_group.index
        sample_times = out.loc[sample_idx, "timestamp_utc_for_event_window"].astype("int64").values

        for family_name, window_seconds in EVENT_WINDOWS_SECONDS.items():
            if family_name == "any_event":
                event_times = any_event_times.get(sid if id_col else None)
            else:
                event_times = family_event_times.get((sid if id_col else None, family_name))
            if event_times is None or len(event_times) == 0:
                continue

            radius_ns = int(window_seconds * 1e9)

            # Causal window [t-window, t]. No future event is visible.
            causal_left = np.searchsorted(event_times, sample_times - radius_ns, side="left")
            causal_right = np.searchsorted(event_times, sample_times, side="right")
            causal_counts = causal_right - causal_left
            out.loc[sample_idx, f"{family_name}_count_prev{window_seconds}s"] = causal_counts
            out.loc[sample_idx, f"near_{family_name}_prev_flag"] = causal_counts > 0

            # Symmetric offline context [t-window, t+window]. NEVER use for causal forecasting.
            sym_left = np.searchsorted(event_times, sample_times - radius_ns, side="left")
            sym_right = np.searchsorted(event_times, sample_times + radius_ns, side="right")
            sym_counts = sym_right - sym_left
            out.loc[sample_idx, f"{family_name}_count_pm{window_seconds}s"] = sym_counts
            out.loc[sample_idx, f"near_{family_name}_flag"] = sym_counts > 0

    return out.drop(columns=["timestamp_utc_for_event_window"], errors="ignore")


lte_dl = add_event_window_features(lte_dl, events_long)

# Legacy compatibility aliases after the refined event-family split.
# The old broad handover_mobility flag now means actual HO execution or HO failure,
# not ordinary A1/A2/A3/A5/A6 measurement reports.
def _sum_existing_event_counts(df: pd.DataFrame, names: Sequence[str], window: int) -> pd.Series:
    cols = [f"{name}_count_pm{window}s" for name in names if f"{name}_count_pm{window}s" in df.columns]
    if not cols:
        return pd.Series(0, index=df.index)
    return df[cols].fillna(0).sum(axis=1)

lte_dl["handover_mobility_count_pm5s"] = _sum_existing_event_counts(lte_dl, ["handover_execution", "handover_failure"], 5)
lte_dl["near_handover_mobility_flag"] = lte_dl["handover_mobility_count_pm5s"] > 0
lte_dl["ca_change_count_pm10s"] = lte_dl.get("ca_activation_change_count_pm10s", pd.Series(0, index=lte_dl.index)).fillna(0)
lte_dl["near_ca_change_flag"] = lte_dl["ca_change_count_pm10s"] > 0
lte_dl["rach_count_pm10s"] = _sum_existing_event_counts(lte_dl, ["rach_attempt", "rach_failure"], 10)
lte_dl["near_rach_flag"] = lte_dl["rach_count_pm10s"] > 0

# Direct RACH result flag if row-level RACH fields exist.
lte_dl["rach_failure_direct_flag"] = lte_dl["rach_result"].astype(str).str.contains("fail|timeout|reject", case=False, na=False)

print("Feature-enriched LTE-DL table shape:", lte_dl.shape)
display(lte_dl[[
    "actual_lte_dl_throughput", "lte_rsrp", "lte_rsrq", "lte_sinr", "lte_cqi", "lte_bler",
    "carrier_count", "neighbor_count", "best_neighbor_rsrp", "near_any_event_flag",
    "near_handover_mobility_flag", "near_rach_failure_flag", "near_ca_change_flag"
]].head(20))

# No generic causal event aliases are created here. The ML notebook consumes the explicit
# past-only event families directly (for example handover_execution_count_prev5s and
# handover_failure_count_prev10s), which avoids mixing differently sized causal windows.

causal_event_feature_cols = sorted([
    c for c in lte_dl.columns if ("_count_prev" in c or c.endswith("_prev_flag"))
])
symmetric_context_feature_cols = sorted([
    c for c in lte_dl.columns if ("_count_pm" in c or (c.startswith("near_") and not c.endswith("_prev_flag")))
])
causality_audit = pd.DataFrame([
    {"column": c, "feature_role": "CAUSAL_PAST_ONLY_MODEL_ELIGIBLE"} for c in causal_event_feature_cols
] + [
    {"column": c, "feature_role": "SYMMETRIC_OFFLINE_RCA_CONTEXT_ONLY"} for c in symmetric_context_feature_cols
])
save_table(causality_audit, "event_feature_causality_audit.csv", category="preprocessing")
print("Causal event features:", len(causal_event_feature_cols))
print("Symmetric offline-only event context features:", len(symmetric_context_feature_cols))


# =========================
# 11B. Pre-anomaly visual EDA and threshold sanity checks
# =========================

if not lte_dl.empty:
    tp_quantiles = lte_dl["actual_lte_dl_throughput"].quantile([0.01, 0.05, 0.10, 0.17, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]).rename("throughput_mbps")
    threshold_sanity = pd.DataFrame({
        "metric": [
            "rows",
            "throughput_p01", "throughput_p05", "throughput_p10", "throughput_p17", "throughput_p25", "throughput_median", "throughput_p75", "throughput_p90", "throughput_p95", "throughput_p99",
            "pct_below_5_mbps", "pct_below_10_mbps", "pct_below_15_mbps", "pct_below_20_mbps",
        ],
        "value": [
            len(lte_dl),
            tp_quantiles.loc[0.01], tp_quantiles.loc[0.05], tp_quantiles.loc[0.10], tp_quantiles.loc[0.17], tp_quantiles.loc[0.25], tp_quantiles.loc[0.50], tp_quantiles.loc[0.75], tp_quantiles.loc[0.90], tp_quantiles.loc[0.95], tp_quantiles.loc[0.99],
            (lte_dl["actual_lte_dl_throughput"] < 5).mean() * 100,
            (lte_dl["actual_lte_dl_throughput"] < 10).mean() * 100,
            (lte_dl["actual_lte_dl_throughput"] < 15).mean() * 100,
            (lte_dl["actual_lte_dl_throughput"] < 20).mean() * 100,
        ],
    })
    threshold_sanity["value"] = threshold_sanity["value"].astype(float).round(3)
    save_table(threshold_sanity, "throughput_threshold_sanity.csv")
    display(threshold_sanity)

    # Time-spacing diagnostic: rolling remains sample-based, but this proves whether
    # sample rows are close to consecutive seconds.
    if "sample_gap_seconds" in lte_dl.columns:
        plot_distribution_with_lines(
            lte_dl,
            "sample_gap_seconds",
            "Sample Gap Distribution for LTE-DL Rows",
            "Seconds since previous sample in same session",
            thresholds={"1 second": 1, "2 seconds": 2},
            bins=40,
            filename="02b_sample_gap_seconds_distribution.png",
            clip_upper_q=0.99,
        )

    # Compare throughput inside and outside the active download analysis window.
    # This context is retained mainly as confidence/evidence. If the medians are similar,
    # do not use separate thresholds for each download-context bucket.
    if "download_context_label" in lte_dl.columns:
        plot_box_by_category(
            lte_dl,
            "download_context_label",
            "actual_lte_dl_throughput",
            "Throughput by Download Activity Context",
            "LTE DL throughput (Mbps)",
            filename="02c_throughput_by_download_activity_context.png",
            category_order=[
                "active_download_analysis_window",
                "download_warmup_or_cooldown",
                "outside_download_activity",
                "activity_filter_not_available",
                "activity_filter_disabled",
                "activity_filter_fallback_all_rows",
            ],
        )

        download_context_summary = (
            lte_dl.groupby("download_context_label", dropna=False)["actual_lte_dl_throughput"]
            .agg(
                rows="count",
                mean="mean",
                p10=lambda s: s.quantile(0.10),
                p25=lambda s: s.quantile(0.25),
                median="median",
                p75=lambda s: s.quantile(0.75),
                pct_below_10=lambda s: (s < LOW_TP_FIXED_MBPS).mean() * 100,
            )
            .reset_index()
        )
        for c in ["mean", "p10", "p25", "median", "p75", "pct_below_10"]:
            download_context_summary[c] = download_context_summary[c].astype(float).round(3)
        save_table(download_context_summary, "throughput_by_download_context_summary.csv")
        display(download_context_summary)

    plot_distribution_with_lines(
        lte_dl,
        "actual_lte_dl_throughput",
        "LTE-DL Throughput Distribution Before Anomaly Detection",
        "LTE DL throughput (Mbps)",
        thresholds={
            "Very low threshold": VERY_LOW_TP_MBPS,
            "Low threshold": LOW_TP_FIXED_MBPS,
            "Global P10": float(tp_quantiles.loc[0.10]),
            "Global P25": float(tp_quantiles.loc[0.25]),
            "Median": float(tp_quantiles.loc[0.50]),
        },
        filename="01_pre_anomaly_throughput_distribution.png",
        clip_upper_q=HISTOGRAM_COLOR_CLIP_Q,
    )

    radio_order = ["Poor", "Fair", "Good", "Excellent"]
    plot_box_by_category(lte_dl, "rsrp_bin", "actual_lte_dl_throughput", "Throughput by RSRP Bin", "LTE DL throughput (Mbps)", "02_throughput_by_rsrp_bin.png", radio_order)
    plot_box_by_category(lte_dl, "rsrq_bin", "actual_lte_dl_throughput", "Throughput by RSRQ Bin", "LTE DL throughput (Mbps)", "03_throughput_by_rsrq_bin.png", radio_order)
    plot_box_by_category(lte_dl, "sinr_bin", "actual_lte_dl_throughput", "Throughput by SINR Bin", "LTE DL throughput (Mbps)", "04_throughput_by_sinr_bin.png", radio_order)

    # Carrier aggregation / CA context.
    lte_dl["ca_condition_label"] = np.select(
        [
            lte_dl["carrier_count"].fillna(0) >= 3,
            lte_dl["carrier_count"].fillna(0) == 2,
            lte_dl["carrier_count"].fillna(0) == 1,
        ],
        ["3CC_or_more_CA", "2CC_CA", "single_carrier"],
        default="unknown_carrier_count",
    )
    plot_box_by_category(lte_dl, "carrier_count", "actual_lte_dl_throughput", "Throughput by LTE Carrier Count", "LTE DL throughput (Mbps)", "05_throughput_by_carrier_count.png")
    plot_box_by_category(lte_dl, "ca_condition_label", "actual_lte_dl_throughput", "Throughput by CA Condition", "LTE DL throughput (Mbps)", "05b_throughput_by_ca_condition.png", category_order=["single_carrier", "2CC_CA", "3CC_or_more_CA", "unknown_carrier_count"])

    ca_summary = (
        lte_dl.groupby(["ca_condition_label", "carrier_count"], dropna=False)["actual_lte_dl_throughput"]
        .agg(
            rows="count",
            mean="mean",
            p10=lambda s: s.quantile(0.10),
            p25=lambda s: s.quantile(0.25),
            median="median",
            p75=lambda s: s.quantile(0.75),
            p90=lambda s: s.quantile(0.90),
            pct_below_10=lambda s: (s < LOW_TP_FIXED_MBPS).mean() * 100,
        )
        .reset_index()
        .sort_values(["carrier_count", "ca_condition_label"])
    )
    for c in ["mean", "p10", "p25", "median", "p75", "p90", "pct_below_10"]:
        ca_summary[c] = ca_summary[c].astype(float).round(3)
    save_table(ca_summary, "throughput_by_ca_condition_summary.csv")
    display(ca_summary)

    # RB usage reliability check. This tells us whether RB allocation can be trusted as evidence.
    rb_cols = [c for c in ["lte_rb_count", "lte_agg_rb_dl", "scell1_rb_count"] if c in lte_dl.columns]
    rb_quality_rows = []
    for col in rb_cols:
        s = pd.to_numeric(lte_dl[col], errors="coerce")
        non_null_pct = s.notna().mean() * 100
        unique_values = int(s.nunique(dropna=True))
        reliable = (non_null_pct >= MIN_RELIABLE_RB_NON_NULL_PCT) and (unique_values >= MIN_RELIABLE_RB_UNIQUE_VALUES)
        rb_quality_rows.append({
            "rb_column": col,
            "non_null_rows": int(s.notna().sum()),
            "non_null_pct": round(non_null_pct, 3),
            "unique_values": unique_values,
            "min": round(float(s.min()), 3) if s.notna().any() else np.nan,
            "p10": round(float(s.quantile(0.10)), 3) if s.notna().any() else np.nan,
            "p25": round(float(s.quantile(0.25)), 3) if s.notna().any() else np.nan,
            "median": round(float(s.median()), 3) if s.notna().any() else np.nan,
            "p75": round(float(s.quantile(0.75)), 3) if s.notna().any() else np.nan,
            "p90": round(float(s.quantile(0.90)), 3) if s.notna().any() else np.nan,
            "max": round(float(s.max()), 3) if s.notna().any() else np.nan,
            "reliable_for_anomaly_evidence": reliable,
        })
    rb_usage_quality_summary = pd.DataFrame(rb_quality_rows)
    save_table(rb_usage_quality_summary, "rb_usage_quality_summary.csv")
    display(rb_usage_quality_summary)

    # Make a global flag so later anomaly logic can decide whether low-RB evidence should be trusted.
    reliable_rb_columns = rb_usage_quality_summary.loc[rb_usage_quality_summary["reliable_for_anomaly_evidence"], "rb_column"].tolist() if not rb_usage_quality_summary.empty else []
    lte_dl["rb_usage_evidence_reliable_flag"] = bool(reliable_rb_columns)
    lte_dl["reliable_rb_columns"] = ";".join(reliable_rb_columns) if reliable_rb_columns else ""


    # Demand/RB interpretation.
    # This is very important for throughput anomaly detection: low observed throughput is
    # only a strong capacity/efficiency anomaly when there is evidence that the scheduler
    # allocated enough resources. RB usage is therefore the main demand/resource-confidence
    # signal. Activity-window labels remain context only.
    preferred_rb_order = [c for c in ["lte_agg_rb_dl", "lte_rb_count", "scell1_rb_count"] if c in reliable_rb_columns]
    rb_reference_col = preferred_rb_order[0] if preferred_rb_order else None
    lte_dl["rb_reference_column"] = rb_reference_col if rb_reference_col else "none_reliable"

    if rb_reference_col:
        rb_values = pd.to_numeric(lte_dl[rb_reference_col], errors="coerce")
        # Use all valid LTE-DL rows for RB quantiles. Activity-window labels are context only.
        rb_reference_mask = rb_values.notna()
        rb_reference_values = rb_values.where(rb_reference_mask)

        rb_low_threshold = float(rb_reference_values.quantile(LOW_RB_QUANTILE))
        rb_medium_threshold = float(rb_reference_values.quantile(MEDIUM_RB_QUANTILE))
        rb_high_threshold = float(rb_reference_values.quantile(HIGH_RB_QUANTILE))

        lte_dl["rb_usage_value"] = rb_values
        lte_dl["rb_low_usage_threshold"] = rb_low_threshold
        lte_dl["rb_medium_usage_threshold"] = rb_medium_threshold
        lte_dl["rb_high_usage_threshold"] = rb_high_threshold
        lte_dl["rb_low_usage_flag"] = rb_values.notna() & (rb_values <= rb_low_threshold)
        lte_dl["rb_medium_or_high_usage_flag"] = rb_values.notna() & (rb_values >= rb_medium_threshold)
        lte_dl["rb_high_usage_flag"] = rb_values.notna() & (rb_values >= rb_high_threshold)
        lte_dl["rb_usage_bucket"] = np.select(
            [
                rb_values.isna(),
                rb_values <= rb_low_threshold,
                rb_values < rb_medium_threshold,
                rb_values < rb_high_threshold,
                rb_values >= rb_high_threshold,
            ],
            ["missing", "low_rb_usage", "below_median_rb_usage", "medium_rb_usage", "high_rb_usage"],
            default="unknown",
        )
        lte_dl["rb_demand_confidence"] = np.select(
            [
                lte_dl["rb_high_usage_flag"],
                lte_dl["rb_medium_or_high_usage_flag"],
                lte_dl["rb_low_usage_flag"],
            ],
            ["high", "medium", "low_or_uncertain"],
            default="unknown",
        )

        # Engineering-normalized RB utilization estimate for future ML/RCA.
        # When aggregate bandwidth is available, use it. Otherwise estimate capacity from
        # serving bandwidth and carrier count. This remains an estimate, but it is more
        # portable than raw RB quantile buckets alone.
        def _lte_rb_capacity_from_bandwidth_mhz(series: pd.Series) -> pd.Series:
            bw = pd.to_numeric(series, errors="coerce")
            return np.select(
                [bw <= 1.4, bw <= 3, bw <= 5, bw <= 10, bw <= 15, bw <= 20],
                [6, 15, 25, 50, 75, 100],
                default=np.nan,
            )

        agg_bw = pd.to_numeric(lte_dl.get("lte_agg_bandwidth_dl", pd.Series(np.nan, index=lte_dl.index)), errors="coerce")
        pcell_bw = pd.to_numeric(lte_dl.get("lte_bandwidth_dl", pd.Series(np.nan, index=lte_dl.index)), errors="coerce")
        carriers = pd.to_numeric(lte_dl.get("carrier_count", pd.Series(1, index=lte_dl.index)), errors="coerce").fillna(1).clip(lower=1)

        estimated_rb_from_agg_bw = pd.Series(_lte_rb_capacity_from_bandwidth_mhz(agg_bw), index=lte_dl.index)
        estimated_rb_from_pcell_bw = pd.Series(_lte_rb_capacity_from_bandwidth_mhz(pcell_bw), index=lte_dl.index) * carriers
        fallback_rb_capacity = 100 * carriers  # conservative 20-MHz-per-carrier fallback when bandwidth is unavailable

        lte_dl["estimated_available_rb"] = estimated_rb_from_agg_bw.fillna(estimated_rb_from_pcell_bw).fillna(fallback_rb_capacity)
        lte_dl["rb_capacity_estimation_method"] = np.select(
            [estimated_rb_from_agg_bw.notna(), estimated_rb_from_pcell_bw.notna()],
            ["aggregate_bandwidth", "pcell_bandwidth_times_carriers"],
            default="fallback_100rb_per_carrier",
        )
        lte_dl["rb_utilization_pct"] = (lte_dl["rb_usage_value"] / lte_dl["estimated_available_rb"].replace(0, np.nan) * 100).clip(lower=0, upper=250)

        rb_demand_summary = (
            lte_dl.groupby(["rb_reference_column", "rb_usage_bucket"], dropna=False)
            .agg(
                rows=("actual_lte_dl_throughput", "count"),
                median_rb=("rb_usage_value", "median"),
                median_tp=("actual_lte_dl_throughput", "median"),
                p25_tp=("actual_lte_dl_throughput", lambda ss: ss.quantile(0.25)),
                p75_tp=("actual_lte_dl_throughput", lambda ss: ss.quantile(0.75)),
                pct_below_10=("actual_lte_dl_throughput", lambda ss: (ss < LOW_TP_FIXED_MBPS).mean() * 100),
            )
            .reset_index()
        )
        for c in ["median_rb", "median_tp", "p25_tp", "p75_tp", "pct_below_10"]:
            rb_demand_summary[c] = rb_demand_summary[c].astype(float).round(3)
        save_table(rb_demand_summary, "throughput_by_rb_demand_summary.csv")
        display(rb_demand_summary)

        # Override the earlier relative low-RB flag so it only uses reliable RB evidence.
        lte_dl["low_rb_allocation_flag"] = lte_dl["rb_low_usage_flag"]

        plot_box_by_category(
            lte_dl,
            "rb_usage_bucket",
            "actual_lte_dl_throughput",
            "Throughput by RB Usage / Demand Bucket",
            "LTE DL throughput (Mbps)",
            "05e_throughput_by_rb_usage_bucket.png",
            category_order=["low_rb_usage", "below_median_rb_usage", "medium_rb_usage", "high_rb_usage", "missing"],
        )
    else:
        lte_dl["rb_usage_value"] = np.nan
        lte_dl["rb_low_usage_threshold"] = np.nan
        lte_dl["rb_medium_usage_threshold"] = np.nan
        lte_dl["rb_high_usage_threshold"] = np.nan
        lte_dl["rb_low_usage_flag"] = False
        lte_dl["rb_medium_or_high_usage_flag"] = True  # no reliable RB, so do not block P75/CA purely because RB is unavailable
        lte_dl["rb_high_usage_flag"] = False
        lte_dl["rb_usage_bucket"] = "rb_not_reliable_or_missing"
        lte_dl["rb_demand_confidence"] = "unknown_rb_not_reliable"
        lte_dl["low_rb_allocation_flag"] = False

    if "lte_agg_rb_dl" in rb_cols:
        rb_series = pd.to_numeric(lte_dl["lte_agg_rb_dl"], errors="coerce")
        if rb_series.notna().mean() * 100 >= MIN_RELIABLE_RB_NON_NULL_PCT:
            rb_bins = [0, 10, 25, 50, 100, 150, 250, np.inf]
            rb_labels = ["0-10", "10-25", "25-50", "50-100", "100-150", "150-250", "250+"]
            lte_dl["lte_agg_rb_dl_bin"] = pd.cut(rb_series, bins=rb_bins, labels=rb_labels, include_lowest=True, right=False)
            plot_box_by_category(lte_dl, "lte_agg_rb_dl_bin", "actual_lte_dl_throughput", "Throughput by Aggregate DL RB Usage Bin", "LTE DL throughput (Mbps)", "05c_throughput_by_agg_rb_bin.png", category_order=rb_labels)
            plot_scatter_sample(lte_dl, "lte_agg_rb_dl", "actual_lte_dl_throughput", "Throughput vs Aggregate DL RB Usage", "Aggregate DL RB usage", "LTE DL throughput (Mbps)", "05d_tp_vs_agg_rb.png")

    plot_scatter_sample(lte_dl, "lte_rsrp", "actual_lte_dl_throughput", "Throughput vs RSRP", "RSRP (dBm)", "LTE DL throughput (Mbps)", "06_tp_vs_rsrp.png")
    plot_scatter_sample(lte_dl, "lte_rsrq", "actual_lte_dl_throughput", "Throughput vs RSRQ", "RSRQ (dB)", "LTE DL throughput (Mbps)", "07_tp_vs_rsrq.png")
    plot_scatter_sample(lte_dl, "lte_sinr", "actual_lte_dl_throughput", "Throughput vs SINR", "SINR (dB)", "LTE DL throughput (Mbps)", "08_tp_vs_sinr.png")

    plot_route_metric(
        lte_dl,
        "actual_lte_dl_throughput",
        "Route Colored by LTE DL Throughput Before Anomaly Detection",
        "09_route_by_throughput.png",
        clip_upper_q=ROUTE_MAP_COLOR_CLIP_Q,
        colorbar_label="LTE DL throughput Mbps",
    )


# -------------------------
# Save clean pre-anomaly feature table for the next notebook and future ML
# -------------------------
# This table is intentionally exported BEFORE any anomaly labels, expected-throughput P75
# references, residuals, scores, or severity labels are created. It is the leakage-safe base
# for Notebook 02 and, later, for ML expected-throughput modeling.
forbidden_pre_anomaly_prefixes = (
    "expected_tp", "throughput_gap_p75", "throughput_ratio_p75", "log_residual_p75",
    "throughput_gap_rb_p75", "throughput_ratio_rb_p75", "log_residual_rb_p75",
    "score_", "anomaly_score", "anomaly_type", "anomaly_severity", "is_throughput_anomaly",
    "underperform_", "low_tp_", "rolling_", "prev_tp", "tp_drop_", "tp_ratio_to_prev",
    "bad_session", "global_p10", "global_p25", "session_p10", "session_p25",
)
forbidden_pre_anomaly_exact = {
    "anomaly_method_count", "context_flag_count", "independent_trigger_count", "trigger_family_flags",
    "rca_handoff_flag", "rca_status", "rca_decision_placeholder",
}
forbidden_cols = [
    c for c in lte_dl.columns
    if c in forbidden_pre_anomaly_exact or any(str(c).startswith(prefix) for prefix in forbidden_pre_anomaly_prefixes)
]
pre_anomaly_feature_table = lte_dl.drop(columns=forbidden_cols, errors="ignore").copy()

pre_anomaly_leakage_check = pd.DataFrame({
    "removed_if_present": forbidden_cols,
    "reason": "post-anomaly/statistical-score/expected-throughput leakage guard",
})
save_table(pre_anomaly_leakage_check, "pre_anomaly_feature_table_leakage_guard.csv", category="preprocessing")
save_parquet_or_csv(pre_anomaly_feature_table, "lte_dl_feature_table_clean_pre_anomaly", category="preprocessing")
# Backward-compatible alias. In this split version, this name now points to the clean table,
# not the post-scoring anomaly audit table.
save_parquet_or_csv(pre_anomaly_feature_table, "lte_dl_modeling_table", category="preprocessing")

print("Saved leakage-safe clean pre-anomaly feature table:", PREPROCESSING_DIR / "lte_dl_feature_table_clean_pre_anomaly.parquet")
print("Clean pre-anomaly shape:", pre_anomaly_feature_table.shape)


# =========================
# Final preprocessing output index
# =========================
output_index = []
for path in sorted(OUTPUT_ROOT.rglob("*")):
    if path.is_file():
        output_index.append({
            "file": path.name,
            "folder": str(path.parent.relative_to(OUTPUT_ROOT)),
            "size": human_bytes(path.stat().st_size),
            "path": str(path),
        })
output_index_df = pd.DataFrame(output_index)
save_table(output_index_df, "output_index.csv", category="preprocessing")
display(output_index_df)

print("Notebook 01 complete.")
print("Clean pre-anomaly table:", PREPROCESSING_DIR / "lte_dl_feature_table_clean_pre_anomaly.parquet")
print("Next step: run Notebook 02 using this table.")
