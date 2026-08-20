"""
AI Trading Engine — Feature Engineering (Phase 2 Enhanced)

Calculates comprehensive technical indicators for each candle.
All features are normalized for ML consumption.

Phase 2 additions:
- Cross-timeframe feature comparison
- Timeframe alignment detection
- Multi-TF trend consensus
- Enhanced support/resistance levels
"""

import numpy as np
import pandas as pd


def calculate_all_features(df):
    """Calculate the full feature set on a DataFrame with OHLCV data."""
    if df is None or len(df) < 30:
        return df

    df = df.copy()
    c = df["close"]
    h = df["high"]
    l = df["low"]
    o = df["open"]
    v = df["volume"]

    # =====================
    # MOVING AVERAGES
    # =====================
    df["ema_20"] = c.ewm(span=20, adjust=False).mean()
    df["ema_50"] = c.ewm(span=50, adjust=False).mean()
    df["ema_100"] = c.ewm(span=100, adjust=False).mean()
    df["ema_200"] = c.ewm(span=200, adjust=False).mean()
    df["sma_20"] = c.rolling(20).mean()
    df["sma_50"] = c.rolling(50).mean()

    # Distance from MAs (normalized %)
    df["dist_ema20"] = pd.Series(
        np.where(df["ema_20"] > 0, (c - df["ema_20"]) / df["ema_20"] * 100, 0), index=df.index
    ).fillna(0)
    df["dist_ema50"] = pd.Series(
        np.where(df["ema_50"] > 0, (c - df["ema_50"]) / df["ema_50"] * 100, 0), index=df.index
    ).fillna(0)
    df["dist_ema200"] = pd.Series(
        np.where(df["ema_200"] > 0, (c - df["ema_200"]) / df["ema_200"] * 100, 0), index=df.index
    ).fillna(0)

    # MA alignment
    df["ma_bullish"] = (
        (df["ema_20"] > df["ema_50"]).astype(int)
        & (df["ema_50"] > df["ema_100"]).astype(int)
    ).astype(int)
    df["ma_bearish"] = (
        (df["ema_20"] < df["ema_50"]).astype(int)
        & (df["ema_50"] < df["ema_100"]).astype(int)
    ).astype(int)

    # =====================
    # RSI
    # =====================
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    df["rsi"] = df["rsi"].fillna(50)

    # RSI zones
    df["rsi_oversold"] = (df["rsi"] < 30).astype(int)
    df["rsi_overbought"] = (df["rsi"] > 70).astype(int)

    # =====================
    # MACD
    # =====================
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["macd_cross_up"] = (
        (df["macd"] > df["macd_signal"])
        & (df["macd"].shift(1) <= df["macd_signal"].shift(1))
    ).astype(int)
    df["macd_cross_down"] = (
        (df["macd"] < df["macd_signal"])
        & (df["macd"].shift(1) >= df["macd_signal"].shift(1))
    ).astype(int)

    # =====================
    # ADX (Average Directional Index)
    # =====================
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)

    plus_dm = h.diff()
    minus_dm = -l.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)

    atr14 = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["adx"] = dx.rolling(14).mean()
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = df["adx"].fillna(25)
    df["plus_di"] = df["plus_di"].fillna(25)
    df["minus_di"] = df["minus_di"].fillna(25)

    # =====================
    # ATR (Average True Range)
    # =====================
    df["atr"] = tr.rolling(14).mean()
    df["atr_pct"] = np.where(c > 0, df["atr"] / c * 100, 0)
    df["atr"] = df["atr"].fillna(0)
    df["atr_pct"] = df["atr_pct"].fillna(0)

    # =====================
    # BOLLINGER BANDS
    # =====================
    df["bb_mid"] = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std
    bb_range = df["bb_upper"] - df["bb_lower"]
    df["bb_width"] = np.where(df["bb_mid"] > 0, bb_range / df["bb_mid"] * 100, 0)
    df["bb_position"] = pd.Series(
        np.where(bb_range > 0, (c - df["bb_lower"]) / bb_range, 0.5), index=df.index
    ).fillna(0.5)

    # =====================
    # VOLUME ANALYSIS
    # =====================
    df["vol_sma_20"] = v.rolling(20).mean()
    df["relative_volume"] = pd.Series(
        np.where(df["vol_sma_20"] > 0, v / df["vol_sma_20"], 1), index=df.index
    ).fillna(1)
    df["volume_trend"] = df["relative_volume"].rolling(5).mean()
    df["volume_trend"] = df["volume_trend"].fillna(1)

    # =====================
    # MOMENTUM
    # =====================
    df["momentum_5"] = c.pct_change(5) * 100
    df["momentum_10"] = c.pct_change(10) * 100
    df["momentum_20"] = c.pct_change(20) * 100
    df["roc"] = c.pct_change(10) * 100  # Rate of Change

    # =====================
    # VOLATILITY
    # =====================
    df["volatility_10"] = c.pct_change().rolling(10).std() * 100
    df["volatility_20"] = c.pct_change().rolling(20).std() * 100
    df["volatility_regime"] = pd.cut(
        df["volatility_20"], bins=[0, 0.5, 1.5, 3, 999],
        labels=[0, 1, 2, 3], include_lowest=True
    ).astype(float).fillna(1)

    # =====================
    # TREND STRENGTH
    # =====================
    df["trend_strength"] = pd.Series(
        np.where(
            df["ema_50"] > 0,
            (df["ema_20"] - df["ema_50"]) / df["ema_50"] * 100,
            0
        ), index=df.index
    ).fillna(0)

    # =====================
    # SUPPORT / RESISTANCE (simplified pivot points)
    # =====================
    df["pivot"] = (h + l + c) / 3
    df["r1"] = 2 * df["pivot"] - l
    df["s1"] = 2 * df["pivot"] - h
    df["r2"] = df["pivot"] + (h - l)
    df["s2"] = df["pivot"] - (h - l)
    df["dist_to_r1"] = np.where(c > 0, (df["r1"] - c) / c * 100, 0)
    df["dist_to_s1"] = np.where(c > 0, (c - df["s1"]) / c * 100, 0)

    # Multi-lookback support/resistance
    df["high_20"] = h.rolling(20).max()
    df["low_20"] = l.rolling(20).min()
    df["high_50"] = h.rolling(50).max()
    df["low_50"] = l.rolling(50).min()

    # =====================
    # CANDLE STRUCTURE
    # =====================
    body = (c - o).abs()
    range_hl = h - l
    wick_up = h - pd.concat([c, o], axis=1).max(axis=1)
    wick_down = pd.concat([c, o], axis=1).min(axis=1) - l

    df["candle_range"] = np.where(c > 0, range_hl / c * 100, 0)
    df["body_ratio"] = np.where(range_hl > 0, body / range_hl, 0.5)
    df["body_ratio"] = df["body_ratio"].fillna(0.5)
    df["upper_wick_ratio"] = np.where(range_hl > 0, wick_up / range_hl, 0)
    df["upper_wick_ratio"] = df["upper_wick_ratio"].fillna(0)
    df["lower_wick_ratio"] = np.where(range_hl > 0, wick_down / range_hl, 0)
    df["lower_wick_ratio"] = df["lower_wick_ratio"].fillna(0)
    df["is_green"] = (c > o).astype(int)
    df["consecutive_green"] = df["is_green"].rolling(3).sum()
    df["consecutive_green"] = df["consecutive_green"].fillna(0)

    # =====================
    # BREAKOUT DETECTION
    # =====================
    df["breakout_up"] = (c > df["high_20"].shift(1)).astype(int)
    df["breakout_down"] = (c < df["low_20"].shift(1)).astype(int)
    df["breakout_up_50"] = (c > df["high_50"].shift(1)).astype(int)
    df["breakout_down_50"] = (c < df["low_50"].shift(1)).astype(int)

    # =====================
    # CLEANUP
    # =====================
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna(method="ffill").fillna(0)

    return df


def get_latest_features(df):
    """Get the latest row of features (for signal generation)."""
    if df is None or df.empty:
        return None
    return df.iloc[-1]


def get_feature_names():
    """Return list of feature names used for ML."""
    return [
        "dist_ema20", "dist_ema50", "dist_ema200",
        "ma_bullish", "ma_bearish",
        "rsi", "rsi_oversold", "rsi_overbought",
        "macd_hist", "macd_cross_up", "macd_cross_down",
        "adx", "plus_di", "minus_di",
        "atr_pct",
        "bb_width", "bb_position",
        "relative_volume", "volume_trend",
        "momentum_5", "momentum_10", "momentum_20", "roc",
        "volatility_10", "volatility_20", "volatility_regime",
        "trend_strength",
        "dist_to_r1", "dist_to_s1",
        "candle_range", "body_ratio", "upper_wick_ratio",
        "lower_wick_ratio", "is_green", "consecutive_green",
        "breakout_up", "breakout_down",
    ]


# ===========================================
# PHASE 2: CROSS-TIMEFRAME ANALYSIS
# ===========================================

def extract_tf_features(df):
    """
    Extract a summary dict of key features from a timeframe's DataFrame.
    Used for cross-timeframe alignment analysis.
    """
    if df is None or len(df) < 30:
        return None

    row = df.iloc[-1]
    return {
        "trend_direction": _get_trend_direction(row),
        "trend_strength": abs(float(row.get("trend_strength", 0))),
        "rsi": float(row.get("rsi", 50)),
        "adx": float(row.get("adx", 25)),
        "macd_hist": float(row.get("macd_hist", 0)),
        "macd_positive": bool(row.get("macd_hist", 0) > 0),
        "relative_volume": float(row.get("relative_volume", 1)),
        "atr_pct": float(row.get("atr_pct", 0)),
        "bb_position": float(row.get("bb_position", 0.5)),
        "momentum_5": float(row.get("momentum_5", 0)),
        "momentum_10": float(row.get("momentum_10", 0)),
        "breakout_up": bool(row.get("breakout_up", 0)),
        "breakout_down": bool(row.get("breakout_down", 0)),
        "ma_bullish": bool(row.get("ma_bullish", 0)),
        "ma_bearish": bool(row.get("ma_bearish", 0)),
        "volatility_20": float(row.get("volatility_20", 0)),
        "adx_strong": bool(row.get("adx", 0) > 25),
    }


def _get_trend_direction(row):
    """Classify the trend direction from features."""
    ema20 = row.get("ema_20", 0)
    ema50 = row.get("ema_50", 0)
    adx = row.get("adx", 0)

    if adx < 15:
        return "NEUTRAL"

    if ema20 > ema50:
        return "BULL"
    elif ema20 < ema50:
        return "BEAR"
    return "NEUTRAL"


def analyze_timeframe_alignment(multi_tf_data, timeframes=None):
    """
    Analyze alignment between multiple timeframes.

    Returns:
        dict with alignment analysis:
        - alignment_score: 0-100
        - direction: 'LONG', 'SHORT', or 'CONFLICTED'
        - aligned_tfs: list of aligned timeframes
        - conflicting_tfs: list of conflicting timeframes
        - macro_trend: from 4h
        - primary_trend: from 1h
        - setup_quality: from 15m
        - entry_quality: from 5m
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    # Extract features for each timeframe
    tf_features = {}
    for tf in timeframes:
        if tf in multi_tf_data and multi_tf_data[tf] is not None:
            features = extract_tf_features(multi_tf_data[tf])
            if features:
                tf_features[tf] = features

    if len(tf_features) < 2:
        return {
            "alignment_score": 0,
            "direction": "CONFLICTED",
            "aligned_tfs": [],
            "conflicting_tfs": list(tf_features.keys()),
            "macro_trend": "UNKNOWN",
            "primary_trend": "UNKNOWN",
            "setup_quality": "UNKNOWN",
            "entry_quality": "UNKNOWN",
        }

    # Determine trend direction per TF
    bull_count = sum(1 for f in tf_features.values() if f["trend_direction"] == "BULL")
    bear_count = sum(1 for f in tf_features.values() if f["trend_direction"] == "BEAR")
    total = len(tf_features)

    # Determine overall alignment
    if bull_count >= total * 0.6:
        direction = "LONG"
        aligned = [tf for tf, f in tf_features.items() if f["trend_direction"] in ("BULL", "NEUTRAL")]
        conflicting = [tf for tf, f in tf_features.items() if f["trend_direction"] == "BEAR"]
    elif bear_count >= total * 0.6:
        direction = "SHORT"
        aligned = [tf for tf, f in tf_features.items() if f["trend_direction"] in ("BEAR", "NEUTRAL")]
        conflicting = [tf for tf, f in tf_features.items() if f["trend_direction"] == "BULL"]
    else:
        direction = "CONFLICTED"
        aligned = []
        conflicting = list(tf_features.keys())

    # Calculate alignment score
    if direction != "CONFLICTED":
        # Base score from majority agreement
        alignment_pct = (bull_count if direction == "LONG" else bear_count) / total
        alignment_score = alignment_pct * 60

        # Bonus for MACD agreement across timeframes
        macd_agree = sum(
            1 for f in tf_features.values()
            if (direction == "LONG" and f["macd_positive"])
            or (direction == "SHORT" and not f["macd_positive"])
        )
        macd_bonus = (macd_agree / total) * 20

        # Bonus for volume confirmation
        vol_confirm = sum(
            1 for f in tf_features.values() if f["relative_volume"] > 1.0
        )
        vol_bonus = (vol_confirm / total) * 10

        # Bonus for ADX strength across timeframes
        adx_strong = sum(1 for f in tf_features.values() if f["adx_strong"])
        adx_bonus = (adx_strong / total) * 10

        alignment_score = min(100, alignment_score + macd_bonus + vol_bonus + adx_bonus)
    else:
        alignment_score = max(0, 30 - (total - bull_count - bear_count) * 10)

    # Get specific TF features for roles
    macro_trend = tf_features.get("4h", {}).get("trend_direction", "UNKNOWN") if "4h" in tf_features else "UNKNOWN"
    primary_trend = tf_features.get("1h", {}).get("trend_direction", "UNKNOWN") if "1h" in tf_features else "UNKNOWN"
    setup_quality = tf_features.get("15m", {}).get("trend_direction", "UNKNOWN") if "15m" in tf_features else "UNKNOWN"
    entry_quality = tf_features.get("5m", {}).get("trend_direction", "UNKNOWN") if "5m" in tf_features else "UNKNOWN"

    return {
        "alignment_score": round(alignment_score, 1),
        "direction": direction,
        "aligned_tfs": aligned,
        "conflicting_tfs": conflicting,
        "macro_trend": macro_trend,
        "primary_trend": primary_trend,
        "setup_quality": setup_quality,
        "entry_quality": entry_quality,
        "tf_features": {tf: f for tf, f in tf_features.items()},
        "bull_count": bull_count,
        "bear_count": bear_count,
        "total_tfs": total,
    }


def get_timeframe_trend_summary(multi_tf_data, timeframes=None):
    """
    Simple trend summary across timeframes.
    Returns dict with trend per TF.
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    summary = {}
    for tf in timeframes:
        if tf in multi_tf_data and multi_tf_data[tf] is not None:
            features = extract_tf_features(multi_tf_data[tf])
            if features:
                summary[tf] = {
                    "direction": features["trend_direction"],
                    "strength": features["trend_strength"],
                    "adx": features["adx"],
                }
            else:
                summary[tf] = {"direction": "UNKNOWN", "strength": 0, "adx": 0}
        else:
            summary[tf] = {"direction": "NO_DATA", "strength": 0, "adx": 0}

    return summary
