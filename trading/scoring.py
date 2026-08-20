"""
AI Trading Engine — Opportunity Scoring Engine

Generates a composite AI score (0-100) from multiple scoring components.
Uses ensemble of technical analysis, trend, momentum, volume, volatility,
regime, and risk/reward scoring.
"""

import numpy as np
import pandas as pd
from trading.regime import detect_regime, is_regime_suitable


def score_opportunity(df, direction, config):
    """
    Score a trade opportunity.

    Args:
        df: DataFrame with all features calculated
        direction: 'LONG' or 'SHORT'
        config: Trading configuration dict

    Returns:
        dict with detailed scoring breakdown
    """
    if df is None or len(df) < 30:
        return _empty_score("Insufficient data")

    row = df.iloc[-1]
    scores = {}

    # Detect regime first
    regime, regime_conf, regime_desc = detect_regime(df)

    # 1. TECHNICAL SCORE (0-100)
    scores["technical"] = _score_technical(row, direction)

    # 2. TREND SCORE (0-100)
    scores["trend"] = _score_trend(row, direction)

    # 3. MOMENTUM SCORE (0-100)
    scores["momentum"] = _score_momentum(row, direction)

    # 4. VOLUME SCORE (0-100)
    scores["volume"] = _score_volume(row)

    # 5. VOLATILITY SCORE (0-100)
    scores["volatility"] = _score_volatility(row, config)

    # 6. REGIME SCORE (0-100)
    scores["regime"] = _score_regime(regime, regime_conf, direction)

    # 7. RISK/REWARD SCORE (0-100)
    rr_data = _estimate_rr(df, direction, config)
    scores["risk_reward"] = rr_data["score"]

    # 8. ML SCORE (placeholder — set to 50 until ML is trained)
    scores["ml"] = 50.0

    # =====================
    # ENSEMBLE WEIGHTS
    # =====================
    weights = {
        "technical": 0.15,
        "trend": 0.20,
        "momentum": 0.15,
        "volume": 0.10,
        "volatility": 0.10,
        "regime": 0.10,
        "risk_reward": 0.15,
        "ml": 0.05,
    }

    # Calculate composite score
    ai_score = sum(scores[k] * weights[k] for k in weights)

    # Penalty: if regime doesn't suit the trade
    if not is_regime_suitable(regime, "trend_following"):
        if direction == "LONG" and regime == "BEAR_TREND":
            ai_score *= 0.5
        elif direction == "SHORT" and regime == "BULL_TREND":
            ai_score *= 0.5

    ai_score = max(0, min(100, ai_score))

    return {
        "ai_score": round(ai_score, 1),
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "direction": direction,
        "regime": regime,
        "regime_confidence": regime_conf,
        "regime_description": regime_desc,
        "entry_price": rr_data["entry"],
        "stop_loss": rr_data["sl"],
        "take_profit1": rr_data["tp1"],
        "take_profit2": rr_data["tp2"],
        "rr_ratio": rr_data["rr"],
        "atr_pct": row.get("atr_pct", 0),
        "reasons": _get_reasons(row, direction, scores, regime),
    }


def _score_technical(row, direction):
    """Score based on raw technical indicators."""
    score = 50  # Neutral

    rsi = row.get("rsi", 50)
    macd_hist = row.get("macd_hist", 0)
    bb_pos = row.get("bb_position", 0.5)
    adx = row.get("adx", 25)

    if direction == "LONG":
        if rsi > 50 and rsi < 70:
            score += 10
        if rsi < 35:
            score += 15  # Oversold bounce
        if macd_hist > 0:
            score += 10
        if bb_pos < 0.3:
            score += 10  # Near lower band
        if adx > 25:
            score += 5
    else:  # SHORT
        if rsi < 50 and rsi > 30:
            score += 10
        if rsi > 65:
            score += 15  # Overbought reversal
        if macd_hist < 0:
            score += 10
        if bb_pos > 0.7:
            score += 10
        if adx > 25:
            score += 5

    return max(0, min(100, score))


def _score_trend(row, direction):
    """Score based on trend alignment."""
    score = 50

    ma_bull = row.get("ma_bullish", 0)
    ma_bear = row.get("ma_bearish", 0)
    trend_str = abs(row.get("trend_strength", 0))
    adx = row.get("adx", 25)
    plus_di = row.get("plus_di", 25)
    minus_di = row.get("minus_di", 25)

    if direction == "LONG":
        if ma_bull:
            score += 20
        if plus_di > minus_di:
            score += 15
        if trend_str > 1:
            score += 10
        if adx > 25:
            score += 5
    else:
        if ma_bear:
            score += 20
        if minus_di > plus_di:
            score += 15
        if trend_str > 1:
            score += 10
        if adx > 25:
            score += 5

    # Penalize counter-trend
    if direction == "LONG" and ma_bear:
        score -= 20
    if direction == "SHORT" and ma_bull:
        score -= 20

    return max(0, min(100, score))


def _score_momentum(row, direction):
    """Score based on momentum indicators."""
    score = 50

    mom5 = row.get("momentum_5", 0)
    mom10 = row.get("momentum_10", 0)
    mom20 = row.get("momentum_20", 0)
    macd_cross_up = row.get("macd_cross_up", 0)
    macd_cross_down = row.get("macd_cross_down", 0)
    consec_green = row.get("consecutive_green", 0)

    if direction == "LONG":
        if mom5 > 0:
            score += 10
        if mom10 > 0:
            score += 10
        if macd_cross_up:
            score += 15
        if consec_green >= 2:
            score += 5
        # Penalize chasing
        if mom5 > 5:
            score -= 10
    else:
        if mom5 < 0:
            score += 10
        if mom10 < 0:
            score += 10
        if macd_cross_down:
            score += 15
        if consec_green == 0:
            score += 5
        if mom5 < -5:
            score -= 10

    return max(0, min(100, score))


def _score_volume(row):
    """Score based on volume confirmation."""
    score = 50

    rel_vol = row.get("relative_volume", 1)
    vol_trend = row.get("volume_trend", 1)

    if rel_vol > 1.5:
        score += 20
    elif rel_vol > 1.2:
        score += 10
    elif rel_vol < 0.5:
        score -= 15  # Low volume warning

    if vol_trend > 1.2:
        score += 10
    elif vol_trend < 0.7:
        score -= 10

    return max(0, min(100, score))


def _score_volatility(row, config):
    """Score based on volatility conditions."""
    score = 50

    atr_pct = row.get("atr_pct", 0)
    bb_width = row.get("bb_width", 2)

    # Optimal volatility range
    if 0.5 < atr_pct < 2.0:
        score += 20
    elif atr_pct < 0.3:
        score -= 10  # Too quiet
    elif atr_pct > 3.0:
        score -= 15  # Too volatile

    if 1.5 < bb_width < 4:
        score += 10

    return max(0, min(100, score))


def _score_regime(regime, regime_conf, direction):
    """Score based on market regime."""
    from trading.regime import (
        BULL_TREND, BEAR_TREND, SIDEWAYS, HIGH_VOL,
        LOW_VOL, BREAKOUT, BREAKDOWN, UNCERTAIN
    )

    regime_scores = {
        BULL_TREND: {"LONG": 85, "SHORT": 20},
        BEAR_TREND: {"LONG": 20, "SHORT": 85},
        SIDEWAYS: {"LONG": 40, "SHORT": 40},
        HIGH_VOL: {"LONG": 35, "SHORT": 35},
        LOW_VOL: {"LONG": 45, "SHORT": 45},
        BREAKOUT: {"LONG": 75, "SHORT": 75},
        BREAKDOWN: {"LONG": 30, "SHORT": 70},
        UNCERTAIN: {"LONG": 15, "SHORT": 15},
    }

    base = regime_scores.get(regime, {}).get(direction, 30)

    # Adjust by confidence
    conf_factor = min(regime_conf / 100, 1.0)
    return base * conf_factor


def _estimate_rr(df, direction, config):
    """Estimate entry, SL, TP and R:R ratio."""
    row = df.iloc[-1]
    atr = row.get("atr", 0)
    price = row.get("close", 0)

    if price <= 0 or atr <= 0:
        atr = price * 0.01  # Fallback: 1% of price
        if atr <= 0:
            return {"entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "rr": 0, "score": 0}

    sl_mult = config.get("sl_atr_multiplier", 1.5)
    tp1_rr = config.get("tp1_rr", 1.5)
    tp2_rr = config.get("tp2_rr", 2.5)

    if direction == "LONG":
        entry = price
        sl = price - (atr * sl_mult)
        tp1 = price + (atr * sl_mult * tp1_rr)
        tp2 = price + (atr * sl_mult * tp2_rr)
    else:
        entry = price
        sl = price + (atr * sl_mult)
        tp1 = price - (atr * sl_mult * tp1_rr)
        tp2 = price - (atr * sl_mult * tp2_rr)

    risk = abs(entry - sl)
    reward = abs(tp1 - entry)
    rr = reward / risk if risk > 0 else 0

    # Score the R:R
    if rr >= 3:
        rr_score = 95
    elif rr >= 2.5:
        rr_score = 85
    elif rr >= 2:
        rr_score = 75
    elif rr >= 1.5:
        rr_score = 60
    elif rr >= 1:
        rr_score = 40
    else:
        rr_score = 20

    return {
        "entry": round(entry, 8),
        "sl": round(sl, 8),
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        "rr": round(rr, 2),
        "score": rr_score,
    }


def _get_reasons(row, direction, scores, regime):
    """Generate human-readable reasons for the score."""
    reasons = []

    if scores["trend"] > 60:
        reasons.append("✓ Multi-timeframe trend alignment")
    elif scores["trend"] < 40:
        reasons.append("✗ Weak trend alignment")

    if scores["momentum"] > 60:
        reasons.append("✓ Strong momentum confirmation")
    elif scores["momentum"] < 40:
        reasons.append("✗ Weak momentum")

    if scores["volume"] > 60:
        reasons.append("✓ Volume confirms move")
    elif scores["volume"] < 40:
        reasons.append("✗ Low volume warning")

    if scores["regime"] > 60:
        reasons.append(f"✓ Favorable market regime ({regime})")
    elif scores["regime"] < 40:
        reasons.append(f"✗ Unfavorable regime ({regime})")

    if scores["risk_reward"] > 60:
        reasons.append(f"✓ Good risk/reward ({scores.get('risk_reward', 0):.1f})")
    elif scores["risk_reward"] < 40:
        reasons.append("✗ Poor risk/reward ratio")

    if scores["technical"] > 60:
        reasons.append("✓ Technical indicators aligned")
    elif scores["technical"] < 40:
        reasons.append("✗ Technical indicators conflicting")

    rsi = row.get("rsi", 50)
    if direction == "LONG" and rsi > 75:
        reasons.append("⚠ RSI overbought — caution")
    if direction == "SHORT" and rsi < 25:
        reasons.append("⚠ RSI oversold — caution")

    return reasons


def _empty_score(reason):
    """Return empty score with reason."""
    return {
        "ai_score": 0,
        "scores": {},
        "direction": "NONE",
        "regime": "UNCERTAIN",
        "regime_confidence": 0,
        "regime_description": reason,
        "entry_price": 0,
        "stop_loss": 0,
        "take_profit1": 0,
        "take_profit2": 0,
        "rr_ratio": 0,
        "atr_pct": 0,
        "reasons": [f"✗ {reason}"],
    }
