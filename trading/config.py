"""
AI Trading Engine — Configuration
All trading parameters in one place. Admin-configurable via database.
"""

DEFAULT_CONFIG = {
    # === TRADING UNIVERSE ===
    "symbols": "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT",

    # === TIMEFRAMES ===
    "timeframes": "5m,15m,1h,4h",
    "macro_tf": "4h",
    "primary_tf": "1h",
    "setup_tf": "15m",
    "entry_tf": "5m",

    # === CAPITAL ===
    "starting_capital": 10000.0,
    "max_positions": 5,

    # === RISK ENGINE ===
    "risk_per_trade_pct": 0.5,
    "max_risk_per_trade_pct": 1.0,
    "max_portfolio_risk_pct": 2.0,
    "daily_loss_limit_pct": 2.0,
    "max_drawdown_warning_pct": 5.0,
    "emergency_shutdown_pct": 10.0,
    "max_consecutive_losses": 3,

    # === ENTRY REQUIREMENTS ===
    "min_ai_score": 70,
    "min_rr_ratio": 1.5,
    "max_correlated_exposure_pct": 60.0,
    "min_volume_usd": 1_000_000,

    # === STOP LOSS ===
    "sl_atr_multiplier": 1.5,
    "sl_min_pct": 0.3,
    "sl_max_pct": 3.0,

    # === TAKE PROFIT ===
    "tp1_rr": 1.5,
    "tp2_rr": 2.5,
    "tp1_close_pct": 0.3,
    "tp2_close_pct": 0.4,
    "trailing_stop_activation_rr": 1.0,
    "trailing_stop_distance_pct": 0.5,

    # === POSITION MANAGEMENT ===
    "max_holding_periods": 48,  # in candles of entry TF
    "break_even_activation_pct": 0.3,

    # === EXECUTION ===
    "slippage_bps": 5,  # basis points
    "commission_bps": 10,  # basis points
    "spread_bps": 3,

    # === ML ===
    "ml_threshold": 0.55,
    "ml_retrain_interval_hours": 24,
    "ml_training_window_days": 90,
    "ml_min_samples": 200,

    # === SAFE MODE ===
    "safe_mode_win_rate_floor": 30.0,
    "safe_mode_pf_floor": 0.8,
    "safe_mode_max_dd_pct": 8.0,

    # === PHASE 6: REGIME-SPECIFIC THRESHOLDS ===
    "high_vol_min_ai_score": 85,
    "high_vol_min_rr": 2.5,
    "high_vol_max_positions": 2,
    "low_vol_min_ai_score": 75,
    "sideways_min_ai_score": 75,

    # === PHASE 6: SYMBOL-SPECIFIC OVERRIDES ===
    "symbol_overrides": {
        "ETHUSDT": {"min_ai_score": 65, "min_volume_usd": 500000},
        "SOLUSDT": {"min_ai_score": 65, "min_volume_usd": 500000},
    },

    # === PHASE 6: DATA SOURCE ===
    "data_source": "auto",
    "data_is_real": False,

    # === MODE ===
    "trading_mode": "PAPER",  # PAPER or REAL
    "bot_status": "STOPPED",  # STOPPED, RUNNING, PAUSED, SAFE_MODE, ERROR

    # === SCANNING ===
    "scan_interval_seconds": 60,
    "candle_limit": 200,
}


def get_trading_config(con):
    """Load trading config from database, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    try:
        rows = con.execute(
            "SELECT key, value FROM trading_settings"
        ).fetchall()
        for row in rows:
            key = row["key"]
            if key in config:
                # Type-cast to match default
                default_val = config[key]
                if isinstance(default_val, float):
                    config[key] = float(row["value"])
                elif isinstance(default_val, int):
                    config[key] = int(row["value"])
                else:
                    config[key] = row["value"]
    except Exception:
        pass
    return config


def set_trading_config(con, key, value):
    """Set a trading config value."""
    con.execute(
        "INSERT OR REPLACE INTO trading_settings (key, value, updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (key, str(value)),
    )
    con.commit()


def init_trading_settings(con):
    """Initialize default trading settings if not present."""
    existing = con.execute("SELECT COUNT(*) as cnt FROM trading_settings").fetchone()["cnt"]
    if existing == 0:
        for key, value in DEFAULT_CONFIG.items():
            con.execute(
                "INSERT INTO trading_settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
        con.commit()
