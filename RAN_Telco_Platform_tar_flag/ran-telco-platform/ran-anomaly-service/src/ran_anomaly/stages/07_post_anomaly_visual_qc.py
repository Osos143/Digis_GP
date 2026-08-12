"""
Stage 07: post anomaly visual qc
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 3051-3186). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

import plotly.graph_objects as go

# 16. Post-anomaly visual QC
# =========================

# These plots help confirm whether flagged samples look abnormal in their surrounding context.
# They also make it easier to explain why some method percentages are high or low.

if not lte_dl.empty:
    plot_distribution_with_lines(
        lte_dl,
        "anomaly_score_0_100",
        "Combined Statistical Anomaly Score Distribution",
        "Anomaly score (0-100)",
        thresholds={"Low": 15, "Medium": 35, "High": 60, "Critical": 80},
        bins=60,
        filename="10_anomaly_score_distribution.png",
        clip_upper_q=None,
    )



    # The full score distribution is usually dominated by normal zero-score rows. This zoom
    # shows only flagged anomalies so score calibration can be reviewed more clearly.
    plot_distribution_with_lines(
        lte_dl[lte_dl["is_throughput_anomaly"].fillna(False).astype(bool)],
        "anomaly_score_0_100",
        "Anomaly Score Distribution for Flagged Samples Only",
        "Anomaly score (0-100)",
        thresholds={"Medium": 35, "High": 60, "Critical": 80},
        bins=50,
        filename="10b_anomaly_score_distribution_flagged_only.png",
        clip_upper_q=None,
    )

    if "anomaly_method_count" in lte_dl.columns:
        method_count_summary = lte_dl["anomaly_method_count"].value_counts().sort_index()
        plt.figure(figsize=(8, 4))
        plt.bar(method_count_summary.index.astype(str), method_count_summary.values)
        plt.xlabel("Number of trigger flags active on the row")
        plt.ylabel("Rows")
        plt.title("Anomaly Trigger-Flag Overlap Distribution")
        save_current_plot("10c_anomaly_trigger_overlap_distribution.png")
        try:
            fig = go.Figure(data=[go.Bar(
                x=method_count_summary.index.astype(str),
                y=method_count_summary.values
            )])
            fig.update_layout(
                template='plotly_white',
                title="Anomaly Trigger-Flag Overlap Distribution",
                xaxis_title="Number of trigger flags active on the row",
                yaxis_title="Rows",
                margin=dict(l=60, r=30, t=50, b=50),
                hovermode='closest',
            )
            fig.write_html(str(PLOTS_DIR / "10c_anomaly_trigger_overlap_distribution.html"), include_plotlyjs='cdn')
        except Exception:
            pass
        plt.show()

    if "method_summary" in globals():
        plot_flag_percentage_bars(method_summary, "11_anomaly_method_percentages.png")

    if "summary_by_type_sev" in globals() and not summary_by_type_sev.empty:
        type_counts = anomaly_handoff["anomaly_type"].value_counts().sort_values(ascending=True)
        plt.figure(figsize=(12, max(5, 0.35 * len(type_counts))))
        plt.barh(type_counts.index.astype(str), type_counts.values)
        plt.xlabel("Anomaly rows")
        plt.title("Anomaly Count by Primary Type")
        save_current_plot("12_anomaly_count_by_type.png")
        try:
            fig = go.Figure(data=[go.Bar(
                x=type_counts.values,
                y=type_counts.index.astype(str),
                orientation='h'
            )])
            fig.update_layout(
                template='plotly_white',
                title="Anomaly Count by Primary Type",
                xaxis_title="Anomaly rows",
                margin=dict(l=60, r=30, t=50, b=50),
                hovermode='closest',
            )
            fig.write_html(str(PLOTS_DIR / "12_anomaly_count_by_type.html"), include_plotlyjs='cdn')
        except Exception:
            pass
        plt.show()

        sev_counts = anomaly_handoff["anomaly_severity"].value_counts().sort_values(ascending=True)
        plt.figure(figsize=(8, 4))
        plt.barh(sev_counts.index.astype(str), sev_counts.values)
        plt.xlabel("Anomaly rows")
        plt.title("Anomaly Count by Severity")
        save_current_plot("13_anomaly_count_by_severity.png")
        try:
            fig = go.Figure(data=[go.Bar(
                x=sev_counts.values,
                y=sev_counts.index.astype(str),
                orientation='h'
            )])
            fig.update_layout(
                template='plotly_white',
                title="Anomaly Count by Severity",
                xaxis_title="Anomaly rows",
                margin=dict(l=60, r=30, t=50, b=50),
                hovermode='closest',
            )
            fig.write_html(str(PLOTS_DIR / "13_anomaly_count_by_severity.html"), include_plotlyjs='cdn')
        except Exception:
            pass
        plt.show()

    plot_actual_vs_expected(lte_dl, "14_actual_vs_expected_with_anomalies.png")

    plot_distribution_with_lines(
        lte_dl,
        "throughput_ratio_p75",
        "Actual / Expected P75 Throughput Ratio",
        "Actual divided by expected P75",
        thresholds={"Underperformance ratio threshold": UNDERPERFORMANCE_RATIO_THRESHOLD, "Perfect match": 1.0},
        bins=80,
        filename="15_throughput_ratio_p75_distribution.png",
        clip_upper_q=0.99,
    )

    plot_distribution_with_lines(
        lte_dl,
        "throughput_gap_p75",
        "Expected P75 Minus Actual Throughput Gap",
        "Throughput gap (Mbps)",
        thresholds={"P75 gap threshold": UNDERPERFORMANCE_GAP_MBPS},
        bins=80,
        filename="16_throughput_gap_p75_distribution.png",
        clip_upper_q=0.99,
    )

    plot_route_metric(lte_dl, "anomaly_score_0_100", "Route Samples Colored by Anomaly Score", "17_route_by_anomaly_score.png", clip_upper_q=None)
    plot_route_anomaly_overlay(lte_dl, "17c_route_with_anomaly_overlay.png")

    if "download_analysis_window_flag" in lte_dl.columns:
        lte_dl["_download_analysis_window_numeric"] = lte_dl["download_analysis_window_flag"].fillna(True).astype(int)
        plot_route_metric(
            lte_dl,
            "_download_analysis_window_numeric",
            "Route Samples Colored by Active Download Analysis Window Flag",
            "17b_route_by_download_analysis_window.png",
        )

    if "anomaly_handoff" in globals() and not anomaly_handoff.empty:
        # Plot top anomaly EPISODES, not repeated neighboring rows from the same episode.
        # This directly fixes the visual issue where several top context windows showed the
        # same sustained low-throughput period instead of independent anomaly cases.
        if "anomaly_episode_id" in anomaly_handoff.columns:
            context_examples = (
                anomaly_handoff.sort_values("anomaly_score_0_100", ascending=False)
                .drop_duplicates("anomaly_episode_id", keep="first")
                .sort_values("anomaly_score_0_100", ascending=False)
                .reset_index(drop=True)
            )
        else:
            context_examples = anomaly_handoff.sort_values("anomaly_score_0_100", ascending=False).reset_index(drop=True)

        for rank in range(min(MAX_TOP_CONTEXT_WINDOWS, len(context_examples))):
            plot_anomaly_context(
                lte_dl,
                anomaly_df=context_examples,
                rank=rank,
                samples_before=ANOMALY_CONTEXT_SAMPLES_BEFORE,
                samples_after=ANOMALY_CONTEXT_SAMPLES_AFTER,
                filename_prefix="18_top_anomaly_episode_context",
            )

        # Add representative examples by anomaly type so review is not biased toward
        # only the highest-score edge cases.
        plot_context_examples_by_type(
            lte_dl,
            anomaly_handoff,
            max_types=MAX_CONTEXT_WINDOWS_BY_TYPE,
            samples_before=ANOMALY_CONTEXT_SAMPLES_BEFORE,
            samples_after=ANOMALY_CONTEXT_SAMPLES_AFTER,
            filename_prefix="19_type_example_context",
        )


# =========================
