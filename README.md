# Quant Model Starter — Setup Guide (macOS)

A moving-average-crossover strategy with a risk-management layer and Claude
as a secondary trade reviewer. Runs in **paper trading** (fake money) by default.

**This is not financial advice, and this is not a system to point at real
money without weeks of paper-trading and your own review of every design
decision.** Treat it as an engineering starting point.

---

## 0. What you'll need accounts for

- **Alpaca** (free) — paper trading brokerage API: https://alpaca.markets
- **Anthropic** (Claude API) — https://console.anthropic.com

Both have free tiers sufficient for this project.

---

## 1. Install prerequisites

Open **Terminal** (Cmd+Space, type "Terminal").

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11+
brew install python@3.11

# Confirm
python3 --version
```

## 2. Get the project onto your machine

Copy the `quant-model` folder (from this chat) into somewhere like `~/Projects/`,
e.g. `~/Projects/quant-model`.

```bash
cd ~/Projects/quant-model
```

## 3. Create a virtual environment

Keeps this project's packages separate from the rest of your system.

```bash
python3 -m venv venv
source venv/bin/activate
```

You'll see `(venv)` appear in your prompt. Every time you come back to work
on this project in a new terminal window, run `source venv/bin/activate` again.

## 4. Install dependencies

```bash
pip install -r requirements.txt
```

## 5. Set up your API keys

```bash
cp .env.example .env
open -e .env   # opens in TextEdit
```

Fill in:
- `ANTHROPIC_API_KEY` — from console.anthropic.com → API Keys
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — from app.alpaca.markets → make sure
  you generate **paper trading** keys, not live keys
- Leave `ALPACA_BASE_URL` pointed at the paper URL

Save and close.

## 6. Review and adjust `config.yaml`

Open it and look at:
- `watchlist` — which stocks it's allowed to touch
- `risk` section — position size caps, stop-loss %, drawdown circuit breaker
- `require_manual_confirmation: true` — **leave this as `true` for now.** It
  means the system will log every trade it *would* make, but won't actually
  submit anything until you flip it to `false`. This is your safety switch.

## 7. Backtest before doing anything else

```bash
python backtest.py
```

This runs the strategy against 5 years of historical data for each ticker
in your watchlist and prints total return, CAGR, Sharpe ratio, max drawdown,
and how it compares to just buying and holding. **If the strategy doesn't
beat a simple buy-and-hold on a risk-adjusted basis over multiple time
periods, that's important information — don't skip this step.**

## 8. Dry-run the daily script

```bash
python main.py
```

This will:
- Pull today's data for each watchlist ticker
- Compute signals
- Run every proposed trade through the risk manager
- Ask Claude to write a plain-English review of each proposed trade
- Log everything to `logs/trade_log.jsonl`
- Since `require_manual_confirmation` is `true`, it will **not** place any
  real (even paper) orders yet — just log what it *would* do

Check the output and `logs/trade_log.jsonl`. Read Claude's review of each
proposed trade. Does the reasoning make sense? Do the risk checks look right?

## 9. Move to actual paper trading

Once you've watched it propose sensible trades for a while:

1. Set `require_manual_confirmation: false` in `config.yaml`
2. Run `python main.py` again — now it will submit real orders to your
   **paper** Alpaca account (still fake money)
3. Check your positions any time: add a small script or just log into
   the Alpaca paper dashboard at app.alpaca.markets

## 10. Automate the daily run (optional, once you trust it)

Use macOS's `launchd` to run this on a schedule instead of a manual terminal
command each day.

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.quantmodel.daily.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.quantmodel.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/Projects/quant-model/venv/bin/python</string>
        <string>/Users/YOUR_USERNAME/Projects/quant-model/main.py</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/YOUR_USERNAME/Projects/quant-model</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>17</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>/Users/YOUR_USERNAME/Projects/quant-model/logs/launchd.log</string>
    <key>StandardErrorPath</key><string>/Users/YOUR_USERNAME/Projects/quant-model/logs/launchd_error.log</string>
</dict>
</plist>
EOF

# Replace YOUR_USERNAME with your actual Mac username, then load it:
launchctl load ~/Library/LaunchAgents/com.quantmodel.daily.plist
```

This runs `main.py` every day at 5:00 PM (after US market close). Adjust
`Hour`/`Minute` as you like. To stop it: `launchctl unload ~/Library/LaunchAgents/com.quantmodel.daily.plist`

## 11. Monitor it

```bash
tail -f logs/trade_log.jsonl
```

Review this regularly. Watch for:
- HALT events (circuit breaker tripped — investigate before resuming)
- STOP_LOSS events
- Claude review confidence dropping to LOW or flagging concerns
- Any stretch where the strategy underperforms buy-and-hold by a lot

---

## What Claude is and isn't doing here

Claude reviews each proposed trade and writes a plain-English explanation
plus a confidence rating. It does **not**:
- See live account data beyond what's explicitly passed to it
- Have the ability to place orders itself
- Override the risk manager's decisions

Think of it as a second pair of eyes that turns "the algorithm bought AAPL"
into "the algorithm bought AAPL because the 50-day average crossed above
the 200-day average, confirmed over 2 days, sized at 20% of the portfolio,
review confidence: HIGH" — something you can actually audit.

## Extending this

- Swap `strategy.py` for a different rule set (mean-reversion, momentum
  ranking) — keep the same `latest_signal()` function signature
- Add persistent storage (SQLite) for portfolio peak value and start-of-day
  snapshots instead of the simplified in-memory versions in `main.py`
- Add email/SMS alerts on HALT or STOP_LOSS events
- Widen the backtest to test across different market regimes (2008, 2020,
  2022) specifically, not just a rolling 5-year window
