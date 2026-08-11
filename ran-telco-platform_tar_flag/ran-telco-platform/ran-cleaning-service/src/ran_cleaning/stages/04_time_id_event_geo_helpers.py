"""
Stage 04: time id event geo helpers
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1009-1178). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 4. Time, ID, event, and geo helpers
# =========================

def parse_drive_test_id(id_value: Any) -> Dict[str, Any]:
    """
    Parse IDs like:
    542020041221088+20250825121610+Fiji-Nadi-MO-D!20250825121533
    """
    text = str(id_value) if pd.notna(id_value) else ""
    result = {
        "id_imsi": np.nan,
        "id_session_time_raw": np.nan,
        "id_route_test_label": np.nan,
        "id_log_time_raw": np.nan,
        "id_session_time": pd.NaT,
        "id_log_time": pd.NaT,
        "id_location_label": np.nan,
        "id_test_type": np.nan,
    }
    if not text:
        return result

    main_part, bang, log_part = text.partition("!")
    plus_parts = main_part.split("+")

    if len(plus_parts) >= 1:
        result["id_imsi"] = plus_parts[0]
    if len(plus_parts) >= 2:
        result["id_session_time_raw"] = plus_parts[1]
        result["id_session_time"] = pd.to_datetime(plus_parts[1], format="%Y%m%d%H%M%S", errors="coerce")
    if len(plus_parts) >= 3:
        label = "+".join(plus_parts[2:])
        result["id_route_test_label"] = label
        label_parts = label.split("-")
        if len(label_parts) >= 2:
            result["id_location_label"] = "-".join(label_parts[:2])
        if len(label_parts) >= 4:
            result["id_test_type"] = "-".join(label_parts[-2:])
        elif len(label_parts) >= 1:
            result["id_test_type"] = label_parts[-1]
    if bang:
        result["id_log_time_raw"] = log_part
        result["id_log_time"] = pd.to_datetime(log_part, format="%Y%m%d%H%M%S", errors="coerce")

    return result


def add_id_features(df: pd.DataFrame, id_col: str = "id") -> pd.DataFrame:
    """Add parsed route/session/test fields from the drive-test id."""
    if id_col not in df.columns:
        print("ID column not found. ID-derived fields will be missing.")
        return df.copy()
    unique_ids = df[id_col].drop_duplicates()
    parsed = unique_ids.apply(parse_drive_test_id).apply(pd.Series)
    parsed[id_col] = unique_ids.values
    return df.merge(parsed, on=id_col, how="left")


def split_multi_value(value: Any, sep: str = "$$$$") -> List[Any]:
    """Split packed event fields that contain multiple values separated by $$$$."""
    if pd.isna(value):
        return []
    return str(value).split(sep)


def build_events_long(df: pd.DataFrame, id_col: str = "id", sample_time_col: str = "timestamp") -> pd.DataFrame:
    """
    Convert packed row-level Events.* columns into a clean event-level table.
    One output row equals one event.
    """
    event_cols = [
        "Events.Timestamp",
        "Events.category",
        "Events.Tech",
        "Events.titles",
        "Events.description",
        "Events.subject",
    ]
    available = [c for c in event_cols if c in df.columns]
    if not available:
        print("No Events.* columns found.")
        return pd.DataFrame()

    source = df[df[available].notna().any(axis=1)].copy()
    event_rows = []

    for idx, row in source.iterrows():
        split_values = {c: split_multi_value(row[c]) for c in available}
        max_len = max([len(v) for v in split_values.values()] + [0])
        for order in range(max_len):
            rec = {"source_index": idx, "event_order_in_sample": order}
            if id_col in df.columns:
                rec[id_col] = row[id_col]
            if sample_time_col in df.columns:
                rec["sample_timestamp"] = row[sample_time_col]
            for c in available:
                values = split_values[c]
                rec[c] = values[order] if order < len(values) else np.nan
            event_rows.append(rec)

    events = pd.DataFrame(event_rows)
    if events.empty:
        return events

    if "Events.Timestamp" in events.columns:
        events["event_timestamp"] = pd.to_datetime(events["Events.Timestamp"], errors="coerce")
    if "sample_timestamp" in events.columns:
        events["sample_timestamp"] = pd.to_datetime(events["sample_timestamp"], errors="coerce")
        if "event_timestamp" in events.columns:
            events["event_delay_from_sample_seconds"] = (
                events["event_timestamp"] - events["sample_timestamp"]
            ).dt.total_seconds()
    return events


def classify_event_family(row: pd.Series) -> str:
    """
    Create a compact event family for anomaly evidence.

    This is not final RCA. The goal is to keep frequent measurement reports separate
    from actual handover execution/failure, RACH failures, and CA activation changes.
    """
    text = " ".join([
        str(row.get("Events.titles", "")),
        str(row.get("Events.subject", "")),
        str(row.get("Events.description", "")),
    ]).lower()

    # RACH / random access.
    if re.search(r"rach|random access", text):
        if re.search(r"fail|failure|timeout|reject|abort|unsuccess", text):
            return "rach_failure"
        return "rach_attempt"

    # Handover failures and radio-link/mobility failures should be separated from
    # ordinary measurement-report events.
    if re.search(r"handover.*(fail|failure|timeout|reject|abort)|ho.*(fail|failure)|radio link failure|rlf|re[- ]?establishment", text):
        return "handover_failure"

    # Actual mobility execution/context. This is still context only, but it is much
    # less broad than treating A1/A2/A3/A5/A6 measurement reports as handovers.
    if re.search(r"handover command|handover complete|handover success|ho command|ho complete|serving cell change|cell reselection", text):
        return "handover_execution"

    # Measurement reports are common and should not dominate event-related evidence.
    if re.search(r"event a1|event a2|event a3|event a5|event a6|measurement report|meas report", text):
        return "measurement_report_event"

    # Carrier aggregation and SCell state changes.
    if re.search(r"lte ca|carrier aggregation|scell|secondary cell|ca init|ca complete|ca deact|ca activ|activation|deactivation|add scell|release scell", text):
        return "ca_activation_change"

    if re.search(r"fail|failure|timeout|reject|abort|unsuccess", text):
        return "failure_other"
    return "other"


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in kilometers."""
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


# =========================
