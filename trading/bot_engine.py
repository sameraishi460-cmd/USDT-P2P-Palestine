import time
import requests
import pandas as pd

from trading.strategy import (
    calculate_indicators,
    generate_signal
)


class TradingBot:

    def __init__(
        self,
        symbol="BTCUSDT",
        interval="1h",
        capital=2500,
        risk_percent=0.5,
        stop_loss_percent=1.0,
        take_profit_percent=1.5
    ):

        self.symbol = symbol
        self.interval = interval
        self.capital = float(capital)

        self.starting_capital = float(capital)

        self.risk_percent = float(risk_percent)
        self.stop_loss_percent = float(stop_loss_percent)
        self.take_profit_percent = float(
            take_profit_percent
        )

        self.position = 0.0
        self.entry_price = 0.0

        self.running = False

        self.trades = []

    # =========================
    # GET MARKET DATA
    # =========================

    def get_data(self):

        url = "https://api.binance.com/api/v3/klines"

        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": 200
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

    # =========================
    # OPEN PAPER TRADE
    # =========================

    def open_position(self, price):

        if self.position > 0:
            return

        risk_amount = (
            self.capital *
            self.risk_percent /
            100
        )

        price_risk = (
            price *
            self.stop_loss_percent /
            100
        )

        if price_risk <= 0:
            return

        quantity = (
            risk_amount /
            price_risk
        )

        self.position = quantity
        self.entry_price = price

        print(
            f"BUY {quantity:.6f} "
            f"{self.symbol} @ {price:.2f}"
        )

    # =========================
    # CLOSE PAPER TRADE
    # =========================

    def close_position(
        self,
        price,
        reason="SIGNAL"
    ):

        if self.position <= 0:
            return

        profit = (
            price -
            self.entry_price
        ) * self.position

        self.capital += profit

        trade = {
            "symbol": self.symbol,
            "entry": self.entry_price,
            "exit": price,
            "quantity": self.position,
            "profit": profit,
            "reason": reason
        }

        self.trades.append(trade)

        print(
            f"SELL @ {price:.2f} | "
            f"Profit: {profit:.2f} | "
            f"Reason: {reason}"
        )

        self.position = 0.0
        self.entry_price = 0.0

    # =========================
    # CHECK CURRENT MARKET
    # =========================

    def check_market(self):

        df = self.get_data()

        df = calculate_indicators(df)

        row = df.iloc[-1]

        price = float(row["close"])

        signal = generate_signal(row)

        print(
            f"{self.symbol} | "
            f"Price: {price:.2f} | "
            f"Signal: {signal}"
        )

        # =========================
        # NO POSITION
        # =========================

        if self.position == 0:

            if signal == "BUY":

                self.open_position(price)

            return

        # =========================
        # POSITION EXISTS
        # =========================

        stop_loss = (
            self.entry_price *
            (1 - self.stop_loss_percent / 100)
        )

        take_profit = (
            self.entry_price *
            (1 + self.take_profit_percent / 100)
        )

        if price <= stop_loss:

            self.close_position(
                price,
                "STOP_LOSS"
            )

        elif price >= take_profit:

            self.close_position(
                price,
                "TAKE_PROFIT"
            )

        elif signal == "SELL":

            self.close_position(
                price,
                "SELL_SIGNAL"
            )

    # =========================
    # START
    # =========================

    def start(self):

        self.running = True

        print("=" * 50)
        print("PAPER TRADING BOT STARTED")
        print("=" * 50)

        while self.running:

            try:

                self.check_market()

            except Exception as e:

                print(
                    "BOT ERROR:",
                    e
                )

            time.sleep(60)

    # =========================
    # STOP
    # =========================

    def stop(self):

        self.running = False

        print(
            "PAPER TRADING BOT STOPPED"
        )

    # =========================
    # STATS
    # =========================

    def stats(self):

        profit = (
            self.capital -
            self.starting_capital
        )

        return {
            "starting_capital":
                self.starting_capital,

            "capital":
                round(self.capital, 2),

            "profit":
                round(profit, 2),

            "return_percent":
                round(
                    (
                        profit /
                        self.starting_capital
                    ) * 100,
                    2
                ),

            "trades":
                len(self.trades)
        }
