"""
Thin wrapper around Alpaca's paper trading API. Everything here defaults
to the paper endpoint -- switching to live trading requires deliberately
changing ALPACA_BASE_URL in .env, which is an intentional speed bump.
"""
import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

load_dotenv()

API_KEY = os.environ.get("ALPACA_API_KEY")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
BASE_URL = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
IS_PAPER = "paper" in BASE_URL

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=IS_PAPER)


def get_account():
    acct = trading_client.get_account()
    return {
        "portfolio_value": float(acct.portfolio_value),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
    }


def get_positions():
    positions = trading_client.get_all_positions()
    return {
        p.symbol: {
            "qty": float(p.qty),
            "market_value": float(p.market_value),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
        }
        for p in positions
    }


def submit_order(ticker: str, side: str, notional_usd: float):
    """
    Submit a market order sized in dollars (notional), not shares -- simpler
    for percentage-of-portfolio position sizing.
    """
    order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    order = MarketOrderRequest(
        symbol=ticker,
        notional=round(notional_usd, 2),
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    return trading_client.submit_order(order)
