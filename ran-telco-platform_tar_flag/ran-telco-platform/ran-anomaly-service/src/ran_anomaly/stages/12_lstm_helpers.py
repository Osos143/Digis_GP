"""
Stage 12: lstm helpers
Extracted verbatim from the original monolithic anomaly_detection.py (source lines 4301-4583). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 22. PyTorch LSTM-Q50 sequence helpers and cross-fitted prediction
# =========================

if TORCH_AVAILABLE:
    class LSTMQ50Dataset(Dataset):
        def __init__(self, X: np.ndarray, y: np.ndarray, row_positions: np.ndarray):
            self.X = torch.tensor(X, dtype=torch.float32)
            self.y = torch.tensor(y, dtype=torch.float32)
            self.row_positions = np.asarray(row_positions, dtype=int)

        def __len__(self):
            return len(self.y)

        def __getitem__(self, idx):
            return self.X[idx], self.y[idx]


    class LSTMQ50Regressor(nn.Module):
        def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
            super().__init__()
            effective_dropout = dropout if num_layers > 1 else 0.0
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=effective_dropout,
                batch_first=True,
            )
            self.head = nn.Sequential(
                nn.Linear(hidden_size, hidden_size // 2),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_size // 2, 1),
            )

        def forward(self, x):
            output, _ = self.lstm(x)
            return self.head(output[:, -1, :]).squeeze(-1)


    def torch_pinball_loss(pred: torch.Tensor, target: torch.Tensor, quantile: float = 0.50) -> torch.Tensor:
        error = target - pred
        return torch.maximum(quantile * error, (quantile - 1.0) * error).mean()


@dataclass
class TemporalScalerBundle:
    columns: List[str]
    medians: pd.Series
    scaler: StandardScaler
    past_tp_log_mean: float
    past_tp_log_std: float


def fit_temporal_scaler(train_df: pd.DataFrame, feature_cols: Sequence[str]) -> TemporalScalerBundle:
    numeric = train_df[list(feature_cols)].apply(pd.to_numeric, errors="coerce")
    medians = numeric.median().fillna(0.0)
    filled = numeric.fillna(medians)
    scaler = StandardScaler()
    scaler.fit(filled)
    past_tp_log = np.log1p(pd.to_numeric(train_df[TARGET_COL], errors="coerce")).dropna()
    tp_mean = float(past_tp_log.mean()) if len(past_tp_log) else 0.0
    tp_std = float(past_tp_log.std(ddof=0)) if len(past_tp_log) else 1.0
    if not np.isfinite(tp_std) or tp_std < 1e-6:
        tp_std = 1.0
    return TemporalScalerBundle(list(feature_cols), medians, scaler, tp_mean, tp_std)


def transform_temporal_rows(df: pd.DataFrame, bundle: TemporalScalerBundle) -> np.ndarray:
    numeric = df[bundle.columns].apply(pd.to_numeric, errors="coerce").fillna(bundle.medians)
    return bundle.scaler.transform(numeric).astype(np.float32)


def build_temporal_sequences(
    df: pd.DataFrame,
    session_ids: Sequence[Any],
    scaler_bundle: TemporalScalerBundle,
    window: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build causal windows. Input positions t-window..t-1 predict target at t."""
    wanted = set(map(str, session_ids))
    X_all, y_all, row_positions = [], [], []
    for _, group in df[df[GROUP_COL].astype(str).isin(wanted)].groupby(GROUP_COL, sort=False):
        group = group.sort_values(TIME_COL) if TIME_COL in group.columns else group.sort_index()
        if len(group) <= window:
            continue
        row_features = transform_temporal_rows(group, scaler_bundle)
        past_tp_log = np.log1p(pd.to_numeric(group[TARGET_COL], errors="coerce").to_numpy(dtype=float)).reshape(-1, 1)
        past_tp_input = (past_tp_log - scaler_bundle.past_tp_log_mean) / scaler_bundle.past_tp_log_std
        row_features = np.concatenate([row_features, past_tp_input.astype(np.float32)], axis=1)
        targets = past_tp_log[:, 0]
        positions = group.index.to_numpy(dtype=int)
        for t in range(window, len(group)):
            X_all.append(row_features[t-window:t])
            y_all.append(targets[t])
            row_positions.append(positions[t])
    if not X_all:
        return (
            np.empty((0, window, len(scaler_bundle.columns) + 1), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype=int),
        )
    return np.asarray(X_all, dtype=np.float32), np.asarray(y_all, dtype=np.float32), np.asarray(row_positions, dtype=int)


def train_lstm_model(
    train_dataset,
    valid_dataset,
    input_size: int,
    seed: int,
) -> Tuple[Any, pd.DataFrame]:
    if not TORCH_AVAILABLE:
        return None, pd.DataFrame()
    torch.manual_seed(seed)
    model = LSTMQ50Regressor(
        input_size=input_size,
        hidden_size=LSTM_HIDDEN_SIZE,
        num_layers=LSTM_NUM_LAYERS,
        dropout=LSTM_DROPOUT,
    ).to(LSTM_DEVICE)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=LSTM_LEARNING_RATE, weight_decay=LSTM_WEIGHT_DECAY
    )
    train_loader = DataLoader(train_dataset, batch_size=LSTM_BATCH_SIZE, shuffle=True)
    valid_loader = DataLoader(valid_dataset, batch_size=LSTM_BATCH_SIZE, shuffle=False)

    best_state, best_valid = None, np.inf
    patience_left = LSTM_EARLY_STOPPING_PATIENCE
    history = []
    for epoch in range(1, LSTM_MAX_EPOCHS + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb, yb = xb.to(LSTM_DEVICE), yb.to(LSTM_DEVICE)
            optimizer.zero_grad(set_to_none=True)
            pred = model(xb)
            loss = torch_pinball_loss(pred, yb, quantile=0.50)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))

        model.eval()
        valid_losses = []
        with torch.no_grad():
            for xb, yb in valid_loader:
                xb, yb = xb.to(LSTM_DEVICE), yb.to(LSTM_DEVICE)
                valid_losses.append(float(torch_pinball_loss(model(xb), yb, 0.50).cpu()))
        train_loss = float(np.mean(train_losses)) if train_losses else np.nan
        valid_loss = float(np.mean(valid_losses)) if valid_losses else np.nan
        history.append({"epoch": epoch, "train_q50_pinball": train_loss, "valid_q50_pinball": valid_loss})

        if valid_loss < best_valid - 1e-5:
            best_valid = valid_loss
            best_state = deepcopy(model.state_dict())
            patience_left = LSTM_EARLY_STOPPING_PATIENCE
        else:
            patience_left -= 1
            if patience_left <= 0:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, pd.DataFrame(history)


def predict_lstm(model, dataset) -> np.ndarray:
    if model is None or len(dataset) == 0:
        return np.empty((0,), dtype=float)
    loader = DataLoader(dataset, batch_size=LSTM_BATCH_SIZE, shuffle=False)
    preds = []
    model.eval()
    with torch.no_grad():
        for xb, _ in loader:
            preds.append(model(xb.to(LSTM_DEVICE)).cpu().numpy())
    return np.concatenate(preds) if preds else np.empty((0,), dtype=float)


def cross_fit_lstm_q50(
    df: pd.DataFrame,
    temporal_features: Sequence[str],
    n_splits: int,
) -> Tuple[np.ndarray, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    oof_pred_log = np.full(len(df), np.nan, dtype=float)
    fold_metric_rows, histories = [], []
    comparison_bundle = {}
    sessions = df[GROUP_COL].astype(str)
    unique_sessions = sessions.drop_duplicates().to_numpy()
    outer = GroupKFold(n_splits=n_splits)

    # GroupKFold operates on rows; its indices still produce whole-session folds.
    dummy = np.zeros(len(df))
    for fold, (outer_train_idx, outer_test_idx) in enumerate(
        outer.split(dummy, groups=sessions.to_numpy()), start=1
    ):
        outer_train_sessions = sessions.iloc[outer_train_idx].drop_duplicates().to_numpy()
        outer_test_sessions = sessions.iloc[outer_test_idx].drop_duplicates().to_numpy()

        # Session-level inner validation for early stopping.
        inner_session_df = pd.DataFrame({GROUP_COL: outer_train_sessions})
        inner_split = GroupShuffleSplit(
            n_splits=1,
            test_size=LSTM_VALIDATION_SESSION_FRACTION,
            random_state=ML_RANDOM_SEED + fold,
        )
        inner_train_pos, inner_valid_pos = next(inner_split.split(
            inner_session_df, groups=inner_session_df[GROUP_COL]
        ))
        train_sessions = inner_session_df.iloc[inner_train_pos][GROUP_COL].astype(str).to_numpy()
        valid_sessions = inner_session_df.iloc[inner_valid_pos][GROUP_COL].astype(str).to_numpy()

        train_rows = df[sessions.isin(train_sessions)]
        scaler_bundle = fit_temporal_scaler(train_rows, temporal_features)

        X_train, y_train, pos_train = build_temporal_sequences(df, train_sessions, scaler_bundle, LSTM_SEQUENCE_LENGTH)
        X_valid, y_valid, pos_valid = build_temporal_sequences(df, valid_sessions, scaler_bundle, LSTM_SEQUENCE_LENGTH)
        X_test, y_test, pos_test = build_temporal_sequences(df, outer_test_sessions, scaler_bundle, LSTM_SEQUENCE_LENGTH)

        if min(len(y_train), len(y_valid), len(y_test)) == 0:
            print(f"Skipping LSTM fold {fold}: insufficient sequences")
            continue

        train_ds = LSTMQ50Dataset(X_train, y_train, pos_train)
        valid_ds = LSTMQ50Dataset(X_valid, y_valid, pos_valid)
        test_ds = LSTMQ50Dataset(X_test, y_test, pos_test)
        model, history = train_lstm_model(train_ds, valid_ds, X_train.shape[-1], ML_RANDOM_SEED + fold)
        pred_test = predict_lstm(model, test_ds)
        oof_pred_log[pos_test] = pred_test

        metric = regression_metrics(y_test, pred_test, "LSTM_temporal_Q50", "fold_validation", fold, alpha=0.50)
        metric["train_sequences"] = len(y_train)
        metric["valid_sequences"] = len(y_valid)
        metric["test_sequences"] = len(y_test)
        metric["train_sessions"] = len(train_sessions)
        metric["valid_sessions"] = len(valid_sessions)
        metric["test_sessions"] = len(outer_test_sessions)
        fold_metric_rows.append(metric)

        history = history.copy()
        history["fold"] = fold
        histories.append(history)

        if fold == 1:
            pred_train = predict_lstm(model, train_ds)
            comparison_bundle = {
                "model": model,
                "scaler_bundle": scaler_bundle,
                "train_sessions": train_sessions,
                "valid_sessions": valid_sessions,
                "test_sessions": outer_test_sessions,
                "train_positions": pos_train,
                "train_predictions_log": pred_train,
                "test_positions": pos_test,
                "test_predictions_log": pred_test,
                "history": history,
            }

    history_df = pd.concat(histories, ignore_index=True) if histories else pd.DataFrame()
    return oof_pred_log, pd.DataFrame(fold_metric_rows), history_df, comparison_bundle


def train_lstm_fixed_epochs(dataset, input_size: int, epochs: int, seed: int):
    """Refit the final LSTM on all accepted sequences for the selected number of epochs."""
    if not TORCH_AVAILABLE or len(dataset) == 0:
        return None
    torch.manual_seed(seed)
    model = LSTMQ50Regressor(input_size, LSTM_HIDDEN_SIZE, LSTM_NUM_LAYERS, LSTM_DROPOUT).to(LSTM_DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LSTM_LEARNING_RATE, weight_decay=LSTM_WEIGHT_DECAY)
    loader = DataLoader(dataset, batch_size=LSTM_BATCH_SIZE, shuffle=True)
    for _ in range(max(1, int(epochs))):
        model.train()
        for xb, yb in loader:
            xb, yb = xb.to(LSTM_DEVICE), yb.to(LSTM_DEVICE)
            optimizer.zero_grad(set_to_none=True)
            loss = torch_pinball_loss(model(xb), yb, 0.50)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    return model



# =========================
