"""
AI Trading Engine — Market Data Engine (Phase 6 Enhanced)

Multi-source market data with:
- Primary: Binance API
- Fallback: CoinGecko API
- Data integrity validation
- Missing/duplicate candle detection
- Timestamp validation
- Source tracking
- Cache with TTL
- Rate limiting
"""

import time
import threading
import hashlib
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ============================================================
# API ENDPOINTS
# ============================================================

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_EXCHANGE_URL = "https://api.binance.com/api/v3/exchangeInfo"

# CoinGecko (free tier, no key needed)
COINGECKO_OHLC_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
COINGECKO_TICKER_URL = "https://api.coingecko.com/api/v3/simple/price"

# Symbol mapping: Binance symbol → CoinGecko coin ID
SYMBOL_TO_COINGECKO = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana", "XRPUSDT": "ripple", "DOGEUSDT": "dogecoin",
    "ADAUSDT": "cardano", "AVAXUSDT": "avalanche-2", "LINKUSDT": "chainlink",
}

# Base prices for synthetic data fallback only
BASE_PRICES = {
    "BTCUSDT": 65000, "ETHUSDT": 3200, "BNBUSDT": 580,
    "SOLUSDT": 150, "XRPUSDT": 0.55, "DOGEUSDT": 0.12,
    "ADAUSDT": 0.45, "AVAXUSDT": 35, "LINKUSDT": 14,
}

# Interval mapping
INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
    "30m": "30m", "1h": "1h", "2h": "2h", "4h": "4h",
    "6h": "6h", "8h": "8h", "12h": "12h", "1d": "1d",
}

# Quality thresholds
MIN_CANDLES = 50
MAX_SPREAD_PCT = 0.3
MIN_VOLUME_24H_USD = 500_000
MAX_SINGLE_CANDLE_GAP = 0.15
MAX_VOLATILITY_ATR_PCT = 5.0
MIN_CANDLE_COUNT_PER_TF = 30

# ============================================================
# DATA SOURCE TRACKING
# ============================================================

class DataSourceTracker:
    """Track which data source was used and data quality metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sources = {}  # symbol_tf -> {source, last_fetch, quality, errors}
        self._global_stats = {
            "binance_hits": 0, "binance_misses": 0,
            "coingecko_hits": 0, "coingecko_misses": 0,
            "synthetic_fallbacks": 0, "integrity_failures": 0,
        }

    def record_fetch(self, symbol, tf, source, quality="OK", candles=0):
        with self._lock:
            key = f"{symbol}_{tf}"
            self._sources[key] = {
                "source": source,
                "last_fetch": datetime.now().isoformat(),
                "quality": quality,
                "candles": candles,
            }
            if source == "binance":
                self._global_stats["binance_hits"] += 1
            elif source == "coingecko":
                self._global_stats["coingecko_hits"] += 1
            elif source == "synthetic":
                self._global_stats["synthetic_fallbacks"] += 1

    def record_failure(self, symbol, tf, source):
        with self._lock:
            key = f"{symbol}_{tf}"
            existing = self._sources.get(key, {})
            existing["source"] = source
            existing["quality"] = "FAILED"
            existing["last_fetch"] = datetime.now().isoformat()
            self._sources[key] = existing
            if source == "binance":
                self._global_stats["binance_misses"] += 1
            elif source == "coingecko":
                self._global_stats["coingecko_misses"] += 1

    def record_integrity_failure(self, symbol, tf, reason):
        with self._lock:
            self._global_stats["integrity_failures"] += 1

    def get_stats(self):
        with self._lock:
            return {
                "sources": dict(self._sources),
                "global": dict(self._global_stats),
            }

    def get_source(self, symbol, tf):
        with self._lock:
            key = f"{symbol}_{tf}"
            return self._sources.get(key, {}).get("source", "unknown")

    def is_real_data(self, symbol=None, tf=None):
        """Check if data is from a real API (not synthetic)."""
        if symbol and tf:
            src = self.get_source(symbol, tf)
            return src in ("binance", "coingecko")
        with self._lock:
            return (self._global_stats["synthetic_fallbacks"] == 0 and
                    self._global_stats["binance_hits"] + self._global_stats["coingecko_hits"] > 0)


# Global tracker
data_tracker = DataSourceTracker()


# ============================================================
# TICKER CACHE
# ============================================================

class TickerCache:
    """Thread-safe ticker data cache with rate limiting."""

    def __init__(self, cache_ttl=30):
        self._cache = {}
        self._lock = threading.Lock()
        self._cache_ttl = cache_ttl
        self._last_fetch = {}
        self._fetch_errors = {}

    def get(self, symbol):
        now = time.time()
        with self._lock:
            if symbol in self._cache:
                age = now - self._last_fetch.get(symbol, 0)
                if age < self._cache_ttl:
                    return self._cache[symbol]

        ticker = self._fetch_ticker_binance(symbol)
        if not ticker:
            ticker = self._fetch_ticker_coingecko(symbol)

        if ticker:
            with self._lock:
                self._cache[symbol] = ticker
                self._last_fetch[symbol] = now
                self._fetch_errors[symbol] = 0
        else:
            with self._lock:
                self._fetch_errors[symbol] = self._fetch_errors.get(symbol, 0) + 1

        return ticker

    def _fetch_ticker_binance(self, symbol):
        try:
            resp = requests.get(BINANCE_TICKER_URL, params={"symbol": symbol}, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            return {
                "symbol": symbol, "source": "binance",
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

    def _fetch_ticker_coingecko(self, symbol):
        coin_id = SYMBOL_TO_COINGECKO.get(symbol)
        if not coin_id:
            return None
        try:
            resp = requests.get(
                COINGECKO_TICKER_URL,
                params={"ids": coin_id, "vs_currencies": "usd",
                         "include_24hr_vol": "true", "include_24hr_change": "true"},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json().get(coin_id, {})
            price = data.get("usd", 0)
            vol = data.get("usd_24h_vol", 0)
            change = data.get("usd_24h_change", 0)
            if price <= 0:
                return None
            return {
                "symbol": symbol, "source": "coingecko",
                "price": float(price),
                "volume_24h": float(vol),
                "change_pct": float(change),
                "high_24h": 0, "low_24h": 0,
                "bid": 0, "ask": 0,
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


_ticker_cache = TickerCache(cache_ttl=30)


# ============================================================
# KLINE FETCHING (MULTI-SOURCE)
# ============================================================

def _generate_synthetic_klines(symbol, interval="1h", limit=1000):
    """Generate realistic synthetic OHLCV data for backtesting when API is unavailable.
    This is ONLY for backtesting — clearly marked as SYNTHETIC."""
    base_price = BASE_PRICES.get(symbol, 100)
    vol_map = {"5m": 0.002, "15m": 0.004, "1h": 0.012, "4h": 0.025}
    vol = vol_map.get(interval, 0.012)
    vol_base_map = {"BTCUSDT": 5e9, "ETHUSDT": 2e9, "BNBUSDT": 500e6,
                    "SOLUSDT": 300e6, "XRPUSDT": 800e6}
    quote_vol_base = vol_base_map.get(symbol, 100e6)

    np.random.seed(hash(symbol + interval) % (2**31))
    interval_minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
    minutes = interval_minutes.get(interval, 60)

    timestamps = []
    now = datetime.now()
    for i in range(limit, 0, -1):
        ts = now - timedelta(minutes=minutes * i)
        timestamps.append(ts)

    returns = np.random.normal(0, vol, limit)
    trend_changes = np.random.choice([0, 1], size=limit, p=[0.97, 0.03])
    trend = 0
    for i in range(limit):
        if trend_changes[i]:
            trend = np.random.normal(0, vol * 2)
        returns[i] += trend * 0.1

    log_prices = np.log(base_price) + np.cumsum(returns)
    closes = np.exp(log_prices)

    rows = []
    for i in range(limit):
        c = closes[i]
        intra_vol = vol * 0.6
        h = c * (1 + abs(np.random.normal(0, intra_vol)))
        l = c * (1 - abs(np.random.normal(0, intra_vol)))
        o = closes[i-1] if i > 0 else c * (1 + np.random.normal(0, intra_vol * 0.3))
        h = max(h, o, c)
        l = min(l, o, c)
        vol_mult = np.random.lognormal(0, 0.5)
        volume = quote_vol_base * vol_mult / base_price
        quote_volume = quote_vol_base * vol_mult
        trades = int(np.random.lognormal(6, 1))
        rows.append({
            "timestamp": timestamps[i], "open": round(o, 8), "high": round(h, 8),
            "low": round(l, 8), "close": round(c, 8),
            "volume": round(volume, 4), "quote_volume": round(quote_volume, 2),
            "trades": trades,
        })

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df, "synthetic"


def _fetch_binance_klines(symbol, interval="1h", limit=200, timeout=15):
    """Fetch from Binance API."""
    params = {
        "symbol": symbol,
        "interval": INTERVAL_MAP.get(interval, interval),
        "limit": min(limit, 1000),
    }
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    if not data or len(data) < MIN_CANDLES:
        return None

    rows = []
    for c in data:
        rows.append({
            "timestamp": datetime.fromtimestamp(c[0] / 1000),
            "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]),
            "volume": float(c[5]), "quote_volume": float(c[7]),
            "trades": int(c[8]),
        })

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)
    return df


def _fetch_coingecko_klines(symbol, interval="1h", limit=200):
    """Fetch OHLC from CoinGecko (free tier: up to 30 days for /ohlc)."""
    coin_id = SYMBOL_TO_COINGECKO.get(symbol)
    if not coin_id:
        return None

    # CoinGecko OHLC supports: 1/7/14/30/90/180/365 days
    days_map = {"5m": 1, "15m": 1, "1h": 7, "4h": 30}
    days = days_map.get(interval, 7)

    resp = requests.get(
        COINGECKO_OHLC_URL.format(coin_id=coin_id),
        params={"vs_currency": "usd", "days": days},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data or len(data) < MIN_CANDLES:
        return None

    # CoinGecko returns [timestamp, open, high, low, close]
    rows = []
    for c in data:
        ts = datetime.fromtimestamp(c[0] / 1000)
        rows.append({
            "timestamp": ts,
            "open": float(c[1]), "high": float(c[2]),
            "low": float(c[3]), "close": float(c[4]),
            "volume": 0, "quote_volume": 0, "trades": 0,
        })

    df = pd.DataFrame(rows)
    df.set_index("timestamp", inplace=True)

    # Remove duplicates
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()

    return df


def fetch_klines(symbol, interval="1h", limit=200, timeout=15):
    """Fetch OHLCV candles from multiple sources with fallback.

    Returns:
        (DataFrame, source_string) — source is 'binance', 'coingecko', or 'synthetic'
    """
    # 1. Try Binance
    try:
        df = _fetch_binance_klines(symbol, interval, limit, timeout)
        if df is not None and len(df) >= MIN_CANDLES:
            data_tracker.record_fetch(symbol, interval, "binance", "OK", len(df))
            return df, "binance"
        data_tracker.record_failure(symbol, interval, "binance")
    except Exception:
        data_tracker.record_failure(symbol, interval, "binance")

    # 2. Try CoinGecko
    try:
        df = _fetch_coingecko_klines(symbol, interval, limit)
        if df is not None and len(df) >= MIN_CANDLES:
            data_tracker.record_fetch(symbol, interval, "coingecko", "OK", len(df))
            return df, "coingecko"
        data_tracker.record_failure(symbol, interval, "coingecko")
    except Exception:
        data_tracker.record_failure(symbol, interval, "coingecko")

    # 3. Synthetic fallback
    print(f"  ⚠ All APIs failed for {symbol}/{interval} — using SYNTHETIC data")
    df, source = _generate_synthetic_klines(symbol, interval, limit)
    data_tracker.record_fetch(symbol, interval, "synthetic", "FALLBACK", len(df))
    return df, source


# Keep legacy compat
def _fetch_klines_legacy(symbol, interval="1h", limit=200, timeout=15):
    """Legacy wrapper that returns only DataFrame (no source)."""
    df, _ = fetch_klines(symbol, interval, limit, timeout)
    return df


# ============================================================
# DATA INTEGRITY CHECKS
# ============================================================

def validate_candles(df, symbol="", source="unknown"):
    """Validate candle data quality with enhanced integrity checks.

    Returns:
        (is_valid: bool, message: str, integrity_info: dict)
    """
    info = {"source": source, "candles": 0, "checks": {}}

    if df is None or df.empty:
        return False, "No data", info

    info["candles"] = len(df)

    if len(df) < MIN_CANDLES:
        return False, f"Insufficient candles: {len(df)}", info

    # 1. NaN check
    nan_pct = df[["open", "high", "low", "close", "volume"]].isna().mean().mean()
    info["checks"]["nan_pct"] = round(nan_pct, 4)
    if nan_pct > 0.05:
        info["checks"]["nan_failed"] = True
        data_tracker.record_integrity_failure(symbol, "", "too_many_nan")
        return False, f"Too many NaN values: {nan_pct:.1%}", info

    # 2. Zero/negative price check
    if (df["close"] <= 0).any():
        info["checks"]["zero_price"] = True
        data_tracker.record_integrity_failure(symbol, "", "zero_price")
        return False, "Zero or negative prices found", info

    # 3. Timestamp validation — check for monotonicity and gaps
    if isinstance(df.index, pd.DatetimeIndex):
        ts_diffs = df.index.to_series().diff().dt.total_seconds()
        # Check for backwards timestamps
        backwards = (ts_diffs < 0).sum()
        info["checks"]["backwards_timestamps"] = int(backwards)
        if backwards > 0:
            data_tracker.record_integrity_failure(symbol, "", "backwards_timestamps")
            return False, f"{backwards} backwards timestamps detected", info

        # Check for extreme gaps (>10x expected interval)
        expected_seconds = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
        # Use median as expected interval
        median_diff = ts_diffs.median()
        if median_diff > 0:
            extreme_gaps = (ts_diffs > median_diff * 10).sum()
            info["checks"]["extreme_gaps"] = int(extreme_gaps)
            # Allow a few gaps (weekends, maintenance)
            if extreme_gaps > len(df) * 0.05:
                data_tracker.record_integrity_failure(symbol, "", "extreme_gaps")
                return False, f"{extreme_gaps} extreme time gaps detected", info

    # 4. Duplicate candle detection
    if isinstance(df.index, pd.DatetimeIndex):
        dup_count = df.index.duplicated().sum()
        info["checks"]["duplicate_candles"] = int(dup_count)
        if dup_count > len(df) * 0.1:
            data_tracker.record_integrity_failure(symbol, "", "too_many_duplicates")
            return False, f"{dup_count} duplicate timestamps", info

    # 5. Extreme gap check (single candle)
    pct_change = df["close"].pct_change().abs()
    max_gap = pct_change.max()
    info["checks"]["max_single_gap"] = round(float(max_gap), 4)
    if max_gap > MAX_SINGLE_CANDLE_GAP:
        data_tracker.record_integrity_failure(symbol, "", "extreme_single_gap")
        return False, f"Extreme price gap detected ({max_gap:.1%})", info

    # 6. Volume check
    if "quote_volume" in df.columns:
        avg_vol = df["quote_volume"].tail(20).mean()
    else:
        avg_vol = df["volume"].tail(20).mean() * df["close"].tail(20).mean() if "volume" in df.columns else 0
    info["checks"]["avg_volume_20"] = round(float(avg_vol), 2)
    if avg_vol < 100_000 and source != "coingecko":
        return False, f"Low volume: ${avg_vol:,.0f}", info

    # 7. Stale data check
    if df["close"].tail(10).std() == 0:
        info["checks"]["stale"] = True
        return False, "Stale price data (no variation)", info

    # 8. OHLC consistency (high >= low, high >= open/close, low <= open/close)
    ohlc_bad = ((df["high"] < df["low"]) |
                (df["high"] < df[["open", "close"]].min(axis=1)) |
                (df["low"] > df[["open", "close"]].max(axis=1))).sum()
    info["checks"]["ohlc_inconsistencies"] = int(ohlc_bad)
    if ohlc_bad > 0:
        data_tracker.record_integrity_failure(symbol, "", "ohlc_inconsistency")
        return False, f"{ohlc_bad} OHLC inconsistencies", info

    info["checks"]["all_passed"] = True
    return True, "OK", info


def remove_duplicate_candles(df):
    """Remove duplicate timestamps, keeping the first occurrence."""
    if df is None or df.empty:
        return df
    before = len(df)
    df = df[~df.index.duplicated(keep="first")]
    removed = before - len(df)
    if removed > 0:
        print(f"  Removed {removed} duplicate candles")
    return df


def fill_missing_candles(df, expected_interval_minutes=60):
    """Fill missing candles with forward-fill for small gaps."""
    if df is None or len(df) < 10:
        return df

    if not isinstance(df.index, pd.DatetimeIndex):
        return df

    # Create expected frequency
    freq_map = {5: "5min", 15: "15min", 60: "1h", 240: "4h"}
    freq = freq_map.get(expected_interval_minutes, "1h")

    # Resample and forward-fill
    full_idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
    df_reindexed = df.reindex(full_idx)

    # Forward-fill OHLC (not volume)
    for col in ["open", "high", "low", "close"]:
        df_reindexed[col] = df_reindexed[col].ffill()
    df_reindexed["volume"] = df_reindexed["volume"].fillna(0)
    df_reindexed["quote_volume"] = df_reindexed.get("quote_volume", pd.Series(0, index=df_reindexed.index)).fillna(0)
    df_reindexed["trades"] = df_reindexed.get("trades", pd.Series(0, index=df_reindexed.index)).fillna(0)

    return df_reindexed


# ============================================================
# QUALITY ANALYSIS
# ============================================================

def analyze_spread(symbol):
    """Analyze bid-ask spread quality."""
    ticker = _ticker_cache.get(symbol)
    if not ticker:
        return {"spread_pct": 999, "quality": False, "reason": "No ticker data"}

    bid = ticker.get("bid", 0)
    ask = ticker.get("ask", 0)

    # CoinGecko doesn't provide bid/ask — skip spread check
    if bid <= 0 or ask <= 0:
        return {"spread_pct": 0, "quality": True, "reason": "N/A (source lacks bid/ask)", "source": ticker.get("source", "unknown")}

    spread = ask - bid
    spread_pct = (spread / ask) * 100
    quality = spread_pct <= MAX_SPREAD_PCT
    reason = "" if quality else f"Spread too wide: {spread_pct:.3f}%"

    return {
        "spread": spread, "spread_pct": round(spread_pct, 4),
        "quality": quality, "reason": reason,
        "bid": bid, "ask": ask, "source": ticker.get("source", "unknown"),
    }


def analyze_volume(symbol):
    """Analyze 24h volume quality."""
    ticker = _ticker_cache.get(symbol)
    if not ticker:
        return {"volume_24h": 0, "quality": False, "reason": "No ticker data"}

    vol = ticker.get("volume_24h", 0)
    quality = vol >= MIN_VOLUME_24H_USD
    reason = "" if quality else f"Low volume: ${vol:,.0f}"

    return {"volume_24h": vol, "quality": quality, "reason": reason}


def detect_abnormal_move(df, lookback=5):
    """Detect abnormal recent price movements."""
    if df is None or len(df) < lookback + 1:
        return False, ""

    recent = df.tail(lookback + 1)
    start_price = recent["close"].iloc[0]
    end_price = recent["close"].iloc[-1]
    cumulative_pct = abs(end_price - start_price) / start_price * 100 if start_price > 0 else 0
    pct_changes = recent["close"].pct_change().abs()
    max_candle = pct_changes.max()

    if cumulative_pct > 8:
        return True, f"Abnormal cumulative move: {cumulative_pct:.1f}% in {lookback} candles"
    if max_candle > 0.05:
        return True, f"Abnormal single candle: {max_candle:.1%}"

    return False, ""


# ============================================================
# MULTI-TF DATA
# ============================================================

def get_multi_tf_data(symbol, timeframes=None, limit=200):
    """Fetch data for multiple timeframes with validation.

    Returns dict of {tf: DataFrame}. Skips invalid TFs.
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    data = {}
    sources = {}
    for tf in timeframes:
        df, source = fetch_klines(symbol, tf, limit)
        valid, msg, info = validate_candles(df, f"{symbol}/{tf}", source)
        if valid:
            data[tf] = df
            sources[tf] = source
        else:
            print(f"  {symbol}/{tf}: {msg} (source={source})")

    return data, sources


def get_spread(symbol):
    """Get current bid-ask spread (legacy compat)."""
    result = analyze_spread(symbol)
    return {"spread": result.get("spread", 0), "spread_pct": result.get("spread_pct", 999)}


def fetch_ticker(symbol):
    """Fetch 24hr ticker data using cache."""
    return _ticker_cache.get(symbol)


def fetch_all_tickers(symbols):
    """Fetch tickers for all symbols in the universe."""
    tickers = {}
    for sym in symbols:
        t = fetch_ticker(sym)
        if t:
            tickers[sym] = t
        time.sleep(0.05)
    return tickers


# ============================================================
# SYMBOL SCAN
# ============================================================

def scan_symbol(symbol, timeframes=None):
    """Full quality scan for a single symbol with multi-source support.

    Returns comprehensive scan result or rejected result.
    """
    if timeframes is None:
        timeframes = ["5m", "15m", "1h", "4h"]

    scan_result = {
        "symbol": symbol,
        "timestamp": datetime.now(),
        "rejected": False,
        "reject_reason": "",
        "quality_checks": {},
        "data_sources": {},
    }

    # API error backoff
    error_count = _ticker_cache.get_error_count(symbol)
    if error_count >= 5:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = f"API error backoff ({error_count} consecutive failures)"
        return scan_result

    # 1. Ticker data
    ticker = fetch_ticker(symbol)
    if not ticker:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = "No ticker data from any source"
        return scan_result
    scan_result["ticker"] = ticker
    scan_result["data_source"] = ticker.get("source", "unknown")

    # 2. Volume check (skip for CoinGecko — less reliable)
    if ticker.get("source") != "coingecko":
        vol_result = analyze_volume(symbol)
        scan_result["quality_checks"]["volume"] = vol_result
        if not vol_result["quality"]:
            scan_result["rejected"] = True
            scan_result["reject_reason"] = vol_result["reason"]
            return scan_result

    # 3. Spread check (skip for CoinGecko — no bid/ask)
    spread_result = analyze_spread(symbol)
    scan_result["quality_checks"]["spread"] = spread_result
    if not spread_result["quality"] and spread_result.get("spread_pct", 0) > 0:
        scan_result["rejected"] = True
        scan_result["reject_reason"] = spread_result["reason"]
        return scan_result

    # 4. Fetch multi-timeframe data
    data, sources = get_multi_tf_data(symbol, timeframes)
    scan_result["data"] = data
    scan_result["data_sources"] = sources

    # Need at least 2 timeframes
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
                    "tf": tf, "volatility": round(recent_vol, 2), "extreme": True,
                }
                # Don't reject — just flag. Let regime engine decide.
                break

    # Reset error count on success
    _ticker_cache.reset_errors(symbol)

    return scan_result


def batch_scan(symbols, timeframes=None):
    """Scan all symbols and return results."""
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
                "symbol": symbol, "rejected": True,
                "reject_reason": f"Scan error: {str(e)}", "quality_checks": {},
            })
        time.sleep(0.1)

    return results


def get_data_source_summary():
    """Get summary of data sources used across all symbols."""
    return data_tracker.get_stats()
