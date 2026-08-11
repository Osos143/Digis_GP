# ran-anomaly-service

The original monolithic `anomaly_detection.py` (6,121 lines), divided into 19
service files under `src/ran_anomaly/stages/`, one per the original author's
own numbered sections. **No logic inside any stage was rewritten** -- each
stage file is the corresponding line range from the original script, copied
verbatim, with exactly three targeted edits (see "What actually changed"
below).

## Why `exec()`-based staging, not 19 independent scripts

This is a single tightly-coupled analytical pipeline: stage 12's statistical
scores feed stage 14's combined flags, which feed stage 15's RCA handoff
table, which stage 19's feature construction reads back, and so on through
ML cross-fitting, LSTM sequencing, and final fusion. Splitting it into
independently-importable modules would require rewriting every cross-stage
variable reference into explicit function parameters/returns across ~6,000
lines -- high risk of silently changing behavior.

Instead, `run_pipeline.py` runs each stage's source through Python's `exec()`
against one shared namespace, in file order (stage files are numbered so
sorting gives the correct order). This is functionally identical to running
the original single file top to bottom -- the split is purely an on-disk
organizational change.

## Stages

| # | File | Original section |
|---|------|-------------------|
| 01 | `01_imports_and_settings.py` | 1. Imports and settings |
| 02 | `02_utility_functions.py` | 2. General utility functions |
| 03 | `03_statistical_anomaly_scores.py` | 12. Simple and robust statistical anomaly scores |
| 04 | `04_group_p75_expected_throughput.py` | 13. Group-based P75 expected throughput with fallback hierarchy |
| 05 | `05_combine_anomaly_cases.py` | 14. Combine anomaly cases, severity, and scores |
| 06 | `06_rca_handoff_table.py` | 15. Build final RCA-ready anomaly handoff table |
| 07 | `07_post_anomaly_visual_qc.py` | 16. Post-anomaly visual QC |
| 08 | `08_ml_lstm_fusion_config.py` | 18. ML/LSTM/fusion imports and configuration |
| 09 | `09_feature_construction.py` | 19. Leakage-safe feature construction and feature-view audits |
| 10 | `10_preprocessors_crossfit.py` | 20. Preprocessors, cross-fitting, repeated validation, and ablation helpers |
| 11 | `11_execute_predictive_models.py` | 21. Execute reduced final predictive model set |
| 12 | `12_lstm_helpers.py` | 22. PyTorch LSTM-Q50 sequence helpers and cross-fitted prediction |
| 13 | `13_execute_lstm_crossfit.py` | 23. Execute LSTM-Q50 cross-fitting and save temporal diagnostics |
| 14 | `14_reduced_ml_anomaly_logic.py` | 24. Reduced ML anomaly logic: production vs validation/context models |
| 15 | `15_final_ml_validation_plots.py` | 25. Final ML validation plots |
| 16 | `16_fusion_layer.py` | 26. Row-level statistical-ML-LSTM fusion |
| 17 | `17_episodes_and_incidents.py` | 27. Candidate episodes, strict final RCA episodes, operational incidents |
| 18 | `18_fusion_episode_visual_validation.py` | 28. Fusion and episode visual validation |
| 19 | `19_final_artifacts_and_index.py` | 29. Fit/save final future-inference artifacts and refreshed output index |

(Note: the original script's own numbering has gaps -- e.g. no separate
sections 3-11 or 17 -- because those exist in the companion cleaning script.
That numbering is preserved here as-is; the table above just re-sequences the
*file* order 01-19.)

## What actually changed (only these three things)

1. **Paths** (`01_imports_and_settings.py`): `DATA_DIR`, `DRIVE_TEST_PATH`,
   `OUTPUT_ROOT` now read from environment variables with the exact same
   defaults as before, so `cli.py` can point them at different locations.
2. **Matplotlib backend** (`01_imports_and_settings.py`): defaults to
   headless `Agg` so `plt.show()` doesn't open a blocking GUI window in a
   CLI/service context (every plot is already saved to PNG right before
   `plt.show()` is called). Opt back into interactive windows with
   `--show-plots`.
3. **`boxplot()` compatibility** (`02_utility_functions.py`): matplotlib
   3.9+ renamed the `labels` kwarg to `tick_labels`. The one call site now
   tries the old name first and falls back to the new one -- same chart
   output either way, just resilient to your installed matplotlib version.

Everything else -- every threshold, every statistical/ML calculation, every
plot, every CSV/parquet export -- is byte-for-byte the original code.

## Install

```bash
pip install -e .
# or, if you use the LSTM stage and have PyTorch available:
pip install -e ".[lstm]"
```

This installs the `ran-anomaly` command.

## Usage

This pipeline reads the cleaned feature table produced by the companion
`ran-cleaning-service` (`ran-clean`), so run that first with the **same**
`--output-dir`:

```bash
ran-clean    --output-dir /data/outputs/run_2026_07_25
ran-anomaly  --output-dir /data/outputs/run_2026_07_25
```

Other options:

```bash
ran-anomaly --dry-run                 # preview config without running
ran-anomaly --show-plots              # interactive GUI windows instead of headless
ran-anomaly --help
```

## Outputs

Unchanged from the original script, under `--output-dir`:

- `02_anomaly_detection/`
- `03_plots/`
- `04_rca_handoff_final/` (with `00_key_review_files/` and
  `01_top_anomaly_case_plots/`)

Plus, if `ML_SAVE_FINAL_MODELS` is enabled in the pipeline config, trained
model artifacts under the model artifact directory the original script
defines.

## Project layout

```
ran-anomaly-service/
├── pyproject.toml
├── README.md
└── src/
    └── ran_anomaly/
        ├── __init__.py
        ├── cli.py              # argparse CLI, thin wrapper only
        ├── run_pipeline.py     # orchestrator: exec()s stages 01-19 in order
        └── stages/
            ├── 01_imports_and_settings.py
            ├── 02_utility_functions.py
            ├── ... (19 stage files total)
            └── 19_final_artifacts_and_index.py
```
