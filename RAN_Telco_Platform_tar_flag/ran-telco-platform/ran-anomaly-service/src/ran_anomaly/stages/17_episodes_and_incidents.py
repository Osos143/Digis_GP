"""
Stage 17: episodes and incidents
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 5397-5880). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

import plotly.graph_objects as go

# 27. Candidate episodes, strict final RCA episodes, and operational incident consolidation
# =========================

if len(fused_handoff_rows):
    all_episode_rows = add_anomaly_episode_ids(fused_handoff_rows.copy()).rename(columns={"anomaly_episode_id": "final_episode_id"})
    all_episode_rows["statistical_type_for_episode"] = all_episode_rows.get("anomaly_type", "normal")
    all_episode_rows["ml_type_for_episode"] = all_episode_rows.get("ml_anomaly_type", "normal")
    episode_group = all_episode_rows.groupby("final_episode_id", dropna=False)

    all_episode_summary = episode_group.agg(
        id=(GROUP_COL, "first"),
        route_label=("id_route_test_label", "first") if "id_route_test_label" in all_episode_rows.columns else (GROUP_COL, "first"),
        start_time=(TIME_COL, "min"), end_time=(TIME_COL, "max"), rows=(TARGET_COL, "size"),
        latitude_start=("latitude", "first") if "latitude" in all_episode_rows.columns else (TARGET_COL, "size"),
        longitude_start=("longitude", "first") if "longitude" in all_episode_rows.columns else (TARGET_COL, "size"),
        latitude_end=("latitude", "last") if "latitude" in all_episode_rows.columns else (TARGET_COL, "size"),
        longitude_end=("longitude", "last") if "longitude" in all_episode_rows.columns else (TARGET_COL, "size"),
        primary_serving_pci=("serving_pci", lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan) if "serving_pci" in all_episode_rows.columns else (TARGET_COL, "size"),
        primary_earfcn=("serving_earfcn", lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan) if "serving_earfcn" in all_episode_rows.columns else (TARGET_COL, "size"),
        primary_band=("serving_band", lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan) if "serving_band" in all_episode_rows.columns else (TARGET_COL, "size"),
        min_actual_tp=(TARGET_COL, "min"), median_actual_tp=(TARGET_COL, "median"),
        max_expected_tp=("fused_best_expected_tp", "max"), max_expected_gap=("fused_expected_gap_mbps", "max"),
        min_actual_expected_ratio=("fused_actual_expected_ratio", "min"),
        max_row_priority=("final_rca_priority_score_0_100", "max"), mean_row_priority=("final_rca_priority_score_0_100", "mean"),
        max_row_impact=("fused_impact_score_0_100", "max"), mean_row_impact=("fused_impact_score_0_100", "mean"),
        max_row_confidence=("fused_detection_confidence_0_100", "max"), mean_row_confidence=("fused_detection_confidence_0_100", "mean"),
        consensus_rows=("fused_consensus_flag", "sum"), statistical_only_rows=("fused_statistical_only_flag", "sum"), ml_only_rows=("fused_ml_only_flag", "sum"),
        dominant_statistical_type=("statistical_type_for_episode", lambda s: s.mode().iloc[0] if len(s.mode()) else "normal"),
        dominant_ml_type=("ml_type_for_episode", lambda s: s.mode().iloc[0] if len(s.mode()) else "normal"),
        fusion_source_mode=("fusion_source", lambda s: s.mode().iloc[0] if len(s.mode()) else "unknown"),
    ).reset_index()

    start_utc = pd.to_datetime(all_episode_summary["start_time"], errors="coerce", utc=True)
    end_utc = pd.to_datetime(all_episode_summary["end_time"], errors="coerce", utc=True)
    all_episode_summary["duration_seconds"] = (end_utc - start_utc).dt.total_seconds().fillna(0)
    if "distance_from_prev_m" in all_episode_rows.columns:
        all_episode_summary["distance_affected_m"] = all_episode_summary["final_episode_id"].map(episode_group["distance_from_prev_m"].sum(min_count=1))
    else:
        all_episode_summary["distance_affected_m"] = np.nan

    all_episode_summary["agreement_pct"] = all_episode_summary["consensus_rows"] / all_episode_summary["rows"].replace(0, np.nan) * 100
    persistence_component = np.clip(np.log1p(all_episode_summary["rows"]) / np.log1p(10), 0, 1)
    duration_component = np.clip(all_episode_summary["duration_seconds"] / 30.0, 0, 1)
    episode_impact = (
        0.55 * (all_episode_summary["max_row_impact"] / 100.0)
        + 0.20 * (all_episode_summary["mean_row_impact"] / 100.0)
        + 0.15 * persistence_component + 0.10 * duration_component
    )
    episode_confidence = (
        0.60 * (all_episode_summary["max_row_confidence"] / 100.0)
        + 0.25 * (all_episode_summary["mean_row_confidence"] / 100.0)
        + 0.15 * np.clip(all_episode_summary["agreement_pct"] / 100.0, 0, 1)
    )
    all_episode_summary["episode_impact_score_0_100"] = (100 * np.clip(episode_impact, 0, 1)).round(2)
    all_episode_summary["episode_detection_confidence_0_100"] = (100 * np.clip(episode_confidence, 0, 1)).round(2)
    all_episode_summary["episode_final_priority_0_100"] = (
        100 * (FUSION_IMPACT_WEIGHT*np.clip(episode_impact,0,1) + FUSION_CONFIDENCE_WEIGHT*np.clip(episode_confidence,0,1))
    ).clip(upper=100).round(2)

    all_episode_summary["episode_impact_severity"] = np.select(
        [all_episode_summary["episode_impact_score_0_100"] >= 80, all_episode_summary["episode_impact_score_0_100"] >= 55, all_episode_summary["episode_impact_score_0_100"] >= 30],
        ["Critical", "High", "Medium"], default="Low",
    )
    all_episode_summary["episode_detection_confidence"] = np.select(
        [all_episode_summary["episode_detection_confidence_0_100"] >= 80, all_episode_summary["episode_detection_confidence_0_100"] >= 60, all_episode_summary["episode_detection_confidence_0_100"] >= 40],
        ["Very High", "High", "Medium"], default="Low",
    )

    # Direct evidence counts used by the final episode keep gate.
    direct_flags = [
        "underperform_vs_p75_flag", "underperform_vs_rb_p75_flag", "low_rb_efficiency_high_rb_flag",
        "ca_underperformance_flag", "ml_q75_resource_underperformance_flag",
        "ml_hgb_resource_underperformance_flag", "ml_hgb_temporal_underperformance_flag",
    ]
    for flag_col in direct_flags + [
        "near_handover_execution_flag", "near_handover_failure_flag", "near_rach_failure_flag", "near_ca_activation_change_flag"
    ]:
        if flag_col in all_episode_rows.columns:
            all_episode_summary[f"{flag_col}_rows"] = all_episode_summary["final_episode_id"].map(episode_group[flag_col].sum()).fillna(0).astype(int)

    direct_evidence_cols = [f"{c}_rows" for c in direct_flags if f"{c}_rows" in all_episode_summary.columns]
    all_episode_summary["strong_direct_evidence_rows"] = all_episode_summary[direct_evidence_cols].sum(axis=1) if direct_evidence_cols else 0

    base_episode_keep = (
        (all_episode_summary["episode_final_priority_0_100"] >= FUSION_EPISODE_MIN_SCORE)
        & ((all_episode_summary["episode_detection_confidence_0_100"] >= FUSION_EPISODE_MIN_CONFIDENCE) | (all_episode_summary["strong_direct_evidence_rows"] > 0))
    )
    singleton_stat_only = (
        (all_episode_summary["rows"] == 1)
        & all_episode_summary["fusion_source_mode"].eq("statistical_only_retained")
    )
    singleton_ok = (
        (all_episode_summary["episode_final_priority_0_100"] >= FUSION_SINGLETON_STAT_ONLY_MIN_SCORE)
        | ((all_episode_summary["strong_direct_evidence_rows"] > 0) & (all_episode_summary["episode_impact_score_0_100"] >= 70))
    )
    all_episode_summary["final_episode_handoff_flag"] = base_episode_keep & (~singleton_stat_only | singleton_ok)

    all_episode_summary["episode_priority_severity"] = np.select(
        [
            ~all_episode_summary["final_episode_handoff_flag"],
            (all_episode_summary["episode_final_priority_0_100"] >= 85) & (all_episode_summary["strong_direct_evidence_rows"] > 0),
            all_episode_summary["episode_final_priority_0_100"] >= FUSION_HIGH,
            all_episode_summary["episode_final_priority_0_100"] >= FUSION_MEDIUM,
        ],
        ["Not handed off", "Critical", "High", "Medium"], default="Low",
    )

    all_episode_summary = all_episode_summary.sort_values(["episode_final_priority_0_100", "rows"], ascending=[False, False])
    final_episode_summary = all_episode_summary[all_episode_summary["final_episode_handoff_flag"]].copy()
    keep_ids = set(final_episode_summary["final_episode_id"].astype(str))
    final_episode_rows = all_episode_rows[all_episode_rows["final_episode_id"].astype(str).isin(keep_ids)].copy()

    # Operational incidents bridge only very close, technically compatible strict episodes.
    def _geo_distance_m(lat1, lon1, lat2, lon2):
        vals = [lat1, lon1, lat2, lon2]
        if not all(pd.notna(v) for v in vals):
            return np.nan
        p1, p2 = np.radians([float(lat1), float(lat2)])
        dphi = p2 - p1
        dl = np.radians(float(lon2) - float(lon1))
        a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return float(2 * 6371008.8 * np.arcsin(np.sqrt(a)))

    operational = final_episode_summary.sort_values(["id", "start_time"]).copy()
    incident_ids, incident_counter, prev = [], 0, None
    for _, row in operational.iterrows():
        new_incident = True
        if prev is not None and str(row["id"]) == str(prev["id"]):
            gap_s = (pd.to_datetime(row["start_time"], utc=True) - pd.to_datetime(prev["end_time"], utc=True)).total_seconds()
            dist_m = _geo_distance_m(prev.get("latitude_end"), prev.get("longitude_end"), row.get("latitude_start"), row.get("longitude_start"))
            pci_compatible = pd.isna(row.get("primary_serving_pci")) or pd.isna(prev.get("primary_serving_pci")) or row.get("primary_serving_pci") == prev.get("primary_serving_pci")
            stat_now, stat_prev = row.get("dominant_statistical_type"), prev.get("dominant_statistical_type")
            ml_now, ml_prev = row.get("dominant_ml_type"), prev.get("dominant_ml_type")
            stat_match = pd.notna(stat_now) and pd.notna(stat_prev) and stat_now != "normal" and stat_now == stat_prev
            ml_match = pd.notna(ml_now) and pd.notna(ml_prev) and ml_now != "normal" and ml_now == ml_prev
            family_compatible = bool(stat_match or ml_match)
            spatial_ok = pd.isna(dist_m) or dist_m <= FUSION_OPERATIONAL_MAX_DISTANCE_M
            new_incident = not (0 <= gap_s <= FUSION_OPERATIONAL_MAX_GAP_SECONDS and spatial_ok and pci_compatible and family_compatible)
        if new_incident:
            incident_counter += 1
        incident_ids.append(f"INC-{incident_counter:06d}")
        prev = row
    operational["operational_incident_id"] = incident_ids

    operational_incident_summary = operational.groupby("operational_incident_id", dropna=False).agg(
        id=("id", "first"), route_label=("route_label", "first"), start_time=("start_time", "min"), end_time=("end_time", "max"),
        strict_episodes=("final_episode_id", "nunique"), rows=("rows", "sum"),
        max_priority=("episode_final_priority_0_100", "max"), mean_priority=("episode_final_priority_0_100", "mean"),
        max_impact=("episode_impact_score_0_100", "max"), max_confidence=("episode_detection_confidence_0_100", "max"),
        consensus_rows=("consensus_rows", "sum"), statistical_only_rows=("statistical_only_rows", "sum"), ml_only_rows=("ml_only_rows", "sum"),
        dominant_statistical_type=("dominant_statistical_type", lambda s: s.mode().iloc[0] if len(s.mode()) else "normal"),
        dominant_ml_type=("dominant_ml_type", lambda s: s.mode().iloc[0] if len(s.mode()) else "normal"),
        primary_serving_pci=("primary_serving_pci", lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan),
    ).reset_index()
    incident_start = pd.to_datetime(operational_incident_summary["start_time"], errors="coerce", utc=True)
    incident_end = pd.to_datetime(operational_incident_summary["end_time"], errors="coerce", utc=True)
    operational_incident_summary["duration_seconds"] = (incident_end - incident_start).dt.total_seconds().fillna(0)
    operational_incident_summary = operational_incident_summary.sort_values(["max_priority", "rows"], ascending=[False, False])
else:
    all_episode_rows = pd.DataFrame()
    all_episode_summary = pd.DataFrame()
    final_episode_rows = pd.DataFrame()
    final_episode_summary = pd.DataFrame()
    operational_incident_summary = pd.DataFrame()

save_table(all_episode_rows, "lte_throughput_anomalies_final_fused_episode_rows_all_candidates.csv", category="anomaly")
save_table(all_episode_summary, "lte_throughput_anomaly_episodes_all_candidates.csv", category="anomaly")
save_table(final_episode_rows, "lte_throughput_anomalies_final_fused_episode_rows.csv", category="anomaly")
save_table(final_episode_summary, "lte_throughput_anomaly_episodes_final_rca_handoff.csv", category="anomaly")
save_table(operational_incident_summary, "lte_throughput_operational_incidents_final_rca_handoff.csv", category="anomaly")

print("All candidate fused episodes:", len(all_episode_summary))
print("Strict final RCA episodes:", len(final_episode_summary))
print("Operational RCA incidents:", len(operational_incident_summary))
display(final_episode_summary.head(25))
display(operational_incident_summary.head(25))

# =========================
# 27B. Compact RCA handoff JSON, diverse shortlist, and top-case gap/drop plots
# =========================

# Map final row evidence to operational incident IDs.
if len(final_episode_rows) and 'operational' in globals() and len(operational):
    episode_to_incident = operational[["final_episode_id", "operational_incident_id"]].drop_duplicates()
    incident_rows = final_episode_rows.merge(episode_to_incident, on="final_episode_id", how="left")
else:
    incident_rows = pd.DataFrame()


def safe_mode(s, default=None):
    m = pd.Series(s).dropna().mode()
    return m.iloc[0] if len(m) else default


def any_bool(g, col):
    return bool(g[col].fillna(False).astype(bool).any()) if col in g.columns else False


def median_num(g, col):
    return float(pd.to_numeric(g[col], errors="coerce").median()) if col in g.columns and pd.to_numeric(g[col], errors="coerce").notna().any() else None


def max_num(g, col):
    return float(pd.to_numeric(g[col], errors="coerce").max()) if col in g.columns and pd.to_numeric(g[col], errors="coerce").notna().any() else None


def primary_detection_case(g):
    # Specific, RCA-useful case priority. These are detection/context labels, not final root causes.
    rules = [
        ("ca_underperformance_flag", "ca_underperformance"),
        ("radio_limited_degradation_flag", "radio_limited_degradation"),
        ("rolling_drop_flag", "temporal_local_drop"),
        ("sudden_drop_flag", "temporal_sudden_drop"),
        ("low_rb_efficiency_high_rb_flag", "rb_efficiency_underperformance"),
        ("underperform_vs_rb_p75_flag", "rb_conditioned_expected_underperformance"),
        ("underperform_vs_p75_flag", "radio_condition_expected_underperformance"),
        ("rolling_sustained_degradation_flag", "sustained_low_throughput"),
        ("low_tail_robust_consensus_flag", "robust_low_tail_consensus"),
    ]
    for col,label in rules:
        if any_bool(g,col): return label
    if any_bool(g,"fused_ml_only_flag"): return "strict_ml_only_underperformance"
    return safe_mode(g.get("anomaly_type", pd.Series(dtype=object)), "other_throughput_anomaly")

# Lookup tables let each incident carry the serving cell/PCI performance rank without
# duplicating the full ranking table inside the JSON.
cell_rank_lookup = {}
if 'cell_rank' in globals() and isinstance(cell_rank, pd.DataFrame) and not cell_rank.empty:
    cell_rank_lookup = cell_rank.set_index("serving_cell_key")[[c for c in ["bad_entity_rank","bad_entity_score_0_100","median_tp_mbps","p10_tp_mbps","median_cqi","median_mcs","median_bler_pct"] if c in cell_rank.columns]].to_dict("index")
pci_rank_lookup = {}
if 'pci_rank' in globals() and isinstance(pci_rank, pd.DataFrame) and not pci_rank.empty:
    pci_rank_lookup = pci_rank.set_index("serving_pci")[[c for c in ["bad_entity_rank","bad_entity_score_0_100"] if c in pci_rank.columns]].to_dict("index")

incident_records = []
if not incident_rows.empty:
    for incident_id, g in incident_rows.groupby("operational_incident_id", dropna=False):
        g = g.sort_values("timestamp") if "timestamp" in g.columns else g
        expected_candidates = [c for c in ["fused_best_expected_tp","expected_tp_radio_p75","expected_tp_rb_conditioned_p75","expected_tp_ml_hgb_resource_q50","expected_tp_ml_q75_resource","expected_tp_ml_hgb_temporal_q50"] if c in g.columns]
        expected_median = float(g[expected_candidates].median(axis=1, skipna=True).median()) if expected_candidates else None
        actual_median = median_num(g, TARGET_COL)
        local_drop = max(v for v in [max_num(g,"rolling_tp_gap"), max_num(g,"tp_drop_from_prev")] if v is not None) if any(v is not None for v in [max_num(g,"rolling_tp_gap"), max_num(g,"tp_drop_from_prev")]) else None
        cell_key_value = safe_mode(g.get("serving_cell_key", pd.Series(dtype=object)))
        pci_value = safe_mode(g.get("serving_pci", pd.Series(dtype=object)))
        cell_perf = cell_rank_lookup.get(cell_key_value, {})
        pci_perf = pci_rank_lookup.get(pci_value, {})
        rec = {
            "incident_id": str(incident_id),
            "session_id": str(safe_mode(g.get("id", pd.Series(dtype=object)), "")),
            "start_time": str(g["timestamp"].min()) if "timestamp" in g.columns else None,
            "end_time": str(g["timestamp"].max()) if "timestamp" in g.columns else None,
            "duration_seconds": float((pd.to_datetime(g["timestamp"], utc=True).max() - pd.to_datetime(g["timestamp"], utc=True).min()).total_seconds()) if "timestamp" in g.columns else None,
            "rows": int(len(g)),
            "serving_cell_key": cell_key_value,
            "serving_pci": pci_value,
            "serving_eci": safe_mode(g.get("serving_eci", pd.Series(dtype=object))),
            "serving_earfcn": safe_mode(g.get("serving_earfcn", pd.Series(dtype=object))),
            "serving_band": safe_mode(g.get("serving_band", pd.Series(dtype=object))),
            "latitude": median_num(g,"latitude"), "longitude": median_num(g,"longitude"),
            "detection_case": primary_detection_case(g),
            "fusion_source": safe_mode(g.get("fusion_source", pd.Series(dtype=object)), "unknown"),
            "priority_score_0_100": max_num(g,"final_rca_priority_score_0_100"),
            "impact_score_0_100": max_num(g,"fused_impact_score_0_100"),
            "detection_confidence_0_100": max_num(g,"fused_detection_confidence_0_100"),
            "severity": safe_mode(g.get("final_priority_severity", pd.Series(dtype=object)), "Unknown"),
            "requires_human_review": any_bool(g,"requires_human_review_flag"),
            "human_review_reason": "strict_ml_only_anomaly_requires_supervised_verification" if any_bool(g,"requires_human_review_flag") else None,
            "throughput": {
                "actual_median_mbps": actual_median,
                "actual_min_mbps": float(pd.to_numeric(g[TARGET_COL], errors="coerce").min()),
                "expected_median_mbps": expected_median,
                "expected_gap_median_mbps": (expected_median - actual_median) if expected_median is not None and actual_median is not None else None,
                "max_local_drop_mbps": local_drop,
                "radio_p75_gap_median_mbps": median_num(g,"throughput_gap_p75"),
                "rb_p75_gap_median_mbps": median_num(g,"throughput_gap_rb_p75"),
            },
            "cell_performance_context": {
                "cell_bad_rank": cell_perf.get("bad_entity_rank"), "cell_badness_score_0_100": cell_perf.get("bad_entity_score_0_100"),
                "cell_median_tp_mbps": cell_perf.get("median_tp_mbps"), "cell_p10_tp_mbps": cell_perf.get("p10_tp_mbps"),
                "cell_median_cqi": cell_perf.get("median_cqi"), "cell_median_mcs": cell_perf.get("median_mcs"),
                "cell_median_bler_pct": cell_perf.get("median_bler_pct"),
                "pci_bad_rank_secondary_view": pci_perf.get("bad_entity_rank"), "pci_badness_score_0_100": pci_perf.get("bad_entity_score_0_100"),
            },
            "radio_kpis": {
                "rsrp_median_dbm": median_num(g,"lte_rsrp"), "rsrq_median_db": median_num(g,"lte_rsrq"),
                "sinr_median_db": median_num(g,"lte_sinr"), "cqi_median": median_num(g,"lte_cqi"),
                "mcs_median": median_num(g,"lte_mcs"), "bler_median_pct": median_num(g,"lte_bler"),
            },
            "resource_kpis": {
                "rb_usage_median": median_num(g,"rb_usage_value"), "throughput_per_rb_median": median_num(g,"throughput_per_rb"),
                "rb_medium_or_high_usage": any_bool(g,"rb_medium_or_high_usage_flag"),
            },
            "ca_context": {
                "ca_active": any_bool(g,"ca_active_flag"), "carrier_count_median": median_num(g,"carrier_count"),
                "scell1_rsrp_median_dbm": median_num(g,"scell1_rsrp"), "scell1_sinr_median_db": median_num(g,"scell1_sinr"),
                "scell1_cqi_median": median_num(g,"scell1_cqi"), "scell1_mcs_median": median_num(g,"scell1_mcs"),
                "scell1_bler_median_pct": median_num(g,"scell1_bler"),
            },
            "statistical_evidence": {
                "global_p10": any_bool(g,"low_tp_global_p10_flag"), "session_p10": any_bool(g,"low_tp_session_p10_flag"),
                "iqr_lower_fence": any_bool(g,"low_tp_iqr_flag"), "robust_mad": any_bool(g,"low_tp_robust_z_flag"),
                "low_tail_consensus": any_bool(g,"low_tail_robust_consensus_flag"),
                "temporal_drop": any_bool(g,"temporal_drop_family_flag"), "expected_underperformance": any_bool(g,"expected_tp_family_flag"),
                "rb_efficiency": any_bool(g,"rb_efficiency_family_flag"), "sustained_window": any_bool(g,"sustained_window_family_flag"),
            },
            "production_ml_evidence": {
                "ml_final_anomaly": any_bool(g,"is_ml_throughput_anomaly"),
                "resource_family": any_bool(g,"ml_resource_family_flag"),
                "temporal_causal_family": any_bool(g,"ml_temporal_family_flag"),
                "ml_confidence_0_100": max_num(g,"ml_detection_confidence_0_100"),
                "hgb_resource_q50_expected_median_mbps": median_num(g,"expected_tp_ml_hgb_resource_q50"),
                "hgb_causal_temporal_q50_expected_median_mbps": median_num(g,"expected_tp_ml_hgb_temporal_q50"),
                "resource_q75_expected_median_mbps": median_num(g,"expected_tp_ml_q75_resource"),
            },
            # Deliberately excludes LSTM and IsolationForest fields from RCA JSON.
        }
        incident_records.append(rec)

rca_incidents_full = pd.DataFrame([{
    "incident_id": r["incident_id"], "session_id": r["session_id"], "start_time": r["start_time"], "end_time": r["end_time"],
    "serving_cell_key": r["serving_cell_key"], "serving_pci": r["serving_pci"], "detection_case": r["detection_case"],
    "priority_score_0_100": r["priority_score_0_100"], "impact_score_0_100": r["impact_score_0_100"],
    "detection_confidence_0_100": r["detection_confidence_0_100"], "severity": r["severity"],
    "requires_human_review": r["requires_human_review"],
} for r in incident_records])

# Diverse shortlist: quota by case first, then fill by priority while avoiding duplicate session+cell+case.
selected_ids = []
if not rca_incidents_full.empty:
    ranked_inc = rca_incidents_full.sort_values("priority_score_0_100", ascending=False).copy()
    for case, cg in ranked_inc.groupby("detection_case", sort=False):
        selected_ids.extend(cg.head(RCA_SHORTLIST_PER_CASE_QUOTA)["incident_id"].tolist())
    selected_ids = list(dict.fromkeys(selected_ids))
    if len(selected_ids) < RCA_SHORTLIST_TARGET_INCIDENTS:
        for _, row in ranked_inc.iterrows():
            if row["incident_id"] not in selected_ids:
                selected_ids.append(row["incident_id"])
            if len(selected_ids) >= RCA_SHORTLIST_TARGET_INCIDENTS:
                break
    # If quotas produced too many, keep diversity by round-robin case rank.
    if len(selected_ids) > RCA_SHORTLIST_TARGET_INCIDENTS:
        shortlist = ranked_inc[ranked_inc["incident_id"].isin(selected_ids)].copy()
        shortlist["case_rank"] = shortlist.groupby("detection_case")["priority_score_0_100"].rank(method="first", ascending=False)
        shortlist = shortlist.sort_values(["case_rank","priority_score_0_100"], ascending=[True,False]).head(RCA_SHORTLIST_TARGET_INCIDENTS)
        selected_ids = shortlist["incident_id"].tolist()

record_by_id = {r["incident_id"]: r for r in incident_records}
shortlist_records = [record_by_id[x] for x in selected_ids if x in record_by_id]

with open(RCA_HANDOFF_DIR / "rca_anomaly_incidents_full_compact.json", "w", encoding="utf-8") as f:
    json.dump(incident_records, f, ensure_ascii=False, indent=2, default=str)
from ran_anomaly.mongo_writer import write_json_to_mongo
write_json_to_mongo("rca_anomaly_incidents_full_compact", incident_records)
with open(RCA_HANDOFF_DIR / "rca_anomaly_incidents_shortlist_diverse.json", "w", encoding="utf-8") as f:
    json.dump(shortlist_records, f, ensure_ascii=False, indent=2, default=str)
write_json_to_mongo("rca_anomaly_incidents_shortlist_diverse", shortlist_records)

if not rca_incidents_full.empty:
    save_table(rca_incidents_full, "rca_anomaly_incidents_full_compact.csv", category="rca")
    save_table(rca_incidents_full[rca_incidents_full["incident_id"].isin(selected_ids)].sort_values("priority_score_0_100", ascending=False), "rca_anomaly_incidents_shortlist_diverse.csv", category="rca")

# Handoff schema dictionary: compact and explicit.
rca_schema = pd.DataFrame([
    ("incident_id", "Identity", "Operational incident identifier"),
    ("session_id/start_time/end_time/duration_seconds", "Identity", "When the anomaly occurred"),
    ("serving_cell_key/PCI/ECI/EARFCN/band", "Cell", "Serving cell identity for RCA"),
    ("detection_case", "Detection", "Primary anomaly/context case; not a final root cause"),
    ("priority/impact/confidence/severity", "Ranking", "Why RCA should review this incident first"),
    ("requires_human_review", "Governance", "True for strict ML-only anomalies"),
    ("throughput.*", "Impact", "Actual, expected, gap, and local drop evidence"),
    ("cell_performance_context.*", "Cell ranking", "Cell/PCI badness ranks and compact cell-level KPI context"),
    ("radio_kpis.*", "Radio evidence", "RSRP/RSRQ/SINR/CQI/MCS/BLER"),
    ("resource_kpis.*", "Resource evidence", "RB demand and throughput efficiency"),
    ("ca_context.*", "CA evidence", "Carrier aggregation and SCell context"),
    ("statistical_evidence.*", "Detector evidence", "P10/IQR/MAD/temporal/P75/RB-efficiency evidence"),
    ("production_ml_evidence.*", "ML evidence", "Only selected production HGB/Q75 evidence; LSTM and IsolationForest excluded"),
], columns=["json_field", "section", "meaning"])
save_table(rca_schema, "rca_json_schema_dictionary.csv", category="rca")

# -------------------------
# Top anomaly-case plots with explicit gap/drop annotation
# -------------------------
def plot_case_context(row, case_name, rank):
    if "timestamp" not in fused.columns or "id" not in fused.columns:
        return
    sid = row.get("id")
    ts0 = pd.to_datetime(row.get("timestamp"), utc=True, errors="coerce")
    if pd.isna(ts0): return
    ctx = fused[fused["id"].astype(str).eq(str(sid))].copy()
    ctx["_ts"] = pd.to_datetime(ctx["timestamp"], utc=True, errors="coerce")
    ctx = ctx[(ctx["_ts"] >= ts0 - pd.Timedelta(seconds=TOP_CASE_CONTEXT_SECONDS)) & (ctx["_ts"] <= ts0 + pd.Timedelta(seconds=TOP_CASE_CONTEXT_SECONDS))].sort_values("_ts")
    if ctx.empty: return
    x = (ctx["_ts"] - ts0).dt.total_seconds()
    plt.figure(figsize=(13,6))
    plt.plot(x, ctx[TARGET_COL], marker="o", markersize=2, linewidth=1.5, label="Actual throughput")
    for col,label in [
        ("expected_tp_radio_p75","Radio P75"), ("expected_tp_rb_conditioned_p75","RB-conditioned P75"),
        ("expected_tp_ml_hgb_temporal_q50","HGB causal Q50"), ("expected_tp_ml_q75_resource","ML resource Q75"),
    ]:
        if col in ctx.columns and pd.to_numeric(ctx[col], errors="coerce").notna().any():
            plt.plot(x, pd.to_numeric(ctx[col], errors="coerce"), linewidth=1.1, label=label)
    plt.axvline(0, linestyle="--", label="Selected anomaly")
    actual = row.get(TARGET_COL, np.nan)
    p75_gap = row.get("throughput_gap_p75", np.nan)
    rb_gap = row.get("throughput_gap_rb_p75", np.nan)
    local_drop = np.nanmax([row.get("rolling_tp_gap", np.nan), row.get("tp_drop_from_prev", np.nan)])
    txt = f"Actual={actual:.2f} Mbps\nRadio-P75 gap={p75_gap:.2f} Mbps\nRB-P75 gap={rb_gap:.2f} Mbps\nLocal drop={local_drop:.2f} Mbps"
    plt.text(0.01, 0.98, txt, transform=plt.gca().transAxes, va="top", bbox=dict(boxstyle="round", alpha=0.15))
    plt.xlabel("Seconds relative to selected anomaly (1 sample = 1 second)")
    plt.ylabel("Throughput (Mbps)")
    plt.title(f"{case_name} — top case #{rank} | priority={row.get('final_rca_priority_score_0_100', np.nan):.1f}")
    plt.legend(loc="best")
    safe_case = re.sub(r"[^A-Za-z0-9_]+", "_", str(case_name))[:80]
    path = RCA_CASE_PLOTS_DIR / f"{safe_case}_top_{rank:02d}.png"
    plt.tight_layout(); plt.savefig(path, dpi=150, bbox_inches="tight");
    try:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=ctx[TARGET_COL], mode='lines+markers', name="Actual throughput"))
        for col, label in [
            ("expected_tp_radio_p75", "Radio P75"), ("expected_tp_rb_conditioned_p75", "RB-conditioned P75"),
            ("expected_tp_ml_hgb_temporal_q50", "HGB causal Q50"), ("expected_tp_ml_q75_resource", "ML resource Q75"),
        ]:
            if col in ctx.columns and pd.to_numeric(ctx[col], errors="coerce").notna().any():
                fig.add_trace(go.Scatter(x=x, y=pd.to_numeric(ctx[col], errors="coerce"), mode='lines', name=label))
        fig.add_vline(x=0, line_dash="dash", annotation_text="Selected anomaly")
        fig.update_layout(
            template='plotly_white',
            title=f"{case_name} — top case #{rank} | priority={row.get('final_rca_priority_score_0_100', np.nan):.1f}",
            xaxis_title="Seconds relative to selected anomaly (1 sample = 1 second)",
            yaxis_title="Throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        # Add annotation text box
        fig.add_annotation(
            text=txt,
            align='left',
            showarrow=False,
            xref='paper',
            yref='paper',
            x=0.01,
            y=0.98,
            bordercolor='white',
            borderwidth=1
        )
        fig.write_html(str(RCA_CASE_PLOTS_DIR / f"{safe_case}_top_{rank:02d}.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

def row_primary_detection_case(row):
    row_rules = [
        ("ca_underperformance_flag", "ca_underperformance"),
        ("radio_limited_degradation_flag", "radio_limited_degradation"),
        ("rolling_drop_flag", "temporal_local_drop"),
        ("sudden_drop_flag", "temporal_sudden_drop"),
        ("low_rb_efficiency_high_rb_flag", "rb_efficiency_underperformance"),
        ("underperform_vs_rb_p75_flag", "rb_conditioned_expected_underperformance"),
        ("underperform_vs_p75_flag", "radio_condition_expected_underperformance"),
        ("rolling_sustained_degradation_flag", "sustained_low_throughput"),
        ("low_tail_robust_consensus_flag", "robust_low_tail_consensus"),
    ]
    if bool(row.get("fused_ml_only_flag", False)):
        return "strict_ml_only_supervised_review"
    for col,label in row_rules:
        if bool(row.get(col, False)):
            return label
    return "other_throughput_anomaly"

if len(fused_handoff_rows):
    plot_rows = fused_handoff_rows.copy()
    plot_rows["final_detection_case"] = plot_rows.apply(row_primary_detection_case, axis=1)
    gap_plot_summary = []
    for case_name, cg in plot_rows.groupby("final_detection_case", dropna=False):
        cg = cg.sort_values("final_rca_priority_score_0_100", ascending=False).head(TOP_PLOTS_PER_ANOMALY_CASE)
        for rank,(_,row) in enumerate(cg.iterrows(), start=1):
            plot_case_context(row, case_name, rank)
            gap_plot_summary.append({
                "case": case_name, "rank_in_case": rank, "source_index": row.get("source_index"),
                "priority": row.get("final_rca_priority_score_0_100"), "actual_tp": row.get(TARGET_COL),
                "radio_p75_gap": row.get("throughput_gap_p75"), "rb_p75_gap": row.get("throughput_gap_rb_p75"),
                "rolling_drop_gap": row.get("rolling_tp_gap"), "previous_sample_drop_gap": row.get("tp_drop_from_prev"),
            })
    gap_plot_summary = pd.DataFrame(gap_plot_summary)
    save_table(gap_plot_summary, "top_anomaly_case_gap_drop_plot_index.csv", category="rca")

# Copy the most important machine-readable review tables into one obvious key-files folder.
key_manifest = pd.DataFrame([
    ("rca_anomaly_incidents_shortlist_diverse.json", "Primary diverse incident shortlist for RCA/demo"),
    ("rca_anomaly_incidents_full_compact.json", "All compact RCA-ready incidents"),
    ("worst_performing_cells_rca_handoff.json", "Worst cells ranked using throughput + CQI/MCS/BLER + anomaly evidence"),
    ("worst_performing_pci_rca_handoff.json", "PCI-only ranking; interpret with PCI reuse caution"),
    ("statistical_threshold_calibration_report.csv", "Data-driven threshold validation"),
    ("fusion_component_empirical_validation.csv", "Checks whether fusion components/bonuses are proportionate"),
    ("fusion_weight_health_check.csv", "Flags if evidence bonuses dominate main anomaly evidence"),
    ("ml_final_model_selection_summary.csv", "Why final predictive models are kept vs validation-only"),
    ("rca_json_schema_dictionary.csv", "Compact JSON field dictionary"),
], columns=["file", "purpose"])
save_table(key_manifest, "FINAL_RCA_KEY_FILES_MANIFEST.csv", category="key")

rca_readme = """RCA HANDOFF — START HERE

1. rca_anomaly_incidents_shortlist_diverse.json
   Primary presentation/review set: diverse high-priority incidents across anomaly cases.
2. rca_anomaly_incidents_full_compact.json
   Full compact RCA-ready incident handoff. Strict ML-only incidents are marked requires_human_review=true.
3. worst_performing_cells_rca_handoff.json
   Serving-cell ranking using throughput, anomaly/gap evidence, CQI, MCS, BLER, SINR, RSRQ and RSRP.
4. worst_performing_pci_rca_handoff.json
   Secondary PCI-only view. PCI reuse means this is not as reliable as ECI/EARFCN+PCI cell identity.
5. 01_top_anomaly_case_plots/
   Top examples per standardized anomaly case with actual throughput, expected references and explicit gap/drop annotation.

LSTM-Q50 and Isolation Forest are model-selection/context validators only and are deliberately excluded from the compact RCA JSON.
"""
(RCA_KEY_FILES_DIR / "README_FIRST_RCA_HANDOFF.txt").write_text(rca_readme, encoding="utf-8")

print("Compact RCA incidents:", len(incident_records), "| Diverse shortlist:", len(shortlist_records))
display(pd.DataFrame(shortlist_records)[[c for c in ["incident_id","detection_case","priority_score_0_100","severity","requires_human_review"] if c in pd.DataFrame(shortlist_records).columns]].head(30) if shortlist_records else pd.DataFrame())


# =========================
