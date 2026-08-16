from trading.bot_engine import TradingBot


bot = TradingBot(
    symbol="BTCUSDT",
    interval="1h",
    capital=2500,
    risk_percent=0.5,
    stop_loss_percent=1.0,
    take_profit_percent=1.5
)


if __name__ == "__main__":

    try:

        bot.start()

    except KeyboardInterrupt:

        bot.stop()

        print()
        print("FINAL STATS")
        print(bot.stats())
