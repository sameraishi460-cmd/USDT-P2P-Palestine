"""
AI Trading Engine — Market Data Engine (Phase 2 Enhanced)

Fetches and caches multi-timeframe market data from Binance.
Handles data validation, gap detection, quality filtering,
spread analysis, volume checks, and API failure recovery.
"""

import time
import threading
import requests
import pandas as pd
from datetime import datetime, timedelta


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_EXCHANGE_URL = "https://api.binance.com/api/v3/exchangeInfo"

# Interval mapping for Binance API
INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
    "6h": "6h", "8h": "8h", "12h": "12h", "1d": "1d",
}

# Minimum candles needed for reliable indicators
MIN_CANDLES = 50

# Quality thresholds
MAX_SPREAD_PCT = 0.3       # Reject if spread > 0.3%
MIN_VOLUME_24H_USD = 500_000  # Reject if 24h volume < $500K
MAX_SINGLE_CANDLE_GAP = 0.15  # Reject if single candle moves > 15%
MAX_VOLATILITY_ATR_PCT = 5.0  # Flag extreme volatility
MIN_CANDLE_COUNT_PER_TF = 30  # Minimum candles per timeframe


class TickerCache:
    """Thread-safe ticker data cache with rate limiting."""

    def __init__(self, cache_ttl=30):
        self._cache = {}
        self._lock = threading.Lock()
        self._cache_ttl = cache_ttl
        self._last_fetch = {}
        self._fetch_errors = {}  # symbol -> consecutive error count

    def get(self, symbol):
        """Get cached ticker or fetch fresh data."""
        now = time.time()
        with self._lock:
            if symbol in self._cache:
                age = now - self._last_fetch.get(symbol, 0)
                if age < self._cache_ttl:
                    return self._cache[symbol]

        # Fetch outside lock
        ticker = self._fetch_ticker(symbol)
        if ticker:
            with self._lock:
                self._cache[symbol] = ticker
                self._last_fetch[symbol] = now
                self._fetch_errors[symbol] = 0
        else:
            with self._lock:
                self._fetch_errors[symbol] = self._fetch_errors.get(symbol, 0) + 1

        return ticker

    def _fetch_ticker(self, symbol):
        """Fetch 24hr ticker from Binance."""
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

    def get_error_count(self, symbol):
        with self._lock:
            return self._fetch_errors.get(symbol, 0)

    def reset_errors(self, symbol):
        with self._lock:
            self._fetch_errors[symbol] = 0

    def invalidate(self, symbol=None):
        with self._lock:
            if symbol:
                self._cache.pop(symbol, None)
            else:
                self._cache.clear()


# Global cache instance
_ticker_cache = TickerCache(cache_ttl=30)


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
    """Fetch 24hr ticker data using cache."""
    return _ticker_cache.get(symbol)


def fetch_all_tickers(symbols):
    """Fetch tickers for all symbols in the universe (with caching)."""
    tickers = {}
    for sym in symbols:
        t = fetch_ticker(sym)
        if t:
            tickers[sym] = t
        time.sleep(0.05)  # Minimal rate limit
    return tickers


def validate_candles(df, symbol=""):
    """Validate candle data quality with enhanced checks."""
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

    # Check for extreme gaps (>MAX_SINGLE_CANDLE_GAP in one candle)
    pct_change = df["close"].pct_change().abs()
    if (pct_change > MAX_SINGLE_CANDLE_GAP).any():
        return False, f"Extreme price gap detected (>{MAX_SINGLE_CANDLE_GAP:.0%})"

    # Check minimum volume
    avg_vol = df["quote_volume"].tail(20).mean() if "quote_volume" in df.columns else 0
    if avg_vol < 100_000:
        return False, f"Low volume: ${avg_vol:,.0f}"

    # Check for stale data (candles all same price)
    if df["close"].tail(10).std() == 0:
        return False, "Stale price data"

    return True, "OK"


def analyze_spread(symbol):
    """
    Analyze bid-ask spread quality.
    Returns dict with spread info and quality flag.
    """
    ticker = fetch_ticker(symbol)
    if not ticker:
        return {"spread_pct": 999, "quality": False, "reason": "No ticker data"}

    bid = ticker.get("bid", 0)
    ask = ticker.get("ask", 0)

    if bid <= 0 or ask <= 0:
        return {"spread_pct": 999, "quality": False, "reason": "Invalid bid/ask"}

    spread = ask - bid
    spread_pct = (spread / ask) * 100

    quality = spread_pct <= MAX_SPREAD_PCT
    reason = "" if quality else f"Spread too wide: {spread_pct:.3f}%"

    return {
        "spread": spread,
        "spread_pct": round(spread_pct, 4),
        "quality": quality,
        "reason": reason,
        "bid": bid,
        "ask": ask,
    }


def analyze_volume(symbol):
    """
    Analyze 24h volume quality.
    Returns dict with volume info and quality flag.
    """
    ticker = fetch_ticker(symbol)
    if not ticker:
        return {"volume_24h": 0, "quality": False, "reason": "No ticker data"}

    vol = ticker.get("volume_24h", 0)
    quality = vol >= MIN_VOLUME_24H_USD
    reason = "" if quality else f"Low volume: ${vol:,.0f}"

    return {
        "volume_24h": vol,
        "quality": quality,
        "reason": reason,
    }


def detect_abnormal_move(df, lookback=5):
    """
    Detect abnormal recent price movements.
    Returns (is_abnormal, description).
    """
    if df is None or len(df) < lookback + 1:
        return False, ""

    recent = df.tail(lookback + 1)
    pct_changes = recent["close"].pct_change().abs()

    # Check cumulative move
    start_price = recent["close"].iloc[0]
    end_price = recent["close"].iloc[-1]
    cumulative_pct = abs(end_price - start_price) / start_price * 100

    # Check single candle extremes
    max_candle = pct_changes.max()

    if cumulative_pct > 8:
        return True, f"Abnormal cumulative move: {cumulative_pct:.1f}% in {lookback} candles"
    if max_candle > 0.05:
        return True, f"Abnormal single candle: {max_candle:.1%}"

    return False, ""


def get_multi_tf_data(symbol, timeframes=None, limit=200):
    """Fetch data for multiple timeframes with validation."""
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
    """Get current bid-ask spread (legacy compat)."""
    result = analyze_spread(symbol)
    return {"spread": result.get("spread", 0), "spread_pct": result.get("spread_pct", 999)}


def scan_symbol(symbol, timeframes=None):
    """
    Full quality scan for a single symbol.
    Returns comprehensive scan result or None if rejected.
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    scan_result = {
        "symbol": symbol,
        "timestamp": datetime.now(),
        "rejected": False,
        "reject_reason": "",
        "quality_checks": {},
    }

    # Check error backoff — skip symbols with repeated failures
    error_count = _ticker_cache.get_error_count(symbol)
    if error_count >= 3:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = f"API error backoff ({error_count} consecutive failures)"
        return scan_result

    # 1. Ticker data
    ticker = fetch_ticker(symbol)
    if not ticker:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = "No ticker data"
        return scan_result

    scan_result["ticker"] = ticker

    # 2. Volume check
    vol_result = analyze_volume(symbol)
    scan_result["quality_checks"]["volume"] = vol_result
    if not vol_result["quality"]:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = vol_result["reason"]
        return scan_result

    # 3. Spread check
    spread_result = analyze_spread(symbol)
    scan_result["quality_checks"]["spread"] = spread_result
    if not spread_result["quality"]:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = spread_result["reason"]
        return scan_result

    # 4. Fetch multi-timeframe data
    data = get_multi_tf_data(symbol, timeframes)
    scan_result["data"] = data

    # Check that we have at least 2 timeframes
    if len(data) < 2:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = f"Only {len(data)}/{len(timeframes)} timeframes available"
        return scan_result

    # 5. Check primary timeframe for abnormal moves
    primary_tf = "1h"
    if primary_tf in data:
        abnormal, reason = detect_abnormal_move(data[primary_tf])
        scan_result["quality_checks"]["abnormal"] = {"is_abnormal": abnormal, "reason": reason}
        if abnormal:
            scan_result["rejected"] = True
            scan_result["reject_reason"] = reason
            return scan_result

    # 6. Check for extreme volatility across timeframes
    for tf, df in data.items():
        if df is not None and len(df) > 14:
            recent_vol = df["close"].pct_change().tail(14).std() * 100
            if recent_vol > MAX_VOLATILITY_ATR_PCT * 14:
                scan_result["quality_checks"]["volatility"] = {
                    "tf": tf, "volatility": recent_vol, "extreme": True
                }
                scan_result["rejected"] = True
                scan_result["reject_reason"] = f"Extreme volatility on {tf}: {recent_vol:.1f}%"
                return scan_result

    # Reset error count on success
    _ticker_cache.reset_errors(symbol)

    return scan_result


def batch_scan(symbols, timeframes=None):
    """
    Scan all symbols and return results.
    Returns list of scan results (both accepted and rejected).
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    results = []
    for symbol in symbols:
        symbol = symbol.strip()
        if not symbol:
            continue
        try:
            result = scan_symbol(symbol, timeframes)
            results.append(result)
        except Exception as e:
            print(f"Batch scan error {symbol}: {e}")
            results.append({
                "symbol": symbol,
                "rejected": True,
                "reject_reason": f"Scan error: {str(e)}",
                "quality_checks": {},
            })
        time.sleep(0.1)  # Rate limit between symbols

    return results
