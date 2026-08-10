"""
Stage 06: profile raw data cleaning plan
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1208-1259). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 6. Profile raw data and build cleaning plan
# =========================

raw_profile = build_data_dictionary(drive_raw, name="drive_raw")
raw_family_summary = summarize_column_families(raw_profile)
missing_impact = threshold_impact(raw_profile)

save_table(raw_profile, "raw_data_dictionary.csv")
save_table(raw_family_summary, "column_family_summary_before_cleaning.csv")
save_table(missing_impact, "missing_threshold_impact.csv")

print("Raw family summary:")
display(raw_family_summary)
print("Missing-threshold impact:")
display(missing_impact)

# Mark protected columns.
raw_profile["is_protected"] = raw_profile["column"].apply(is_protected_column)

# Reason priority: 100% missing > above threshold > constant/single unique.
raw_profile["remove_reason"] = ""
fully_missing = raw_profile["full_missing_pct"] == 100
above_threshold = raw_profile["full_missing_pct"] > MISSING_THRESHOLD_PCT
constant = raw_profile["sample_unique_count"] <= 1
protected = raw_profile["is_protected"]

if DROP_FULLY_MISSING_PROTECTED_COLUMNS:
    raw_profile.loc[fully_missing, "remove_reason"] = "100% missing"
else:
    raw_profile.loc[fully_missing & (~protected), "remove_reason"] = "100% missing"

raw_profile.loc[(raw_profile["remove_reason"] == "") & above_threshold & (~protected), "remove_reason"] = f">{MISSING_THRESHOLD_PCT:.0f}% missing"
raw_profile.loc[(raw_profile["remove_reason"] == "") & constant & (~protected), "remove_reason"] = "constant / single unique value"

removed_columns_report = raw_profile[raw_profile["remove_reason"] != ""].copy()
kept_columns_report = raw_profile[raw_profile["remove_reason"] == ""].copy()
protected_columns_report = raw_profile[raw_profile["is_protected"]].copy()

save_table(removed_columns_report, "removed_columns_report.csv")
save_table(kept_columns_report, "kept_columns_after_cleaning.csv")
save_table(protected_columns_report, "protected_columns_report.csv")

reason_summary = removed_columns_report["remove_reason"].value_counts().reset_index()
reason_summary.columns = ["remove_reason", "columns_removed"]
save_table(reason_summary, "removed_columns_reason_summary.csv")

display(reason_summary)
print("Kept columns:", len(kept_columns_report))
print("Removed columns:", len(removed_columns_report))
print("Protected columns kept or reviewed:", len(protected_columns_report))

# =========================
