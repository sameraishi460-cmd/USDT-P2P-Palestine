"""
AI Trading Engine — Feature Engineering

Calculates comprehensive technical indicators for each candle.
All features are normalized for ML consumption.
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

    # Distance from MAs (normalized)
    df["dist_ema20"] = (c - df["ema_20"]) / df["ema_20"] * 100
    df["dist_ema50"] = (c - df["ema_50"]) / df["ema_50"] * 100
    df["dist_ema200"] = (c - df["ema_200"]) / df["ema_200"] * 100

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
    df["macd_cross_up"] = ((df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1))).astype(int)
    df["macd_cross_down"] = ((df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1))).astype(int)

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
    df["atr_pct"] = df["atr"] / c * 100
    df["atr"] = df["atr"].fillna(0)
    df["atr_pct"] = df["atr_pct"].fillna(0)

    # =====================
    # BOLLINGER BANDS
    # =====================
    df["bb_mid"] = c.rolling(20).mean()
    bb_std = c.rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * bb_std
    df["bb_lower"] = df["bb_mid"] - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100
    df["bb_position"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    df["bb_position"] = df["bb_position"].fillna(0.5)

    # =====================
    # VOLUME ANALYSIS
    # =====================
    df["vol_sma_20"] = v.rolling(20).mean()
    df["relative_volume"] = v / df["vol_sma_20"].replace(0, np.nan)
    df["relative_volume"] = df["relative_volume"].fillna(1)
    df["volume_trend"] = (v / df["vol_sma_20"].replace(0, np.nan)).rolling(5).mean()
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
    df["trend_strength"] = (
        df["ema_bullish_strength"] if "ema_bullish_strength" in df.columns
        else (df["ema_20"] - df["ema_50"]) / df["ema_50"] * 100
    ).fillna(0)

    # =====================
    # SUPPORT / RESISTANCE (simplified)
    # =====================
    df["pivot"] = (h + l + c) / 3
    df["r1"] = 2 * df["pivot"] - l
    df["s1"] = 2 * df["pivot"] - h
    df["dist_to_r1"] = (df["r1"] - c) / c * 100
    df["dist_to_s1"] = (c - df["s1"]) / c * 100

    # =====================
    # CANDLE STRUCTURE
    # =====================
    body = (c - df["open"]).abs()
    wick_up = h - pd.concat([c, df["open"]], axis=1).max(axis=1)
    wick_down = pd.concat([c, df["open"]], axis=1).min(axis=1) - l

    df["candle_range"] = (h - l) / c * 100
    df["body_ratio"] = body / (h - l).replace(0, np.nan)
    df["body_ratio"] = df["body_ratio"].fillna(0.5)
    df["upper_wick_ratio"] = wick_up / (h - l).replace(0, np.nan)
    df["upper_wick_ratio"] = df["upper_wick_ratio"].fillna(0)
    df["lower_wick_ratio"] = wick_down / (h - l).replace(0, np.nan)
    df["lower_wick_ratio"] = df["lower_wick_ratio"].fillna(0)
    df["is_green"] = (c > df["open"]).astype(int)
    df["consecutive_green"] = df["is_green"].rolling(3).sum()
    df["consecutive_green"] = df["consecutive_green"].fillna(0)

    # =====================
    # BREAKOUT DETECTION
    # =====================
    df["high_20"] = h.rolling(20).max()
    df["low_20"] = l.rolling(20).min()
    df["breakout_up"] = (c > df["high_20"].shift(1)).astype(int)
    df["breakout_down"] = (c < df["low_20"].shift(1)).astype(int)

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
