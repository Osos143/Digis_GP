"""
Stage 15: final ml validation plots
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 4925-5102). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

import plotly.graph_objects as go

# 25. Final ML validation plots — model quality, train vs test, Q75 calibration
# =========================


def plot_actual_vs_expected_oof(df, expected_col, title, filename, max_points=15000):
    if expected_col not in df.columns:
        return
    tmp = df[[TARGET_COL, expected_col]].dropna().copy()
    if len(tmp) > max_points:
        tmp = tmp.sample(max_points, random_state=ML_RANDOM_SEED)
    plt.figure(figsize=(8,7))
    plt.scatter(tmp[expected_col], tmp[TARGET_COL], s=8, alpha=0.25, label="OOF rows")
    limit = max(tmp[expected_col].quantile(0.995), tmp[TARGET_COL].quantile(0.995), 1)
    plt.plot([0,limit],[0,limit], linestyle="--", label="Actual = Expected")
    plt.xlabel("Expected throughput (Mbps)")
    plt.ylabel("Actual throughput (Mbps)")
    plt.title(title)
    plt.legend()
    save_current_plot(filename)
    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=tmp[expected_col], y=tmp[TARGET_COL], mode='markers', marker=dict(size=4, opacity=0.3), name="OOF rows"))
        fig.add_trace(go.Scatter(x=[0, limit], y=[0, limit], mode='lines', line=dict(dash='dash'), name="Actual = Expected"))
        fig.update_layout(
            template='plotly_white', title=title,
            xaxis_title="Expected throughput (Mbps)", yaxis_title="Actual throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / filename.replace(".png", ".html")), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()


def plot_train_vs_test_accuracy(comparison, title, filename):
    """Same plot: training fit and held-out-session test accuracy with different colors."""
    if not comparison:
        return
    train_idx = np.asarray(comparison["train_idx"], dtype=int)
    test_idx = np.asarray(comparison["test_idx"], dtype=int)
    y_train = pd.to_numeric(ml_audit.iloc[train_idx][TARGET_COL], errors="coerce").to_numpy()
    y_test = pd.to_numeric(ml_audit.iloc[test_idx][TARGET_COL], errors="coerce").to_numpy()
    pred_train = np.maximum(np.expm1(np.asarray(comparison["pred_train_log"])), 0)
    pred_test = np.maximum(np.expm1(np.asarray(comparison["pred_test_log"])), 0)
    train_mae = mean_absolute_error(y_train, pred_train)
    test_mae = mean_absolute_error(y_test, pred_test)
    train_r2 = r2_score(y_train, pred_train)
    test_r2 = r2_score(y_test, pred_test)
    # Sample only for visual density, metrics use full fold arrays above.
    rng = np.random.default_rng(ML_RANDOM_SEED)
    tr_sel = rng.choice(len(y_train), size=min(len(y_train), 8000), replace=False)
    te_sel = rng.choice(len(y_test), size=min(len(y_test), 8000), replace=False)
    plt.figure(figsize=(9,7))
    plt.scatter(y_train[tr_sel], pred_train[tr_sel], s=7, alpha=0.20, label=f"Training: R²={train_r2:.3f}, MAE={train_mae:.2f}")
    plt.scatter(y_test[te_sel], pred_test[te_sel], s=10, alpha=0.35, label=f"Held-out test: R²={test_r2:.3f}, MAE={test_mae:.2f}")
    limit = max(np.nanpercentile(np.r_[y_train,y_test,pred_train,pred_test],99.5),1)
    plt.plot([0,limit],[0,limit], linestyle="--", label="Perfect prediction")
    plt.xlim(0,limit); plt.ylim(0,limit)
    plt.xlabel("Actual throughput (Mbps)")
    plt.ylabel("Predicted throughput (Mbps)")
    plt.title(title)
    plt.legend()
    save_current_plot(filename)
    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=y_train[tr_sel], y=pred_train[tr_sel], mode='markers', marker=dict(size=4, opacity=0.3), name=f"Training: R²={train_r2:.3f}, MAE={train_mae:.2f}"))
        fig.add_trace(go.Scattergl(x=y_test[te_sel], y=pred_test[te_sel], mode='markers', marker=dict(size=5, opacity=0.4), name=f"Held-out test: R²={test_r2:.3f}, MAE={test_mae:.2f}"))
        fig.add_trace(go.Scatter(x=[0, limit], y=[0, limit], mode='lines', line=dict(dash='dash'), name="Perfect prediction"))
        fig.update_layout(
            template='plotly_white', title=title,
            xaxis_title="Actual throughput (Mbps)", yaxis_title="Predicted throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest',
            xaxis=dict(range=[0, limit]), yaxis=dict(range=[0, limit])
        )
        fig.write_html(str(PLOTS_DIR / filename.replace(".png", ".html")), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()


def plot_q75_calibration_deciles(calibration_df, filename):
    if calibration_df is None or calibration_df.empty:
        return
    decile_cols = [c for c in calibration_df.columns if c.endswith("_prediction_decile")]
    if not decile_cols:
        print("Q75 calibration plot skipped: no decile column")
        return
    decile_col = decile_cols[0]
    x = np.arange(len(calibration_df))
    plt.figure(figsize=(11,5))
    plt.plot(x, calibration_df["empirical_q75_coverage"], marker="o", label="Empirical coverage")
    plt.axhline(0.75, linestyle="--", label="Target Q75 coverage = 0.75")
    plt.xticks(x, [str(v) for v in calibration_df[decile_col]], rotation=45, ha="right")
    plt.ylabel("P(actual ≤ predicted Q75)")
    plt.xlabel("Predicted-Q75 decile")
    plt.title("Resource Q75 calibration by prediction decile")
    plt.legend()
    save_current_plot(filename)
    try:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=calibration_df["empirical_q75_coverage"], mode='lines+markers', name="Empirical coverage"))
        fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[0.75, 0.75], mode='lines', line=dict(dash='dash'), name="Target Q75 coverage = 0.75"))
        fig.update_layout(
            template='plotly_white', title="Resource Q75 calibration by prediction decile",
            xaxis_title="Predicted-Q75 decile", yaxis_title="P(actual ≤ predicted Q75)",
            xaxis=dict(tickmode='array', tickvals=x, ticktext=[str(v) for v in calibration_df[decile_col]]),
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / filename.replace(".png", ".html")), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()



def plot_route_final_overlay(df, score_col, flag_col, title, filename, max_background_points=50000):
    needed = {"longitude", "latitude", score_col, flag_col}
    if not needed.issubset(df.columns):
        return
    tmp = df.dropna(subset=["longitude", "latitude", score_col]).copy()
    bg = tmp.sample(min(len(tmp), max_background_points), random_state=ML_RANDOM_SEED) if len(tmp) else tmp
    anom = tmp[tmp[flag_col].fillna(False).astype(bool)].copy()
    plt.figure(figsize=(10,8))
    plt.scatter(bg["longitude"], bg["latitude"], s=4, alpha=0.10, label="All route samples")
    if len(anom):
        vmax = anom[score_col].quantile(0.95)
        sc = plt.scatter(anom["longitude"], anom["latitude"], c=anom[score_col].clip(upper=vmax), s=22, alpha=0.90, label="Final anomalies")
        plt.colorbar(sc, label=f"Score clipped at P95={vmax:.1f}")
    plt.xlabel("Longitude"); plt.ylabel("Latitude"); plt.title(title); plt.legend()
    save_current_plot(filename);
    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=bg["longitude"], y=bg["latitude"], mode='markers', marker=dict(size=3, opacity=0.2, color='gray'), name="All route samples"))
        if len(anom):
            fig.add_trace(go.Scattergl(x=anom["longitude"], y=anom["latitude"], mode='markers', marker=dict(size=6, color=anom[score_col].clip(upper=vmax), colorscale='Viridis', showscale=True), name="Final anomalies"))
        fig.update_layout(
            template='plotly_white', title=title,
            xaxis_title="Longitude", yaxis_title="Latitude",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / filename.replace(".png", ".html")), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

# OOF quality plots for the reduced predictive set + LSTM validation comparator.
for col,title,filename in [
    ("expected_tp_ml_hgb_temporal_q50", "OOF Actual vs HGB Strict-Causal Temporal Q50", "ml_21_actual_vs_hgb_temporal_oof.png"),
    ("expected_tp_ml_hgb_resource_q50", "OOF Actual vs HGB Resource Q50", "ml_22_actual_vs_hgb_resource_oof.png"),
    ("expected_tp_ml_q75_resource", "OOF Actual vs Calibrated Resource Q75", "ml_23_actual_vs_q75_resource_oof.png"),
    ("expected_tp_ml_lstm_q50", "OOF Actual vs LSTM-Q50 — validation comparator", "ml_24_actual_vs_lstm_oof.png"),
]:
    if col in ml_audit.columns and ml_audit[col].notna().any():
        plot_actual_vs_expected_oof(ml_audit, col, title, filename)

# Same-plot training vs held-out test comparison requested for easy overfit validation.
plot_train_vs_test_accuracy(hgb_temporal_comparison, "HGB Strict-Causal Temporal Q50 — Training vs Held-Out Test", "ml_30_hgb_temporal_train_vs_test_same_plot.png")
plot_train_vs_test_accuracy(hgb_resource_comparison, "HGB Resource Q50 — Training vs Held-Out Test", "ml_31_hgb_resource_train_vs_test_same_plot.png")
plot_train_vs_test_accuracy(q75_resource_comparison, "Resource Q75 — Training vs Held-Out Test", "ml_32_q75_resource_train_vs_test_same_plot.png")

# LSTM comparison object uses different keys; make an equivalent plot.
if lstm_comparison:
    train_pos = np.asarray(lstm_comparison["train_positions"], dtype=int)
    test_pos = np.asarray(lstm_comparison["test_positions"], dtype=int)
    y_train = pd.to_numeric(ml_audit.loc[train_pos, TARGET_COL], errors="coerce").to_numpy()
    y_test = pd.to_numeric(ml_audit.loc[test_pos, TARGET_COL], errors="coerce").to_numpy()
    pred_train = np.maximum(np.expm1(np.asarray(lstm_comparison["train_predictions_log"])),0)
    pred_test = np.maximum(np.expm1(np.asarray(lstm_comparison["test_predictions_log"])),0)
    plt.figure(figsize=(9,7))
    plt.scatter(y_train, pred_train, s=6, alpha=0.15, label=f"Training: R²={r2_score(y_train,pred_train):.3f}, MAE={mean_absolute_error(y_train,pred_train):.2f}")
    plt.scatter(y_test, pred_test, s=9, alpha=0.30, label=f"Held-out test: R²={r2_score(y_test,pred_test):.3f}, MAE={mean_absolute_error(y_test,pred_test):.2f}")
    limit = max(np.nanpercentile(np.r_[y_train,y_test,pred_train,pred_test],99.5),1)
    plt.plot([0,limit],[0,limit], linestyle="--", label="Perfect prediction")
    plt.xlim(0,limit); plt.ylim(0,limit)
    plt.xlabel("Actual throughput (Mbps)"); plt.ylabel("Predicted throughput (Mbps)")
    plt.title("LSTM-Q50 — Training vs Held-Out Test (validation only)")
    plt.legend(); save_current_plot("ml_33_lstm_train_vs_test_same_plot.png");
    try:
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=y_train, y=pred_train, mode='markers', marker=dict(size=4, opacity=0.3), name=f"Training: R²={r2_score(y_train,pred_train):.3f}, MAE={mean_absolute_error(y_train,pred_train):.2f}"))
        fig.add_trace(go.Scattergl(x=y_test, y=pred_test, mode='markers', marker=dict(size=5, opacity=0.4), name=f"Held-out test: R²={r2_score(y_test,pred_test):.3f}, MAE={mean_absolute_error(y_test,pred_test):.2f}"))
        fig.add_trace(go.Scatter(x=[0, limit], y=[0, limit], mode='lines', line=dict(dash='dash'), name="Perfect prediction"))
        fig.update_layout(
            template='plotly_white', title="LSTM-Q50 — Training vs Held-Out Test (validation only)",
            xaxis_title="Actual throughput (Mbps)", yaxis_title="Predicted throughput (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50), hovermode='closest',
            xaxis=dict(range=[0, limit]), yaxis=dict(range=[0, limit])
        )
        fig.write_html(str(PLOTS_DIR / "ml_33_lstm_train_vs_test_same_plot.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

plot_q75_calibration_deciles(ml_q75_resource_decile_calibration, "ml_34_q75_resource_calibration_by_decile.png")

# Model-selection summary: best predictive models are visually marked KEEP; LSTM/IF are context validation.
model_selection_rows = []
if not boosted_fold_metrics.empty and "model" in boosted_fold_metrics.columns:
    for model_name, g in boosted_fold_metrics.groupby("model"):
        valid = g[g["split"].astype(str).str.contains("validation|test", case=False, na=False)]
        if valid.empty:
            valid = g
        name_low = str(model_name).lower()
        if "temporal" in name_low:
            reason = "KEEP: strongest strict-causal forecasting benchmark; uses past-only session history and context."
        elif "q75" in name_low:
            reason = "KEEP: calibrated upper expected-throughput reference; used for underperformance gap rather than central prediction."
        else:
            reason = "KEEP: strong resource/radio-conditioned central predictor independent of current throughput history."
        model_selection_rows.append({
            "model": model_name, "role": "KEEP_PRODUCTION", "selection_reason": reason,
            "mean_r2_mbps": valid.get("r2_mbps", pd.Series(dtype=float)).mean(),
            "mean_mae_mbps": valid.get("mae_mbps", pd.Series(dtype=float)).mean(),
        })
else:
    model_selection_rows.extend([
        {"model": "HGB_strict_causal_temporal_Q50", "role": "KEEP_PRODUCTION", "selection_reason": "KEEP: pre-trained strict-causal forecasting model.", "mean_r2_mbps": np.nan, "mean_mae_mbps": np.nan},
        {"model": "HGB_resource_conditioned_Q50", "role": "KEEP_PRODUCTION", "selection_reason": "KEEP: pre-trained resource-conditioned central predictor.", "mean_r2_mbps": np.nan, "mean_mae_mbps": np.nan},
        {"model": "GradientBoosting_resource_conditioned_Q75_calibrated", "role": "KEEP_PRODUCTION", "selection_reason": "KEEP: pre-trained calibrated upper expected-throughput reference.", "mean_r2_mbps": np.nan, "mean_mae_mbps": np.nan},
    ])
if not lstm_fold_metrics.empty:
    model_selection_rows.append({
        "model": "LSTM_Q50", "role": "CONTEXT_VALIDATION_ONLY",
        "selection_reason": "VALIDATION ONLY: sequence-model comparator for model selection; excluded from final cases/JSON to avoid unnecessary complexity and weaker or less stable generalization.",
        "mean_r2_mbps": lstm_fold_metrics.get("r2_mbps", pd.Series(dtype=float)).mean(),
        "mean_mae_mbps": lstm_fold_metrics.get("mae_mbps", pd.Series(dtype=float)).mean(),
    })
model_selection_rows.append({"model":"IsolationForest_residual_space", "role":"CONTEXT_VALIDATION_ONLY", "selection_reason":"VALIDATION ONLY: unsupervised residual-space corroboration; not a throughput predictor and excluded from final cases/JSON.", "mean_r2_mbps":np.nan, "mean_mae_mbps":np.nan})
ml_model_selection_summary = pd.DataFrame(model_selection_rows)
save_table(ml_model_selection_summary, "ml_final_model_selection_summary.csv", category="key")
display(ml_model_selection_summary.round(4))

# R2 visual comparison for predictive models only.
plot_df = ml_model_selection_summary.dropna(subset=["mean_r2_mbps"]).sort_values("mean_r2_mbps")
if not plot_df.empty:
    plt.figure(figsize=(11,6))
    plt.barh(plot_df["model"] + " | " + plot_df["role"], plot_df["mean_r2_mbps"])
    plt.xlabel("Mean held-out R² (Mbps)")
    plt.title("Final ML model selection — predictive quality and role")
    save_current_plot("ml_35_final_model_selection_r2.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=plot_df["mean_r2_mbps"],
            y=plot_df["model"] + " | " + plot_df["role"],
            orientation='h'
        )])
        fig.update_layout(
            template='plotly_white',
            title="Final ML model selection — predictive quality and role",
            xaxis_title="Mean held-out R² (Mbps)",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "ml_35_final_model_selection_r2.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()

mae_df = ml_model_selection_summary.dropna(subset=["mean_mae_mbps"]).sort_values("mean_mae_mbps", ascending=False)
if not mae_df.empty:
    plt.figure(figsize=(11,6))
    plt.barh(mae_df["model"] + " | " + mae_df["role"], mae_df["mean_mae_mbps"])
    plt.xlabel("Mean held-out MAE (Mbps) — lower is better")
    plt.title("Final ML model selection — held-out prediction error")
    save_current_plot("ml_36_final_model_selection_mae.png")
    try:
        fig = go.Figure(data=[go.Bar(
            x=mae_df["mean_mae_mbps"],
            y=mae_df["model"] + " | " + mae_df["role"],
            orientation='h'
        )])
        fig.update_layout(
            template='plotly_white',
            title="Final ML model selection — held-out prediction error",
            xaxis_title="Mean held-out MAE (Mbps) — lower is better",
            margin=dict(l=60, r=30, t=50, b=50),
            hovermode='closest'
        )
        fig.write_html(str(PLOTS_DIR / "ml_36_final_model_selection_mae.html"), include_plotlyjs='cdn')
    except Exception:
        pass
    plt.show()


# =========================
