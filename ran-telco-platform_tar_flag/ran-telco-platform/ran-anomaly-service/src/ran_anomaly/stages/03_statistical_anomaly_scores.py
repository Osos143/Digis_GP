"""
Stage 03: statistical anomaly scores
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 936-1281). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 12. Simple and robust statistical anomaly scores
# =========================


def minmax_clip_score(value: pd.Series, denominator: float) -> pd.Series:
    """Convert a positive gap into a clipped 0..1 score."""
    if denominator is None or denominator == 0 or pd.isna(denominator):
        return pd.Series(0.0, index=value.index)
    return (value / denominator).clip(lower=0, upper=1)


def robust_mad_zscore(x: pd.Series) -> pd.Series:
    """Robust modified z-score using median absolute deviation.

    The median and MAD are calculated from the non-null values. This allows us to pass a
    series where non-eligible values may be set to NaN.
    """
    x = pd.to_numeric(x, errors="coerce")
    med = x.median(skipna=True)
    mad = (x - med).abs().median(skipna=True)
    if pd.isna(mad) or mad == 0:
        std = x.std(skipna=True)
        if pd.isna(std) or std == 0:
            return pd.Series(0.0, index=x.index)
        return (x - med) / std
    return 0.6745 * (x - med) / mad


def rolling_stat_by_session(df: pd.DataFrame, target: str, window: int, stat: str) -> pd.Series:
    """Return a centered sample-based rolling statistic calculated inside each session.

    The drive-test cadence is project-verified at exactly 1 second/sample. Therefore an
    11-sample window is an 11-second local window. Timestamp deltas are still exported as QC.

    Non-eligible values can be stored as NaN in the target column. Pandas rolling
    statistics ignore NaN values but still require enough valid samples through min_periods.
    """
    min_periods = max(MIN_ROLLING_SAMPLES, window // 3)

    def _apply(s: pd.Series) -> pd.Series:
        roll = s.rolling(window=window, min_periods=min_periods, center=True)
        if stat == "median":
            return roll.median()
        if stat == "p25":
            return roll.quantile(0.25)
        if stat == "count":
            return roll.count()
        raise ValueError(f"Unsupported rolling stat: {stat}")

    if "id" in df.columns:
        return df.groupby("id", group_keys=False)[target].apply(_apply).reindex(df.index)
    return _apply(df[target])


tp = pd.to_numeric(lte_dl["actual_lte_dl_throughput"], errors="coerce")
lte_dl["log_actual_lte_dl_throughput"] = np.log1p(tp)

# Main analysis population: all valid LTE-DL rows.
# The download activity window remains in the table as context only. This change is based on
# the observed fact that active/warmup/outside activity rows had very similar throughput medians.
analysis_mask = tp.notna() & (tp >= 0)

# Safety fallback: if something unexpected removes all rows, analyze the LTE-DL table as-is.
if not analysis_mask.any():
    print("Warning: anomaly analysis mask is empty. Falling back to all LTE-DL rows.")
    analysis_mask = pd.Series(True, index=lte_dl.index)

lte_dl["anomaly_analysis_window_flag"] = analysis_mask
analysis_n = int(analysis_mask.sum())
all_n = len(lte_dl)
print(f"Anomaly analysis rows: {analysis_n:,} / {all_n:,} LTE-DL rows ({analysis_n / max(all_n, 1) * 100:.2f}%).")
print("Download activity context is retained only as metadata; RB usage is the main demand/resource-confidence signal.")

tp_active = tp.where(analysis_mask)
log_tp_active = np.log1p(tp_active)

# 1) Fixed threshold.
lte_dl["low_tp_fixed_flag"] = analysis_mask & (tp < LOW_TP_FIXED_MBPS)
lte_dl["score_fixed_low_tp"] = ((LOW_TP_FIXED_MBPS - tp) / LOW_TP_FIXED_MBPS).clip(lower=0, upper=1)
lte_dl["score_fixed_low_tp"] = lte_dl["score_fixed_low_tp"].where(lte_dl["low_tp_fixed_flag"], 0.0)

fixed_threshold_pct_analysis = float(lte_dl["low_tp_fixed_flag"].sum() / max(analysis_n, 1) * 100)
fixed_threshold_pct_all = float(lte_dl["low_tp_fixed_flag"].sum() / max(all_n, 1) * 100)
print(
    f"LOW_TP_FIXED_MBPS={LOW_TP_FIXED_MBPS:g} Mbps flags "
    f"{fixed_threshold_pct_analysis:.2f}% of analyzed LTE-DL rows "
    f"({fixed_threshold_pct_all:.2f}% of all LTE-DL rows)."
)

# 2) Global percentile lower-tail threshold calculated on analyzable rows only.
global_p10 = tp_active.quantile(0.10)
global_p25 = tp_active.quantile(0.25)
lte_dl["global_p10_tp_threshold"] = global_p10
lte_dl["global_p25_tp_threshold"] = global_p25
lte_dl["low_tp_global_p10_flag"] = analysis_mask & (tp <= global_p10)
lte_dl["score_global_p10_low_tp"] = ((global_p10 - tp) / max(global_p10, 1e-9)).clip(lower=0, upper=1)
lte_dl["score_global_p10_low_tp"] = lte_dl["score_global_p10_low_tp"].where(lte_dl["low_tp_global_p10_flag"], 0.0)

# 3) Session percentile threshold based only on valid LTE-DL samples.
if "id" in lte_dl.columns:
    tmp_session = lte_dl[["id"]].copy()
    tmp_session["_tp_active"] = tp_active

    session_group = tmp_session.groupby("id")["_tp_active"]
    session_q10 = session_group.transform(lambda x: x.dropna().quantile(0.10) if x.notna().any() else np.nan)
    session_q25 = session_group.transform(lambda x: x.dropna().quantile(0.25) if x.notna().any() else np.nan)
    session_rows = session_group.transform("count")
    session_mean = session_group.transform("mean")
    session_median = session_group.transform("median")
    session_low_tp_ratio = session_group.transform(
        lambda x: float((x.dropna() < LOW_TP_FIXED_MBPS).mean()) if x.notna().any() else np.nan
    )
else:
    session_q10 = pd.Series(global_p10, index=lte_dl.index)
    session_q25 = pd.Series(global_p25, index=lte_dl.index)
    session_rows = pd.Series(analysis_n, index=lte_dl.index)
    session_mean = pd.Series(tp_active.mean(), index=lte_dl.index)
    session_median = pd.Series(tp_active.median(), index=lte_dl.index)
    session_low_tp_ratio = pd.Series(float((tp_active.dropna() < LOW_TP_FIXED_MBPS).mean()), index=lte_dl.index)

# Fill sessions without valid LTE-DL samples from global LTE-DL values so outputs remain numeric.
session_q10 = session_q10.fillna(global_p10)
session_q25 = session_q25.fillna(global_p25)
session_mean = session_mean.fillna(tp_active.mean())
session_median = session_median.fillna(tp_active.median())
session_low_tp_ratio = session_low_tp_ratio.fillna(float((tp_active.dropna() < LOW_TP_FIXED_MBPS).mean()))

lte_dl["session_rows"] = session_rows.fillna(0).astype(int)
lte_dl["session_mean_tp"] = session_mean
lte_dl["session_median_tp"] = session_median
lte_dl["session_p10_tp_threshold"] = session_q10
lte_dl["session_p25_tp"] = session_q25
lte_dl["session_low_tp_ratio"] = session_low_tp_ratio

lte_dl["low_tp_session_p10_flag"] = (
    analysis_mask &
    (tp <= session_q10) &
    (session_q10 <= SESSION_P10_MAX_THRESHOLD_MBPS)
)
lte_dl["score_session_p10_low_tp"] = ((session_q10 - tp) / session_q10.replace(0, np.nan)).clip(lower=0, upper=1).fillna(0)
lte_dl["score_session_p10_low_tp"] = lte_dl["score_session_p10_low_tp"].where(lte_dl["low_tp_session_p10_flag"], 0.0)

# 4) Robust log z-score lower-tail method.
lte_dl["log_tp_modified_z"] = robust_mad_zscore(log_tp_active)
lte_dl["low_tp_robust_z_flag"] = analysis_mask & (lte_dl["log_tp_modified_z"] <= ROBUST_Z_LOWER_THRESHOLD)
lte_dl["score_robust_z_low_tp"] = (lte_dl["log_tp_modified_z"] / ROBUST_Z_LOWER_THRESHOLD).clip(lower=0, upper=1)
lte_dl["score_robust_z_low_tp"] = lte_dl["score_robust_z_low_tp"].where(lte_dl["low_tp_robust_z_flag"], 0.0).fillna(0.0)
print(
    f"Robust log modified-z min={lte_dl['log_tp_modified_z'].min(skipna=True):.3f}; "
    f"threshold={ROBUST_Z_LOWER_THRESHOLD:.1f}; "
    f"flagged={int(lte_dl['low_tp_robust_z_flag'].sum())} rows."
)

# 5) IQR lower-tail on log throughput using valid LTE-DL samples.
q1 = log_tp_active.quantile(0.25)
q3 = log_tp_active.quantile(0.75)
iqr = q3 - q1
log_iqr_lower_fence = q1 - 1.5 * iqr
lte_dl["log_iqr_lower_fence"] = log_iqr_lower_fence
lte_dl["low_tp_iqr_flag"] = analysis_mask & (np.log1p(tp) < log_iqr_lower_fence)
lte_dl["score_iqr_low_tp"] = ((log_iqr_lower_fence - np.log1p(tp)) / max(abs(log_iqr_lower_fence), 1e-9)).clip(lower=0, upper=1)
lte_dl["score_iqr_low_tp"] = lte_dl["score_iqr_low_tp"].where(lte_dl["low_tp_iqr_flag"], 0.0)

# 6) Rolling context inside each session.
# All valid LTE-DL rows are used as rolling values. Sampling is exactly 1 second, so the
# sample-based rolling window is also a directly interpretable seconds-based window.
lte_dl["_tp_for_active_rolling"] = tp.where(analysis_mask)
lte_dl["rolling_median_tp"] = rolling_stat_by_session(lte_dl, "_tp_for_active_rolling", ROLLING_WINDOW_SAMPLES, "median")
lte_dl["rolling_p25_tp"] = rolling_stat_by_session(lte_dl, "_tp_for_active_rolling", ROLLING_WINDOW_SAMPLES, "p25")
lte_dl["rolling_count"] = rolling_stat_by_session(lte_dl, "_tp_for_active_rolling", ROLLING_WINDOW_SAMPLES, "count")

lte_dl["rolling_tp_gap"] = lte_dl["rolling_median_tp"] - tp
lte_dl["rolling_tp_ratio"] = tp / lte_dl["rolling_median_tp"].replace(0, np.nan)

# Contrast anomaly: current sample suddenly falls from a locally healthy baseline.
lte_dl["rolling_drop_flag"] = (
    analysis_mask &
    (lte_dl["rolling_count"] >= MIN_ROLLING_SAMPLES) &
    (lte_dl["rolling_median_tp"] >= LOW_TP_FIXED_MBPS) &
    (lte_dl["rolling_tp_ratio"] <= ROLLING_DROP_RATIO_THRESHOLD) &
    (lte_dl["rolling_tp_gap"] >= SUDDEN_DROP_GAP_MBPS)
)
lte_dl["score_rolling_drop"] = (1 - lte_dl["rolling_tp_ratio"]).clip(lower=0, upper=1).fillna(0)
lte_dl["score_rolling_drop"] = lte_dl["score_rolling_drop"].where(lte_dl["rolling_drop_flag"], 0.0)

# Sustained-window context: the whole local LTE-DL window is poor, not just one sample.
lte_dl["rolling_bad_window_flag"] = (
    analysis_mask &
    (lte_dl["rolling_count"] >= MIN_ROLLING_SAMPLES) &
    (
        (lte_dl["rolling_median_tp"] < ROLLING_BAD_WINDOW_MEDIAN_MBPS) |
        (lte_dl["rolling_p25_tp"] < ROLLING_BAD_WINDOW_P25_MBPS)
    )
)

lte_dl["rolling_sustained_degradation_flag"] = lte_dl["rolling_bad_window_flag"] & (
    lte_dl["low_tp_fixed_flag"] |
    lte_dl["low_tp_global_p10_flag"] |
    lte_dl["low_tp_session_p10_flag"] |
    lte_dl["low_tp_iqr_flag"] |
    (tp <= lte_dl["rolling_p25_tp"])
)
lte_dl["score_rolling_bad_window"] = np.maximum(
    ((ROLLING_BAD_WINDOW_MEDIAN_MBPS - lte_dl["rolling_median_tp"]) / ROLLING_BAD_WINDOW_MEDIAN_MBPS).clip(lower=0, upper=1).fillna(0),
    ((ROLLING_BAD_WINDOW_P25_MBPS - lte_dl["rolling_p25_tp"]) / ROLLING_BAD_WINDOW_P25_MBPS).clip(lower=0, upper=1).fillna(0),
)
lte_dl["score_rolling_bad_window"] = lte_dl["score_rolling_bad_window"].where(lte_dl["rolling_sustained_degradation_flag"], 0.0)

# 7) Bad-session context and sample-level bad-session anomaly.
lte_dl["bad_session_flag"] = (
    (lte_dl["session_rows"] >= SESSION_MIN_ROWS_FOR_BAD_SESSION) &
    (
        (lte_dl["session_median_tp"] < BAD_SESSION_MEDIAN_MBPS) |
        (lte_dl["session_p25_tp"] < BAD_SESSION_P25_MBPS) |
        (lte_dl["session_low_tp_ratio"] >= BAD_SESSION_LOW_TP_RATIO_THRESHOLD)
    )
)
lte_dl["bad_session_sample_flag"] = analysis_mask & lte_dl["bad_session_flag"] & (
    lte_dl["low_tp_fixed_flag"] |
    lte_dl["low_tp_global_p10_flag"] |
    lte_dl["low_tp_session_p10_flag"] |
    lte_dl["low_tp_iqr_flag"] |
    lte_dl["low_tp_robust_z_flag"]
)
lte_dl["score_bad_session"] = np.maximum.reduce([
    ((BAD_SESSION_MEDIAN_MBPS - lte_dl["session_median_tp"]) / BAD_SESSION_MEDIAN_MBPS).clip(lower=0, upper=1).fillna(0).values,
    ((BAD_SESSION_P25_MBPS - lte_dl["session_p25_tp"]) / BAD_SESSION_P25_MBPS).clip(lower=0, upper=1).fillna(0).values,
    (lte_dl["session_low_tp_ratio"] / BAD_SESSION_LOW_TP_RATIO_THRESHOLD).clip(lower=0, upper=1).fillna(0).values,
])
lte_dl["score_bad_session"] = pd.Series(lte_dl["score_bad_session"], index=lte_dl.index).where(lte_dl["bad_session_sample_flag"], 0.0)

# 8) Sudden drop compared with previous valid LTE-DL sample in the same session.
lte_dl["prev_tp"] = np.nan
if "id" in lte_dl.columns:
    for _, idx in lte_dl[analysis_mask].groupby("id", sort=False).groups.items():
        idx = list(idx)
        lte_dl.loc[idx, "prev_tp"] = lte_dl.loc[idx, "actual_lte_dl_throughput"].shift(1)
else:
    analysis_idx = lte_dl.index[analysis_mask]
    lte_dl.loc[analysis_idx, "prev_tp"] = lte_dl.loc[analysis_idx, "actual_lte_dl_throughput"].shift(1)

lte_dl["tp_drop_from_prev"] = lte_dl["prev_tp"] - tp
lte_dl["tp_ratio_to_prev"] = tp / lte_dl["prev_tp"].replace(0, np.nan)
lte_dl["sudden_drop_flag"] = (
    analysis_mask &
    (lte_dl["prev_tp"] >= SUDDEN_DROP_PREV_MIN_MBPS) &
    (lte_dl["tp_ratio_to_prev"] <= SUDDEN_DROP_RATIO_THRESHOLD) &
    (lte_dl["tp_drop_from_prev"] >= SUDDEN_DROP_GAP_MBPS)
)
lte_dl["score_sudden_drop"] = (1 - lte_dl["tp_ratio_to_prev"]).clip(lower=0, upper=1).fillna(0)
lte_dl["score_sudden_drop"] = lte_dl["score_sudden_drop"].where(lte_dl["sudden_drop_flag"], 0.0)

print("Global LTE-DL-row P10 throughput threshold:", round(float(global_p10), 3), "Mbps")
print("Global LTE-DL-row P25 throughput threshold:", round(float(global_p25), 3), "Mbps")
print("Rolling bad-window context rows:", int(lte_dl["rolling_bad_window_flag"].sum()))
print("Rolling sustained-degradation sample rows:", int(lte_dl["rolling_sustained_degradation_flag"].sum()))
print("Bad-session context rows:", int(lte_dl["bad_session_flag"].sum()))
print("Bad-session low-sample rows:", int(lte_dl["bad_session_sample_flag"].sum()))

# =========================
# 12B. Data-driven threshold calibration, overlap, and low-tail consensus
# =========================

# Keep P10, IQR, and robust MAD as separate visible detectors. They are valuable because
# they learn the low tail from the data rather than depending on one domain threshold.
# For fusion, however, they are correlated views of LOW_LEVEL evidence and must not be
# counted as separate independent families.

log_med = log_tp_active.median(skipna=True)
log_mad = (log_tp_active - log_med).abs().median(skipna=True)
if pd.notna(log_mad) and log_mad > 0:
    robust_mad_cutoff_log = log_med + (ROBUST_Z_LOWER_THRESHOLD * log_mad / 0.6745)
    robust_mad_cutoff_mbps = float(np.expm1(robust_mad_cutoff_log))
else:
    robust_mad_cutoff_mbps = np.nan

iqr_cutoff_mbps = float(np.expm1(log_iqr_lower_fence)) if pd.notna(log_iqr_lower_fence) else np.nan
session_p10_median = float(lte_dl.loc[analysis_mask, "session_p10_tp_threshold"].median())

lte_dl["low_tail_robust_consensus_count"] = pd.concat([
    lte_dl["low_tp_global_p10_flag"].fillna(False).astype(int),
    lte_dl["low_tp_iqr_flag"].fillna(False).astype(int),
    lte_dl["low_tp_robust_z_flag"].fillna(False).astype(int),
], axis=1).sum(axis=1)
lte_dl["low_tail_robust_consensus_flag"] = lte_dl["low_tail_robust_consensus_count"] >= 2
lte_dl["low_tail_robust_consensus_strength_0_1"] = lte_dl["low_tail_robust_consensus_count"] / 3.0

threshold_rows = [
    ("fixed_domain_reference", LOW_TP_FIXED_MBPS, "Domain reference; not the only detector."),
    ("global_p10", float(global_p10), "Data-driven bottom 10% threshold."),
    ("median_session_p10", session_p10_median, "Typical session-relative bottom 10% threshold."),
    ("iqr_lower_fence", iqr_cutoff_mbps, "Distribution-adaptive extreme lower fence in log-throughput."),
    ("robust_mad_modified_z_cutoff", robust_mad_cutoff_mbps, "Robust distribution-adaptive extreme tail cutoff."),
]
threshold_calibration_report = pd.DataFrame(threshold_rows, columns=["threshold_method", "threshold_mbps", "interpretation"])
threshold_calibration_report["distance_from_fixed_10mbps"] = threshold_calibration_report["threshold_mbps"] - LOW_TP_FIXED_MBPS

flag_map = {
    "global_p10": "low_tp_global_p10_flag",
    "iqr_lower_fence": "low_tp_iqr_flag",
    "robust_mad_modified_z_cutoff": "low_tp_robust_z_flag",
}
threshold_calibration_report["flagged_rows"] = threshold_calibration_report["threshold_method"].map(
    lambda m: int(lte_dl[flag_map[m]].sum()) if m in flag_map else np.nan
)
threshold_calibration_report["flagged_pct_analysis"] = threshold_calibration_report["threshold_method"].map(
    lambda m: float(lte_dl[flag_map[m]].sum() / max(analysis_n, 1) * 100) if m in flag_map else np.nan
)

robust_method_flags = {
    "global_p10": lte_dl["low_tp_global_p10_flag"].fillna(False).astype(bool),
    "iqr": lte_dl["low_tp_iqr_flag"].fillna(False).astype(bool),
    "robust_mad": lte_dl["low_tp_robust_z_flag"].fillna(False).astype(bool),
}
overlap_rows = []
for a_name, a in robust_method_flags.items():
    for b_name, b in robust_method_flags.items():
        inter = int((a & b).sum())
        union = int((a | b).sum())
        overlap_rows.append({
            "method_a": a_name, "method_b": b_name,
            "intersection_rows": inter, "union_rows": union,
            "jaccard": inter / union if union else np.nan,
        })
low_tail_overlap_matrix = pd.DataFrame(overlap_rows)

# A compact validation verdict: fixed 10 Mbps is treated as a useful domain anchor when it
# lies in the broad neighborhood of the empirical low-tail cutoffs; no automatic retuning is
# performed because P10/IQR/MAD already provide data-adaptive coverage.
empirical_cutoffs = pd.Series([global_p10, session_p10_median, iqr_cutoff_mbps, robust_mad_cutoff_mbps], dtype=float).dropna()
if len(empirical_cutoffs):
    empirical_q25, empirical_q75 = empirical_cutoffs.quantile([0.25, 0.75])
    fixed_threshold_validation = "SUPPORTED_AS_DOMAIN_ANCHOR" if (LOW_TP_FIXED_MBPS >= empirical_q25 * 0.5 and LOW_TP_FIXED_MBPS <= empirical_q75 * 2.0) else "REVIEW_DOMAIN_ANCHOR"
else:
    fixed_threshold_validation = "INSUFFICIENT_EMPIRICAL_CUTOFFS"
threshold_calibration_report["fixed_10mbps_validation"] = fixed_threshold_validation

save_table(threshold_calibration_report, "statistical_threshold_calibration_report.csv", category="key")
save_table(low_tail_overlap_matrix, "statistical_low_tail_method_overlap.csv", category="key")

print("Data-driven low-tail calibration:")
display(threshold_calibration_report.round(4))
print("Low-tail consensus rows (>=2 of global P10 / IQR / robust MAD):", int(lte_dl["low_tail_robust_consensus_flag"].sum()))
display(low_tail_overlap_matrix.round(4))

# =========================
