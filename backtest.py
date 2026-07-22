"""
Backtest the strategy against historical data before running it live/paper.

Run: python backtest.py
"""
import yaml
import pandas as pd
import numpy as np

from data import get_price_history
from strategy import compute_signals


def backtest_ticker(ticker: str, short_window: int, long_window: int, confirmation_days: int,
                     starting_cash: float = 10000, period: str = "5y") -> dict:
    df = get_price_history(ticker, period=period)
    signals = compute_signals(df, short_window, long_window, confirmation_days)

    cash = starting_cash
    shares = 0
    equity_curve = []
    trades = []

    for date, row in signals.iterrows():
        price = row["Close"]
        if row["signal"] == "BUY" and cash > 0:
            shares = cash / price
            cash = 0
            trades.append({"date": str(date.date()), "action": "BUY", "price": float(price)})
        elif row["signal"] == "SELL" and shares > 0:
            cash = shares * price
            shares = 0
            trades.append({"date": str(date.date()), "action": "SELL", "price": float(price)})

        equity_curve.append(cash + shares * price)

    signals["equity"] = equity_curve
    final_value = equity_curve[-1] if equity_curve else starting_cash

    # Buy-and-hold equity curve for comparison (same starting cash, no trading)
    bh_curve = (signals["Close"] / signals["Close"].iloc[0] * starting_cash).tolist()

    # Metrics
    returns = pd.Series(equity_curve).pct_change().dropna()
    total_return = (final_value / starting_cash) - 1
    years = len(signals) / 252
    cagr = (final_value / starting_cash) ** (1 / years) - 1 if years > 0 else 0
    sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

    equity_series = pd.Series(equity_curve)
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    max_drawdown = drawdown.min()

    # Buy-and-hold benchmark
    bh_return = (signals["Close"].iloc[-1] / signals["Close"].iloc[0]) - 1

    return {
        "ticker": ticker,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "buy_and_hold_return_pct": round(bh_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "num_trades": len(trades),
        "trades": trades,
        "dates": [str(d.date()) for d in signals.index],
        "equity_curve": equity_curve,
        "buy_hold_curve": bh_curve,
    }


if __name__ == "__main__":
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    import time

    s = config["strategy"]
    print(f"{'Ticker':<8}{'Total Ret':>12}{'Buy&Hold':>12}{'CAGR':>10}{'Sharpe':>10}{'MaxDD':>10}{'Trades':>8}")
    for i, ticker in enumerate(config["watchlist"]):
        if i > 0:
            time.sleep(2)  # small pause between tickers to avoid triggering rate limits
        result = backtest_ticker(ticker, s["short_window"], s["long_window"], s["confirmation_days"])
        print(f"{result['ticker']:<8}{result['total_return_pct']:>11}%{result['buy_and_hold_return_pct']:>11}%"
              f"{result['cagr_pct']:>9}%{result['sharpe_ratio']:>10}{result['max_drawdown_pct']:>9}%{result['num_trades']:>8}")
