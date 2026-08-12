"""
Stage 07: apply cleaning derive features
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1260-1348). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 7. Apply cleaning and derive time/location features
# =========================

kept_columns = kept_columns_report["column"].tolist()
drive_clean = drive_raw[kept_columns].copy()

# Parse timestamp. The row-level timestamp is the main clock for route/event/anomaly alignment.
if "timestamp" in drive_clean.columns:
    drive_clean["timestamp"] = pd.to_datetime(drive_clean["timestamp"], errors="coerce")
else:
    raise KeyError("Required row-level timestamp column 'timestamp' was not found after cleaning.")

# Parse ID/session metadata.
drive_clean = add_id_features(drive_clean, id_col="id") if "id" in drive_clean.columns else drive_clean

# Sort rows to recover session sequence.
sort_cols = [c for c in ["id", "timestamp"] if c in drive_clean.columns]
if sort_cols:
    drive_clean = drive_clean.sort_values(sort_cols).reset_index(drop=True)

# Derived time features.
drive_clean["date"] = drive_clean["timestamp"].dt.date
drive_clean["hour"] = drive_clean["timestamp"].dt.hour
drive_clean["minute"] = drive_clean["timestamp"].dt.minute
if "id" in drive_clean.columns:
    drive_clean["sample_gap_seconds"] = drive_clean.groupby("id")["timestamp"].diff().dt.total_seconds()
    drive_clean["session_elapsed_seconds"] = (
        drive_clean["timestamp"] - drive_clean.groupby("id")["timestamp"].transform("min")
    ).dt.total_seconds()
else:
    drive_clean["sample_gap_seconds"] = drive_clean["timestamp"].diff().dt.total_seconds()
    drive_clean["session_elapsed_seconds"] = (drive_clean["timestamp"] - drive_clean["timestamp"].min()).dt.total_seconds()

# Parse activity timestamps if present.
for col in ["Activity.Start TimeStamp", "Activity.End TimeStamp"]:
    if col in drive_clean.columns:
        drive_clean[col + "_parsed"] = pd.to_datetime(drive_clean[col], errors="coerce")

if {"Activity.Start TimeStamp_parsed", "Activity.End TimeStamp_parsed"}.issubset(drive_clean.columns):
    drive_clean["activity_duration_seconds_from_timestamps"] = (
        drive_clean["Activity.End TimeStamp_parsed"] - drive_clean["Activity.Start TimeStamp_parsed"]
    ).dt.total_seconds()

# Location cleanup and route distance.
LAT_COL = "Location - Latitude"
LON_COL = "Location - Longitude"
SPEED_COL = "Location - Speed"
ACCURACY_COL = "Location - Accuracy"
ALTITUDE_COL = "Location - Altitude"

if {LAT_COL, LON_COL}.issubset(drive_clean.columns):
    drive_clean[LAT_COL] = pd.to_numeric(drive_clean[LAT_COL], errors="coerce")
    drive_clean[LON_COL] = pd.to_numeric(drive_clean[LON_COL], errors="coerce")
    drive_clean["has_valid_location"] = drive_clean[[LAT_COL, LON_COL]].notna().all(axis=1)
    if "id" in drive_clean.columns:
        drive_clean["prev_lat"] = drive_clean.groupby("id")[LAT_COL].shift(1)
        drive_clean["prev_lon"] = drive_clean.groupby("id")[LON_COL].shift(1)
    else:
        drive_clean["prev_lat"] = drive_clean[LAT_COL].shift(1)
        drive_clean["prev_lon"] = drive_clean[LON_COL].shift(1)
    drive_clean["distance_from_prev_m"] = haversine_km(
        drive_clean["prev_lat"], drive_clean["prev_lon"], drive_clean[LAT_COL], drive_clean[LON_COL]
    ) * 1000
    drive_clean.loc[drive_clean["sample_gap_seconds"].isna(), "distance_from_prev_m"] = np.nan
else:
    drive_clean["has_valid_location"] = False

clean_profile = build_data_dictionary(drive_clean, name="drive_clean_throughput_base")
clean_family_summary = summarize_column_families(clean_profile)

save_table(clean_profile, "cleaned_throughput_data_dictionary.csv")
save_table(clean_family_summary, "column_family_summary_after_cleaning.csv")

cleaning_summary = pd.DataFrame([
    {"metric": "raw_rows", "value": len(drive_raw)},
    {"metric": "raw_columns", "value": drive_raw.shape[1]},
    {"metric": "clean_rows", "value": len(drive_clean)},
    {"metric": "clean_columns", "value": drive_clean.shape[1]},
    {"metric": "columns_removed_total", "value": len(removed_columns_report)},
    {"metric": "columns_kept_total", "value": len(kept_columns_report)},
    {"metric": "missing_threshold_pct", "value": MISSING_THRESHOLD_PCT},
])
save_table(cleaning_summary, "cleaning_summary.csv")
save_parquet_or_csv(drive_clean, "drive_clean_throughput_base")

overview(drive_clean, "Cleaned throughput base")
display(cleaning_summary)

# =========================
