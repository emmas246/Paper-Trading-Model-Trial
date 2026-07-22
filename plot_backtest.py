"""
Generates equity curve charts (strategy vs. buy-and-hold) for every ticker
in the watchlist, plus a summary bar chart comparing returns.

Run: python plot_backtest.py
Output: charts/<ticker>_equity.png and charts/summary_returns.png
"""
import os
import yaml
import matplotlib
matplotlib.use("Agg")  # no GUI needed, just save files
import matplotlib.pyplot as plt
import pandas as pd

from backtest import backtest_ticker

CHART_DIR = "charts"


def plot_ticker(result: dict):
    dates = pd.to_datetime(result["dates"])
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, result["equity_curve"], label="Strategy (MA crossover)", color="#2563eb", linewidth=1.6)
    ax.plot(dates, result["buy_hold_curve"], label="Buy & Hold", color="#94a3b8", linewidth=1.4, linestyle="--")

    # Mark trades
    for t in result["trades"]:
        t_date = pd.to_datetime(t["date"])
        marker = "^" if t["action"] == "BUY" else "v"
        color = "#16a34a" if t["action"] == "BUY" else "#dc2626"
        idx = dates.get_indexer([t_date], method="nearest")[0]
        ax.scatter(t_date, result["equity_curve"][idx], marker=marker, color=color, s=70, zorder=5)

    ax.set_title(f"{result['ticker']} — Strategy vs Buy & Hold "
                 f"(Total: {result['total_return_pct']}% vs {result['buy_and_hold_return_pct']}%, "
                 f"Max Drawdown: {result['max_drawdown_pct']}%)")
    ax.set_ylabel("Portfolio value ($)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.25)
    fig.tight_layout()

    os.makedirs(CHART_DIR, exist_ok=True)
    path = os.path.join(CHART_DIR, f"{result['ticker']}_equity.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def plot_summary(results: list):
    tickers = [r["ticker"] for r in results]
    strat_returns = [r["total_return_pct"] for r in results]
    bh_returns = [r["buy_and_hold_return_pct"] for r in results]

    x = range(len(tickers))
    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([i - width/2 for i in x], strat_returns, width, label="Strategy", color="#2563eb")
    ax.bar([i + width/2 for i in x], bh_returns, width, label="Buy & Hold", color="#94a3b8")
    ax.set_xticks(list(x))
    ax.set_xticklabels(tickers)
    ax.set_ylabel("Total return (%)")
    ax.set_title("Strategy vs Buy & Hold — Total Return by Ticker")
    ax.legend()
    ax.grid(alpha=0.25, axis="y")
    ax.axhline(0, color="black", linewidth=0.8)
    fig.tight_layout()

    os.makedirs(CHART_DIR, exist_ok=True)
    path = os.path.join(CHART_DIR, "summary_returns.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


if __name__ == "__main__":
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    s = config["strategy"]

    results = []
    for ticker in config["watchlist"]:
        result = backtest_ticker(ticker, s["short_window"], s["long_window"], s["confirmation_days"])
        path = plot_ticker(result)
        print(f"Saved {path}")
        results.append(result)

    summary_path = plot_summary(results)
    print(f"Saved {summary_path}")
