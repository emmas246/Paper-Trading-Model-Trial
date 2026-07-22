"""
Risk management layer. Every proposed trade must pass through here before
it's allowed to execute. This is deliberately the strictest, most boring
code in the project -- that's the point.
"""
from dataclasses import dataclass


@dataclass
class RiskDecision:
    approved: bool
    reason: str


class RiskManager:
    def __init__(self, risk_config: dict):
        self.max_position_pct = risk_config["max_position_pct"]
        self.max_total_invested_pct = risk_config["max_total_invested_pct"]
        self.stop_loss_pct = risk_config["stop_loss_pct"]
        self.max_daily_loss_pct = risk_config["max_daily_loss_pct"]
        self.max_drawdown_pct = risk_config["max_drawdown_pct"]
        self.max_trades_per_day = risk_config["max_trades_per_day"]

    def check_new_buy(self, *, portfolio_value: float, cash_available: float,
                       current_position_value: float, proposed_trade_value: float,
                       total_invested_value: float, trades_today: int,
                       portfolio_peak_value: float) -> RiskDecision:
        """Run every safety check for a proposed BUY. Fails closed: any violation blocks the trade."""

        # 1. Circuit breaker: are we already in a large drawdown? If so, no new risk.
        drawdown = 1 - (portfolio_value / portfolio_peak_value) if portfolio_peak_value > 0 else 0
        if drawdown >= self.max_drawdown_pct:
            return RiskDecision(False, f"BLOCKED: portfolio drawdown {drawdown:.1%} >= max allowed {self.max_drawdown_pct:.1%}. Trading halted, review manually.")

        # 2. Daily trade count cap
        if trades_today >= self.max_trades_per_day:
            return RiskDecision(False, f"BLOCKED: already made {trades_today} trades today (limit {self.max_trades_per_day}).")

        # 3. Position concentration cap
        resulting_position_value = current_position_value + proposed_trade_value
        if resulting_position_value / portfolio_value > self.max_position_pct:
            return RiskDecision(False, f"BLOCKED: this trade would put {resulting_position_value/portfolio_value:.1%} of the portfolio in one stock (limit {self.max_position_pct:.1%}).")

        # 4. Total invested cap (must keep a cash buffer)
        resulting_invested = total_invested_value + proposed_trade_value
        if resulting_invested / portfolio_value > self.max_total_invested_pct:
            return RiskDecision(False, f"BLOCKED: this trade would push total invested to {resulting_invested/portfolio_value:.1%}, above the {self.max_total_invested_pct:.1%} cap (cash buffer rule).")

        # 5. Sufficient cash
        if proposed_trade_value > cash_available:
            return RiskDecision(False, "BLOCKED: insufficient cash for this trade size.")

        return RiskDecision(True, "OK: passed all pre-trade risk checks.")

    def check_stop_loss(self, *, entry_price: float, current_price: float) -> RiskDecision:
        """Should an existing position be force-sold due to the stop-loss rule?"""
        loss_pct = (entry_price - current_price) / entry_price
        if loss_pct >= self.stop_loss_pct:
            return RiskDecision(True, f"STOP-LOSS TRIGGERED: position down {loss_pct:.1%}, exceeds {self.stop_loss_pct:.1%} limit. Selling.")
        return RiskDecision(False, "Stop-loss not triggered.")

    def check_daily_loss_halt(self, *, portfolio_value_start_of_day: float, portfolio_value_now: float) -> RiskDecision:
        """Should all NEW trading halt for today because of a bad day?"""
        loss_pct = (portfolio_value_start_of_day - portfolio_value_now) / portfolio_value_start_of_day
        if loss_pct >= self.max_daily_loss_pct:
            return RiskDecision(True, f"DAILY LOSS HALT: portfolio down {loss_pct:.1%} today, limit is {self.max_daily_loss_pct:.1%}. No new trades until tomorrow.")
        return RiskDecision(False, "Daily loss within limits.")
