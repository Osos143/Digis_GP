"""
Stage 08: ml lstm fusion config
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 3187-3362). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 18. ML/LSTM/fusion imports and configuration
# =========================

from copy import deepcopy
from dataclasses import dataclass
from collections import defaultdict
import time

from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingRegressor, GradientBoostingRegressor, IsolationForest
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from threadpoolctl import threadpool_limits
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    mean_pinball_loss,
)
import joblib

# PyTorch is used for the compact LSTM-Q50 trial. The notebook remains runnable without
# TensorFlow and uses CPU automatically when no GPU is present.
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except Exception as exc:
    TORCH_AVAILABLE = False
    print("PyTorch is not available. The LSTM trial will be skipped.")
    print("Reason:", exc)

TARGET_COL = "actual_lte_dl_throughput"
GROUP_COL = "id"
TIME_COL = "timestamp"

# -------------------------
# Reproducibility and runtime controls
# -------------------------
ML_RANDOM_SEED = RANDOM_SEED
np.random.seed(ML_RANDOM_SEED)
if TORCH_AVAILABLE:
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    torch.manual_seed(ML_RANDOM_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(ML_RANDOM_SEED)

ML_OOF_N_SPLITS = 5
ML_REPEATED_GROUP_RUNS = 5
ML_REPEATED_TEST_SIZE = 0.20
ML_RUN_REPEATED_VALIDATION = True
ML_RUN_FEATURE_ABLATION = False  # final model set already selected; keep notebook lean
ML_RUN_ROBUST_REFERENCE_REFIT = True
ML_REFERENCE_REFIT_EXTREME_QUANTILE = 0.01
ML_REFERENCE_INNER_N_SPLITS = 3
ML_NESTED_REFERENCE_FILTERING = True
ML_CALIBRATE_Q75_WITH_INNER_OOF = True
ML_SAVE_FINAL_MODELS = True

# Use None for the real run. A positive integer can be used only for code debugging.
ML_MAX_ROWS_DEBUG = None

# -------------------------
# Core expected-throughput gates
# -------------------------
ML_MIN_EXPECTED_TP_MBPS = 25.0
ML_MIN_GAP_MBPS = 15.0
ML_LOW_EXPECTED_CONTEXT_MBPS = 20.0
ML_Q75_RATIO_GATE = 0.35
ML_Q75_RESOURCE_RATIO_GATE = 0.40
ML_HGB_RATIO_GATE = 0.40
ML_LSTM_RATIO_GATE = 0.50
ML_IFOREST_RATIO_GATE = 0.50
ML_IFOREST_CONTAMINATION = 0.03

# A model trigger requires the expected/RB gates and at least this many of:
# severe ratio, severe gap, severe residual percentile.
# Ratio and absolute gap are one magnitude family; residual/model-family agreement is
# treated as separate confirmation so correlated ratio+gap evidence is not double counted.
ML_MIN_MAGNITUDE_EVIDENCE_COUNT = 2  # retained only for backward-compatible QC columns
ML_SINGLE_FAMILY_MIN_CONFIDENCE = 70.0
ML_SINGLE_FAMILY_MIN_GAP_MBPS = 30.0
ML_SINGLE_FAMILY_MAX_RATIO = 0.25
ML_SINGLE_FAMILY_MIN_EVIDENCE = 0.75

# -------------------------
# Boosted-tree model parameters
# -------------------------
HGB_COMMON_PARAMS = dict(
    max_iter=350,
    learning_rate=0.04,
    max_leaf_nodes=31,
    min_samples_leaf=25,
    l2_regularization=1.0,
    early_stopping=False,  # tuning/validation is session-group aware outside the model
    random_state=ML_RANDOM_SEED,
)

Q75_GB_PARAMS = dict(
    loss="quantile",
    alpha=0.75,
    n_estimators=300,
    learning_rate=0.04,
    max_depth=3,
    min_samples_leaf=20,
    subsample=0.85,
    random_state=ML_RANDOM_SEED,
)

# -------------------------
# LSTM-Q50 parameters
# -------------------------
ML_RUN_LSTM_Q50 = True
LSTM_SEQUENCE_LENGTH = 20
LSTM_HIDDEN_SIZE = 48
LSTM_NUM_LAYERS = 1
LSTM_DROPOUT = 0.10
LSTM_BATCH_SIZE = 256
LSTM_MAX_EPOCHS = 35
LSTM_EARLY_STOPPING_PATIENCE = 6
LSTM_LEARNING_RATE = 1e-3
LSTM_WEIGHT_DECAY = 1e-5
LSTM_VALIDATION_SESSION_FRACTION = 0.15
LSTM_OOF_N_SPLITS = ML_OOF_N_SPLITS
LSTM_DEVICE = "cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu"

# -------------------------
# ML score and final fusion calibration
# -------------------------
ML_SCORE_MEDIUM = 45.0
ML_SCORE_HIGH = 70.0
ML_SCORE_CRITICAL = 90.0
ML_NON_CATASTROPHIC_CAP = 95.0

FUSION_IMPACT_WEIGHT = 0.55
FUSION_CONFIDENCE_WEIGHT = 0.45
FUSION_MEDIUM = 40.0
FUSION_HIGH = 65.0
FUSION_CRITICAL = 90.0
FUSION_MIN_ROW_HANDOFF_SCORE = 40.0
FUSION_CONSENSUS_MIN_SCORE = 40.0
FUSION_STAT_EXPECTED_MIN_SCORE = 50.0
FUSION_STAT_RADIO_TEMPORAL_MIN_SCORE = 55.0
FUSION_ML_ONLY_MIN_SCORE = 55.0
FUSION_ML_ONLY_MIN_CONFIDENCE = 60.0
FUSION_EPISODE_MIN_SCORE = 40.0
FUSION_EPISODE_MIN_CONFIDENCE = 40.0
FUSION_SINGLETON_STAT_ONLY_MIN_SCORE = 55.0
FUSION_OPERATIONAL_MAX_GAP_SECONDS = 5.0
FUSION_OPERATIONAL_MAX_DISTANCE_M = 50.0

# Validation-informed reliability priors. They are role weights, not probabilities.
ML_RELIABILITY_HGB_TEMPORAL = 0.95
ML_RELIABILITY_HGB_RESOURCE = 0.90
ML_RELIABILITY_Q75_RESOURCE = 0.90
ML_RELIABILITY_LSTM = 0.68
ML_RELIABILITY_IFOREST = 0.55

# Final roles: only these three predictive models may influence final ML anomaly decisions.
ML_PRODUCTION_MODELS = ["hgb_temporal", "hgb_resource", "q75_resource"]
ML_CONTEXT_VALIDATION_MODELS = ["lstm_q50", "iforest"]
ML_ONLY_REQUIRES_HUMAN_REVIEW = True

MODEL_ARTIFACT_DIR = ANOMALY_DIR / "ml_model_artifacts"
MODEL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

_REQUIRED_ARTIFACTS = [
    "hgb_resource_q50.joblib", "hgb_strict_causal_temporal_q50.joblib",
    "gb_resource_q75_calibrated_base.joblib", "isolation_forest_context_only.joblib",
]

import shutil

candidate_artifact_dirs = [
    MODEL_ARTIFACT_DIR,
    OUTPUT_ROOT.parent / "02_anomaly_detection" / "ml_model_artifacts",
    OUTPUT_ROOT.parent / "outputs" / "02_anomaly_detection" / "ml_model_artifacts",
    Path("/data/outputs/02_anomaly_detection/ml_model_artifacts"),
    Path("./outputs/02_anomaly_detection/ml_model_artifacts"),
    Path("/media/mogahed/New Volume/iti_gp/Sakr_200/ran-telco-platform_tar_flag/ran-telco-platform/outputs/02_anomaly_detection/ml_model_artifacts"),
]

env_artifact_dir = os.environ.get("RAN_MODEL_ARTIFACT_DIR")
if env_artifact_dir:
    candidate_artifact_dirs.insert(0, Path(env_artifact_dir))

source_artifact_dir = None
for candidate in candidate_artifact_dirs:
    if candidate.exists() and all((candidate / _f).exists() for _f in _REQUIRED_ARTIFACTS):
        source_artifact_dir = candidate
        break

if source_artifact_dir:
    for _f in _REQUIRED_ARTIFACTS:
        src_file = source_artifact_dir / _f
        dest_file = MODEL_ARTIFACT_DIR / _f
        if src_file.resolve() != dest_file.resolve() and not dest_file.exists():
            shutil.copyfile(src_file, dest_file)
    ML_ARTIFACTS_EXIST = True
else:
    ML_ARTIFACTS_EXIST = all((MODEL_ARTIFACT_DIR / _f).exists() for _f in _REQUIRED_ARTIFACTS)

ML_FORCE_TRAINING = os.environ.get("RAN_ANOMALY_FORCE_TRAINING", "").strip().lower() in {"1", "true", "yes"}
ML_SKIP_TRAINING = ML_ARTIFACTS_EXIST and not ML_FORCE_TRAINING
if ML_SKIP_TRAINING:
    ML_RUN_LSTM_Q50 = False
    print(f"Pre-trained model artifacts found at {source_artifact_dir or MODEL_ARTIFACT_DIR} — running in INFERENCE mode (skipping ML training).")
elif ML_ARTIFACTS_EXIST:
    print("Artifacts exist but RAN_ANOMALY_FORCE_TRAINING is set — retraining from scratch.")
else:
    print("No pre-trained artifacts found — running full training pipeline.")

print("PyTorch available:", TORCH_AVAILABLE)
print("LSTM device:", LSTM_DEVICE)
print("OOF group folds:", ML_OOF_N_SPLITS)


# =========================
