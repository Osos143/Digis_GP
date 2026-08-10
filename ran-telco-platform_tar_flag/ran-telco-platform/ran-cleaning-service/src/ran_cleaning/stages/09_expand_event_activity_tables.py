"""
Stage 09: expand event activity tables
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1453-1489). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 9. Expand event and activity tables for handoff/evidence
# =========================

# Event table: one row per event. This is useful for event-window anomaly features.
events_long = build_events_long(drive_clean, id_col="id", sample_time_col="timestamp")
if not events_long.empty:
    events_long["event_family"] = events_long.apply(classify_event_family, axis=1)
    save_table(events_long, "events_long.csv")

    for col in ["Events.category", "Events.Tech", "Events.titles", "Events.subject", "event_family"]:
        if col in events_long.columns:
            summary = events_long[col].fillna("Unknown").astype(str).value_counts().reset_index()
            summary.columns = [col, "event_count"]
            save_table(summary, f"event_summary_{col.replace('.', '_').replace(' ', '_')}.csv")
else:
    print("No events were available to expand.")

# Activity table: preserve sparse activity records for the later RCA colleague.
activity_cols = [c for c in drive_clean.columns if str(c).startswith("Activity.")]
activity_key_cols = [c for c in ["id", "timestamp", "id_route_test_label", "id_test_type"] if c in drive_clean.columns]

if activity_cols:
    activity_table = drive_clean[activity_key_cols + activity_cols].copy()
    activity_table = activity_table[activity_table[activity_cols].notna().any(axis=1)].reset_index(drop=True)
    save_table(activity_table, "activity_table.csv")
    if "Activity.Activity" in activity_table.columns:
        activity_summary = activity_table["Activity.Activity"].fillna("Unknown").astype(str).value_counts().reset_index()
        activity_summary.columns = ["activity", "rows"]
        save_table(activity_summary, "activity_type_summary.csv")
else:
    activity_table = pd.DataFrame()
    print("No Activity.* columns found.")

print("Events long shape:", events_long.shape)
print("Activity table shape:", activity_table.shape)

# =========================
