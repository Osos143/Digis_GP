"""
Stage 03: data profiling cleaning helpers
Extracted verbatim from the original monolithic data_cleaning.py (source lines 845-1008). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 3. Data profiling and cleaning helpers
# =========================

def build_data_dictionary(
    df: pd.DataFrame,
    name: str,
    sample_rows: int = PROFILE_SAMPLE_ROWS,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Build a practical data dictionary.

    Full missingness is calculated on all rows.
    Examples, unique counts, and numeric summaries are calculated on a sample for speed.
    """
    sample = sample_df(df, sample_rows)
    missing_count = df.isna().sum()
    missing_pct = df.isna().mean() * 100
    non_null_count = df.notna().sum()

    records = []
    for col in df.columns:
        s_full = df[col]
        s = sample[col]
        dtype = str(s_full.dtype)
        family = get_column_family(col)
        nunique_sample = s.nunique(dropna=True)
        non_null_sample = s.notna().sum()

        record = {
            "dataset": name,
            "column": col,
            "family": family,
            "dtype": dtype,
            "full_non_null_count": int(non_null_count[col]),
            "full_missing_count": int(missing_count[col]),
            "full_missing_pct": round(float(missing_pct[col]), 3),
            "sample_unique_count": int(nunique_sample),
            "sample_unique_pct": round(float(nunique_sample / max(non_null_sample, 1) * 100), 3),
            "sample_non_null_examples": s.dropna().astype(str).head(top_n).tolist(),
        }

        if pd.api.types.is_numeric_dtype(s_full):
            numeric_s = pd.to_numeric(s, errors="coerce")
            record.update({
                "sample_min": numeric_s.min(),
                "sample_max": numeric_s.max(),
                "sample_mean": numeric_s.mean(),
                "sample_std": numeric_s.std(),
                "sample_top_values": None,
            })
        else:
            record.update({
                "sample_min": None,
                "sample_max": None,
                "sample_mean": None,
                "sample_std": None,
                "sample_top_values": safe_value_counts(s, top_n=top_n),
            })
        records.append(record)

    return (
        pd.DataFrame(records)
        .sort_values(["full_missing_pct", "family", "column"], ascending=[False, True, True])
        .reset_index(drop=True)
    )


def summarize_column_families(profile: pd.DataFrame) -> pd.DataFrame:
    """Summarize missingness by column family."""
    summary = (
        profile.groupby("family")
        .agg(
            columns=("column", "count"),
            avg_missing_pct=("full_missing_pct", "mean"),
            min_missing_pct=("full_missing_pct", "min"),
            max_missing_pct=("full_missing_pct", "max"),
            zero_missing_columns=("full_missing_pct", lambda x: int((x == 0).sum())),
            fully_missing_columns=("full_missing_pct", lambda x: int((x == 100).sum())),
            above_threshold_missing=("full_missing_pct", lambda x: int((x > MISSING_THRESHOLD_PCT).sum())),
        )
        .reset_index()
        .sort_values(["columns", "avg_missing_pct"], ascending=[False, False])
    )
    summary["avg_missing_pct"] = summary["avg_missing_pct"].round(3)
    return summary


def threshold_impact(profile: pd.DataFrame, thresholds: Sequence[int] = (50, 60, 70, 75, 80, 90, 95, 99)) -> pd.DataFrame:
    """Show how many columns would be removed at each missing-value threshold."""
    total = len(profile)
    rows = []
    for threshold in thresholds:
        removed = int((profile["full_missing_pct"] > threshold).sum())
        rows.append({
            "missing_threshold_pct": threshold,
            "columns_removed_if_not_protected": removed,
            "columns_kept_if_not_protected": total - removed,
            "removed_pct_of_all_columns": round(removed / max(total, 1) * 100, 2),
        })
    return pd.DataFrame(rows)


# Exact columns known from the cleaning outputs and reports.
EXACT_PROTECTED_COLUMNS = {
    "id",
    "imsi",
    "timestamp",
    "Location - Latitude",
    "Location - Longitude",
    "Location - Speed",
    "Location - Altitude",
    "Location - Accuracy",
    "Activity.Start TimeStamp",
    "Activity.End TimeStamp",
    "Activity.Activity",
    "Activity.Status",
    "Activity.Tech",
    "Activity.Duration",
    "Activity.Throughput",
    "Activity.Power",
    "Activity.Quality",
    "Activity.SINR",
    "Events.Timestamp",
    "Events.category",
    "Events.Tech",
    "Events.titles",
    "Events.description",
    "Events.subject",
    "LTE.LTE_Data_KPI.Agg_Throughput_DL",
    "LTE.DownlinkMeasurements.Throughput_DL",
    "LTE - PrimaryCell - PCell_Throughput",
    "LTE - SecondaryCell 1 - SCell1_Throughput",
    "Throughput.HTTP_DL",
    "Throughput.Physical_DL",
}

# Pattern protection preserves sparse columns that are useful for anomaly handoff and later RCA.
PROTECTED_PATTERNS = [
    r"^Location",
    r"^Events\.",
    r"^Activity\.",
    r"^LTE - Serving -",
    r"^LTE - PrimaryCell",
    r"^LTE - PrimaryCell Radio",
    r"^LTE - SecondaryCell 1",
    r"^LTE\.LTE_Data_KPI\.(Agg_Throughput_DL|Agg_Throughput_UL|Agg_RB_DL|Agg_RB_UL|Agg_Bandwidth_DL)$",
    r"^LTE\.DownlinkMeasurements\.Throughput_DL$",
    r"^LTE\.DedicatedRadioLink\.CarrierCount$",
    r"^LTE\.RACH\.",
    r"^Throughput\.(HTTP_DL|Physical_DL)$",
    r"^Extra_KPIs\.(LTE Handover Interruption Time|UMTS Handover Interruption Time|ERRC Connection Setup Time|RRC Connection Setup Time|Attach Delay)$",
]


def is_protected_column(col: str) -> bool:
    """Return True when a column should survive the missingness threshold for throughput/anomaly handoff."""
    text = str(col)
    if text in EXACT_PROTECTED_COLUMNS:
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in PROTECTED_PATTERNS)


# =========================
