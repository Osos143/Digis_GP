"""
Stage 18: fusion episode visual validation
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 5881-6055). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

import plotly.graph_objects as go

# 28. Fusion and episode visual validation
# =========================

if len(fused_handoff_rows):
    plot_distribution_with_lines(
        fused_handoff_rows,
        "final_rca_priority_score_0_100",
        "Final Fused RCA Priority — Row-Level Handoff",
        "Final RCA priority score",
        {"Medium": FUSION_MEDIUM, "High": FUSION_HIGH, "Critical": FUSION_CRITICAL},
        bins=55,
        clip_upper_q=None,
        filename="50_final_fused_row_priority_distribution.png",
    )

    plt.figure(figsize=(8, 6))
    plt.scatter(
        fused_handoff_rows.get("anomaly_score_0_100", 0),
        fused_handoff_rows.get("ml_anomaly_score_0_100", 0),
        c=fused_handoff_rows["final_rca_priority_score_0_100"],
        s=14,
        alpha=0.65,
    )
    plt.xlabel("Statistical anomaly score")
    plt.ylabel("Production ML anomaly score")
    plt.title("Statistical vs Production-ML Score — Colored by Final Fused Priority")
    plt.colorbar(label="Final fused priority")
    save_current_plot("51_statistical_vs_ml_score_fusion.png")
    try:
        fig = go.Figure(data=[go.Scattergl(
            x=fused_handoff_rows.get("anomaly_score_0_100", 0),
            y=fused_handoff_rows.get("ml_anomaly_score_0_100", 0),
            mode='markers',
            marker=dict(
                color=fused_handoff_rows["final_rca_priority_score_0_100"],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Final fused priority"),
                size=6,
                opacity=0.7
            )
        )])
        fig.update_layout(
            template='plotly_white',
            title="Statistical vs Production-ML Score — Colored by Final Fused Priority",
            xaxis_title="Statistical anomaly score",
            yaxis_title="Production ML anomaly score",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "51_statistical_vs_ml_score_fusion.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

    # Compare score fusion alternatives on the same final handoff population.
    plt.figure(figsize=(10, 5))
    for col, label in [
        ("fusion_naive_average_score_0_100", "Naive average (diagnostic only)"),
        ("fusion_weighted_max_score_0_100", "Weighted max (diagnostic only)"),
        ("fusion_selected_impact_confidence_score_0_100", "Selected impact/confidence fusion"),
    ]:
        values = fused_handoff_rows[col].dropna().sort_values().to_numpy()
        if len(values):
            y = np.linspace(0, 1, len(values), endpoint=True)
            plt.plot(values, y, label=label)
    plt.xlabel("Score")
    plt.ylabel("Empirical cumulative share")
    plt.title("Fusion-Method Score Comparison on Final Handoff Rows")
    plt.legend()
    save_current_plot("52_fusion_method_ecdf_comparison.png")
    try:
        fig = go.Figure()
        for col, label in [
            ("fusion_naive_average_score_0_100", "Naive average (diagnostic only)"),
            ("fusion_weighted_max_score_0_100", "Weighted max (diagnostic only)"),
            ("fusion_selected_impact_confidence_score_0_100", "Selected impact/confidence fusion"),
        ]:
            values = fused_handoff_rows[col].dropna().sort_values().to_numpy()
            if len(values):
                y = np.linspace(0, 1, len(values), endpoint=True)
                fig.add_trace(go.Scatter(x=values, y=y, mode='lines', name=label))
        fig.update_layout(
            template='plotly_white',
            title="Fusion-Method Score Comparison on Final Handoff Rows",
            xaxis_title="Score",
            yaxis_title="Empirical cumulative share",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "52_fusion_method_ecdf_comparison.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

    source_counts = fused_handoff_rows["fusion_source"].value_counts()
    plt.figure(figsize=(8, 5))
    plt.bar(source_counts.index.astype(str), source_counts.values)
    plt.ylabel("Rows")
    plt.title("Final Handoff Rows by Fusion Source")
    plt.xticks(rotation=20, ha="right")
    save_current_plot("52_final_handoff_by_fusion_source.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=source_counts.index.astype(str),
            y=source_counts.values
        )])
        fig.update_layout(
            template='plotly_white',
            title="Final Handoff Rows by Fusion Source",
            xaxis_title="Fusion Source",
            yaxis_title="Rows",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "52_final_handoff_by_fusion_source.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

    plot_route_final_overlay(
        fused,
        "final_rca_priority_score_0_100",
        "final_rca_handoff_flag",
        "Route with Final Statistical–Production-ML Fused Anomalies",
        "53_route_final_fused_anomaly_overlay.png",
    )

if len(final_episode_summary):
    plot_distribution_with_lines(
        final_episode_summary,
        "episode_final_priority_0_100",
        "Final RCA Episode Priority Distribution",
        "Episode priority score",
        {"Medium": FUSION_MEDIUM, "High": FUSION_HIGH, "Critical": FUSION_CRITICAL},
        bins=45,
        clip_upper_q=None,
        filename="54_final_episode_priority_distribution.png",
    )

    plt.figure(figsize=(8, 6))
    plt.scatter(
        final_episode_summary["duration_seconds"],
        final_episode_summary["episode_final_priority_0_100"],
        c=final_episode_summary["agreement_pct"],
        s=np.clip(final_episode_summary["rows"] * 8, 15, 150),
        alpha=0.70,
    )
    plt.xlabel("Episode duration (seconds)")
    plt.ylabel("Episode final priority")
    plt.title("Episode Duration vs Priority — Color Shows Statistical/ML Agreement")
    plt.colorbar(label="Consensus rows (%)")
    save_current_plot("55_episode_duration_vs_priority.png")
    try:
        fig = go.Figure(data=[go.Scattergl(
            x=final_episode_summary["duration_seconds"],
            y=final_episode_summary["episode_final_priority_0_100"],
            mode='markers',
            marker=dict(
                color=final_episode_summary["agreement_pct"],
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(title="Consensus rows (%)"),
                size=np.clip(final_episode_summary["rows"] * 2, 8, 30),
                opacity=0.7
            )
        )])
        fig.update_layout(
            template='plotly_white',
            title="Episode Duration vs Priority — Color Shows Statistical/ML Agreement",
            xaxis_title="Episode duration (seconds)",
            yaxis_title="Episode final priority",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "55_episode_duration_vs_priority.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

    # Funnel from broad statistical candidates to final incidents.
    funnel_labels = [
        "All LTE-DL rows",
        "Broad statistical candidates",
        "Statistical RCA handoff rows",
        "Final production-ML anomalies",
        "Final fused handoff rows",
        "Strict final fused episodes",
        "Operational RCA incidents",
    ]
    funnel_values = [
        len(fused),
        int(bool_col(fused, "is_throughput_anomaly").sum()),
        int(stat_handoff.sum()),
        int(ml_final.sum()),
        len(fused_handoff_rows),
        len(final_episode_summary),
        len(operational_incident_summary),
    ]
    plt.figure(figsize=(10, 5))
    plt.bar(funnel_labels, funnel_values)
    plt.ylabel("Count")
    plt.title("Anomaly-Detection and RCA-Handoff Funnel")
    plt.xticks(rotation=25, ha="right")
    save_current_plot("56_final_detection_funnel.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=funnel_labels,
            y=funnel_values
        )])
        fig.update_layout(
            template='plotly_white',
            title="Anomaly-Detection and RCA-Handoff Funnel",
            yaxis_title="Count",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "56_final_detection_funnel.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()


def plot_top_fused_episode(rank: int, filename: str, context_rows: int = 40) -> None:
    if final_episode_summary.empty or rank >= len(final_episode_summary):
        return
    ep = final_episode_summary.iloc[rank]
    ep_rows = final_episode_rows[final_episode_rows["final_episode_id"].eq(ep["final_episode_id"])].sort_values(TIME_COL)
    session = fused[fused[GROUP_COL].eq(ep[GROUP_COL])].sort_values(TIME_COL).copy()
    if session.empty or ep_rows.empty:
        return
    first_idx = ep_rows.index.min()
    session_positions = np.where(session.index.to_numpy() == first_idx)[0]
    center = int(session_positions[0]) if len(session_positions) else len(session) // 2
    win = session.iloc[max(0, center-context_rows):min(len(session), center+len(ep_rows)+context_rows)]
    x = np.arange(len(win))
    plt.figure(figsize=(14, 5))
    plt.plot(x, win[TARGET_COL], linewidth=1.7, label="Actual")
    for col, label in [
        ("expected_tp_radio_p75", "Statistical radio P75"),
        ("expected_tp_rb_conditioned_p75", "Statistical RB-conditioned P75"),
        ("expected_tp_ml_q75_resource", "ML resource Q75"),
        ("expected_tp_ml_hgb_resource_q50", "HGB resource Q50"),
        ("expected_tp_ml_hgb_temporal_q50", "HGB strict-causal temporal Q50"),
    ]:
        if col in win.columns:
            plt.plot(x, win[col], linewidth=1.1, label=label)
    episode_mask = win.index.isin(ep_rows.index)
    if episode_mask.any():
        positions = np.where(episode_mask)[0]
        plt.axvspan(positions.min(), positions.max(), alpha=0.15, label="Final fused episode")
    plt.xlabel("Ordered samples around episode")
    plt.ylabel("Throughput (Mbps)")
    plt.title(
        f"Top Final Episode #{rank+1} | priority={ep['episode_final_priority_0_100']:.1f} | "
        f"impact={ep['episode_impact_score_0_100']:.1f} | confidence={ep['episode_detection_confidence_0_100']:.1f}"
    )
    plt.legend()
    save_current_plot(filename)
    try:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=win[TARGET_COL], mode='lines', name="Actual"))
        for col, label in [
            ("expected_tp_radio_p75", "Statistical radio P75"),
            ("expected_tp_rb_conditioned_p75", "Statistical RB-conditioned P75"),
            ("expected_tp_ml_q75_resource", "ML resource Q75"),
            ("expected_tp_ml_hgb_resource_q50", "HGB resource Q50"),
            ("expected_tp_ml_hgb_temporal_q50", "HGB strict-causal temporal Q50"),
        ]:
            if col in win.columns:
                fig.add_trace(go.Scatter(x=x, y=win[col], mode='lines', name=label))
        
        if episode_mask.any():
            positions = np.where(episode_mask)[0]
            fig.add_vrect(x0=positions.min(), x1=positions.max(), fillcolor="blue", opacity=0.15, layer="below", line_width=0, annotation_text="Final fused episode")
            
        fig.update_layout(
            template='plotly_white',
            title=f"Top Final Episode #{rank+1} | priority={ep['episode_final_priority_0_100']:.1f} | impact={ep['episode_impact_score_0_100']:.1f} | confidence={ep['episode_detection_confidence_0_100']:.1f}",
            xaxis_title="Ordered samples around episode",
            yaxis_title="Throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / filename.replace(".png", ".html")), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()


for rank in range(min(8, len(final_episode_summary))):
    plot_top_fused_episode(rank, f"57_top_fused_episode_context_{rank+1:02d}.png")


if 'operational_incident_summary' in globals() and len(operational_incident_summary):
    plot_distribution_with_lines(
        operational_incident_summary,
        "max_priority",
        "Operational RCA Incident Priority Distribution",
        "Maximum strict-episode priority",
        {"Medium": FUSION_MEDIUM, "High": FUSION_HIGH, "Critical": 85.0},
        bins=40, clip_upper_q=None,
        filename="58_operational_incident_priority_distribution.png",
    )

# =========================
