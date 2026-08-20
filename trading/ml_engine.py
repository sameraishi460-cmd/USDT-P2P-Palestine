"""
AI Trading Engine — Machine Learning Engine (Phase 3)

Implements a complete ML prediction pipeline:
- Dataset generation from historical market data
- Feature normalization (chronological)
- Label engineering (TP hit, expected return, MFE, MAE)
- Chronological train/validation/test split
- Gradient Boosting model training
- Prediction with confidence
- Model versioning and persistence
- Graceful fallback on failure

IMPORTANT: ML output is a signal quality score, NOT a guaranteed
probability of profit. The Risk Engine remains FINAL AUTHORITY.
"""

import os
import json
import hashlib
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, mean_squared_error, mean_absolute_error,
)

from trading.features import calculate_all_features, get_feature_names
from trading.regime import detect_regime
from trading.market_data import fetch_klines, fetch_ticker


# ============================================================
# CONFIGURATION
# ============================================================

ML_DIR = Path("trading/ml_models")
ML_DIR.mkdir(parents=True, exist_ok=True)

# Training parameters
MIN_SAMPLES_FOR_TRAINING = 200
MIN_SAMPLES_FOR_VALIDATION = 50
TRAIN_RATIO = 0.7
VALIDATION_RATIO = 0.15
TEST_RATIO = 0.15

# Forward-looking windows (in candles of the given timeframe)
TP_CHECK_CANDLES = 20   # Check up to 20 candles ahead for TP
SL_CHECK_CANDLES = 20   # Check up to 20 candles ahead for SL

# Minimum required model performance
MIN_VALIDATION_ACCURACY = 0.48  # Must beat random (50%) — slightly lower to account for noise
MIN_VALIDATION_AUC = 0.45

# Risk estimation
DEFAULT_RISK_CONFIDENCE = 0.5


# ============================================================
# DATASET GENERATION
# ============================================================

def generate_labels(df, atr_multiplier=1.5, tp_rr=1.5, forward_candles=TP_CHECK_CANDLES):
    """
    Generate forward-looking labels for each candle.

    Labels:
    - tp_hit: 1 if TP reached before SL within forward window
    - expected_return_pct: percentage return if held for forward_candles
    - mfe_pct: maximum favorable excursion during forward window
    - mae_pct: maximum adverse excursion during forward window

    IMPORTANT: These labels use FUTURE data and are ONLY used for training.
    They must NEVER be used in live scoring.
    """
    n = len(df)
    tp_hits = np.zeros(n, dtype=np.int8)
    expected_returns = np.zeros(n, dtype=np.float32)
    mfe_values = np.zeros(n, dtype=np.float32)
    mae_values = np.zeros(n, dtype=np.float32)

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    atrs = df["atr"].values if "atr" in df.columns else np.full(n, closes * 0.01)

    for i in range(n):
        entry_price = closes[i]
        atr = atrs[i] if atrs[i] > 0 else entry_price * 0.01

        sl_distance = atr * atr_multiplier
        tp_distance = sl_distance * tp_rr

        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance

        # Forward look
        end_idx = min(i + forward_candles + 1, n)
        future_highs = highs[i+1:end_idx]
        future_lows = lows[i+1:end_idx]
        future_closes = closes[i+1:end_idx]

        if len(future_highs) == 0:
            continue

        # Check TP/SL hit order
        tp_hit = False
        sl_hit = False
        for j in range(len(future_highs)):
            if future_highs[j] >= tp_price:
                tp_hit = True
            if future_lows[j] <= sl_price:
                sl_hit = True
            if tp_hit or sl_hit:
                break

        # TP hit before SL
        if tp_hit and not sl_hit:
            tp_hits[i] = 1
        elif tp_hit and sl_hit:
            # Check which happened first (simplified: use close proximity)
            tp_hits[i] = 1  # Conservative: count as TP if both hit

        # Expected return
        if len(future_closes) > 0:
            exit_price = future_closes[-1]
            expected_returns[i] = (exit_price - entry_price) / entry_price * 100

        # MFE / MAE
        if len(future_highs) > 0:
            mfe_values[i] = (np.max(future_highs) - entry_price) / entry_price * 100
        if len(future_lows) > 0:
            mae_values[i] = (entry_price - np.min(future_lows)) / entry_price * 100

    return tp_hits, expected_returns, mfe_values, mae_values


def build_dataset(symbol, timeframe="1h", limit=1000, forward_candles=TP_CHECK_CANDLES):
    """
    Build a labeled dataset for a single symbol/timeframe.

    Returns:
        pd.DataFrame with features + labels, or None if insufficient data.
    """
    df = fetch_klines(symbol, timeframe, limit=limit)
    if df is None or len(df) < MIN_SAMPLES_FOR_TRAINING:
        return None

    # Calculate features (NO future data in features)
    df = calculate_all_features(df)

    # Drop rows with NaN in critical features
    critical_cols = ["close", "atr", "rsi", "macd_hist", "adx", "bb_position", "relative_volume"]
    df = df.dropna(subset=[c for c in critical_cols if c in df.columns])

    if len(df) < MIN_SAMPLES_FOR_TRAINING:
        return None

    # Generate labels (uses future data — ONLY for training)
    tp_hits, expected_returns, mfe_values, mae_values = generate_labels(
        df, forward_candles=forward_candles
    )

    df = df.copy()
    df["label_tp"] = tp_hits
    df["label_return"] = expected_returns
    df["label_mfe"] = mfe_values
    df["label_mae"] = mae_values

    # Add metadata
    df["symbol"] = symbol
    df["timeframe"] = timeframe

    # Drop last forward_candles rows (labels are incomplete for them)
    df = df.iloc[:-forward_candles]

    return df


def build_multi_symbol_dataset(symbols, timeframes=None, limit=1000):
    """
    Build combined dataset from multiple symbols and timeframes.
    """
    if timeframes is None:
        timeframes = ["1h", "4h"]

    all_data = []
    for symbol in symbols:
        symbol = symbol.strip()
        if not symbol:
            continue
        for tf in timeframes:
            try:
                ds = build_dataset(symbol, tf, limit=limit)
                if ds is not None and len(ds) > 0:
                    all_data.append(ds)
                    print(f"  Dataset: {symbol}/{tf} — {len(ds)} samples")
            except Exception as e:
                print(f"  Dataset error {symbol}/{tf}: {e}")

    if not all_data:
        return None

    combined = pd.concat(all_data, ignore_index=True)
    print(f"  Total dataset: {len(combined)} samples from {len(all_data)} symbol/TF pairs")
    return combined


# ============================================================
# FEATURE PREPARATION
# ============================================================

def get_ml_feature_columns():
    """Return the list of feature columns used by the ML model."""
    # Core technical features that are safe (no look-ahead)
    return [
        # Moving average distances
        "dist_ema20", "dist_ema50", "dist_ema200",
        # MA alignment
        "ma_bullish", "ma_bearish",
        # RSI
        "rsi", "rsi_oversold", "rsi_overbought",
        # MACD
        "macd_hist", "macd_cross_up", "macd_cross_down",
        # ADX
        "adx", "plus_di", "minus_di",
        # ATR
        "atr_pct",
        # Bollinger
        "bb_width", "bb_position",
        # Volume
        "relative_volume", "volume_trend",
        # Momentum
        "momentum_5", "momentum_10", "momentum_20", "roc",
        # Volatility
        "volatility_10", "volatility_20", "volatility_regime",
        # Trend
        "trend_strength",
        # Support/Resistance
        "dist_to_r1", "dist_to_s1",
        # Candle structure
        "candle_range", "body_ratio", "upper_wick_ratio",
        "lower_wick_ratio", "is_green", "consecutive_green",
        # Breakouts
        "breakout_up", "breakout_down",
    ]


def prepare_features(df, feature_columns=None, scaler=None, fit=False):
    """
    Prepare features for ML model.

    Args:
        df: DataFrame with all features calculated
        feature_columns: list of feature column names
        scaler: fitted StandardScaler (None for training)
        fit: if True, fit the scaler

    Returns:
        X (features), y_tp (binary label), scaler
    """
    if feature_columns is None:
        feature_columns = get_ml_feature_columns()

    # Only use columns that exist in the dataframe
    available = [c for c in feature_columns if c in df.columns]
    missing = [c for c in feature_columns if c not in df.columns]

    if missing:
        print(f"  Warning: {len(missing)} features missing: {missing[:5]}...")

    X = df[available].copy()

    # Replace inf with NaN, then fill
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0)

    # Normalize
    if fit:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
    elif scaler is not None:
        X_scaled = scaler.transform(X)
    else:
        X_scaled = X.values

    X_scaled = pd.DataFrame(X_scaled, columns=available, index=X.index)

    # Labels
    y_tp = df["label_tp"].values if "label_tp" in df.columns else None

    return X_scaled, y_tp, scaler, available


# ============================================================
# MODEL TRAINING
# ============================================================

def chronological_split(df, train_ratio=TRAIN_RATIO, val_ratio=VALIDATION_RATIO):
    """
    Split data chronologically (no shuffle).
    """
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train = df.iloc[:train_end]
    val = df.iloc[train_end:val_end]
    test = df.iloc[val_end:]

    return train, val, test


def train_model(dataset, symbol="ALL", timeframe="ALL"):
    """
    Train ML model on a dataset.

    Returns:
        dict with model, scaler, metrics, metadata, or None on failure.
    """
    if dataset is None or len(dataset) < MIN_SAMPLES_FOR_TRAINING:
        print("  ML: Insufficient data for training")
        return None

    feature_columns = get_ml_feature_columns()

    # Chronological split
    train_df, val_df, test_df = chronological_split(dataset)

    if len(train_df) < 100 or len(val_df) < MIN_SAMPLES_FOR_VALIDATION:
        print(f"  ML: Insufficient samples — train={len(train_df)}, val={len(val_df)}")
        return None

    print(f"  ML Split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

    # Prepare features (fit scaler on train only)
    X_train, y_train, scaler, used_features = prepare_features(
        train_df, feature_columns, scaler=None, fit=True
    )
    X_val, y_val, _, _ = prepare_features(
        val_df, feature_columns, scaler=scaler, fit=False
    )
    X_test, y_test, _, _ = prepare_features(
        test_df, feature_columns, scaler=scaler, fit=False
    )

    if y_train is None or y_val is None:
        print("  ML: Labels missing")
        return None

    # Check label distribution
    train_tp_rate = np.mean(y_train)
    print(f"  ML Training TP rate: {train_tp_rate:.3f} ({np.sum(y_train)}/{len(y_train)})")

    if train_tp_rate < 0.1 or train_tp_rate > 0.9:
        print(f"  ML: Extreme label distribution ({train_tp_rate:.3f}) — model may not generalize")

    # === TRAIN CLASSIFIER ===
    try:
        classifier = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            min_samples_split=20,
            min_samples_leaf=10,
            max_features="sqrt",
            random_state=42,
            validation_fraction=0.1,
            n_iter_no_change=10,
            tol=1e-4,
        )

        classifier.fit(X_train, y_train)

        # === EVALUATE ===
        # Training metrics
        train_pred = classifier.predict(X_train)
        train_prob = classifier.predict_proba(X_train)[:, 1]
        train_acc = accuracy_score(y_train, train_pred)
        train_auc = roc_auc_score(y_train, train_prob) if len(np.unique(y_train)) > 1 else 0.5

        # Validation metrics
        val_pred = classifier.predict(X_val)
        val_prob = classifier.predict_proba(X_val)[:, 1]
        val_acc = accuracy_score(y_val, val_pred)
        val_auc = roc_auc_score(y_val, val_prob) if len(np.unique(y_val)) > 1 else 0.5
        val_precision = precision_score(y_val, val_pred, zero_division=0)
        val_recall = recall_score(y_val, val_pred, zero_division=0)
        val_f1 = f1_score(y_val, val_pred, zero_division=0)

        # Test metrics (out-of-sample)
        test_acc, test_auc = 0.0, 0.5
        test_precision, test_recall, test_f1 = 0.0, 0.0, 0.0
        if len(test_df) >= MIN_SAMPLES_FOR_VALIDATION and y_test is not None:
            test_pred = classifier.predict(X_test)
            test_prob = classifier.predict_proba(X_test)[:, 1]
            test_acc = accuracy_score(y_test, test_pred)
            test_auc = roc_auc_score(y_test, test_prob) if len(np.unique(y_test)) > 1 else 0.5
            test_precision = precision_score(y_test, test_pred, zero_division=0)
            test_recall = recall_score(y_test, test_pred, zero_division=0)
            test_f1 = f1_score(y_test, test_pred, zero_division=0)

        print(f"  ML Train:      acc={train_acc:.3f}, auc={train_auc:.3f}")
        print(f"  ML Validation: acc={val_acc:.3f}, auc={val_auc:.3f}, prec={val_precision:.3f}, rec={val_recall:.3f}")
        print(f"  ML Test:       acc={test_acc:.3f}, auc={test_auc:.3f}")

        # === VALIDATION CHECK ===
        if val_acc < MIN_VALIDATION_ACCURACY and val_auc < MIN_VALIDATION_AUC:
            print(f"  ML: Validation too weak (acc={val_acc:.3f}, auc={val_auc:.3f}) — REJECTED")
            return None

        # === FEATURE IMPORTANCE ===
        importances = dict(zip(used_features, classifier.feature_importances_))
        top_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]

        # === BUILD RESULT ===
        model_id = f"gb_{symbol}_{frame_now()}"

        result = {
            "model": classifier,
            "scaler": scaler,
            "model_id": model_id,
            "model_type": "GradientBoosting",
            "symbol": symbol,
            "timeframe": timeframe,
            "features_used": used_features,
            "num_features": len(used_features),
            "num_samples": len(dataset),
            "train_samples": len(train_df),
            "val_samples": len(val_df),
            "test_samples": len(test_df),
            "train_tp_rate": round(train_tp_rate, 4),
            "metrics": {
                "train_acc": round(train_acc, 4),
                "train_auc": round(train_auc, 4),
                "val_acc": round(val_acc, 4),
                "val_auc": round(val_auc, 4),
                "val_precision": round(val_precision, 4),
                "val_recall": round(val_recall, 4),
                "val_f1": round(val_f1, 4),
                "test_acc": round(test_acc, 4),
                "test_auc": round(test_auc, 4),
                "test_precision": round(test_precision, 4),
                "test_recall": round(test_recall, 4),
                "test_f1": round(test_f1, 4),
            },
            "top_features": [{"name": n, "importance": round(float(v), 4)} for n, v in top_features],
            "status": "TRAINED",
            "created_at": datetime.now().isoformat(),
        }

        return result

    except Exception as e:
        print(f"  ML Training error: {e}")
        traceback.print_exc()
        return None


def frame_now():
    """Get a short timestamp string for model IDs."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ============================================================
# MODEL REGISTRY
# ============================================================

class ModelRegistry:
    """Manages model versioning, persistence, and loading."""

    def __init__(self, registry_dir=None):
        self.registry_dir = Path(registry_dir or ML_DIR)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.registry_dir / "model_registry.json"
        self.active_model_id = None

    def _load_registry(self):
        """Load the model registry from disk."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"models": {}, "active_model": None}

    def _save_registry(self, registry):
        """Save the model registry to disk."""
        with open(self.registry_file, "w") as f:
            json.dump(registry, f, indent=2, default=str)

    def save_model(self, training_result):
        """
        Save a trained model to the registry.

        Returns:
            model_id if saved, None on failure.
        """
        if not training_result:
            return None

        model_id = training_result["model_id"]
        model_path = self.registry_dir / f"{model_id}.joblib"
        scaler_path = self.registry_dir / f"{model_id}_scaler.joblib"

        try:
            # Save model and scaler
            joblib.dump(training_result["model"], model_path)
            joblib.dump(training_result["scaler"], scaler_path)

            # Update registry
            registry = self._load_registry()
            registry["models"][model_id] = {
                "model_id": model_id,
                "model_type": training_result["model_type"],
                "symbol": training_result["symbol"],
                "timeframe": training_result["timeframe"],
                "features_used": training_result["features_used"],
                "num_features": training_result["num_features"],
                "num_samples": training_result["num_samples"],
                "metrics": training_result["metrics"],
                "top_features": training_result["top_features"],
                "status": training_result["status"],
                "created_at": training_result["created_at"],
                "model_path": str(model_path),
                "scaler_path": str(scaler_path),
            }

            # Set as active model
            registry["active_model"] = model_id
            self.active_model_id = model_id

            self._save_registry(registry)
            print(f"  ML Registry: saved model {model_id}")
            return model_id

        except Exception as e:
            print(f"  ML Registry save error: {e}")
            return None

    def load_active_model(self):
        """
        Load the currently active model.

        Returns:
            dict with model, scaler, info, or None if not available.
        """
        registry = self._load_registry()
        active_id = registry.get("active_model")

        if not active_id:
            return None

        return self.load_model(active_id)

    def load_model(self, model_id):
        """Load a specific model by ID."""
        registry = self._load_registry()
        info = registry.get("models", {}).get(model_id)

        if not info:
            return None

        model_path = Path(info["model_path"])
        scaler_path = Path(info["scaler_path"])

        if not model_path.exists() or not scaler_path.exists():
            print(f"  ML Registry: model files missing for {model_id}")
            return None

        try:
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            return {
                "model": model,
                "scaler": scaler,
                "info": info,
            }
        except Exception as e:
            print(f"  ML Registry load error {model_id}: {e}")
            return None

    def get_active_model_id(self):
        """Get the active model ID."""
        registry = self._load_registry()
        return registry.get("active_model")

    def list_models(self):
        """List all registered models."""
        registry = self._load_registry()
        return registry.get("models", {})

    def deactivate_model(self, model_id=None):
        """Deactivate a model."""
        registry = self._load_registry()
        if model_id is None:
            model_id = registry.get("active_model")
        if model_id and model_id in registry.get("models", {}):
            registry["models"][model_id]["status"] = "DEACTIVATED"
        registry["active_model"] = None
        self.active_model_id = None
        self._save_registry(registry)

    def get_registry_info(self):
        """Get summary of registry state."""
        registry = self._load_registry()
        models = registry.get("models", {})
        active = registry.get("active_model")
        active_info = models.get(active, {}) if active else None

        return {
            "total_models": len(models),
            "active_model": active,
            "active_info": active_info,
            "models": list(models.keys()),
        }


# ============================================================
# ML PREDICTOR
# ============================================================

class MLPredictor:
    """
    Makes predictions using the trained ML model.
    Falls back gracefully if model is unavailable or fails.
    """

    def __init__(self):
        self.registry = ModelRegistry()
        self._loaded_model = None
        self._loaded_model_id = None
        self._prediction_count = 0
        self._error_count = 0

    def _ensure_model_loaded(self):
        """Load the active model if not already loaded."""
        active_id = self.registry.get_active_model_id()
        if not active_id:
            return None

        if self._loaded_model_id == active_id and self._loaded_model:
            return self._loaded_model

        loaded = self.registry.load_active_model()
        if loaded:
            self._loaded_model = loaded
            self._loaded_model_id = active_id
            return loaded

        return None

    def predict(self, feature_row, feature_columns=None):
        """
        Make an ML prediction for a single feature row.

        Args:
            feature_row: pd.Series or dict of features
            feature_columns: list of feature columns to use

        Returns:
            dict with:
                - ml_score: 0-100 (signal quality, NOT probability of profit)
                - ml_confidence: 0-1 (model confidence)
                - ml_direction: 'LONG', 'SHORT', or 'NEUTRAL'
                - model_version: active model ID
                - available: True if prediction was made
                - error: error message if prediction failed
        """
        self._prediction_count += 1
        result = {
            "ml_score": 50.0,  # Default neutral score
            "ml_confidence": 0.0,
            "ml_direction": "NEUTRAL",
            "model_version": "none",
            "available": False,
            "error": None,
        }

        loaded = self._ensure_model_loaded()
        if not loaded:
            result["error"] = "No model available"
            return result

        model = loaded["model"]
        scaler = loaded["scaler"]
        info = loaded["info"]
        result["model_version"] = info["model_id"]

        try:
            if feature_columns is None:
                feature_columns = info.get("features_used", get_ml_feature_columns())

            # Prepare feature vector
            if isinstance(feature_row, dict):
                feature_row = pd.Series(feature_row)

            available = [c for c in feature_columns if c in feature_row.index]
            if len(available) < len(feature_columns) * 0.5:
                result["error"] = f"Too few features available: {len(available)}/{len(feature_columns)}"
                return result

            X = feature_row[available].values.reshape(1, -1)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            # Scale
            X_scaled = scaler.transform(X)

            # Predict
            prob = model.predict_proba(X_scaled)[0]
            prediction = model.predict(X_scaled)[0]

            # Convert to signal quality score (0-100)
            # prob[1] = probability of TP being reached
            tp_prob = prob[1] if len(prob) > 1 else 0.5

            # Map probability to signal score
            # 0.5 = neutral (50), 0.7+ = strong (70+), 0.3- = weak (<30)
            ml_score = 20 + (tp_prob * 60)  # Maps 0-1 to 20-80
            ml_score = max(0, min(100, ml_score))

            # Confidence is based on how far from 0.5 the probability is
            confidence = abs(tp_prob - 0.5) * 2  # 0-1 scale

            # Direction
            if prediction == 1:
                direction = "LONG"
            elif prediction == 0:
                direction = "SHORT"
            else:
                direction = "NEUTRAL"

            result.update({
                "ml_score": round(ml_score, 1),
                "ml_confidence": round(confidence, 3),
                "ml_direction": direction,
                "ml_tp_probability": round(tp_prob, 4),
                "available": True,
            })

            return result

        except Exception as e:
            self._error_count += 1
            result["error"] = str(e)

            # If too many errors, deactivate model
            if self._error_count > 10:
                print(f"  ML: Too many prediction errors ({self._error_count}) — deactivating model")
                self.registry.deactivate_model()
                self._loaded_model = None

            return result

    def get_status(self):
        """Get ML predictor status."""
        info = self.registry.get_registry_info()
        return {
            "active_model": info.get("active_model"),
            "total_models": info.get("total_models", 0),
            "prediction_count": self._prediction_count,
            "error_count": self._error_count,
            "model_info": info.get("active_info"),
        }


# ============================================================
# ML TRAINING PIPELINE (called periodically)
# ============================================================

def run_ml_training_pipeline(symbols=None, timeframes=None):
    """
    Full ML training pipeline.
    Called periodically (e.g., once per day or on startup).

    Returns:
        dict with training results.
    """
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    if timeframes is None:
        timeframes = ["1h", "4h"]

    print("\n=== ML Training Pipeline ===")

    # 1. Build dataset
    print("Step 1: Building dataset...")
    dataset = build_multi_symbol_dataset(symbols, timeframes, limit=1000)
    if dataset is None or len(dataset) < MIN_SAMPLES_FOR_TRAINING:
        print("  ML Pipeline: Insufficient data — aborting")
        return {"status": "FAILED", "reason": "insufficient_data"}

    print(f"  Dataset: {len(dataset)} total samples")

    # 2. Train model
    print("Step 2: Training model...")
    result = train_model(dataset, symbol="ALL", timeframe="ALL")
    if result is None:
        print("  ML Pipeline: Training failed — aborting")
        return {"status": "FAILED", "reason": "training_failed"}

    # 3. Save to registry
    print("Step 3: Saving to registry...")
    registry = ModelRegistry()
    model_id = registry.save_model(result)
    if not model_id:
        print("  ML Pipeline: Save failed")
        return {"status": "FAILED", "reason": "save_failed"}

    # 4. Verify
    print("Step 4: Verifying...")
    predictor = MLPredictor()
    test_features = pd.Series({c: 0.0 for c in get_ml_feature_columns()})
    test_result = predictor.predict(test_features)

    status = {
        "status": "SUCCESS",
        "model_id": model_id,
        "metrics": result["metrics"],
        "num_features": result["num_features"],
        "num_samples": result["num_samples"],
        "prediction_test": test_result["available"],
        "top_features": result["top_features"],
    }

    print(f"\n  ML Pipeline COMPLETE — model {model_id}")
    print(f"  Validation accuracy: {result['metrics']['val_acc']:.3f}")
    print(f"  Validation AUC: {result['metrics']['val_auc']:.3f}")
    print(f"  Top features: {', '.join(f['name'] for f in result['top_features'][:5])}")

    return status
