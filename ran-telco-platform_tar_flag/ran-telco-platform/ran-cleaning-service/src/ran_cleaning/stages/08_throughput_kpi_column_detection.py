"""
Stage 08: throughput kpi column detection
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1349-1452). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 8. Canonical throughput and LTE KPI column detection
# =========================

def find_column(
    df: pd.DataFrame,
    exact: Sequence[str] = (),
    regex: Sequence[str] = (),
    exclude_regex: Sequence[str] = (),
    prefer_most_non_null: bool = False,
) -> Optional[str]:
    """
    Find a column by exact candidates first, then regex patterns.

    exact candidates preserve the known drive-test schema.
    regex candidates make the notebook more robust if exports vary slightly.
    """
    for col in exact:
        if col in df.columns:
            return col

    candidates = []
    for col in df.columns:
        text = str(col)
        if regex and not any(re.search(p, text, flags=re.IGNORECASE) for p in regex):
            continue
        if exclude_regex and any(re.search(p, text, flags=re.IGNORECASE) for p in exclude_regex):
            continue
        candidates.append(col)

    if not candidates:
        return None
    if prefer_most_non_null:
        return max(candidates, key=lambda c: df[c].notna().sum())
    return candidates[0]


SOURCE_COLS = {
    # Target and duplicates/references.
    "target_lte_dl_tp": find_column(drive_clean, exact=[
        "LTE.LTE_Data_KPI.Agg_Throughput_DL",
        "LTE.DownlinkMeasurements.Throughput_DL",
        "LTE - PrimaryCell - PCell_Throughput",
    ], regex=[r"LTE.*(Agg_)?Throughput.*DL", r"Downlink.*Throughput"], prefer_most_non_null=True),
    "duplicate_lte_dl_tp": find_column(drive_clean, exact=["LTE.DownlinkMeasurements.Throughput_DL"]),
    "pcell_tp": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_Throughput"]),
    "scell1_tp": find_column(drive_clean, exact=["LTE - SecondaryCell 1 - SCell1_Throughput"]),
    "http_dl_tp": find_column(drive_clean, exact=["Throughput.HTTP_DL"]),
    "physical_dl_tp": find_column(drive_clean, exact=["Throughput.Physical_DL"]),
    "activity_tp": find_column(drive_clean, exact=["Activity.Throughput"]),

    # Identity and serving-cell context.
    "serving_pci": find_column(drive_clean, exact=["LTE - Serving - PCI", "LTE - PrimaryCell - PCell_PCI"]),
    "serving_earfcn": find_column(drive_clean, exact=["LTE - Serving - EARFCN_DL", "LTE - PrimaryCell - PCell_EARFCN_DL"]),
    "serving_band": find_column(drive_clean, exact=["LTE - Serving - Band", "LTE - PrimaryCell - PCell_Band"]),
    "serving_eci": find_column(drive_clean, exact=["LTE - Serving - ECI"]),
    "serving_enodebid": find_column(drive_clean, exact=["LTE - Serving - EnodeBID"]),
    "serving_lci": find_column(drive_clean, exact=["LTE - Serving - LCI"]),

    # Radio quality.
    "lte_rsrp": find_column(drive_clean, exact=["LTE - PrimaryCell Radio - RSRP"]),
    "lte_rsrq": find_column(drive_clean, exact=["LTE - PrimaryCell Radio - PCell_RSRQ"]),
    "lte_sinr": find_column(drive_clean, exact=["LTE - PrimaryCell Radio - PCell_SINR"]),
    "lte_rssi": find_column(drive_clean, exact=["LTE - PrimaryCell Radio - PCell_RSSI"]),

    # PHY/scheduler/link adaptation.
    "lte_cqi": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_CQI", "LTE - PrimaryCell - PCell_CQI_CW0"]),
    "lte_mcs": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_MCS_CW0"]),
    "lte_bler": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_BLER"]),
    "lte_rank": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_SpatialRank", "LTE - PrimaryCell - PCell_LayerNum"]),
    "lte_rb_count": find_column(drive_clean, exact=["LTE - PrimaryCell - PCell_ResourceBlockNum", "LTE.LTE_Data_KPI.Agg_RB_DL"]),
    "lte_agg_rb_dl": find_column(drive_clean, exact=["LTE.LTE_Data_KPI.Agg_RB_DL"]),
    "lte_bandwidth_dl": find_column(drive_clean, exact=["LTE - Serving - BandWidth_DL", "LTE - PrimaryCell - PCell_BandWidth_DL"]),
    "lte_agg_bandwidth_dl": find_column(drive_clean, exact=["LTE.LTE_Data_KPI.Agg_Bandwidth_DL"]),

    # Carrier aggregation / SCell1.
    "carrier_count": find_column(drive_clean, exact=["LTE.DedicatedRadioLink.CarrierCount"]),
    "scell1_rsrp": find_column(drive_clean, exact=["LTE - SecondaryCell 1 Radio - SCell1_RSRP"]),
    "scell1_rsrq": find_column(drive_clean, exact=["LTE - SecondaryCell 1 Radio - SCell1_RSRQ"]),
    "scell1_sinr": find_column(drive_clean, exact=["LTE - SecondaryCell 1 Radio - SCell1_SINR"]),
    "scell1_cqi": find_column(drive_clean, exact=["LTE - SecondaryCell 1 - SCell1_CQI", "LTE - SecondaryCell 1 - SCell1_CQI_CW0"]),
    "scell1_mcs": find_column(drive_clean, exact=["LTE - SecondaryCell 1 - SCell1_MCS_CW0"]),
    "scell1_bler": find_column(drive_clean, exact=["LTE - SecondaryCell 1 - SCell1_BLER"]),
    "scell1_rb_count": find_column(drive_clean, exact=["LTE - SecondaryCell 1 - SCell1_ResourceBlockNum"]),

    # LTE RACH direct fields, preserved as event/access evidence.
    "rach_result": find_column(drive_clean, exact=["LTE.RACH.RACH_Result"]),
    "rach_reason": find_column(drive_clean, exact=["LTE.RACH.RACH_Reason"]),
    "rach_latency": find_column(drive_clean, exact=["LTE.RACH.RACH_Latency"]),
}

canonical_mapping = pd.DataFrame([
    {"canonical_name": key, "source_column": value}
    for key, value in SOURCE_COLS.items()
])
save_table(canonical_mapping, "canonical_column_mapping.csv")
display(canonical_mapping)

if SOURCE_COLS["target_lte_dl_tp"] is None:
    raise KeyError(
        "Could not detect an LTE downlink throughput target column. "
        "Check canonical_column_mapping.csv and update SOURCE_COLS candidates."
    )

    # =========================
