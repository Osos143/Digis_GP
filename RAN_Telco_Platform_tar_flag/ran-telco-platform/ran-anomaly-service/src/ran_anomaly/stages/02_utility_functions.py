"""
Stage 02: utility functions
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 283-935). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 2. General utility functions
# =========================

import plotly.graph_objects as go

def human_bytes(num_bytes: float) -> str:
    """Convert bytes to a readable memory-size string."""
    if pd.isna(num_bytes):
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024:
            return f"{size:,.2f} {unit}"
        size /= 1024
    return f"{size:,.2f} PB"



def infer_output_dir(filename: str, category: Optional[str] = None) -> Path:
    """
    Route output artifacts into the requested folder.

    category can be:
    - "preprocessing" / "cleaning"
    - "anomaly"
    - "plots"
    - "rca" / "handoff" / "key"

    When category is omitted, the filename is classified using stable prefixes.
    """
    if category is not None:
        cat = str(category).lower()
        if cat in {"preprocessing", "cleaning", "preprocess", "clean"}:
            return PREPROCESSING_DIR
        if cat in {"anomaly", "anomalies", "detection"}:
            return ANOMALY_DIR
        if cat in {"plot", "plots", "figure", "figures"}:
            return PLOTS_DIR
        if cat in {"rca", "handoff", "final"}:
            return RCA_HANDOFF_DIR
        if cat in {"key", "review", "key_review"}:
            return RCA_KEY_FILES_DIR

    name = str(filename).lower()
    preprocessing_prefixes = (
        "raw_", "column_family_", "missing_", "kept_", "removed_",
        "cleaning_", "cleaned_", "drive_clean_", "activity_", "events_",
        "event_", "canonical_", "detected_", "lte_dl_modeling_table",
        "download_activity_", "throughput_by_download_context", "throughput_by_ca_condition",
        "throughput_by_rb_demand", "rb_usage_quality", "threshold_calibration",
    )
    if name.startswith(preprocessing_prefixes):
        return PREPROCESSING_DIR
    return ANOMALY_DIR


def save_table(df: pd.DataFrame, filename: str, index: bool = False, category: Optional[str] = None) -> Path:
    """Save a table as UTF-8 CSV inside the correct output subfolder."""
    folder = infer_output_dir(filename, category=category)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    df.to_csv(path, index=index, encoding="utf-8-sig")
    print(f"Saved CSV: {path}  shape={df.shape}")
    return path


def save_parquet_or_csv(df: pd.DataFrame, filename_no_ext: str, index: bool = False, category: Optional[str] = None) -> Path:
    """
    Save a DataFrame as Parquet when pyarrow/fastparquet is available.
    If Parquet support is missing, save a compressed CSV fallback.
    """
    folder = infer_output_dir(filename_no_ext, category=category)
    folder.mkdir(parents=True, exist_ok=True)
    parquet_path = folder / f"{filename_no_ext}.parquet"
    csv_path = folder / f"{filename_no_ext}.csv.gz"
    try:
        df.to_parquet(parquet_path, index=index)
        print(f"Saved Parquet: {parquet_path}  shape={df.shape}")
        return parquet_path
    except Exception as exc:
        print("Parquet export failed. Falling back to compressed CSV.")
        print("Reason:", exc)
        df.to_csv(csv_path, index=index, compression="gzip", encoding="utf-8-sig")
        print(f"Saved compressed CSV: {csv_path}  shape={df.shape}")
        return csv_path


def sample_df(df: pd.DataFrame, n: int = 100_000, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Return a safe sample. If df is smaller than n, return a copy of the full df."""
    if len(df) <= n:
        return df.copy()
    return df.sample(n=n, random_state=seed).copy()


def safe_value_counts(s: pd.Series, top_n: int = 10) -> Dict[str, int]:
    """Return top value counts as a dict without failing on mixed dtypes."""
    non_null = s.dropna()
    if non_null.empty:
        return {}
    return non_null.astype(str).value_counts().head(top_n).to_dict()


def get_column_family(col: str) -> str:
    """Infer a practical telecom family from a column name."""
    text = str(col)
    if " - " in text:
        return text.split(" - ")[0].strip()
    if "." in text:
        return text.split(".")[0].strip()
    return text.split()[0].strip() if text.split() else "Unknown"


def first_existing(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    """Return the first existing column from a candidate list."""
    for col in candidates:
        if col in df.columns:
            return col
    return None


def to_numeric_series(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
    """Return a numeric Series for col; returns all-NaN if col is missing."""
    if col is None or col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def overview(df: pd.DataFrame, name: str) -> None:
    """Display a compact overview of a dataframe."""
    print(f"===== {name} =====")
    print("Shape:", df.shape)
    print("Rows:", f"{len(df):,}")
    print("Columns:", f"{df.shape[1]:,}")
    print("Memory:", human_bytes(df.memory_usage(deep=True).sum()))
    display(pd.DataFrame({
        "column": df.columns,
        "dtype": df.dtypes.astype(str).values,
        "non_null": df.notna().sum().values,
        "missing": df.isna().sum().values,
        "missing_pct": (df.isna().mean().values * 100).round(3),
    }).head(250))

    # =========================
# 2B. Visualization helper functions
# =========================


def save_current_plot(filename: str) -> None:
    """Save the current matplotlib figure into the notebook plot-output folder."""
    path = PLOTS_DIR / filename
    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    print(f"Saved plot: {path}")


def save_plotly_html(fig, filename: str) -> None:
    """Save the Plotly figure as an interactive HTML file."""
    try:
        html_filename = str(filename).replace('.png', '.html')
        if not html_filename.endswith('.html'):
            html_filename += '.html'
        path = PLOTS_DIR / html_filename
        fig.write_html(path, include_plotlyjs='cdn')
        print(f"Saved interactive plot: {path}")
    except Exception as e:
        print(f"Plotly HTML save failed: {e}")


def clip_for_plot(s: pd.Series, lower: Optional[float] = None, upper_q: Optional[float] = 0.995) -> pd.Series:
    """Return a numeric series clipped only for visualization, never for modeling."""
    out = pd.to_numeric(s, errors="coerce")
    if lower is not None:
        out = out.clip(lower=lower)
    if upper_q is not None and out.notna().any():
        upper = out.quantile(upper_q)
        out = out.clip(upper=upper)
    return out


def plot_distribution_with_lines(
    df: pd.DataFrame,
    col: str,
    title: str,
    xlabel: str,
    thresholds: Optional[Dict[str, float]] = None,
    bins: int = 80,
    filename: Optional[str] = None,
    clip_upper_q: Optional[float] = 0.995,
) -> None:
    """Plot a histogram with optional vertical reference thresholds."""
    if col not in df.columns:
        print(f"Skipped {title}: column not found: {col}")
        return
    s = clip_for_plot(df[col], lower=0 if "throughput" in col.lower() or "score" in col.lower() else None, upper_q=clip_upper_q).dropna()
    if s.empty:
        print(f"Skipped {title}: no numeric values in {col}")
        return
    plt.figure(figsize=(12, 5))
    plt.hist(s, bins=bins)
    if thresholds:
        for label, value in thresholds.items():
            if pd.notna(value):
                plt.axvline(float(value), linestyle="--", label=f"{label}: {float(value):.2f}")
        plt.legend()
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("Rows")
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        fig.add_trace(go.Histogram(x=s, nbinsx=bins, name=col))
        if thresholds:
            y_max = np.histogram(s, bins=bins)[0].max() if len(s) > 0 else 1
            for label, value in thresholds.items():
                if pd.notna(value):
                    fig.add_trace(go.Scatter(x=[float(value), float(value)], y=[0, y_max], mode='lines', name=label, line=dict(dash='dash')))
        fig.update_layout(
            template='plotly_white',
            title=title,
            xaxis_title=xlabel,
            yaxis_title="Rows",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for {title}: {e}")

    plt.show()


def plot_box_by_category(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    title: str,
    ylabel: str,
    filename: Optional[str] = None,
    category_order: Optional[List[Any]] = None,
    clip_upper_q: Optional[float] = 0.995,
) -> None:
    """Plot a boxplot for a numeric value split by a categorical column."""
    if category_col not in df.columns or value_col not in df.columns:
        print(f"Skipped {title}: missing {category_col} or {value_col}")
        return
    tmp = df[[category_col, value_col]].copy()
    tmp[value_col] = clip_for_plot(tmp[value_col], lower=0, upper_q=clip_upper_q)
    tmp = tmp.dropna(subset=[category_col, value_col])
    if tmp.empty:
        print(f"Skipped {title}: no data after dropping missing values")
        return
    if category_order is None:
        category_order = list(tmp[category_col].astype(str).value_counts().index)
    data = [tmp.loc[tmp[category_col].astype(str) == str(cat), value_col].values for cat in category_order]
    labels = [str(cat) for cat, arr in zip(category_order, data) if len(arr) > 0]
    data = [arr for arr in data if len(arr) > 0]
    if not data:
        print(f"Skipped {title}: no non-empty groups")
        return
    plt.figure(figsize=(12, 5))
    try:
        # matplotlib < 3.9 API
        plt.boxplot(data, labels=labels, showfliers=False)
    except TypeError:
        # matplotlib >= 3.9 renamed `labels` to `tick_labels`; same visual result either way.
        plt.boxplot(data, tick_labels=labels, showfliers=False)
    plt.title(title)
    plt.xlabel(category_col)
    plt.ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        for cat, arr, label in zip(category_order, data, labels):
            fig.add_trace(go.Box(y=arr, name=label))
        fig.update_layout(
            template='plotly_white',
            title=title,
            xaxis_title=category_col,
            yaxis_title=ylabel,
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for {title}: {e}")

    plt.show()


def plot_scatter_sample(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    xlabel: str,
    ylabel: str,
    filename: Optional[str] = None,
    max_points: int = 20_000,
    y_clip_upper_q: Optional[float] = 0.995,
) -> None:
    """Scatter plot on a random sample to keep the notebook responsive."""
    if x_col not in df.columns or y_col not in df.columns:
        print(f"Skipped {title}: missing {x_col} or {y_col}")
        return
    tmp = df[[x_col, y_col]].copy()
    tmp[y_col] = clip_for_plot(tmp[y_col], lower=0, upper_q=y_clip_upper_q)
    tmp = tmp.dropna()
    if tmp.empty:
        print(f"Skipped {title}: no data")
        return
    tmp = sample_df(tmp, max_points)
    plt.figure(figsize=(10, 5))
    plt.scatter(tmp[x_col], tmp[y_col], s=6, alpha=0.35)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(
            x=tmp[x_col], 
            y=tmp[y_col], 
            mode='markers',
            marker=dict(size=6, opacity=0.35)
        ))
        fig.update_layout(
            template='plotly_white',
            title=title,
            xaxis_title=xlabel,
            yaxis_title=ylabel,
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for {title}: {e}")

    plt.show()



def plot_route_metric(
    df: pd.DataFrame,
    metric_col: str,
    title: str,
    filename: Optional[str] = None,
    max_points: int = 30_000,
    clip_upper_q: Optional[float] = ROUTE_MAP_COLOR_CLIP_Q,
    colorbar_label: Optional[str] = None,
) -> None:
    """Route scatter colored by a metric, with optional display-only clipping.

    The metric values are never changed in the dataframe. Clipping is applied only to the
    plotted color values so that extreme throughput outliers do not make the whole route
    appear dark. This is especially useful for drive-test throughput maps where the most
    important visual detail is often in the 0-80 Mbps range, while a few samples exceed
    200 Mbps.
    """
    required = {"latitude", "longitude", metric_col}
    if not required.issubset(df.columns):
        print(f"Skipped {title}: missing one of {required}")
        return
    tmp = df.dropna(subset=["latitude", "longitude", metric_col]).copy()
    if tmp.empty:
        print(f"Skipped {title}: no valid GPS/metric rows")
        return
    tmp = sample_df(tmp, max_points)

    color_values = pd.to_numeric(tmp[metric_col], errors="coerce")
    cb_label = colorbar_label or metric_col
    if clip_upper_q is not None and color_values.notna().any():
        upper = color_values.quantile(clip_upper_q)
        color_values = color_values.clip(upper=upper)
        cb_label = f"{cb_label} (display clipped at P{int(clip_upper_q * 100)}={upper:.2f})"

    plt.figure(figsize=(8, 8))
    sc = plt.scatter(tmp["longitude"], tmp["latitude"], c=color_values, s=7, alpha=0.75)
    plt.colorbar(sc, label=cb_label)
    plt.title(title)
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(
            x=tmp["longitude"], 
            y=tmp["latitude"], 
            mode='markers', 
            marker=dict(
                color=color_values, 
                colorscale='Viridis',
                size=7,
                opacity=0.75,
                colorbar=dict(title=cb_label)
            ),
            text=color_values,
            hovertemplate="Lon: %{x}<br>Lat: %{y}<br>Value: %{text}<extra></extra>"
        ))
        fig.update_layout(
            template='plotly_white',
            title=title,
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for {title}: {e}")

    plt.show()


def plot_route_anomaly_overlay(
    df: pd.DataFrame,
    filename: Optional[str] = None,
    max_points: int = 40_000,
) -> None:
    """Show the full route as background and overlay anomaly samples.

    This makes spatial anomaly interpretation easier than coloring every point with the
    raw score. The background route shows coverage of the drive path, while overlaid samples
    show where the detector found problematic LTE-DL behavior.
    """
    required = {"latitude", "longitude", "is_throughput_anomaly"}
    if not required.issubset(df.columns):
        print(f"Skipped anomaly overlay map: missing one of {required}")
        return
    tmp = df.dropna(subset=["latitude", "longitude"]).copy()
    if tmp.empty:
        print("Skipped anomaly overlay map: no valid GPS rows")
        return
    tmp = sample_df(tmp, max_points)
    normal = tmp[~tmp["is_throughput_anomaly"].fillna(False).astype(bool)]
    anom = tmp[tmp["is_throughput_anomaly"].fillna(False).astype(bool)]

    plt.figure(figsize=(8, 8))
    if not normal.empty:
        plt.scatter(normal["longitude"], normal["latitude"], s=5, alpha=0.20, label="Not flagged")
    if not anom.empty:
        score = pd.to_numeric(anom.get("anomaly_score_0_100", pd.Series(1, index=anom.index)), errors="coerce").fillna(1)
        plt.scatter(anom["longitude"], anom["latitude"], c=score, s=10, alpha=0.85, label="Flagged anomaly")
        plt.colorbar(label="Anomaly score (0-100)")
    plt.title("Route with Throughput Anomaly Overlay")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend()
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        if not normal.empty:
            fig.add_trace(go.Scattergl(
                x=normal["longitude"],
                y=normal["latitude"],
                mode='markers',
                marker=dict(size=5, opacity=0.20, color='blue'),
                name="Not flagged",
                hovertemplate="Lon: %{x}<br>Lat: %{y}<extra></extra>"
            ))
        if not anom.empty:
            score = pd.to_numeric(anom.get("anomaly_score_0_100", pd.Series(1, index=anom.index)), errors="coerce").fillna(1)
            fig.add_trace(go.Scattergl(
                x=anom["longitude"],
                y=anom["latitude"],
                mode='markers',
                marker=dict(
                    color=score,
                    colorscale='Viridis',
                    size=10,
                    opacity=0.85,
                    colorbar=dict(title="Anomaly score (0-100)")
                ),
                name="Flagged anomaly",
                text=score,
                hovertemplate="Lon: %{x}<br>Lat: %{y}<br>Score: %{text}<extra></extra>"
            ))
        fig.update_layout(
            template='plotly_white',
            title="Route with Throughput Anomaly Overlay",
            xaxis_title="Longitude",
            yaxis_title="Latitude",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for Route with Throughput Anomaly Overlay: {e}")

    plt.show()


def plot_flag_percentage_bars(summary_df: pd.DataFrame, filename: Optional[str] = None) -> None:
    """Plot anomaly method/case percentages from anomaly_method_summary.csv."""
    if summary_df is None or summary_df.empty or "method_or_case" not in summary_df.columns:
        print("Skipped method-percentage plot: summary table is empty")
        return
    tmp = summary_df.sort_values("flagged_pct", ascending=True)
    plt.figure(figsize=(12, max(5, 0.35 * len(tmp))))
    plt.barh(tmp["method_or_case"], tmp["flagged_pct"])
    plt.xlabel("Flagged rows (%)")
    plt.title("Anomaly Method / Case Flagging Rate")
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=tmp["flagged_pct"],
            y=tmp["method_or_case"],
            orientation='h'
        ))
        fig.update_layout(
            template='plotly_white',
            title="Anomaly Method / Case Flagging Rate",
            xaxis_title="Flagged rows (%)",
            yaxis_title="",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for Anomaly Method / Case Flagging Rate: {e}")

    plt.show()


def plot_actual_vs_expected(df: pd.DataFrame, filename: Optional[str] = None, max_points: int = 25_000) -> None:
    """Actual-vs-expected scatter with anomaly samples highlighted."""
    needed = {"actual_lte_dl_throughput", "expected_tp_p75", "is_throughput_anomaly"}
    if not needed.issubset(df.columns):
        print(f"Skipped actual-vs-expected plot: missing {needed - set(df.columns)}")
        return
    tmp = df.dropna(subset=["actual_lte_dl_throughput", "expected_tp_p75"]).copy()
    if tmp.empty:
        print("Skipped actual-vs-expected plot: no valid rows")
        return
    tmp = sample_df(tmp, max_points)
    normal = tmp[~tmp["is_throughput_anomaly"].fillna(False).astype(bool)]
    anom = tmp[tmp["is_throughput_anomaly"].fillna(False).astype(bool)]
    plt.figure(figsize=(8, 8))
    if not normal.empty:
        plt.scatter(normal["expected_tp_p75"], normal["actual_lte_dl_throughput"], s=5, alpha=0.25, label="Not flagged")
    if not anom.empty:
        plt.scatter(anom["expected_tp_p75"], anom["actual_lte_dl_throughput"], s=7, alpha=0.55, label="Flagged anomaly")
    max_axis = np.nanpercentile(tmp[["expected_tp_p75", "actual_lte_dl_throughput"]].values, 99)
    plt.plot([0, max_axis], [0, max_axis], linestyle="--", label="Actual = expected")
    plt.xlabel("Expected throughput P75 (Mbps)")
    plt.ylabel("Actual LTE DL throughput (Mbps)")
    plt.title("Actual vs Group-P75 Expected Throughput")
    plt.legend()
    if filename:
        save_current_plot(filename)

    try:
        fig = go.Figure()
        if not normal.empty:
            fig.add_trace(go.Scattergl(
                x=normal["expected_tp_p75"],
                y=normal["actual_lte_dl_throughput"],
                mode='markers',
                marker=dict(size=5, opacity=0.25, color='blue'),
                name="Not flagged"
            ))
        if not anom.empty:
            fig.add_trace(go.Scattergl(
                x=anom["expected_tp_p75"],
                y=anom["actual_lte_dl_throughput"],
                mode='markers',
                marker=dict(size=7, opacity=0.55, color='orange'),
                name="Flagged anomaly"
            ))
        fig.add_trace(go.Scatter(
            x=[0, max_axis],
            y=[0, max_axis],
            mode='lines',
            line=dict(dash='dash', color='white'),
            name="Actual = expected"
        ))
        fig.update_layout(
            template='plotly_white',
            title="Actual vs Group-P75 Expected Throughput",
            xaxis_title="Expected throughput P75 (Mbps)",
            yaxis_title="Actual LTE DL throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename:
            save_plotly_html(fig, filename)
    except Exception as e:
        print(f"Plotly generation failed for Actual vs Group-P75 Expected Throughput: {e}")

    plt.show()



def plot_anomaly_context(
    df: pd.DataFrame,
    anomaly_df: Optional[pd.DataFrame] = None,
    rank: int = 0,
    samples_before: int = 40,
    samples_after: int = 40,
    filename_prefix: Optional[str] = None,
    title_prefix: str = "Top anomaly context window",
) -> None:
    """Plot surrounding session samples around a selected anomaly.

    The rolling/anomaly context is sample-based because the current drive-test export is
    mostly consecutive. To make the sample axis easier to interpret, the x-axis tick labels
    also show the real elapsed seconds from the selected anomaly when timestamps exist.

    The selected anomaly itself is shown with a vertical dashed line. The plot helps answer:
    - Is this an isolated drop?
    - Is it part of a sustained bad window?
    - Is expected P75 consistently above actual, or only locally?
    - Did radio KPIs degrade around the same time?
    """
    if anomaly_df is None:
        if "is_throughput_anomaly" not in df.columns:
            print("Skipped anomaly context: no anomaly flag available")
            return
        anomaly_df = df[df["is_throughput_anomaly"].fillna(False).astype(bool)].copy()

    if anomaly_df.empty:
        print("Skipped anomaly context: no anomalies available")
        return

    if "anomaly_score_0_100" in anomaly_df.columns:
        anomaly_df = anomaly_df.sort_values("anomaly_score_0_100", ascending=False)

    if rank >= len(anomaly_df):
        print(f"Skipped anomaly context: rank {rank} out of range")
        return

    row = anomaly_df.iloc[rank]
    sid = row.get("id", None)

    if "id" in df.columns and pd.notna(sid):
        session = df[df["id"] == sid].copy()
    else:
        session = df.copy()

    if "timestamp" in session.columns:
        session = session.sort_values("timestamp")

    # Find the center row using source_index when available, otherwise nearest timestamp.
    center_pos = None
    if "source_index" in row.index and "source_index" in session.columns:
        matches = np.where(session["source_index"].values == row["source_index"])[0]
        if len(matches):
            center_pos = int(matches[0])

    if center_pos is None and "timestamp" in row.index and "timestamp" in session.columns:
        session_ts_utc = pd.to_datetime(session["timestamp"], utc=True, errors="coerce")
        row_ts_utc = pd.to_datetime(row["timestamp"], utc=True, errors="coerce")
        diffs = (session_ts_utc - row_ts_utc).abs()
        center_pos = int(diffs.argmin()) if len(diffs) else None

    if center_pos is None:
        print("Skipped anomaly context: could not locate selected anomaly in session")
        return

    start = max(0, center_pos - samples_before)
    end = min(len(session), center_pos + samples_after + 1)
    ctx = session.iloc[start:end].copy().reset_index(drop=True)
    ctx["context_sample_number"] = np.arange(len(ctx))
    center_x = center_pos - start

    selected_timestamp_text = ""
    if "timestamp" in ctx.columns:
        ts = pd.to_datetime(ctx["timestamp"], utc=True, errors="coerce")
        center_ts = ts.iloc[center_x]
        ctx["seconds_from_selected_anomaly"] = (ts - center_ts).dt.total_seconds()
        if pd.notna(center_ts):
            selected_timestamp_text = f" | selected time: {center_ts}"

    def _apply_time_ticks() -> None:
        """Use tick labels that show both sample index and seconds from selected anomaly."""
        if "seconds_from_selected_anomaly" not in ctx.columns:
            plt.xlabel("Sample number inside context window")
            return
        max_ticks = min(11, len(ctx))
        ticks = np.linspace(0, len(ctx) - 1, max_ticks).round().astype(int)
        ticks = np.unique(np.r_[ticks, center_x])
        tick_labels = []
        for t in ticks:
            sec = ctx.loc[int(t), "seconds_from_selected_anomaly"]
            if pd.notna(sec):
                tick_labels.append(f"{int(t)}\n{sec:+.0f}s")
            else:
                tick_labels.append(str(int(t)))
        plt.xticks(ticks, tick_labels)
        plt.xlabel("Context sample number\n(second line = seconds from selected anomaly)")

    # Print a compact textual summary before the plots.
    summary_cols = [
        "timestamp", "id", "anomaly_type", "anomaly_type_flags", "anomaly_score_0_100",
        "actual_lte_dl_throughput", "expected_tp_p75", "expected_tp_rb_conditioned_p75", "throughput_ratio_p75", "throughput_ratio_rb_p75",
        "rb_usage_value", "rb_usage_bucket", "rb_demand_confidence", "throughput_per_rb",
        "lte_rsrp", "lte_rsrq", "lte_sinr", "carrier_count",
        "download_context_label", "download_analysis_window_flag",
    ]
    available_summary_cols = [c for c in summary_cols if c in row.index]
    if available_summary_cols:
        print("Selected anomaly summary:")
        display(pd.DataFrame([row[available_summary_cols].to_dict()]))

    plt.figure(figsize=(14, 5))
    plt.plot(ctx["context_sample_number"], ctx["actual_lte_dl_throughput"], marker="o", markersize=3, label="Actual TP")
    if "expected_tp_p75" in ctx.columns:
        plt.plot(ctx["context_sample_number"], ctx["expected_tp_p75"], linestyle="--", label="Radio P75")
    if "expected_tp_rb_conditioned_p75" in ctx.columns:
        plt.plot(ctx["context_sample_number"], ctx["expected_tp_rb_conditioned_p75"], linestyle="-.", label="RB-conditioned P75")
    if "rolling_median_tp" in ctx.columns:
        plt.plot(ctx["context_sample_number"], ctx["rolling_median_tp"], linestyle=":", label="Rolling median")
    if "download_analysis_window_flag" in ctx.columns:
        # Lightly mark samples that are outside the parsed active download window.
        # This is context only; it is not the main anomaly-analysis mask in the latest version.
        inactive = ~ctx["download_analysis_window_flag"].fillna(True).astype(bool)
        if inactive.any():
            y_marker = max(0, np.nanmin(ctx["actual_lte_dl_throughput"]) if ctx["actual_lte_dl_throughput"].notna().any() else 0)
            plt.scatter(ctx.loc[inactive, "context_sample_number"], np.repeat(y_marker, inactive.sum()), marker="x", s=25, label="Outside parsed active download window")
    plt.axvline(center_x, linestyle="--", label="Selected anomaly")
    plt.title(f"{title_prefix} #{rank + 1}: throughput behavior{selected_timestamp_text}")
    _apply_time_ticks()
    plt.ylabel("Throughput (Mbps)")
    plt.legend()
    if filename_prefix:
        save_current_plot(f"{filename_prefix}_rank_{rank + 1}_throughput_context.png")

    try:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ctx["context_sample_number"], y=ctx["actual_lte_dl_throughput"], mode='lines+markers', name="Actual TP", marker=dict(size=3)))
        if "expected_tp_p75" in ctx.columns:
            fig.add_trace(go.Scatter(x=ctx["context_sample_number"], y=ctx["expected_tp_p75"], mode='lines', line=dict(dash='dash'), name="Radio P75"))
        if "expected_tp_rb_conditioned_p75" in ctx.columns:
            fig.add_trace(go.Scatter(x=ctx["context_sample_number"], y=ctx["expected_tp_rb_conditioned_p75"], mode='lines', line=dict(dash='dashdot'), name="RB-conditioned P75"))
        if "rolling_median_tp" in ctx.columns:
            fig.add_trace(go.Scatter(x=ctx["context_sample_number"], y=ctx["rolling_median_tp"], mode='lines', line=dict(dash='dot'), name="Rolling median"))
        
        if "download_analysis_window_flag" in ctx.columns:
            inactive = ~ctx["download_analysis_window_flag"].fillna(True).astype(bool)
            if inactive.any():
                y_marker = max(0, np.nanmin(ctx["actual_lte_dl_throughput"]) if ctx["actual_lte_dl_throughput"].notna().any() else 0)
                fig.add_trace(go.Scatter(
                    x=ctx.loc[inactive, "context_sample_number"],
                    y=np.repeat(y_marker, inactive.sum()),
                    mode='markers',
                    marker=dict(symbol='x', size=8),
                    name="Outside parsed active download window"
                ))
        
        y_max = ctx["actual_lte_dl_throughput"].max()
        fig.add_trace(go.Scatter(x=[center_x, center_x], y=[0, y_max if pd.notna(y_max) else 100], mode='lines', line=dict(dash='dash', color='red'), name="Selected anomaly"))
        
        fig.update_layout(
            template='plotly_white',
            title=f"{title_prefix} #{rank + 1}: throughput behavior{selected_timestamp_text}",
            xaxis_title="Context sample number\n(second line = seconds from selected anomaly)" if "seconds_from_selected_anomaly" in ctx.columns else "Sample number inside context window",
            yaxis_title="Throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest',
        )
        if filename_prefix:
            save_plotly_html(fig, f"{filename_prefix}_rank_{rank + 1}_throughput_context.png")
    except Exception as e:
        print(f"Plotly generation failed for context throughput: {e}")

    plt.show()

    # Separate radio-context plot so throughput and radio scales are not mixed.
    radio_cols = [c for c in ["lte_rsrp", "lte_rsrq", "lte_sinr"] if c in ctx.columns]
    if radio_cols:
        plt.figure(figsize=(14, 5))
        for col in radio_cols:
            plt.plot(ctx["context_sample_number"], ctx[col], marker="o", markersize=3, label=col)
        plt.axvline(center_x, linestyle="--", label="Selected anomaly")
        plt.title(f"{title_prefix} #{rank + 1}: radio evidence{selected_timestamp_text}")
        _apply_time_ticks()
        plt.ylabel("Radio KPI value")
        plt.legend()
        if filename_prefix:
            save_current_plot(f"{filename_prefix}_rank_{rank + 1}_radio_context.png")

        try:
            fig2 = go.Figure()
            for col in radio_cols:
                fig2.add_trace(go.Scatter(x=ctx["context_sample_number"], y=ctx[col], mode='lines+markers', name=col, marker=dict(size=3)))
            
            y_max2 = ctx[radio_cols].max().max()
            y_min2 = ctx[radio_cols].min().min()
            fig2.add_trace(go.Scatter(x=[center_x, center_x], y=[y_min2 if pd.notna(y_min2) else -100, y_max2 if pd.notna(y_max2) else 100], mode='lines', line=dict(dash='dash', color='red'), name="Selected anomaly"))
            
            fig2.update_layout(
                template='plotly_white',
                title=f"{title_prefix} #{rank + 1}: radio evidence{selected_timestamp_text}",
                xaxis_title="Context sample number\n(second line = seconds from selected anomaly)" if "seconds_from_selected_anomaly" in ctx.columns else "Sample number inside context window",
                yaxis_title="Radio KPI value",
                margin=dict(l=60, r=30, t=50, b=50),
                hovermode='closest',
            )
            if filename_prefix:
                save_plotly_html(fig2, f"{filename_prefix}_rank_{rank + 1}_radio_context.png")
        except Exception as e:
            print(f"Plotly generation failed for context radio: {e}")

        plt.show()


def plot_context_examples_by_type(
    df: pd.DataFrame,
    anomaly_df: pd.DataFrame,
    max_types: int = 8,
    samples_before: int = 60,
    samples_after: int = 60,
    filename_prefix: str = "19_type_example_context",
) -> None:
    """Plot one high-score context example for several anomaly types.

    Top-score-only examples often show extreme edge cases. This helper adds diversity by
    selecting one representative high-score sample from each major anomaly type.
    """
    if anomaly_df is None or anomaly_df.empty or "anomaly_type" not in anomaly_df.columns:
        print("Skipped type examples: anomaly table is empty or missing anomaly_type")
        return

    types = anomaly_df["anomaly_type"].value_counts().head(max_types).index.tolist()
    for i, anomaly_type in enumerate(types, start=1):
        subset = anomaly_df[anomaly_df["anomaly_type"] == anomaly_type].copy()
        if subset.empty:
            continue
        subset = subset.sort_values("anomaly_score_0_100", ascending=False).head(1)
        print(f"\nRepresentative anomaly type example: {anomaly_type}")
        plot_anomaly_context(
            df,
            anomaly_df=subset,
            rank=0,
            samples_before=samples_before,
            samples_after=samples_after,
            filename_prefix=f"{filename_prefix}_{i}_{str(anomaly_type).replace('/', '_').replace(' ', '_')}",
            title_prefix=f"Representative {anomaly_type}",
        )


# =========================
# Load Notebook 01 output
# =========================

def read_parquet_robust(path: Path) -> pd.DataFrame:
    """Read parquet with a pyarrow-direct fallback.

    Some environments can have a pandas/pyarrow extension-type compatibility issue.
    The fallback uses pyarrow directly and ignores pandas metadata.
    """
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        print("pd.read_parquet failed; trying pyarrow direct fallback.")
        print("Reason:", exc)
        try:
            import pyarrow.parquet as pq
            return pq.read_table(path).to_pandas(ignore_metadata=True)
        except Exception as exc2:
            raise RuntimeError(f"Both pandas and pyarrow failed to read {path}") from exc2


def load_pre_anomaly_feature_table() -> pd.DataFrame:
    candidate_paths = [
        PRE_ANOMALY_FEATURE_TABLE_PATH,
        Path("lte_dl_feature_table_clean_pre_anomaly.parquet"),
        Path("/mnt/data/lte_dl_feature_table_clean_pre_anomaly.parquet"),
    ]
    for path in candidate_paths:
        if path.exists():
            print("Loading clean pre-anomaly parquet:", path)
            return read_parquet_robust(path)

    csv_candidates = [
        PRE_ANOMALY_FEATURE_TABLE_FALLBACK_CSV,
        Path("lte_dl_feature_table_clean_pre_anomaly.csv.gz"),
        Path("/mnt/data/lte_dl_feature_table_clean_pre_anomaly.csv.gz"),
    ]
    for path in csv_candidates:
        if path.exists():
            print("Loading clean pre-anomaly compressed CSV:", path)
            return pd.read_csv(path)

    raise FileNotFoundError(
        "Clean pre-anomaly feature table was not found. Run Notebook 01 first, or place "
        f"the file at {PRE_ANOMALY_FEATURE_TABLE_PATH}."
    )

lte_dl = load_pre_anomaly_feature_table()
print("Loaded clean pre-anomaly LTE-DL table shape:", lte_dl.shape)

# Guard against accidental leakage from an old post-scoring table.
leakage_prefixes = (
    "expected_tp", "throughput_gap_p75", "throughput_ratio_p75", "log_residual_p75",
    "score_", "anomaly_score", "anomaly_type", "anomaly_severity", "is_throughput_anomaly",
    "underperform_", "low_tp_", "rolling_", "prev_tp", "tp_drop_", "tp_ratio_to_prev",
    "bad_session",
)
leakage_cols_at_load = [c for c in lte_dl.columns if any(str(c).startswith(p) for p in leakage_prefixes)]
if leakage_cols_at_load:
    print("Warning: post-anomaly columns found in loaded table and will be overwritten/recomputed as needed:")
    print(leakage_cols_at_load[:50])

preview_cols = [c for c in ["source_index", "id", "timestamp", "actual_lte_dl_throughput", "lte_rsrp", "lte_sinr", "rb_usage_bucket", "carrier_count", "download_context_label"] if c in lte_dl.columns]
display(lte_dl[preview_cols].head(20))


# =========================
