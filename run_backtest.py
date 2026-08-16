import requests
import pandas as pd

from trading.backtest import run_backtest


SYMBOL = "BTCUSDT"
INTERVAL = "1h"

STARTING_CAPITAL = 2500


def get_binance_data():

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": 1000
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    rows = []

    for candle in data:

        rows.append({
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": float(candle[5])
        })

    return pd.DataFrame(rows)


def main():

    print("=" * 50)
    print("TRADING BOT BACKTEST")
    print("=" * 50)

    print()
    print("Downloading BTC/USDT data...")

    df = get_binance_data()

    print(
        f"Downloaded {len(df)} candles"
    )

    print()

    result = run_backtest(
        df,
        starting_capital=STARTING_CAPITAL,
        risk_percent=0.5,
        stop_loss_percent=1.0,
        take_profit_percent=1.5
    )

    print("=" * 50)
    print("BACKTEST RESULT")
    print("=" * 50)

    print(
        "Starting Capital:",
        result["starting_capital"]
    )

    print(
        "Final Capital:",
        result["final_capital"]
    )

    print(
        "Total Profit:",
        result["total_profit"]
    )

    print(
        "Return:",
        result["return_percent"],
        "%"
    )

    print(
        "Trades:",
        result["total_trades"]
    )

    print(
        "Winning:",
        result["winning_trades"]
    )

    print(
        "Losing:",
        result["losing_trades"]
    )

    print(
        "Win Rate:",
        result["win_rate"],
        "%"
    )

    print("=" * 50)


if __name__ == "__main__":
    main()
