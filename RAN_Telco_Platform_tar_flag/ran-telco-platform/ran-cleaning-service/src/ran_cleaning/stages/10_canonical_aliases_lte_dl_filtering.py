"""
Stage 10: canonical aliases lte dl filtering
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1490-1697). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 10. Canonical aliases and LTE-DL filtering
# =========================

lte = drive_clean.copy()

# Canonical metadata and location aliases.
lte["latitude"] = to_numeric_series(lte, LAT_COL)
lte["longitude"] = to_numeric_series(lte, LON_COL)
lte["speed"] = to_numeric_series(lte, SPEED_COL)
lte["location_accuracy"] = to_numeric_series(lte, ACCURACY_COL)
lte["altitude"] = to_numeric_series(lte, ALTITUDE_COL)

# Canonical LTE target and context aliases.
lte["actual_lte_dl_throughput"] = to_numeric_series(lte, SOURCE_COLS["target_lte_dl_tp"]) * THROUGHPUT_TO_MBPS
lte["serving_pci"] = to_numeric_series(lte, SOURCE_COLS["serving_pci"])
lte["serving_earfcn"] = to_numeric_series(lte, SOURCE_COLS["serving_earfcn"])
lte["serving_band"] = to_numeric_series(lte, SOURCE_COLS["serving_band"])
lte["serving_eci"] = to_numeric_series(lte, SOURCE_COLS["serving_eci"])
lte["serving_enodebid"] = to_numeric_series(lte, SOURCE_COLS["serving_enodebid"])
lte["serving_lci"] = to_numeric_series(lte, SOURCE_COLS["serving_lci"])

# Radio/PHY/CA aliases.
for alias in [
    "lte_rsrp", "lte_rsrq", "lte_sinr", "lte_rssi", "lte_cqi", "lte_mcs", "lte_bler",
    "lte_rank", "lte_rb_count", "lte_agg_rb_dl", "lte_bandwidth_dl", "lte_agg_bandwidth_dl",
    "carrier_count", "scell1_rsrp", "scell1_rsrq", "scell1_sinr", "scell1_cqi",
    "scell1_mcs", "scell1_bler", "scell1_rb_count", "rach_latency",
]:
    lte[alias] = to_numeric_series(lte, SOURCE_COLS.get(alias))

# Categorical direct aliases.
for alias in ["rach_result", "rach_reason"]:
    src = SOURCE_COLS.get(alias)
    lte[alias] = lte[src] if src in lte.columns else np.nan

# Carrier count fallback: if missing, infer 2 carriers when SCell1 metrics exist, otherwise 1.
scell_present = lte[[c for c in ["scell1_rsrp", "scell1_sinr", "scell1_cqi", "scell1_rb_count"] if c in lte.columns]].notna().any(axis=1)
carrier_count_fallback = pd.Series(np.where(scell_present, 2, 1), index=lte.index, dtype="float64")
lte["carrier_count"] = lte["carrier_count"].fillna(carrier_count_fallback)

# Availability flags.
lte["has_lte_measurement"] = lte[["lte_rsrp", "lte_rsrq", "lte_sinr", "serving_pci", "serving_earfcn"]].notna().any(axis=1)
lte["has_lte_dl_throughput"] = lte["actual_lte_dl_throughput"].notna() & (lte["actual_lte_dl_throughput"] >= 0)

# Download-test filter from parsed id_test_type when available.
if "id_test_type" in lte.columns:
    lte["is_download_test"] = lte["id_test_type"].astype(str).str.contains("DL", case=False, na=False)
else:
    lte["is_download_test"] = True

filter_mask = lte["has_lte_measurement"] & lte["has_lte_dl_throughput"] & lte["is_download_test"]
lte_dl = lte.loc[filter_mask].copy().reset_index(drop=False).rename(columns={"index": "source_index"})

# Fallback warning: if the DL filter gives zero rows, use LTE throughput rows and let the analyst inspect id_test_type.
if lte_dl.empty:
    print("Warning: LTE-DL filter returned zero rows. Falling back to all LTE rows with valid DL throughput.")
    filter_mask = lte["has_lte_measurement"] & lte["has_lte_dl_throughput"]
    lte_dl = lte.loc[filter_mask].copy().reset_index(drop=False).rename(columns={"index": "source_index"})

print("LTE-DL modeling table shape:", lte_dl.shape)
print("Throughput target source column:", SOURCE_COLS["target_lte_dl_tp"])
print("Throughput stats in Mbps:")
display(lte_dl["actual_lte_dl_throughput"].describe(percentiles=[0.01, 0.05, 0.10, 0.25, 0.5, 0.75, 0.90, 0.95, 0.99]).to_frame())


# -------------------------
# Download activity-window context
# -------------------------

def add_download_activity_window_flags(
    samples: pd.DataFrame,
    activities: pd.DataFrame,
    session_col: str = "id",
    sample_time_col: str = "timestamp",
    activity_name_col: str = "Activity.Activity",
    activity_start_col: str = "Activity.Start TimeStamp_parsed",
    activity_end_col: str = "Activity.End TimeStamp_parsed",
    activity_status_col: str = "Activity.Status",
    activity_pattern: str = DOWNLOAD_ACTIVITY_NAME_PATTERN,
    warmup_seconds: int = DOWNLOAD_ACTIVITY_WARMUP_SECONDS,
    cooldown_seconds: int = DOWNLOAD_ACTIVITY_COOLDOWN_SECONDS,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Mark samples that fall inside HTTP/HTTPS download activity windows.

    Why this is needed:
    LTE-DL session rows may include script/activity timing such as HTTP transfer start/end.
    In earlier versions this was used as a hard anomaly-analysis mask. In the latest version
    it is retained only as context because the active/warmup/outside throughput distributions
    were close enough to analyze all valid LTE-DL rows together. RB usage is now the primary
    demand/resource-confidence signal.

    Returns:
    - samples with raw and analysis-window flags.
    - activity intervals used for filtering.
    """
    out = samples.copy()
    out["download_activity_window_raw_flag"] = False
    out["download_analysis_window_flag"] = True
    out["download_context_label"] = "activity_filter_not_available"

    if activities is None or activities.empty:
        return out, pd.DataFrame()

    required = {session_col, activity_name_col, activity_start_col, activity_end_col}
    if not required.issubset(activities.columns) or sample_time_col not in out.columns:
        return out, pd.DataFrame()

    acts = activities.copy()
    acts = acts[acts[activity_name_col].astype(str).str.contains(activity_pattern, case=False, na=False)].copy()
    if acts.empty:
        return out, pd.DataFrame()

    acts[activity_start_col] = pd.to_datetime(acts[activity_start_col], utc=True, errors="coerce")
    acts[activity_end_col] = pd.to_datetime(acts[activity_end_col], utc=True, errors="coerce")
    acts = acts.dropna(subset=[session_col, activity_start_col, activity_end_col]).copy()
    acts = acts[acts[activity_end_col] > acts[activity_start_col]].copy()
    if acts.empty:
        return out, pd.DataFrame()

    warmup = pd.to_timedelta(warmup_seconds, unit="s")
    cooldown = pd.to_timedelta(cooldown_seconds, unit="s")
    acts["download_raw_start_utc"] = acts[activity_start_col]
    acts["download_raw_end_utc"] = acts[activity_end_col]
    acts["download_analysis_start_utc"] = acts[activity_start_col] + warmup
    acts["download_analysis_end_utc"] = acts[activity_end_col] - cooldown

    # If the activity is too short for the warmup/cooldown margin, fall back to the raw window.
    invalid_analysis = acts["download_analysis_end_utc"] <= acts["download_analysis_start_utc"]
    acts.loc[invalid_analysis, "download_analysis_start_utc"] = acts.loc[invalid_analysis, "download_raw_start_utc"]
    acts.loc[invalid_analysis, "download_analysis_end_utc"] = acts.loc[invalid_analysis, "download_raw_end_utc"]

    out["_sample_timestamp_utc"] = pd.to_datetime(out[sample_time_col], utc=True, errors="coerce")
    out["download_analysis_window_flag"] = False
    out["download_context_label"] = "outside_download_activity"

    for sid, g in acts.groupby(session_col, sort=False):
        sample_idx = out.index[out[session_col].eq(sid) & out["_sample_timestamp_utc"].notna()]
        if len(sample_idx) == 0:
            continue

        sample_times = out.loc[sample_idx, "_sample_timestamp_utc"]
        raw_mask = pd.Series(False, index=sample_idx)
        analysis_mask = pd.Series(False, index=sample_idx)

        for _, act in g.iterrows():
            raw_mask |= sample_times.between(act["download_raw_start_utc"], act["download_raw_end_utc"], inclusive="both")
            analysis_mask |= sample_times.between(act["download_analysis_start_utc"], act["download_analysis_end_utc"], inclusive="both")

        out.loc[sample_idx, "download_activity_window_raw_flag"] |= raw_mask.values
        out.loc[sample_idx, "download_analysis_window_flag"] |= analysis_mask.values

    # Context labels.
    out.loc[out["download_activity_window_raw_flag"] & ~out["download_analysis_window_flag"], "download_context_label"] = "download_warmup_or_cooldown"
    out.loc[out["download_analysis_window_flag"], "download_context_label"] = "active_download_analysis_window"

    out = out.drop(columns=["_sample_timestamp_utc"])
    return out, acts.reset_index(drop=True)


if BUILD_DOWNLOAD_ACTIVITY_CONTEXT_FLAGS and "activity_table" in globals():
    lte_dl, download_activity_intervals = add_download_activity_window_flags(lte_dl, activity_table)
else:
    lte_dl["download_activity_window_raw_flag"] = False
    lte_dl["download_analysis_window_flag"] = True
    lte_dl["download_context_label"] = "activity_context_flags_disabled"
    download_activity_intervals = pd.DataFrame()

# If no valid download intervals are found, keep all LTE-DL rows analyzable rather than silently removing everything.
if BUILD_DOWNLOAD_ACTIVITY_CONTEXT_FLAGS and not bool(lte_dl["download_analysis_window_flag"].any()):
    print("Warning: no active HTTP/HTTPS download windows were detected. Falling back to analyzing all LTE-DL rows.")
    lte_dl["download_analysis_window_flag"] = True
    lte_dl["download_context_label"] = "activity_context_fallback_all_rows"

lte_dl["inactive_download_context_flag"] = ~lte_dl["download_analysis_window_flag"].fillna(True).astype(bool)

download_window_summary = (
    lte_dl["download_context_label"]
    .fillna("Unknown")
    .value_counts(dropna=False)
    .rename_axis("download_context_label")
    .reset_index(name="rows")
)
download_window_summary["pct_of_lte_dl_rows"] = (download_window_summary["rows"] / max(len(lte_dl), 1) * 100).round(3)
save_table(download_window_summary, "download_activity_window_summary.csv")
display(download_window_summary)

if not download_activity_intervals.empty:
    interval_summary = download_activity_intervals.copy()
    interval_summary["raw_duration_seconds"] = (
        interval_summary["download_raw_end_utc"] - interval_summary["download_raw_start_utc"]
    ).dt.total_seconds()
    interval_summary["analysis_duration_seconds"] = (
        interval_summary["download_analysis_end_utc"] - interval_summary["download_analysis_start_utc"]
    ).dt.total_seconds()
    keep_cols = [
        c for c in [
            "id", "Activity.Activity", "Activity.Status", "Activity.Tech",
            "download_raw_start_utc", "download_raw_end_utc",
            "download_analysis_start_utc", "download_analysis_end_utc",
            "raw_duration_seconds", "analysis_duration_seconds",
        ]
        if c in interval_summary.columns
    ]
    save_table(interval_summary[keep_cols], "download_activity_intervals_used.csv")


# =========================
