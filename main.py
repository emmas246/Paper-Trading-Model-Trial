"""
Daily run script. Intended to be run once per day, after market close
or before market open, via cron/launchd (see README.md).

Flow per ticker in the watchlist:
  1. Pull latest price history -> compute signal (strategy.py)
  2. If signal is BUY or SELL -> run it through RiskManager (risk.py)
  3. If risk-approved -> ask Claude for a plain-English review (claude_review.py)
  4. Log everything. Only actually submit the order if:
       - risk approved it, AND
       - config.require_manual_confirmation is False (else it just logs
         "PROPOSED" and waits for you to confirm)
  5. Separately, check every existing position for stop-loss triggers
  6. Check the daily-loss circuit breaker before allowing any new trades
"""
import json
import yaml
from datetime import datetime, date

from data import get_price_history
from strategy import latest_signal
from risk import RiskManager
from claude_review import review_trade
import broker

LOG_PATH = "logs/trade_log.jsonl"


def log_event(event: dict):
    event["timestamp"] = datetime.now().isoformat()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")
    print(json.dumps(event, indent=2))


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def run():
    config = load_config()
    risk_cfg = config["risk"]
    strat_cfg = config["strategy"]
    risk_mgr = RiskManager(risk_cfg)

    account = broker.get_account()
    positions = broker.get_positions()
    portfolio_value = account["portfolio_value"]
    cash_available = account["cash"]

    # NOTE: for a real deployment, persist portfolio_peak_value and
    # start-of-day portfolio value to disk/DB. Simplified here for clarity.
    portfolio_peak_value = max(portfolio_value, portfolio_value)  # load real peak from your own log in production
    portfolio_value_start_of_day = portfolio_value  # load real start-of-day snapshot in production

    daily_halt = risk_mgr.check_daily_loss_halt(
        portfolio_value_start_of_day=portfolio_value_start_of_day,
        portfolio_value_now=portfolio_value,
    )
    if daily_halt.approved:  # "approved" here means the halt condition IS triggered
        log_event({"type": "HALT", "reason": daily_halt.reason})
        return

    trades_today = 0
    total_invested_value = sum(p["market_value"] for p in positions.values())

    # --- 1. Check existing positions for stop-loss ---
    for ticker, pos in positions.items():
        stop = risk_mgr.check_stop_loss(entry_price=pos["avg_entry_price"], current_price=pos["current_price"])
        if stop.approved:
            log_event({"type": "STOP_LOSS", "ticker": ticker, "reason": stop.reason})
            if not config["require_manual_confirmation"]:
                broker.submit_order(ticker, "SELL", pos["market_value"])
                log_event({"type": "ORDER_SUBMITTED", "ticker": ticker, "action": "SELL", "value": pos["market_value"]})
            else:
                log_event({"type": "ORDER_PROPOSED", "ticker": ticker, "action": "SELL", "value": pos["market_value"],
                           "note": "Manual confirmation required -- not submitted automatically."})

    # --- 2. Check watchlist for new signals ---
    for ticker in config["watchlist"]:
        if trades_today >= risk_cfg["max_trades_per_day"]:
            log_event({"type": "INFO", "reason": "Daily trade cap reached, skipping remaining tickers."})
            break

        df = get_price_history(ticker, period="2y", use_cache=False)
        signal_info = latest_signal(df, strat_cfg["short_window"], strat_cfg["long_window"], strat_cfg["confirmation_days"])

        if signal_info["signal"] not in ("BUY", "SELL"):
            continue

        current_position_value = positions.get(ticker, {}).get("market_value", 0)
        proposed_trade_value = portfolio_value * risk_cfg["max_position_pct"] if signal_info["signal"] == "BUY" else current_position_value

        if signal_info["signal"] == "BUY":
            decision = risk_mgr.check_new_buy(
                portfolio_value=portfolio_value,
                cash_available=cash_available,
                current_position_value=current_position_value,
                proposed_trade_value=proposed_trade_value,
                total_invested_value=total_invested_value,
                trades_today=trades_today,
                portfolio_peak_value=portfolio_peak_value,
            )
        else:
            decision = type(risk_mgr.check_new_buy(
                portfolio_value=1, cash_available=1, current_position_value=0,
                proposed_trade_value=0, total_invested_value=0, trades_today=0,
                portfolio_peak_value=1))(True, "OK: sell signal, closing existing position.")

        claude_opinion = review_trade(
            ticker=ticker,
            action=signal_info["signal"],
            signal_info=signal_info,
            risk_decision=decision.reason,
            trade_value=proposed_trade_value,
            portfolio_value=portfolio_value,
        )

        event = {
            "type": "SIGNAL",
            "ticker": ticker,
            "signal": signal_info,
            "risk_decision": {"approved": decision.approved, "reason": decision.reason},
            "claude_review": claude_opinion,
        }
        log_event(event)

        if decision.approved:
            trades_today += 1
            if not config["require_manual_confirmation"]:
                broker.submit_order(ticker, signal_info["signal"], proposed_trade_value)
                log_event({"type": "ORDER_SUBMITTED", "ticker": ticker, "action": signal_info["signal"], "value": proposed_trade_value})
            else:
                log_event({"type": "ORDER_PROPOSED", "ticker": ticker, "action": signal_info["signal"], "value": proposed_trade_value,
                           "note": "Manual confirmation required -- review logs/trade_log.jsonl and confirm manually."})


if __name__ == "__main__":
    run()
