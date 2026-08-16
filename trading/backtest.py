import pandas as pd

from trading.strategy import (
    calculate_indicators,
    generate_signal
)


def run_backtest(
    df,
    starting_capital=2500,
    risk_percent=0.5,
    stop_loss_percent=1.0,
    take_profit_percent=1.5
):

    df = calculate_indicators(df)

    capital = float(starting_capital)

    position = 0.0
    entry_price = 0.0

    trades = []

    for _, row in df.iterrows():

        price = float(row["close"])

        signal = generate_signal(row)

        # =========================
        # OPEN POSITION
        # =========================

        if position == 0 and signal == "BUY":

            entry_price = price

            risk_amount = capital * (
                risk_percent / 100
            )

            price_risk = (
                entry_price *
                stop_loss_percent /
                100
            )

            if price_risk <= 0:
                continue

            position = (
                risk_amount /
                price_risk
            )

            trades.append({
                "type": "BUY",
                "price": price,
                "quantity": position
            })

        # =========================
        # CLOSE POSITION
        # =========================

        elif position > 0:

            stop_loss = (
                entry_price *
                (1 - stop_loss_percent / 100)
            )

            take_profit = (
                entry_price *
                (1 + take_profit_percent / 100)
            )

            should_close = (
                price <= stop_loss
                or
                price >= take_profit
                or
                signal == "SELL"
            )

            if should_close:

                profit = (
                    price - entry_price
                ) * position

                capital += profit

                trades.append({
                    "type": "SELL",
                    "price": price,
                    "quantity": position,
                    "profit": profit
                })

                position = 0.0
                entry_price = 0.0

    # =========================
    # CLOSE OPEN POSITION
    # =========================

    if position > 0:

        last_price = float(
            df.iloc[-1]["close"]
        )

        profit = (
            last_price - entry_price
        ) * position

        capital += profit

        trades.append({
            "type": "SELL",
            "price": last_price,
            "quantity": position,
            "profit": profit
        })

    # =========================
    # STATISTICS
    # =========================

    sell_trades = [
        t for t in trades
        if t["type"] == "SELL"
    ]

    winning = [
        t for t in sell_trades
        if t.get("profit", 0) > 0
    ]

    losing = [
        t for t in sell_trades
        if t.get("profit", 0) < 0
    ]

    total_profit = (
        capital - starting_capital
    )

    return {
        "starting_capital": starting_capital,
        "final_capital": round(capital, 2),
        "total_profit": round(total_profit, 2),
        "return_percent": round(
            (total_profit / starting_capital) * 100,
            2
        ),
        "total_trades": len(sell_trades),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(
            (
                len(winning) /
                len(sell_trades) *
                100
            )
            if sell_trades
            else 0,
            2
        )
    }
