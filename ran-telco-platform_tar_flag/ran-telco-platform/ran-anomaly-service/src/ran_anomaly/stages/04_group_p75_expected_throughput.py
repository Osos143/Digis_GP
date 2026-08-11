"""
Stage 04: group p75 expected throughput
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 1282-1711). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 13. Group-based P75 expected throughput with fallback hierarchy
# =========================

# Discretize conditions. These bins match the calibrated real-drive-test thresholds.
lte_dl["sinr_bin_for_expected"] = pd.cut(
    lte_dl["lte_sinr"],
    bins=[-50, SINR_FAIR_MIN_DB, SINR_GOOD_MIN_DB, SINR_EXCELLENT_MIN_DB, 80],
    labels=["Poor", "Fair", "Good", "Excellent"],
    include_lowest=True,
    right=False,
)
lte_dl["rsrp_bin_for_expected"] = pd.cut(
    lte_dl["lte_rsrp"],
    bins=[-160, RSRP_FAIR_MIN_DBM, RSRP_GOOD_MIN_DBM, RSRP_EXCELLENT_MIN_DBM, 0],
    labels=["Poor", "Fair", "Good", "Excellent"],
    include_lowest=True,
    right=False,
)
lte_dl["rsrq_bin_for_expected"] = pd.cut(
    lte_dl["lte_rsrq"],
    bins=[-40, RSRQ_FAIR_MIN_DB, RSRQ_GOOD_MIN_DB, RSRQ_EXCELLENT_MIN_DB, 0],
    labels=["Poor", "Fair", "Good", "Excellent"],
    include_lowest=True,
    right=False,
)

def _safe_to_clean_str(series: pd.Series) -> pd.Series:
    if series is None or not isinstance(series, pd.Series):
        return pd.Series(np.nan)
    def _convert_val(val):
        if pd.isna(val):
            return np.nan
        try:
            f = float(val)
            if np.isnan(f):
                return np.nan
            if f.is_integer():
                return str(int(f))
            return str(f)
        except (ValueError, TypeError):
            s = str(val).strip()
            return s if s and s not in {"nan", "None", "<NA>", "null"} else np.nan
    return series.apply(_convert_val)

lte_dl["carrier_count_for_expected"] = lte_dl["carrier_count"].round().clip(lower=1, upper=4)
lte_dl["serving_band_for_expected"] = _safe_to_clean_str(lte_dl["serving_band"]) if "serving_band" in lte_dl.columns else np.nan
lte_dl["serving_earfcn_for_expected"] = _safe_to_clean_str(lte_dl["serving_earfcn"]) if "serving_earfcn" in lte_dl.columns else np.nan

# Radio-only P75 excludes RB on purpose. It answers:
# "Given radio/CA/band/frequency context, what throughput was realistically achievable?"
EXPECTED_HIERARCHY_RADIO = [
    (1, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected", "serving_band_for_expected", "serving_earfcn_for_expected"]),
    (2, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected", "serving_band_for_expected"]),
    (3, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected"]),
    (4, ["sinr_bin_for_expected", "carrier_count_for_expected"]),
    (5, ["carrier_count_for_expected"]),
]

# RB-conditioned P75 includes RB demand bucket. It answers:
# "Given radio/CA/band/frequency context AND allocated RB resources, was throughput still unusually low?"
EXPECTED_HIERARCHY_RB = [
    (1, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected", "serving_band_for_expected", "serving_earfcn_for_expected", "rb_usage_bucket"]),
    (2, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected", "serving_band_for_expected", "rb_usage_bucket"]),
    (3, ["sinr_bin_for_expected", "rsrp_bin_for_expected", "carrier_count_for_expected", "rb_usage_bucket"]),
    (4, ["sinr_bin_for_expected", "carrier_count_for_expected", "rb_usage_bucket"]),
    (5, ["carrier_count_for_expected", "rb_usage_bucket"]),
]


def bootstrap_quantile_ci(
    values: pd.Series,
    q: float = P75_QUANTILE,
    n_boot: int = P75_CI_BOOTSTRAP_N,
    alpha: float = P75_CI_ALPHA,
    seed: int = RANDOM_SEED,
) -> Tuple[float, float]:
    """Bootstrap confidence interval for a quantile.

    The interval is used as a stricter guard for P75 underperformance. If a group is
    too small or invalid, NaN bounds are returned and the point P75 remains as context.
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if len(arr) < MIN_GROUP_SIZE_FOR_P75:
        return np.nan, np.nan
    rng = np.random.default_rng(seed + len(arr))
    boots = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        boots[i] = np.quantile(rng.choice(arr, size=len(arr), replace=True), q)
    return float(np.quantile(boots, alpha / 2)), float(np.quantile(boots, 1 - alpha / 2))


def build_expected_p75_with_fallback(
    df: pd.DataFrame,
    target_col: str,
    hierarchy: List[Tuple[int, List[str]]],
    min_group_size: int = MIN_GROUP_SIZE_FOR_P75,
    quantile: float = P75_QUANTILE,
    reference_mask: Optional[pd.Series] = None,
    reference_name: str = "radio",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Assign group-P75 expected throughput using increasingly broad fallback groups.

    P75 is calculated from reference rows only. The P75 value is then merged back to
    all LTE-DL rows for context. The function records fallback level and group count
    because sparse/broad P75 references can inflate anomaly counts.
    """
    out = df.copy()
    out["expected_tp_p75"] = np.nan
    out["expected_tp_source_level"] = np.nan
    out["expected_tp_group_n"] = np.nan
    out["expected_tp_group_cols"] = ""
    out["expected_tp_p75_ci_low"] = np.nan
    out["expected_tp_p75_ci_high"] = np.nan
    out["expected_tp_p75_ci_width"] = np.nan

    if reference_mask is None:
        reference_mask = pd.Series(True, index=out.index)
    else:
        reference_mask = reference_mask.reindex(out.index).fillna(False).astype(bool)

    ref = out.loc[reference_mask].copy()
    reference_scope = "all_valid_lte_dl_rows"
    if ref.empty:
        print(f"Warning: P75 reference mask is empty for {reference_name}. Falling back to all rows.")
        ref = out.copy()
        reference_scope = "all_rows_fallback"

    reference_tables = []

    for level, cols in hierarchy:
        available_cols = [c for c in cols if c in out.columns]
        if not available_cols:
            continue

        ref_group_base = ref.dropna(subset=available_cols + [target_col])
        grouped = (
            ref_group_base
            .groupby(available_cols, dropna=False)[target_col]
            .agg(
                expected_tp_p75=lambda s: s.quantile(quantile),
                expected_tp_median="median",
                expected_tp_mean="mean",
                expected_tp_group_n="count",
                expected_tp_p75_ci_low=lambda s: bootstrap_quantile_ci(s, q=quantile)[0],
                expected_tp_p75_ci_high=lambda s: bootstrap_quantile_ci(s, q=quantile)[1],
            )
            .reset_index()
        )
        grouped["expected_tp_p75_ci_width"] = grouped["expected_tp_p75_ci_high"] - grouped["expected_tp_p75_ci_low"]

        grouped = grouped[grouped["expected_tp_group_n"] >= min_group_size].copy()
        grouped["fallback_level"] = level
        grouped["group_cols"] = ",".join(available_cols)
        grouped["reference_scope"] = reference_scope
        grouped["reference_name"] = reference_name
        reference_tables.append(grouped)

        if grouped.empty:
            continue

        pending_idx = out[out["expected_tp_p75"].isna()].index
        pending_keys = out.loc[pending_idx, available_cols].reset_index()
        merged = pending_keys.merge(
            grouped[available_cols + ["expected_tp_p75", "expected_tp_group_n", "expected_tp_p75_ci_low", "expected_tp_p75_ci_high", "expected_tp_p75_ci_width"]],
            on=available_cols,
            how="left",
        ).set_index("index")

        valid = merged["expected_tp_p75"].notna()
        assign_idx = merged.index[valid]
        out.loc[assign_idx, "expected_tp_p75"] = merged.loc[assign_idx, "expected_tp_p75"]
        out.loc[assign_idx, "expected_tp_source_level"] = level
        out.loc[assign_idx, "expected_tp_group_n"] = merged.loc[assign_idx, "expected_tp_group_n"]
        out.loc[assign_idx, "expected_tp_group_cols"] = ",".join(available_cols)
        out.loc[assign_idx, "expected_tp_p75_ci_low"] = merged.loc[assign_idx, "expected_tp_p75_ci_low"]
        out.loc[assign_idx, "expected_tp_p75_ci_high"] = merged.loc[assign_idx, "expected_tp_p75_ci_high"]
        out.loc[assign_idx, "expected_tp_p75_ci_width"] = merged.loc[assign_idx, "expected_tp_p75_ci_width"]

    # Final global P75 fallback. Useful as context, not trusted for strict anomalies.
    global_p75 = ref[target_col].quantile(quantile)
    global_n = ref[target_col].notna().sum()
    global_ci_low, global_ci_high = bootstrap_quantile_ci(ref[target_col], q=quantile)
    global_ci_width = global_ci_high - global_ci_low if pd.notna(global_ci_low) and pd.notna(global_ci_high) else np.nan
    missing_expected = out["expected_tp_p75"].isna()
    out.loc[missing_expected, "expected_tp_p75"] = global_p75
    out.loc[missing_expected, "expected_tp_source_level"] = 6
    out.loc[missing_expected, "expected_tp_group_n"] = global_n
    out.loc[missing_expected, "expected_tp_group_cols"] = "GLOBAL"
    out.loc[missing_expected, "expected_tp_p75_ci_low"] = global_ci_low
    out.loc[missing_expected, "expected_tp_p75_ci_high"] = global_ci_high
    out.loc[missing_expected, "expected_tp_p75_ci_width"] = global_ci_width

    global_ref = pd.DataFrame([{
        "expected_tp_p75": global_p75,
        "expected_tp_median": ref[target_col].median(),
        "expected_tp_mean": ref[target_col].mean(),
        "expected_tp_group_n": global_n,
        "expected_tp_p75_ci_low": global_ci_low,
        "expected_tp_p75_ci_high": global_ci_high,
        "expected_tp_p75_ci_width": global_ci_width,
        "fallback_level": 6,
        "group_cols": "GLOBAL",
        "reference_scope": reference_scope,
        "reference_name": reference_name,
    }])
    reference_tables.append(global_ref)

    expected_reference = pd.concat(reference_tables, ignore_index=True, sort=False) if reference_tables else global_ref
    return out, expected_reference


# P75 references are built from all valid LTE-DL rows. Download activity context is metadata only.
p75_reference_mask = lte_dl["actual_lte_dl_throughput"].notna() & (lte_dl["actual_lte_dl_throughput"] >= 0)

# -------------------------
# A) Radio-condition P75
# -------------------------
lte_dl, expected_reference_radio = build_expected_p75_with_fallback(
    lte_dl,
    target_col="actual_lte_dl_throughput",
    hierarchy=EXPECTED_HIERARCHY_RADIO,
    reference_mask=p75_reference_mask,
    reference_name="radio_condition",
)

# Keep legacy column names for compatibility. Also create explicit radio-P75 aliases.
lte_dl["expected_tp_radio_p75"] = lte_dl["expected_tp_p75"]
lte_dl["expected_tp_radio_source_level"] = lte_dl["expected_tp_source_level"]
lte_dl["expected_tp_radio_group_n"] = lte_dl["expected_tp_group_n"]
lte_dl["expected_tp_radio_group_cols"] = lte_dl["expected_tp_group_cols"]
lte_dl["expected_tp_radio_p75_ci_low"] = lte_dl["expected_tp_p75_ci_low"]
lte_dl["expected_tp_radio_p75_ci_high"] = lte_dl["expected_tp_p75_ci_high"]
lte_dl["expected_tp_radio_p75_ci_width"] = lte_dl["expected_tp_p75_ci_width"]

lte_dl["expected_tp_reliable_flag"] = (
    (lte_dl["expected_tp_radio_source_level"] <= MAX_RELIABLE_P75_FALLBACK_LEVEL) &
    (lte_dl["expected_tp_radio_group_n"] >= MIN_RELIABLE_P75_GROUP_N)
)
lte_dl["expected_tp_confidence"] = np.select(
    [
        lte_dl["expected_tp_reliable_flag"],
        (lte_dl["expected_tp_radio_source_level"] <= 5) & (lte_dl["expected_tp_radio_group_n"] >= MIN_RELIABLE_P75_GROUP_N),
    ],
    ["high", "medium"],
    default="low_global_or_sparse",
)

lte_dl["throughput_gap_p75"] = lte_dl["expected_tp_radio_p75"] - lte_dl["actual_lte_dl_throughput"]
lte_dl["throughput_ratio_p75"] = lte_dl["actual_lte_dl_throughput"] / lte_dl["expected_tp_radio_p75"].replace(0, np.nan)
lte_dl["log_residual_p75"] = np.log1p(lte_dl["actual_lte_dl_throughput"]) - np.log1p(lte_dl["expected_tp_radio_p75"])
lte_dl["score_group_p75_gap_raw"] = (1 - lte_dl["throughput_ratio_p75"]).clip(lower=0, upper=1).fillna(0)
radio_expected_for_strict = lte_dl["expected_tp_radio_p75_ci_low"].where(lte_dl["expected_tp_radio_p75_ci_low"].notna(), lte_dl["expected_tp_radio_p75"])
lte_dl["throughput_gap_p75_ci_low"] = radio_expected_for_strict - lte_dl["actual_lte_dl_throughput"]
lte_dl["throughput_ratio_p75_ci_low"] = lte_dl["actual_lte_dl_throughput"] / radio_expected_for_strict.replace(0, np.nan)

# Demand-aware strict radio-P75 gate.
rb_reliable_global = bool(lte_dl["rb_usage_evidence_reliable_flag"].fillna(False).any()) if "rb_usage_evidence_reliable_flag" in lte_dl.columns else False
if REQUIRE_RB_DEMAND_FOR_STRICT_P75 and rb_reliable_global and "rb_medium_or_high_usage_flag" in lte_dl.columns:
    rb_demand_ok_for_p75 = lte_dl["rb_medium_or_high_usage_flag"].fillna(False).astype(bool)
else:
    rb_demand_ok_for_p75 = pd.Series(True, index=lte_dl.index)

lte_dl["p75_demand_confirmed_flag"] = rb_demand_ok_for_p75

lte_dl["underperform_vs_p75_context_flag"] = (
    p75_reference_mask &
    (lte_dl["expected_tp_radio_p75"] >= MIN_EXPECTED_TP_MBPS_FOR_UNDERPERFORMANCE) &
    (lte_dl["throughput_ratio_p75"] <= UNDERPERFORMANCE_RATIO_THRESHOLD) &
    (lte_dl["throughput_gap_p75"] >= UNDERPERFORMANCE_GAP_MBPS)
)
lte_dl["p75_underperformance_demand_unknown_context_flag"] = (
    lte_dl["underperform_vs_p75_context_flag"] &
    lte_dl["expected_tp_reliable_flag"] &
    ~rb_demand_ok_for_p75
)
lte_dl["underperform_vs_p75_flag"] = (
    p75_reference_mask &
    lte_dl["expected_tp_reliable_flag"] &
    rb_demand_ok_for_p75 &
    (radio_expected_for_strict >= MIN_EXPECTED_TP_MBPS_FOR_UNDERPERFORMANCE) &
    (lte_dl["throughput_ratio_p75_ci_low"] <= UNDERPERFORMANCE_RATIO_THRESHOLD) &
    (lte_dl["throughput_gap_p75_ci_low"] >= UNDERPERFORMANCE_GAP_MBPS)
)
lte_dl["score_group_p75_gap"] = lte_dl["score_group_p75_gap_raw"].where(lte_dl["underperform_vs_p75_flag"], 0.0)

# -------------------------
# B) RB-conditioned P75
# -------------------------
rb_conditioned_available = (
    USE_RB_CONDITIONED_P75 and
    "rb_usage_bucket" in lte_dl.columns and
    rb_reliable_global
)

if rb_conditioned_available:
    tmp_rb, expected_reference_rb = build_expected_p75_with_fallback(
        lte_dl,
        target_col="actual_lte_dl_throughput",
        hierarchy=EXPECTED_HIERARCHY_RB,
        reference_mask=p75_reference_mask,
        reference_name="rb_conditioned",
    )
    lte_dl["expected_tp_rb_conditioned_p75"] = tmp_rb["expected_tp_p75"]
    lte_dl["expected_tp_rb_source_level"] = tmp_rb["expected_tp_source_level"]
    lte_dl["expected_tp_rb_group_n"] = tmp_rb["expected_tp_group_n"]
    lte_dl["expected_tp_rb_group_cols"] = tmp_rb["expected_tp_group_cols"]
    lte_dl["expected_tp_rb_p75_ci_low"] = tmp_rb["expected_tp_p75_ci_low"]
    lte_dl["expected_tp_rb_p75_ci_high"] = tmp_rb["expected_tp_p75_ci_high"]
    lte_dl["expected_tp_rb_p75_ci_width"] = tmp_rb["expected_tp_p75_ci_width"]
else:
    expected_reference_rb = pd.DataFrame(columns=expected_reference_radio.columns)
    lte_dl["expected_tp_rb_conditioned_p75"] = np.nan
    lte_dl["expected_tp_rb_source_level"] = np.nan
    lte_dl["expected_tp_rb_group_n"] = np.nan
    lte_dl["expected_tp_rb_group_cols"] = "not_available"
    lte_dl["expected_tp_rb_p75_ci_low"] = np.nan
    lte_dl["expected_tp_rb_p75_ci_high"] = np.nan
    lte_dl["expected_tp_rb_p75_ci_width"] = np.nan

lte_dl["expected_tp_rb_reliable_flag"] = (
    rb_conditioned_available &
    (lte_dl["expected_tp_rb_source_level"] <= MAX_RELIABLE_P75_FALLBACK_LEVEL) &
    (lte_dl["expected_tp_rb_group_n"] >= MIN_RELIABLE_P75_GROUP_N)
)
lte_dl["expected_tp_rb_confidence"] = np.select(
    [
        lte_dl["expected_tp_rb_reliable_flag"],
        rb_conditioned_available & (lte_dl["expected_tp_rb_source_level"] <= 5) & (lte_dl["expected_tp_rb_group_n"] >= MIN_RELIABLE_P75_GROUP_N),
    ],
    ["high", "medium"],
    default="not_available_or_sparse",
)

lte_dl["throughput_gap_rb_p75"] = lte_dl["expected_tp_rb_conditioned_p75"] - lte_dl["actual_lte_dl_throughput"]
lte_dl["throughput_ratio_rb_p75"] = lte_dl["actual_lte_dl_throughput"] / lte_dl["expected_tp_rb_conditioned_p75"].replace(0, np.nan)
lte_dl["log_residual_rb_p75"] = np.log1p(lte_dl["actual_lte_dl_throughput"]) - np.log1p(lte_dl["expected_tp_rb_conditioned_p75"])
lte_dl["score_group_rb_p75_gap_raw"] = (1 - lte_dl["throughput_ratio_rb_p75"]).clip(lower=0, upper=1).fillna(0)
rb_expected_for_strict = lte_dl["expected_tp_rb_p75_ci_low"].where(lte_dl["expected_tp_rb_p75_ci_low"].notna(), lte_dl["expected_tp_rb_conditioned_p75"])
lte_dl["throughput_gap_rb_p75_ci_low"] = rb_expected_for_strict - lte_dl["actual_lte_dl_throughput"]
lte_dl["throughput_ratio_rb_p75_ci_low"] = lte_dl["actual_lte_dl_throughput"] / rb_expected_for_strict.replace(0, np.nan)

lte_dl["underperform_vs_rb_p75_context_flag"] = (
    p75_reference_mask &
    rb_conditioned_available &
    (lte_dl["expected_tp_rb_conditioned_p75"] >= MIN_EXPECTED_TP_MBPS_FOR_UNDERPERFORMANCE) &
    (lte_dl["throughput_ratio_rb_p75"] <= UNDERPERFORMANCE_RATIO_THRESHOLD) &
    (lte_dl["throughput_gap_rb_p75"] >= UNDERPERFORMANCE_GAP_MBPS)
)
lte_dl["underperform_vs_rb_p75_flag"] = (
    p75_reference_mask &
    rb_conditioned_available &
    lte_dl["expected_tp_rb_reliable_flag"] &
    rb_demand_ok_for_p75 &
    (rb_expected_for_strict >= MIN_EXPECTED_TP_MBPS_FOR_UNDERPERFORMANCE) &
    (lte_dl["throughput_ratio_rb_p75_ci_low"] <= UNDERPERFORMANCE_RATIO_THRESHOLD) &
    (lte_dl["throughput_gap_rb_p75_ci_low"] >= UNDERPERFORMANCE_GAP_MBPS)
)
lte_dl["score_group_rb_p75_gap"] = lte_dl["score_group_rb_p75_gap_raw"].where(lte_dl["underperform_vs_rb_p75_flag"], 0.0)

# Save references. The legacy file name is kept for compatibility and points to radio-P75.
save_table(expected_reference_radio, "expected_throughput_group_p75.csv")
save_table(expected_reference_radio, "expected_throughput_group_radio_p75.csv")
save_table(expected_reference_rb, "expected_throughput_group_rb_conditioned_p75.csv")
print("Radio P75 reference levels:")
display(expected_reference_radio["fallback_level"].value_counts().sort_index().to_frame("groups"))
if not expected_reference_rb.empty:
    print("RB-conditioned P75 reference levels:")
    display(expected_reference_rb["fallback_level"].value_counts().sort_index().to_frame("groups"))

p75_reliability_summary = (
    lte_dl.groupby(["expected_tp_radio_source_level", "expected_tp_confidence"], dropna=False)
    .agg(
        rows=("actual_lte_dl_throughput", "count"),
        median_expected_p75=("expected_tp_radio_p75", "median"),
        median_actual_tp=("actual_lte_dl_throughput", "median"),
        underperform_context_pct=("underperform_vs_p75_context_flag", "mean"),
        strict_underperform_pct=("underperform_vs_p75_flag", "mean"),
    )
    .reset_index()
    .sort_values(["expected_tp_radio_source_level", "expected_tp_confidence"])
)
for c in ["median_expected_p75", "median_actual_tp", "underperform_context_pct", "strict_underperform_pct"]:
    p75_reliability_summary[c] = p75_reliability_summary[c].astype(float).round(3)
p75_reliability_summary["underperform_context_pct"] *= 100
p75_reliability_summary["strict_underperform_pct"] *= 100
save_table(p75_reliability_summary, "p75_reliability_summary.csv")
display(p75_reliability_summary)

rb_p75_reliability_summary = (
    lte_dl.groupby(["expected_tp_rb_source_level", "expected_tp_rb_confidence"], dropna=False)
    .agg(
        rows=("actual_lte_dl_throughput", "count"),
        median_expected_rb_p75=("expected_tp_rb_conditioned_p75", "median"),
        median_actual_tp=("actual_lte_dl_throughput", "median"),
        underperform_context_pct=("underperform_vs_rb_p75_context_flag", "mean"),
        strict_underperform_pct=("underperform_vs_rb_p75_flag", "mean"),
    )
    .reset_index()
    .sort_values(["expected_tp_rb_source_level", "expected_tp_rb_confidence"])
)
for c in ["median_expected_rb_p75", "median_actual_tp", "underperform_context_pct", "strict_underperform_pct"]:
    rb_p75_reliability_summary[c] = rb_p75_reliability_summary[c].astype(float).round(3)
rb_p75_reliability_summary["underperform_context_pct"] *= 100
rb_p75_reliability_summary["strict_underperform_pct"] *= 100
save_table(rb_p75_reliability_summary, "rb_conditioned_p75_reliability_summary.csv")
display(rb_p75_reliability_summary)

p75_diagnostics = pd.DataFrame([
    {
        "scope": "all_lte_dl_rows_radio_p75",
        "rows": len(lte_dl),
        "mean_actual_tp": lte_dl["actual_lte_dl_throughput"].mean(),
        "median_actual_tp": lte_dl["actual_lte_dl_throughput"].median(),
        "mean_expected_p75": lte_dl["expected_tp_radio_p75"].mean(),
        "median_expected_p75": lte_dl["expected_tp_radio_p75"].median(),
        "underperform_context_pct": lte_dl["underperform_vs_p75_context_flag"].mean() * 100,
        "strict_underperform_pct": lte_dl["underperform_vs_p75_flag"].mean() * 100,
    },
    {
        "scope": "analysis_rows_all_valid_lte_dl_radio_p75",
        "rows": int(p75_reference_mask.sum()),
        "mean_actual_tp": lte_dl.loc[p75_reference_mask, "actual_lte_dl_throughput"].mean(),
        "median_actual_tp": lte_dl.loc[p75_reference_mask, "actual_lte_dl_throughput"].median(),
        "mean_expected_p75": lte_dl.loc[p75_reference_mask, "expected_tp_radio_p75"].mean(),
        "median_expected_p75": lte_dl.loc[p75_reference_mask, "expected_tp_radio_p75"].median(),
        "underperform_context_pct": lte_dl.loc[p75_reference_mask, "underperform_vs_p75_context_flag"].mean() * 100,
        "strict_underperform_pct": lte_dl.loc[p75_reference_mask, "underperform_vs_p75_flag"].mean() * 100,
    },
    {
        "scope": "all_lte_dl_rows_rb_conditioned_p75",
        "rows": len(lte_dl),
        "mean_actual_tp": lte_dl["actual_lte_dl_throughput"].mean(),
        "median_actual_tp": lte_dl["actual_lte_dl_throughput"].median(),
        "mean_expected_p75": lte_dl["expected_tp_rb_conditioned_p75"].mean(),
        "median_expected_p75": lte_dl["expected_tp_rb_conditioned_p75"].median(),
        "underperform_context_pct": lte_dl["underperform_vs_rb_p75_context_flag"].mean() * 100,
        "strict_underperform_pct": lte_dl["underperform_vs_rb_p75_flag"].mean() * 100,
    },
])
for col in ["mean_actual_tp", "median_actual_tp", "mean_expected_p75", "median_expected_p75", "underperform_context_pct", "strict_underperform_pct"]:
    p75_diagnostics[col] = p75_diagnostics[col].astype(float).round(3)
save_table(p75_diagnostics, "p75_expected_throughput_diagnostics.csv")
display(p75_diagnostics)


# =========================
