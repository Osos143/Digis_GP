# ran-cleaning-service (modular)

The original monolithic `data_cleaning.py` (2,268 lines), divided into 11
service files under `src/ran_cleaning/stages/`, one per the original author's
own numbered sections. **No logic inside any stage was rewritten** -- each
stage file is the corresponding line range from the original script, copied
verbatim, with exactly three targeted edits (see "What actually changed").

## Why `exec()`-based staging, not 11 independent scripts

This is a single pipeline where later stages depend on dataframes/variables
built by earlier ones -- e.g. stage 7's cleaned dataframe feeds stage 8's
column detection, which feeds stage 10's LTE-DL filtering, which feeds stage
11's quality bins and neighbor features. Splitting it into independently
importable modules would mean rewriting every cross-stage variable reference
into explicit function parameters/returns -- exactly the kind of rewrite risk
you asked to avoid.

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
| 03 | `03_data_profiling_cleaning_helpers.py` | 3. Data profiling and cleaning helpers |
| 04 | `04_time_id_event_geo_helpers.py` | 4. Time, ID, event, and geo helpers |
| 05 | `05_load_raw_pickle.py` | 5. Load the raw drive-test pickle |
| 06 | `06_profile_raw_data_cleaning_plan.py` | 6. Profile raw data and build cleaning plan |
| 07 | `07_apply_cleaning_derive_features.py` | 7. Apply cleaning and derive time/location features |
| 08 | `08_throughput_kpi_column_detection.py` | 8. Canonical throughput and LTE KPI column detection |
| 09 | `09_expand_event_activity_tables.py` | 9. Expand event and activity tables for handoff/evidence |
| 10 | `10_canonical_aliases_lte_dl_filtering.py` | 10. Canonical aliases and LTE-DL filtering |
| 11 | `11_quality_bins_flags_neighbor_features.py` | 11. Quality bins, flags, neighbor aggregates, event-window features |

## What actually changed (only these three things)

1. **Paths** (`01_imports_and_settings.py`): `DATA_DIR`, `DRIVE_TEST_PATH`,
   `OUTPUT_ROOT` now read from environment variables with the exact same
   defaults as before, so `cli.py` can point them at different locations.
2. **Matplotlib backend** (`01_imports_and_settings.py`): defaults to
   headless `Agg` so `plt.show()` doesn't open a blocking GUI window in a
   CLI/service context. Opt back into interactive windows with `--show-plots`.
3. **`boxplot()` compatibility** (`02_utility_functions.py`): matplotlib
   3.9+ renamed the `labels` kwarg to `tick_labels`. The one call site now
   tries the old name first and falls back to the new one.

Everything else is byte-for-byte the original code.

## Install

```bash
pip install -e .
```

Installs the `ran-clean` command.

## Usage

```bash
ran-clean --input /data/drivetests/Network_Drive_Test.pkl --output-dir /data/outputs/run1
ran-clean --dry-run       # preview config, don't run
ran-clean --show-plots    # interactive GUI windows instead of headless PNG saving
ran-clean --help
```

## Outputs

Unchanged, under `--output-dir` (default `Throughput_Anomaly_Detection_Outputs/`):

- `01_preprocessing_cleaning/`
- `03_plots/`

## Project layout

```
ran-cleaning-service/
├── pyproject.toml
├── README.md
└── src/
    └── ran_cleaning/
        ├── __init__.py
        ├── cli.py              # argparse CLI, thin wrapper only
        ├── run_pipeline.py     # orchestrator: exec()s stages 01-11 in order
        └── stages/
            ├── 01_imports_and_settings.py
            ├── ...
            └── 11_quality_bins_flags_neighbor_features.py
```
