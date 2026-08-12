"""
Stage 01: imports and settings
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 1-282). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# =========================
# 1. Imports and settings
# =========================

from pathlib import Path
import os
import re
import json
import math
import warnings
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# The original script never pinned a matplotlib backend. Run as a plain CLI process,
# matplotlib would otherwise pick an interactive GUI backend, and every plt.show() call
# would BLOCK until the window is closed -- closing one can even kill the whole process.
# Every plot is already saved to PNG via save_current_plot() right before plt.show() is
# called, so we default to headless (Agg): plots save, nothing blocks. Set
# RAN_ANOMALY_SHOW_PLOTS=1 (or pass --show-plots to the CLI) to restore interactive windows.
import matplotlib
if os.environ.get("RAN_ANOMALY_SHOW_PLOTS", "").strip().lower() not in {"1", "true", "yes"}:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt

from IPython.display import display

warnings.filterwarnings("ignore")

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 150)
pd.set_option("display.max_colwidth", 180)
pd.set_option("display.width", 260)

# Use plain matplotlib only.
plt.rcParams["figure.figsize"] = (12, 5)
plt.rcParams["axes.grid"] = True

# -------------------------
# Project paths
# -------------------------
# Behavior is 100% unchanged from the original script: these paths keep the exact same
# default values as before. The only addition is that the CLI service (cli.py) can
# override them via environment variables.
DATA_DIR = Path(os.environ.get("RAN_ANOMALY_DATA_DIR", "Raw_Data"))
DRIVE_TEST_PATH = Path(os.environ["RAN_ANOMALY_INPUT_FILE"]) if os.environ.get("RAN_ANOMALY_INPUT_FILE") else DATA_DIR / "Network_Drive_Test.pkl"
OUTPUT_ROOT = Path(os.environ.get("RAN_ANOMALY_OUTPUT_DIR", "Throughput_Anomaly_Detection_Outputs"))
PREPROCESSING_DIR = OUTPUT_ROOT / "01_preprocessing_cleaning"
ANOMALY_DIR = OUTPUT_ROOT / "02_anomaly_detection"
PLOTS_DIR = OUTPUT_ROOT / "03_plots"
RCA_HANDOFF_DIR = OUTPUT_ROOT / "04_rca_handoff_final"
RCA_KEY_FILES_DIR = RCA_HANDOFF_DIR / "00_key_review_files"
RCA_CASE_PLOTS_DIR = RCA_HANDOFF_DIR / "01_top_anomaly_case_plots"
# OUTPUT_DIR remains as the root for backward compatibility inside helper functions.
OUTPUT_DIR = OUTPUT_ROOT
for _dir in [OUTPUT_ROOT, PREPROCESSING_DIR, ANOMALY_DIR, PLOTS_DIR, RCA_HANDOFF_DIR, RCA_KEY_FILES_DIR, RCA_CASE_PLOTS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# -------------------------
# Cleaning configuration
# -------------------------
MISSING_THRESHOLD_PCT = 70.0
DROP_FULLY_MISSING_PROTECTED_COLUMNS = True
RANDOM_SEED = 42
PROFILE_SAMPLE_ROWS = 100_000
EARTH_RADIUS_KM = 6371.0088
# Project-verified cadence. All local sample windows map directly to seconds.
SAMPLE_INTERVAL_SECONDS = 1.0

# Canonical columns are defined early because statistical ranking/QC runs before the ML section.
TARGET_COL = "actual_lte_dl_throughput"
GROUP_COL = "id"
TIME_COL = "timestamp"

# -------------------------
# Throughput configuration
# -------------------------
# Most common drive-test exports store the selected LTE throughput KPI in Mbps.
# If your exported target is Kbps, set THROUGHPUT_TO_MBPS = 1 / 1000.
THROUGHPUT_TO_MBPS = 1.0

LOW_TP_FIXED_MBPS = 10.0
MIN_EXPECTED_TP_MBPS_FOR_UNDERPERFORMANCE = 25.0
UNDERPERFORMANCE_RATIO_THRESHOLD = 0.35
UNDERPERFORMANCE_GAP_MBPS = 15.0

# Robust lower-tail z-score setting.
# A classic modified-z threshold of -3.5 can become too strict after log1p() compression
# and may produce 0 rows. -3.0 keeps this as an extreme lower-tail detector.
ROBUST_Z_LOWER_THRESHOLD = -3.0

# Group P75 expected-throughput settings.
MIN_GROUP_SIZE_FOR_P75 = 30
P75_QUANTILE = 0.75

# Rolling/sudden-drop settings.
ROLLING_WINDOW_SAMPLES = 11
ROLLING_DROP_RATIO_THRESHOLD = 0.50
SUDDEN_DROP_PREV_MIN_MBPS = 10.0
SUDDEN_DROP_RATIO_THRESHOLD = 0.50
SUDDEN_DROP_GAP_MBPS = 5.0

# Sustained-window and bad-session settings.
# Sudden-drop detection looks for contrast versus a healthy local baseline.
# The following thresholds catch the different case where the whole local window/session is bad.
MIN_ROLLING_SAMPLES = 5
VERY_LOW_TP_MBPS = 5.0
ROLLING_BAD_WINDOW_MEDIAN_MBPS = LOW_TP_FIXED_MBPS
ROLLING_BAD_WINDOW_P25_MBPS = VERY_LOW_TP_MBPS

SESSION_MIN_ROWS_FOR_BAD_SESSION = 20
BAD_SESSION_MEDIAN_MBPS = LOW_TP_FIXED_MBPS
BAD_SESSION_P25_MBPS = VERY_LOW_TP_MBPS
BAD_SESSION_LOW_TP_RATIO_THRESHOLD = 0.40
SESSION_P10_MAX_THRESHOLD_MBPS = 20.0

# -------------------------
# Download activity-window settings
# -------------------------
# LTE-DL session rows can include script/activity context such as HTTP/HTTPS download windows.
# Earlier versions used active download windows as the main analysis mask. The latest V1 uses
# all valid LTE-DL rows because the observed throughput distributions across active/warmup/outside
# activity windows were very close. Activity windows are now kept as context only.
BUILD_DOWNLOAD_ACTIVITY_CONTEXT_FLAGS = True
DOWNLOAD_ACTIVITY_NAME_PATTERN = r"HTTP|HTTPS|Download"
DOWNLOAD_ACTIVITY_WARMUP_SECONDS = 5
DOWNLOAD_ACTIVITY_COOLDOWN_SECONDS = 2

# Visual context settings.
MAX_TOP_CONTEXT_WINDOWS = 8
MAX_CONTEXT_WINDOWS_BY_TYPE = 8
ANOMALY_CONTEXT_SAMPLES_BEFORE = 60
ANOMALY_CONTEXT_SAMPLES_AFTER = 60


# -------------------------
# LTE radio-quality bin thresholds
# -------------------------
# These thresholds are intentionally calibrated for this real drive-test export.
# They are slightly more forgiving than some textbook/paper thresholds because field
# measurements, mobility, server/application behavior, and route conditions can make
# practical throughput lower than ideal lab expectations.
#
# RSRP bins:
#   Excellent: >= -90 dBm
#   Good:      [-100, -90) dBm
#   Fair:      [-120, -100) dBm
#   Poor:      < -120 dBm
RSRP_EXCELLENT_MIN_DBM = -90.0
RSRP_GOOD_MIN_DBM = -100.0
RSRP_FAIR_MIN_DBM = -120.0

# RSRQ bins:
#   Excellent: >= -10 dB
#   Good:      [-15, -10) dB
#   Fair:      [-20, -15) dB
#   Poor:      < -20 dB
RSRQ_EXCELLENT_MIN_DB = -10.0
RSRQ_GOOD_MIN_DB = -15.0
RSRQ_FAIR_MIN_DB = -20.0

# SINR bins:
#   Excellent: >= 15 dB
#   Good:      [10, 15) dB
#   Fair:      [0, 10) dB
#   Poor:      < 0 dB
SINR_EXCELLENT_MIN_DB = 15.0
SINR_GOOD_MIN_DB = 10.0
SINR_FAIR_MIN_DB = 0.0


# -------------------------
# Final visual-QC and false-positive-control settings
# -------------------------
# Visualization clipping only affects plots, never the data used by anomaly detection.
ROUTE_MAP_COLOR_CLIP_Q = 0.95
HISTOGRAM_COLOR_CLIP_Q = 0.99

# RB reliability checks. RB fields are only used as strong evidence when coverage and
# cardinality show that the export contains enough valid RB data.
MIN_RELIABLE_RB_NON_NULL_PCT = 70.0
MIN_RELIABLE_RB_UNIQUE_VALUES = 10
LOW_RB_QUANTILE = 0.25
MEDIUM_RB_QUANTILE = 0.50
HIGH_RB_QUANTILE = 0.75

# Demand/RB evidence controls.
# If RB data is reliable, strict expected-throughput and CA-underperformance flags
# require medium-or-high RB usage. Otherwise low observed throughput can be caused by
# low offered traffic or a scheduler/resource-allocation state, so it should be lower
# confidence instead of a strong capacity anomaly.
REQUIRE_RB_DEMAND_FOR_STRICT_P75 = True
REQUIRE_RB_DEMAND_FOR_CA_UNDERPERFORMANCE = True

# Score calibration after removing aggressive flag stacking.
# These floors prevent visually obvious severe samples from receiving unrealistically low
# scores, while caps prevent low-RB/low-demand rows from looking like confirmed capacity failures.
MIN_SCORE_ANY_TRIGGER = 15.0
MIN_SCORE_FIXED_LOW_TP = 25.0
MIN_SCORE_SUSTAINED_LOW_WINDOW = 35.0
MIN_SCORE_RADIO_LIMITED = 35.0
MIN_SCORE_LOCAL_DROP = 50.0
MIN_SCORE_P75_UNDERPERF = 55.0
MIN_SCORE_SEVERE_P75_UNDERPERF = 75.0
LOW_RB_DEMAND_SCORE_CAP = 45.0

# Score saturation control. Scores are softly capped below 100 unless a truly catastrophic
# case is present. This prevents too many rows from saturating at 100.
SCORE_SOFT_CAP_NON_CATASTROPHIC = 95.0
CATASTROPHIC_ACTUAL_TP_MBPS = 1.0
CATASTROPHIC_EXPECTED_TP_MBPS = 50.0

# RB-efficiency anomaly settings. Throughput per RB becomes useful after RB availability
# was proven reliable. It checks whether throughput is inefficient even when resources exist.
RB_EFFICIENCY_REFERENCE_QUANTILE = 0.10
RB_EFFICIENCY_MIN_ACTUAL_TP_FOR_CONTEXT_MBPS = 0.0


# Continuous score calibration. The final score is no longer just a sum of flags or only
# a set of floors. It combines: strongest-trigger base, continuous anomaly magnitude,
# independent trigger-family bonus, and capped evidence/context bonus.
MULTI_TRIGGER_BONUS_PER_LOG_STEP = 5.0
MULTI_TRIGGER_BONUS_CAP = 12.0
EVIDENCE_BONUS_CAP = 10.0
MAGNITUDE_GAP_DENOMINATOR_MBPS = 80.0
MAGNITUDE_DROP_DENOMINATOR_MBPS = 40.0
MAGNITUDE_LOW_TP_REFERENCE_MBPS = 20.0

# RB-conditioned P75 expected-throughput controls.
USE_RB_CONDITIONED_P75 = True
RB_P75_LABEL = "rb_conditioned"

# P75 reliability controls. Specific group references are more trustworthy than global fallback.
MAX_RELIABLE_P75_FALLBACK_LEVEL = 4
MIN_RELIABLE_P75_GROUP_N = MIN_GROUP_SIZE_FOR_P75

# Bootstrap confidence interval settings for group P75 references.
# These CIs are used as an additional confidence guard for strict P75 underperformance.
P75_CI_BOOTSTRAP_N = 80
P75_CI_ALPHA = 0.05

# Tighter CA-underperformance controls.
CA_UNDERPERF_MIN_EXPECTED_MBPS = 30.0
CA_UNDERPERF_MAX_ACTUAL_MBPS = 15.0
CA_UNDERPERF_RATIO_THRESHOLD = 0.35

# Episode grouping converts consecutive row-level anomalies into reviewable periods.
MAX_SECONDS_GAP_SAME_ANOMALY_EPISODE = 3.0

# Event-window settings used only to prepare anomaly evidence, not final RCA.
# Measurement reports are separated from actual HO execution/failure so mobility context does
# not become too broad. Legacy aliases are created later for compatibility.
EVENT_WINDOWS_SECONDS = {
    "any_event": 30,
    "measurement_report_event": 5,
    "handover_execution": 5,
    "handover_failure": 10,
    "rach_attempt": 10,
    "rach_failure": 10,
    "ca_activation_change": 10,
    "failure_other": 10,
}

# Candidate-vs-handoff split. The candidate table keeps broad statistical findings;
# the baseline handoff table is a stricter subset for practical RCA review.
RCA_HANDOFF_MIN_SCORE = 35.0

# Final bad-cell / PCI ranking and RCA shortlist settings.
CELL_RANK_MIN_ROWS = 30
CELL_RANK_MIN_SESSIONS = 1
BAD_CELL_TOP_N = 25
BAD_PCI_TOP_N = 25
RCA_SHORTLIST_TARGET_INCIDENTS = 15
RCA_SHORTLIST_PER_CASE_QUOTA = 3
TOP_PLOTS_PER_ANOMALY_CASE = 2
TOP_CASE_CONTEXT_SECONDS = 30

# Low-tail methods are retained individually but grouped as one independent family.
LOW_TAIL_CONSENSUS_METHODS = ["global_p10", "iqr", "robust_mad"]
LOW_TAIL_CONSENSUS_EVIDENCE_BONUS_MAX = 4.0

print("Notebook configured.")
print("Raw drive-test path:", DRIVE_TEST_PATH)
print("Output root:", OUTPUT_ROOT.resolve())
print("Preprocessing/cleaning folder:", PREPROCESSING_DIR.resolve())
print("Anomaly-detection folder:", ANOMALY_DIR.resolve())
print("Plots folder:", PLOTS_DIR.resolve())
print("Final RCA handoff folder:", RCA_HANDOFF_DIR.resolve())
print("Missing threshold:", MISSING_THRESHOLD_PCT, "%")

PRE_ANOMALY_FEATURE_TABLE_PATH = PREPROCESSING_DIR / "lte_dl_feature_table_clean_pre_anomaly.parquet"
PRE_ANOMALY_FEATURE_TABLE_FALLBACK_CSV = PREPROCESSING_DIR / "lte_dl_feature_table_clean_pre_anomaly.csv.gz"

# =========================
