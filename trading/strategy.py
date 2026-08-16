import pandas as pd


def calculate_indicators(df):

    df = df.copy()

    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)

    df["rsi"] = 100 - (100 / (1 + rs))

    return df


def generate_signal(row):

    if pd.isna(row["ema20"]) or pd.isna(row["ema50"]) or pd.isna(row["rsi"]):
        return "HOLD"

    if (
        row["ema20"] > row["ema50"]
        and 45 <= row["rsi"] <= 68
    ):
        return "BUY"

    if (
        row["ema20"] < row["ema50"]
        or row["rsi"] > 75
    ):
        return "SELL"

    return "HOLD"
