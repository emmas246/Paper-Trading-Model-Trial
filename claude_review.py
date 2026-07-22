"""
Claude integration.

IMPORTANT DESIGN CHOICE: Claude is used here as a *secondary reviewer*,
not as the primary decision-maker. The quant strategy (strategy.py) and
risk manager (risk.py) decide what CAN happen based on fixed, testable
rules. Claude's job is to:
  1. Sanity-check the proposed trade in plain English (catch dumb mistakes,
     e.g. a signal firing on stale/bad data, a position size that looks off)
  2. Summarize *why* the trade is happening so you have a human-readable log
  3. Flag anything unusual it notices about the context you give it

Claude does NOT have live market data or account access, and does not
place orders. It only reasons over the numbers you pass it. Treat its
output as a second opinion, not a green light -- `require_manual_confirmation`
in config.yaml determines whether trades still need your sign-off regardless
of what Claude says.
"""
import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a cautious secondary reviewer for a small automated trading system.
You will be given: a proposed trade, the strategy signal that generated it, and the current
risk-check result. Your job is NOT to approve or override risk decisions -- the risk manager's
decision is final and already applied. Instead:

1. In 2-4 sentences, explain in plain English why this trade is happening.
2. Note anything in the inputs that looks off, inconsistent, or worth a human double-checking
   (e.g. a price that seems stale, a signal right at a noisy threshold, unusual position sizing).
3. Rate your confidence that this looks like a normal, well-formed trade: HIGH, MEDIUM, or LOW.

Respond ONLY with valid JSON in this exact shape, no other text:
{"explanation": "...", "concerns": "...", "confidence": "HIGH|MEDIUM|LOW"}
"""


def review_trade(*, ticker: str, action: str, signal_info: dict, risk_decision: str,
                  trade_value: float, portfolio_value: float) -> dict:
    """
    Ask Claude to review a proposed trade and return a structured opinion.
    Falls back to a safe default if the API call fails -- a failed review
    should never be silently treated as approval.
    """
    user_content = json.dumps({
        "ticker": ticker,
        "action": action,
        "signal_info": signal_info,
        "risk_manager_decision": risk_decision,
        "trade_value_usd": trade_value,
        "portfolio_value_usd": portfolio_value,
        "trade_value_pct_of_portfolio": round(trade_value / portfolio_value, 4) if portfolio_value else None,
    })

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        return {
            "explanation": "Claude review unavailable due to an error.",
            "concerns": f"Review call failed: {e}. Treat this trade as unreviewed.",
            "confidence": "LOW",
        }
