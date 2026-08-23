"""
AI Trading Engine — Opportunity Scoring Engine (Phase 6 Enhanced)

Generates a composite AI score (0-100) from multiple scoring components.
Uses ensemble of technical analysis, trend, momentum, volume, volatility,
regime, risk/reward, multi-TF alignment, and ML scoring.

Phase 6 changes:
- ML component = INACTIVE (score=0) when no trained model exists
- Regime-aware scoring penalties for HIGH_VOLATILITY
- Component breakdown shown separately
- "NO TRADE" is a valid, healthy decision
"""

import numpy as np
import pandas as pd
from trading.regime import (
    detect_regime, is_regime_suitable, detect_multi_tf_regime,
    HIGH_VOL, LOW_VOL, SIDEWAYS, UNCERTAIN, BULL_TREND, BEAR_TREND,
    BREAKOUT, BREAKDOWN,
)
from trading.features import analyze_timeframe_alignment


# ============================================================
# SCORING WEIGHTS
# ============================================================

WEIGHTS_WITH_ML = {
    "technical": 0.12, "trend": 0.15, "momentum": 0.12,
    "volume": 0.08, "volatility": 0.08, "regime": 0.10,
    "risk_reward": 0.12, "ml": 0.05, "tf_alignment": 0.18,
}

# When ML is inactive, redistribute its weight proportionally
WEIGHTS_NO_ML = {
    "technical": 0.133, "trend": 0.167, "momentum": 0.133,
    "volume": 0.089, "volatility": 0.089, "regime": 0.111,
    "risk_reward": 0.133, "ml": 0.0, "tf_alignment": 0.145,
}

# Regime-specific penalty multipliers (to reduce false signals)
REGIME_PENALTIES = {
    HIGH_VOL: 0.4,      # Very strict — 14% win rate historically
    UNCERTAIN: 0.3,     # Unclear conditions → reduce
    LOW_VOL: 0.85,      # Mild penalty for low volatility
    SIDEWAYS: 0.9,      # Mild penalty for range-bound
    BULL_TREND: 1.0,    # No penalty
    BEAR_TREND: 1.0,    # No penalty
    BREAKOUT: 1.05,     # Slight bonus
    BREAKDOWN: 1.05,    # Slight bonus
}


def score_opportunity(df, direction, config, multi_tf_data=None):
    """
    Score a trade opportunity.

    Args:
        df: DataFrame with all features calculated (primary TF)
        direction: 'LONG' or 'SHORT'
        config: Trading configuration dict
        multi_tf_data: Optional dict of {tf: DataFrame} for multi-TF scoring

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

    # 8. ML SCORE — Phase 6: INACTIVE when no model
    ml_prediction = _get_ml_prediction(row, direction)
    ml_active = ml_prediction.get("available", False)
    scores["ml"] = ml_prediction["ml_score"] if ml_active else 0.0

    # 9. MULTI-TF ALIGNMENT SCORE
    tf_alignment = None
    if multi_tf_data and len(multi_tf_data) >= 2:
        tf_alignment = analyze_timeframe_alignment(multi_tf_data)
        scores["tf_alignment"] = _score_tf_alignment(tf_alignment, direction)
    else:
        scores["tf_alignment"] = 30.0  # Low score when no multi-TF data

    # =====================
    # ENSEMBLE WEIGHTS
    # =====================
    weights = WEIGHTS_WITH_ML if ml_active else WEIGHTS_NO_ML

    # Calculate composite score
    ai_score = sum(scores[k] * weights[k] for k in weights if weights[k] > 0)

    # === REGIME-AWARE ADJUSTMENTS (Phase 6) ===
    regime_mult = REGIME_PENALTIES.get(regime, 1.0)
    ai_score *= regime_mult

    # Additional HIGH_VOL penalty: require stronger confirmation
    if regime == HIGH_VOL:
        # Need strong multi-TF alignment + high R:R to trade in high vol
        if tf_alignment and tf_alignment.get("alignment_score", 0) < 70:
            ai_score *= 0.5
        if rr_data["rr"] < 2.0:
            ai_score *= 0.7
        # Require higher ADX to confirm trend in high vol
        adx = row.get("adx", 25)
        if adx < 30:
            ai_score *= 0.6

    # Penalty: if regime doesn't suit the trade direction
    if not is_regime_suitable(regime, "trend_following"):
        if direction == "LONG" and regime in (BEAR_TREND, BREAKDOWN):
            ai_score *= 0.5
        elif direction == "SHORT" and regime in (BULL_TREND, BREAKOUT):
            ai_score *= 0.5

    # Penalty: conflicting timeframes
    if tf_alignment and tf_alignment["direction"] == "CONFLICTED":
        ai_score *= 0.6

    # Bonus: strong multi-TF alignment in the trade direction
    if tf_alignment and tf_alignment["direction"] == direction and tf_alignment["alignment_score"] > 70:
        ai_score *= 1.1

    ai_score = max(0, min(100, ai_score))

    # Build reasons list
    reasons = _get_reasons(row, direction, scores, regime, config)
    if tf_alignment:
        reasons.extend(_get_tf_reasons(tf_alignment, direction))

    # Quality grade
    quality = _get_quality_grade(ai_score)

    # === COMPONENT BREAKDOWN (Phase 6) ===
    component_breakdown = {
        "technical": {"score": round(scores["technical"], 1), "weight": weights["technical"]},
        "trend": {"score": round(scores["trend"], 1), "weight": weights["trend"]},
        "momentum": {"score": round(scores["momentum"], 1), "weight": weights["momentum"]},
        "volume": {"score": round(scores["volume"], 1), "weight": weights["volume"]},
        "volatility": {"score": round(scores["volatility"], 1), "weight": weights["volatility"]},
        "regime": {"score": round(scores["regime"], 1), "weight": weights["regime"]},
        "risk_reward": {"score": round(scores["risk_reward"], 1), "weight": weights["risk_reward"]},
        "ml": {"score": round(scores["ml"], 1), "weight": weights["ml"], "active": ml_active},
        "tf_alignment": {"score": round(scores["tf_alignment"], 1), "weight": weights["tf_alignment"]},
        "regime_adjustment": round(regime_mult, 2),
    }

    return {
        "ai_score": round(ai_score, 1),
        "quality": quality,
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "component_breakdown": component_breakdown,
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
        "tf_alignment": tf_alignment,
        "ml_prediction": ml_prediction,
        "reasons": reasons,
    }


# ============================================
# ML INTEGRATION (Phase 6: INACTIVE when no model)
# ============================================

_ml_predictor = None
_ml_checked = False


def _get_ml_prediction(row, direction):
    """
    Get ML prediction. Returns INACTIVE (score=0) when no model is trained.
    NEVER returns placeholder 50.0 — that was misleading.
    """
    global _ml_predictor, _ml_checked

    if not _ml_checked:
        _ml_checked = True
        try:
            from trading.ml_engine import MLPredictor
            _ml_predictor = MLPredictor()
        except Exception:
            _ml_predictor = None

    if _ml_predictor is None:
        return {
            "ml_score": 0.0,
            "ml_confidence": 0.0,
            "ml_direction": "NEUTRAL",
            "model_version": "none",
            "available": False,
            "status": "INACTIVE",
            "error": "No ML model trained",
        }

    try:
        result = _ml_predictor.predict(row)
        if not result.get("available"):
            result["ml_score"] = 0.0
            result["status"] = "INACTIVE"
        else:
            result["status"] = "ACTIVE"
        return result
    except Exception as e:
        return {
            "ml_score": 0.0, "ml_confidence": 0.0,
            "ml_direction": "NEUTRAL", "model_version": "none",
            "available": False, "status": "ERROR",
            "error": str(e),
        }


# ============================================
# INDIVIDUAL SCORERS
# ============================================

def _score_tf_alignment(tf_alignment, direction):
    """Score based on multi-timeframe alignment."""
    if not tf_alignment:
        return 30.0

    alignment_score = tf_alignment.get("alignment_score", 0)
    tf_direction = tf_alignment.get("direction", "CONFLICTED")

    if tf_direction == direction:
        return min(100, alignment_score)
    elif tf_direction == "CONFLICTED":
        return max(10, alignment_score * 0.3)
    else:
        return max(0, alignment_score * 0.2)


def _score_technical(row, direction):
    """Score based on raw technical indicators."""
    score = 50

    rsi = row.get("rsi", 50)
    macd_hist = row.get("macd_hist", 0)
    bb_pos = row.get("bb_position", 0.5)
    adx = row.get("adx", 25)

    if direction == "LONG":
        if rsi > 50 and rsi < 70:
            score += 10
        if rsi < 35:
            score += 15
        if macd_hist > 0:
            score += 10
        if bb_pos < 0.3:
            score += 10
        if adx > 25:
            score += 5
    else:
        if rsi < 50 and rsi > 30:
            score += 10
        if rsi > 65:
            score += 15
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

    if direction == "LONG":
        if ma_bull:
            score += 20
        if trend_str > 0.5:
            score += 10
        if adx > 25:
            score += 10
    else:
        if ma_bear:
            score += 20
        if trend_str > 0.5:
            score += 10
        if adx > 25:
            score += 10

    return max(0, min(100, score))


def _score_momentum(row, direction):
    """Score based on momentum indicators."""
    score = 50

    mom5 = row.get("momentum_5", 0)
    mom10 = row.get("momentum_10", 0)
    macd_hist = row.get("macd_hist", 0)
    rsi = row.get("rsi", 50)

    if direction == "LONG":
        if mom5 > 0:
            score += 10
        if mom10 > 0:
            score += 10
        if macd_hist > 0:
            score += 10
        if 40 < rsi < 65:
            score += 5
    else:
        if mom5 < 0:
            score += 10
        if mom10 < 0:
            score += 10
        if macd_hist < 0:
            score += 10
        if 35 < rsi < 60:
            score += 5

    return max(0, min(100, score))


def _score_volume(row):
    """Score based on volume analysis."""
    score = 50

    rel_vol = row.get("relative_volume", 1)
    vol_trend = row.get("volume_trend", 1)

    if rel_vol > 1.5:
        score += 20
    elif rel_vol > 1.0:
        score += 10
    elif rel_vol < 0.5:
        score -= 15

    if vol_trend > 1.2:
        score += 10
    elif vol_trend < 0.7:
        score -= 10

    return max(0, min(100, score))


def _score_volatility(row, config):
    """Score based on volatility — penalize extremes."""
    score = 50

    atr_pct = row.get("atr_pct", 0)
    bb_width = row.get("bb_width", 2)
    vol_regime = row.get("volatility_regime", 1)

    # Sweet spot: moderate volatility
    if 0.5 < atr_pct < 2.0:
        score += 15
    elif atr_pct > 3.0:
        score -= 20  # Too volatile
    elif atr_pct < 0.3:
        score -= 10  # Too quiet

    if 1.5 < bb_width < 4.0:
        score += 10
    elif bb_width > 6.0:
        score -= 15

    # Volatility regime (0=low, 1=normal, 2=high, 3=extreme)
    if vol_regime == 1:
        score += 10
    elif vol_regime >= 3:
        score -= 20

    return max(0, min(100, score))


def _score_regime(regime, regime_conf, direction):
    """Score based on market regime."""
    score = 30  # Base

    # Strong trend = good
    if regime in (BULL_TREND, BEAR_TREND):
        score += 30
        if regime_conf > 60:
            score += 15

    # Breakout/breakdown can be good
    if regime in (BREAKOUT, BREAKDOWN):
        score += 20
        if regime_conf > 50:
            score += 10

    # Sideways = neutral
    if regime == SIDEWAYS:
        score += 5

    # High vol = bad for trend following
    if regime == HIGH_VOL:
        score -= 20

    # Uncertain = bad
    if regime == UNCERTAIN:
        score -= 15

    return max(0, min(100, score))


def _estimate_rr(df, direction, config):
    """Estimate risk/reward ratio."""
    if df is None or len(df) < 14:
        return {"entry": 0, "sl": 0, "tp1": 0, "tp2": 0, "rr": 0, "score": 0}

    row = df.iloc[-1]
    price = row["close"]
    atr = row.get("atr", 0)
    if atr <= 0:
        atr = price * 0.01  # Fallback

    sl_mult = config.get("sl_atr_multiplier", 1.5)
    tp1_rr = config.get("tp1_rr", 1.5)
    tp2_rr = config.get("tp2_rr", 2.5)

    entry = price

    if direction == "LONG":
        sl = price - (atr * sl_mult)
        tp1 = price + (atr * sl_mult * tp1_rr)
        tp2 = price + (atr * sl_mult * tp2_rr)
    else:
        sl = price + (atr * sl_mult)
        tp1 = price - (atr * sl_mult * tp1_rr)
        tp2 = price - (atr * sl_mult * tp2_rr)

    risk = abs(entry - sl)
    reward = abs(tp1 - entry)
    rr = reward / risk if risk > 0 else 0

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
        "entry": round(entry, 8), "sl": round(sl, 8),
        "tp1": round(tp1, 8), "tp2": round(tp2, 8),
        "rr": round(rr, 2), "score": rr_score,
    }


def _get_quality_grade(ai_score):
    """Get quality grade from AI score."""
    if ai_score >= 90:
        return {"grade": "A+", "label": "استثنائي", "label_en": "EXCEPTIONAL"}
    elif ai_score >= 80:
        return {"grade": "A", "label": "قوي جداً", "label_en": "STRONG"}
    elif ai_score >= 70:
        return {"grade": "B+", "label": "مقبول", "label_en": "ACCEPTABLE"}
    elif ai_score >= 60:
        return {"grade": "B", "label": "ضعيف", "label_en": "WEAK"}
    elif ai_score >= 50:
        return {"grade": "C", "label": "ضعيف جداً", "label_en": "VERY WEAK"}
    else:
        return {"grade": "F", "label": "لا يتداول", "label_en": "NO TRADE"}


def _get_reasons(row, direction, scores, regime, config):
    """Generate human-readable reasons for the score."""
    reasons = []

    if scores["technical"] > 60:
        reasons.append("✓ Technical indicators aligned")
    elif scores["technical"] < 40:
        reasons.append("✗ Technical indicators conflicting")

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
        reasons.append(f"✓ Good risk/reward")
    elif scores["risk_reward"] < 40:
        reasons.append("✗ Poor risk/reward ratio")

    # Phase 6: Regime-specific warnings
    if regime == HIGH_VOL:
        reasons.append("⚠ HIGH VOLATILITY — extra confirmation required")
    if regime == UNCERTAIN:
        reasons.append("⚠ Market conditions uncertain — NO TRADE recommended")

    rsi = row.get("rsi", 50)
    if direction == "LONG" and rsi > 75:
        reasons.append("⚠ RSI overbought — caution")
    if direction == "SHORT" and rsi < 25:
        reasons.append("⚠ RSI oversold — caution")

    return reasons


def _get_tf_reasons(tf_alignment, direction):
    """Generate reasons from multi-TF alignment."""
    reasons = []

    if not tf_alignment:
        return reasons

    tf_dir = tf_alignment.get("direction", "CONFLICTED")
    aligned = tf_alignment.get("aligned_tfs", [])
    conflicting = tf_alignment.get("conflicting_tfs", [])
    score = tf_alignment.get("alignment_score", 0)

    if tf_dir == direction:
        reasons.append(f"✓ Timeframes aligned ({len(aligned)}/{tf_alignment.get('total_tfs', 0)} agree)")
        if score > 70:
            reasons.append(f"✓ Strong multi-TF consensus")
    elif tf_dir == "CONFLICTED":
        reasons.append("✗ Timeframes conflicting — NO TRADE")
    else:
        reasons.append(f"✗ {tf_dir} trend on higher timeframes")

    macro = tf_alignment.get("macro_trend", "UNKNOWN")
    primary = tf_alignment.get("primary_trend", "UNKNOWN")
    if macro != "UNKNOWN":
        reasons.append(f"  4h: {macro}")
    if primary != "UNKNOWN":
        reasons.append(f"  1h: {primary}")

    return reasons


def _empty_score(reason):
    """Return empty score with reason."""
    return {
        "ai_score": 0,
        "quality": {"grade": "F", "label": "لا يتداول", "label_en": "NO TRADE"},
        "scores": {},
        "component_breakdown": {},
        "direction": "NONE",
        "regime": "UNCERTAIN",
        "regime_confidence": 0,
        "regime_description": reason,
        "entry_price": 0, "stop_loss": 0,
        "take_profit1": 0, "take_profit2": 0,
        "rr_ratio": 0, "atr_pct": 0,
        "tf_alignment": None,
        "ml_prediction": {
            "ml_score": 0.0, "ml_confidence": 0.0,
            "ml_direction": "NEUTRAL", "model_version": "none",
            "available": False, "status": "INACTIVE", "error": reason,
        },
        "reasons": [f"✗ {reason}"],
    }
