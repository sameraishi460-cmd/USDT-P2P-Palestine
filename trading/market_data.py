"""
AI Trading Engine — Market Data Engine

Fetches and caches multi-timeframe market data from Binance.
Handles data validation, gap detection, and quality filtering.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"

# Interval mapping for Binance API
INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
    "6h": "6h", "8h": "8h", "12h": "12h", "1d": "1d",
}

# Minimum candles needed for reliable indicators
MIN_CANDLES = 50


def fetch_klines(symbol, interval="1h", limit=200, timeout=15):
    """Fetch OHLCV candles from Binance."""
    params = {
        "symbol": symbol,
        "interval": INTERVAL_MAP.get(interval, interval),
        "limit": min(limit, 1000),
    }
    try:
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()

        if not data or len(data) < MIN_CANDLES:
            return None

        rows = []
        for c in data:
            rows.append({
                "timestamp": datetime.fromtimestamp(c[0] / 1000),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "quote_volume": float(c[7]),
                "trades": int(c[8]),
            })

        df = pd.DataFrame(rows)
        df.set_index("timestamp", inplace=True)
        return df

    except Exception as e:
        print(f"MarketData error {symbol}/{interval}: {e}")
        return None


def fetch_ticker(symbol):
    """Fetch 24hr ticker data."""
    try:
        resp = requests.get(
            BINANCE_TICKER_URL,
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "symbol": symbol,
            "price": float(data.get("lastPrice", 0)),
            "volume_24h": float(data.get("quoteVolume", 0)),
            "change_pct": float(data.get("priceChangePercent", 0)),
            "high_24h": float(data.get("highPrice", 0)),
            "low_24h": float(data.get("lowPrice", 0)),
            "bid": float(data.get("bidPrice", 0)),
            "ask": float(data.get("askPrice", 0)),
        }
    except Exception:
        return None


def fetch_all_tickers(symbols):
    """Fetch tickers for all symbols in the universe."""
    tickers = {}
    for sym in symbols:
        t = fetch_ticker(sym)
        if t:
            tickers[sym] = t
        time.sleep(0.1)  # Rate limit
    return tickers


def validate_candles(df, symbol=""):
    """Validate candle data quality."""
    if df is None or df.empty:
        return False, "No data"

    if len(df) < MIN_CANDLES:
        return False, f"Insufficient candles: {len(df)}"

    # Check for NaN
    nan_pct = df[["open", "high", "low", "close", "volume"]].isna().mean().mean()
    if nan_pct > 0.05:
        return False, f"Too many NaN values: {nan_pct:.1%}"

    # Check for zero prices
    if (df["close"] <= 0).any():
        return False, "Zero or negative prices found"

    # Check for extreme gaps (>20% in one candle)
    pct_change = df["close"].pct_change().abs()
    if (pct_change > 0.20).any():
        return False, "Extreme price gap detected"

    # Check minimum volume
    avg_vol = df["quote_volume"].tail(20).mean() if "quote_volume" in df.columns else 0
    if avg_vol < 100_000:
        return False, f"Low volume: ${avg_vol:,.0f}"

    return True, "OK"


def get_multi_tf_data(symbol, timeframes=None, limit=200):
    """Fetch data for multiple timeframes."""
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    data = {}
    for tf in timeframes:
        df = fetch_klines(symbol, tf, limit)
        valid, msg = validate_candles(df, f"{symbol}/{tf}")
        if valid:
            data[tf] = df
        else:
            print(f"  {symbol}/{tf}: {msg}")

    return data


def get_spread(symbol):
    """Get current bid-ask spread."""
    ticker = fetch_ticker(symbol)
    if ticker and ticker["bid"] > 0 and ticker["ask"] > 0:
        spread = ticker["ask"] - ticker["bid"]
        spread_pct = (spread / ticker["ask"]) * 100
        return {"spread": spread, "spread_pct": spread_pct}
    return {"spread": 0, "spread_pct": 999}
