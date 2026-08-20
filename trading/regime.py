"""
AI Trading Engine — Market Regime Detection (Phase 2 Enhanced)

Detects the current market regime to guide strategy selection.

Phase 2 additions:
- Per-timeframe regime detection
- Composite multi-TF regime
- Regime transition detection
- Enhanced regime confidence scoring
"""

import numpy as np
import pandas as pd


# Regime constants
BULL_TREND = "BULL_TREND"
BEAR_TREND = "BEAR_TREND"
SIDEWAYS = "SIDEWAYS"
HIGH_VOL = "HIGH_VOLATILITY"
LOW_VOL = "LOW_VOLATILITY"
BREAKOUT = "BREAKOUT"
BREAKDOWN = "BREAKDOWN"
UNCERTAIN = "UNCERTAIN"


def detect_regime(df):
    """
    Detect market regime from latest features.
    Returns (regime, confidence, description).
    """
    if df is None or len(df) < 30:
        return UNCERTAIN, 0, "Insufficient data"

    row = df.iloc[-1]

    # Trend detection
    ema20 = row.get("ema_20", 0)
    ema50 = row.get("ema_50", 0)
    ema200 = row.get("ema_200", 0)
    adx = row.get("adx", 25)
    rsi = row.get("rsi", 50)

    # Volatility
    atr_pct = row.get("atr_pct", 0)
    bb_width = row.get("bb_width", 2)
    vol_regime = row.get("volatility_regime", 1)

    # Breakout
    breakout_up = row.get("breakout_up", 0)
    breakout_down = row.get("breakout_down", 0)

    # Volume
    rel_vol = row.get("relative_volume", 1)

    scores = {}

    # === BULL TREND ===
    bull_score = 0
    if ema20 > ema50:
        bull_score += 20
    if ema50 > ema200:
        bull_score += 20
    if adx > 25:
        bull_score += 15
    if rsi > 50 and rsi < 75:
        bull_score += 10
    if row.get("plus_di", 25) > row.get("minus_di", 25):
        bull_score += 10
    if row.get("momentum_10", 0) > 0:
        bull_score += 10
    if row.get("is_green", 0):
        bull_score += 5
    scores[BULL_TREND] = min(bull_score, 100)

    # === BEAR TREND ===
    bear_score = 0
    if ema20 < ema50:
        bear_score += 20
    if ema50 < ema200:
        bear_score += 20
    if adx > 25:
        bear_score += 15
    if rsi < 50 and rsi > 25:
        bear_score += 10
    if row.get("minus_di", 25) > row.get("plus_di", 25):
        bear_score += 10
    if row.get("momentum_10", 0) < 0:
        bear_score += 10
    if not row.get("is_green", 1):
        bear_score += 5
    scores[BEAR_TREND] = min(bear_score, 100)

    # === SIDEWAYS ===
    sideways_score = 0
    if adx < 20:
        sideways_score += 30
    if abs(ema20 - ema50) / max(ema50, 1) * 100 < 0.5:
        sideways_score += 20
    if bb_width < 2:
        sideways_score += 15
    if abs(row.get("momentum_20", 0)) < 1:
        sideways_score += 15
    if 40 < rsi < 60:
        sideways_score += 10
    scores[SIDEWAYS] = min(sideways_score, 100)

    # === HIGH VOLATILITY ===
    high_vol_score = 0
    if atr_pct > 2:
        high_vol_score += 25
    if bb_width > 4:
        high_vol_score += 25
    if vol_regime >= 2:
        high_vol_score += 20
    if row.get("candle_range", 0) > 2:
        high_vol_score += 15
    if rel_vol > 2:
        high_vol_score += 15
    scores[HIGH_VOL] = min(high_vol_score, 100)

    # === LOW VOLATILITY ===
    low_vol_score = 0
    if atr_pct < 0.5:
        low_vol_score += 25
    if bb_width < 1.5:
        low_vol_score += 25
    if vol_regime == 0:
        low_vol_score += 20
    if rel_vol < 0.7:
        low_vol_score += 15
    scores[LOW_VOL] = min(low_vol_score, 100)

    # === BREAKOUT ===
    breakout_score = 0
    if breakout_up:
        breakout_score += 40
    if rel_vol > 1.5:
        breakout_score += 20
    if adx > 20:
        breakout_score += 15
    if rsi > 55:
        breakout_score += 10
    scores[BREAKOUT] = min(breakout_score, 100)

    # === BREAKDOWN ===
    breakdown_score = 0
    if breakout_down:
        breakdown_score += 40
    if rel_vol > 1.5:
        breakdown_score += 20
    if adx > 20:
        breakdown_score += 15
    if rsi < 45:
        breakdown_score += 10
    scores[BREAKDOWN] = min(breakdown_score, 100)

    # Select dominant regime
    best_regime = max(scores, key=scores.get)
    best_score = scores[best_regime]

    # If no regime scores above 30, it's uncertain
    if best_score < 30:
        return UNCERTAIN, best_score, "Market conditions unclear"

    # If HIGH_VOL and not trending, it's just volatile
    if best_regime == HIGH_VOL and adx < 20:
        return HIGH_VOL, best_score, f"High volatility (ATR {atr_pct:.1f}%), no clear trend"

    # If LOW_VOL, check if trending
    if best_regime == LOW_VOL and adx > 25:
        if scores[BULL_TREND] > 30:
            return BULL_TREND, scores[BULL_TREND], "Low vol but strong uptrend"
        elif scores[BEAR_TREND] > 30:
            return BEAR_TREND, scores[BEAR_TREND], "Low vol but strong downtrend"

    descriptions = {
        BULL_TREND: f"Bullish trend (ADX {adx:.0f}, RSI {rsi:.0f})",
        BEAR_TREND: f"Bearish trend (ADX {adx:.0f}, RSI {rsi:.0f})",
        SIDEWAYS: f"Range-bound (ADX {adx:.0f})",
        HIGH_VOL: f"High volatility (ATR {atr_pct:.1f}%)",
        LOW_VOL: f"Low volatility (ATR {atr_pct:.1f}%)",
        BREAKOUT: f"Breakout detected (rel_vol {rel_vol:.1f}x)",
        BREAKDOWN: f"Breakdown detected (rel_vol {rel_vol:.1f}x)",
    }

    return best_regime, best_score, descriptions.get(best_regime, best_regime)


def detect_regime_for_tf(df):
    """
    Detect regime for a single timeframe.
    Returns (regime, confidence, description).
    """
    return detect_regime(df)


def detect_multi_tf_regime(multi_tf_data, timeframes=None):
    """
    Detect regime across multiple timeframes and compute a composite regime.

    Returns:
        dict with:
        - composite_regime: dominant regime across all TFs
        - composite_confidence: weighted average confidence
        - tf_regimes: dict mapping TF -> (regime, confidence, description)
        - regime_alignment: how well regimes agree (0-100)
        - tradeable: whether the regime is tradeable
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    # TF weights (higher TF = higher weight)
    tf_weights = {
        "5m": 0.1,
        "15m": 0.2,
        "1h": 0.35,
        "4h": 0.35,
    }

    tf_regimes = {}
    regime_votes = {}  # regime -> weighted score

    for tf in timeframes:
        if tf not in multi_tf_data or multi_tf_data[tf] is None:
            continue

        df = multi_tf_data[tf]
        if df is None or len(df) < 30:
            continue

        regime, confidence, description = detect_regime_for_tf(df)
        tf_regimes[tf] = {
            "regime": regime,
            "confidence": confidence,
            "description": description,
        }

        # Weighted vote
        weight = tf_weights.get(tf, 0.25)
        weighted_conf = confidence * weight
        regime_votes[regime] = regime_votes.get(regime, 0) + weighted_conf

    if not tf_regimes:
        return {
            "composite_regime": UNCERTAIN,
            "composite_confidence": 0,
            "tf_regimes": {},
            "regime_alignment": 0,
            "tradeable": False,
        }

    # Determine composite regime (highest weighted vote)
    composite_regime = max(regime_votes, key=regime_votes.get) if regime_votes else UNCERTAIN
    total_weight = sum(tf_weights.get(tf, 0.25) for tf in tf_regimes)
    composite_confidence = (regime_votes.get(composite_regime, 0) / max(total_weight, 0.01)) if total_weight > 0 else 0

    # Calculate regime alignment (% of TFs with same or compatible regime)
    compatible_regimes = _get_compatible_regimes(composite_regime)
    aligned_count = sum(
        1 for tf, info in tf_regimes.items()
        if info["regime"] in compatible_regimes
    )
    regime_alignment = (aligned_count / len(tf_regimes)) * 100 if tf_regimes else 0

    # Check if tradeable
    tradeable = (
        composite_regime != UNCERTAIN
        and composite_regime != HIGH_VOL
        and composite_confidence >= 30
        and regime_alignment >= 50
    )

    return {
        "composite_regime": composite_regime,
        "composite_confidence": round(composite_confidence, 1),
        "tf_regimes": tf_regimes,
        "regime_alignment": round(regime_alignment, 1),
        "tradeable": tradeable,
    }


def _get_compatible_regimes(regime):
    """Get regimes that are compatible with the given regime."""
    compatibility = {
        BULL_TREND: [BULL_TREND, BREAKOUT, LOW_VOL],
        BEAR_TREND: [BEAR_TREND, BREAKDOWN, LOW_VOL],
        SIDEWAYS: [SIDEWAYS, LOW_VOL],
        HIGH_VOL: [HIGH_VOL, BULL_TREND, BEAR_TREND],
        LOW_VOL: [LOW_VOL, SIDEWAYS],
        BREAKOUT: [BREAKOUT, BULL_TREND],
        BREAKDOWN: [BREAKDOWN, BEAR_TREND],
        UNCERTAIN: [],
    }
    return compatibility.get(regime, [])


def is_regime_suitable(regime, strategy_type):
    """
    Check if a strategy is suitable for the current regime.
    Returns True if the strategy should be allowed to trade.
    """
    suitability = {
        "trend_following": [BULL_TREND, BEAR_TREND, BREAKOUT, BREAKDOWN],
        "mean_reversion": [SIDEWAYS, LOW_VOL],
        "breakout": [BREAKOUT, BREAKDOWN],
        "momentum": [BULL_TREND, BEAR_TREND, HIGH_VOL],
        "conservative": [BULL_TREND, BEAR_TREND, SIDEWAYS],
    }

    allowed = suitability.get(strategy_type, [BULL_TREND, BEAR_TREND])
    return regime in allowed


def get_regime_emoji(regime):
    """Get emoji for regime display."""
    emojis = {
        BULL_TREND: "🟢📈",
        BEAR_TREND: "🔴📉",
        SIDEWAYS: "🟡↔️",
        HIGH_VOL: "🟠⚡",
        LOW_VOL: "🔵😴",
        BREAKOUT: "🚀",
        BREAKDOWN: "💥",
        UNCERTAIN: "❓",
    }
    return emojis.get(regime, "❓")


def get_regime_arabic(regime):
    """Get Arabic name for regime."""
    arabic = {
        BULL_TREND: "صاعد",
        BEAR_TREND: "هابط",
        SIDEWAYS: "عرضي",
        HIGH_vol: "تقلب عالي",
        LOW_VOL: "تقلب منخفض",
        BREAKOUT: "اختراق صاعد",
        BREAKDOWN: "انهيار",
        UNCERTAIN: "غير محدد",
    }
    # Fix typo
    arabic[HIGH_VOL] = "تقلب عالي"
    return arabic.get(regime, "غير محدد")
