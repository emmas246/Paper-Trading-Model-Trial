"""
Strategy logic: moving average crossover with a confirmation filter.

Signal rules:
- BUY  when short MA crosses above long MA, and stays above for `confirmation_days`
- SELL when short MA crosses below long MA, and stays below for `confirmation_days`
- Otherwise HOLD

This is intentionally simple and explainable. Swap this module out if you
want to test a different strategy -- keep the same function signature so
the rest of the system doesn't need to change.
"""
import pandas as pd


def compute_signals(df: pd.DataFrame, short_window: int, long_window: int, confirmation_days: int) -> pd.DataFrame:
    df = df.copy()
    df["ma_short"] = df["Close"].rolling(short_window).mean()
    df["ma_long"] = df["Close"].rolling(long_window).mean()
    df["above"] = df["ma_short"] > df["ma_long"]

    # Require the "above" state to hold for `confirmation_days` in a row before acting
    df["confirmed_above"] = df["above"].rolling(confirmation_days).sum() == confirmation_days
    df["confirmed_below"] = (~df["above"]).rolling(confirmation_days).sum() == confirmation_days

    df["signal"] = "HOLD"
    # A crossover BUY happens the first day confirmed_above turns true after being false
    buy_trigger = df["confirmed_above"] & ~df["confirmed_above"].shift(1).fillna(False)
    sell_trigger = df["confirmed_below"] & ~df["confirmed_below"].shift(1).fillna(False)

    df.loc[buy_trigger, "signal"] = "BUY"
    df.loc[sell_trigger, "signal"] = "SELL"

    return df


def latest_signal(df: pd.DataFrame, short_window: int, long_window: int, confirmation_days: int) -> dict:
    """Return the most recent signal plus supporting context for logging / review."""
    signals = compute_signals(df, short_window, long_window, confirmation_days)
    last = signals.iloc[-1]
    return {
        "date": str(signals.index[-1].date()),
        "close": float(last["Close"]),
        "ma_short": float(last["ma_short"]) if pd.notna(last["ma_short"]) else None,
        "ma_long": float(last["ma_long"]) if pd.notna(last["ma_long"]) else None,
        "signal": str(last["signal"]),
    }
