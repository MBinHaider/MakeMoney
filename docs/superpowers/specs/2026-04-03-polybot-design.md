# PolyBot — AI-Powered Polymarket Trading Bot

## Overview

PolyBot is a hybrid-intelligence automated trading bot for Polymarket's crypto up/down prediction markets. It combines copy-trading top-performing wallets with AI-powered signal filtering to generate and execute trades autonomously.

**Target markets:** BTC and ETH 5-minute up/down markets (expandable based on data analysis).

## Goals & Constraints

- **Starting capital:** $25-100 USDC on Polygon
- **User experience level:** Has crypto wallet, new to Polymarket, not a developer
- **Infrastructure:** Local (Mac) first, cloud VPS later
- **Autonomy:** Semi-autonomous with Telegram notifications and kill switch
- **Language:** Python (best ecosystem for Polymarket tooling)
- **Risk model:** Copy top performer sizing patterns, scaled to user budget

## System Architecture

```
┌─────────────────────────────────────────────────┐
│                   PolyBot                        │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │  Wallet   │→│  Signal   │→│  Trade        │ │
│  │  Scanner  │  │  Engine   │  │  Executor     │ │
│  └──────────┘  └──────────┘  └───────────────┘ │
│       ↑              ↑              │            │
│  ┌──────────┐        │         ┌────▼────────┐  │
│  │  Data     │────────┘         │  Notifier   │  │
│  │  Collector│                  │  (Telegram) │  │
│  └──────────┘                  └─────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │           Risk Manager                    │   │
│  │  (drawdown limits, position sizing,       │   │
│  │   kill switch)                             │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**5 modules + 1 cross-cutting concern:**

1. **Data Collector** — Fetches Polymarket data, crypto prices, wallet histories
2. **Wallet Scanner** — Analyzes top wallets, scores them, tracks real-time activity
3. **Signal Engine** — Combines whale activity + market conditions into confidence-scored signals
4. **Trade Executor** — Places bets on Polymarket via CLOB API
5. **Notifier** — Telegram alerts for trades, summaries, and kill-switch commands
6. **Risk Manager** (cross-cutting) — Enforces drawdown limits, position sizing, pause/kill

**Data storage:** SQLite (no server needed, portable between local and cloud).

## Module 1: Data Collector

Gathers four types of data:

### 1.1 Polymarket Market Data
- Fetches active 5-minute crypto up/down markets via Polymarket CLOB API
- Polls every 30 seconds
- Stores: market ID, token pair, current odds, volume, time to resolution

### 1.2 Wallet History (batch)
- Runs on startup + daily refresh
- Pulls trade history from top wallets via Polymarket public API
- Target: top 500 wallets by profit on crypto up/down markets over last 90 days
- Stores: wallet address, each trade (market, side, size, entry price, outcome, P&L)

### 1.3 Real-Time Wallet Monitoring
- Tracks top ~20 wallets identified by Wallet Scanner
- Polls recent trades every 15 seconds
- New bet detected → immediately pushes to Signal Engine

### 1.4 Crypto Price Feed
- BTC and ETH spot prices from Binance public API (free, no auth)
- 1-minute candles for momentum/volatility calculations
- Used by Signal Engine for market condition scoring

### Rate Limiting
- All API calls respect rate limits with exponential backoff
- No authentication needed for read-only Polymarket data

## Module 2: Wallet Scanner

Identifies which wallets are worth following.

### 2.1 Initial Scan
1. Pull all wallets that traded crypto up/down markets in last 90 days
2. Filter to wallets with 100+ trades
3. Score each wallet:

| Factor | Weight | Measures |
|--------|--------|----------|
| Win Rate | 25% | % of profitable trades |
| Consistency | 25% | Steady returns vs lucky streaks (Sharpe-like) |
| Total PNL | 20% | Absolute profit |
| Trade Frequency | 15% | Active enough to generate signals |
| Recency | 15% | Recent performance weighted higher |

4. Rank by composite score, select top 20 as tracked wallets

### 2.2 Wallet Profiles
Stored per wallet:
- Average bet size, preferred markets (BTC vs ETH), preferred time-of-day
- Win rate by market type, average hold time
- Sizing pattern: flat bets vs confidence-scaled vs martingale
- Used by Risk Manager to scale user's bets

### 2.3 Daily Refresh
- Re-scores all wallets every 24 hours
- Wallets below threshold removed, new high-performers added
- Telegram notification when tracked list changes

### 2.4 Edge Detection
- 55%+ win rate over 1,000+ trades = statistically significant edge
- <52% win rate or <100 trades filtered out regardless of PNL

## Module 3: Signal Engine

Decides when to trade and how confident.

### 3.1 Signal Score (0-100)

**Whale Score (0-40 points):**
- Wallet composite rank (top 5 = 15pts, top 10 = 10pts, top 20 = 5pts)
- Bet size vs their average (larger = more conviction = more points)
- Win rate on this specific market type

**Market Score (0-35 points):**
- Price momentum alignment with whale's bet direction (+15pts)
- Volatility window — moderate is ideal (+10pts)
- Polymarket market volume/liquidity (+10pts)

**Confluence Score (0-25 points):**
- Multiple tracked wallets same direction within 2 minutes (+15pts)
- Consistency with wallet's typical pattern (time, market type) (+10pts)

### 3.2 Signal Thresholds

| Score | Action |
|-------|--------|
| 70-100 | Auto-execute trade |
| 50-69 | Telegram alert only |
| Below 50 | Log, don't act |

### 3.3 Cooldown Rules
- Max 1 trade per market per 5-minute window
- Max 10 active positions at any time
- 3 consecutive losses → pause 30 minutes + Telegram notify

## Module 4: Trade Executor

Places actual bets on Polymarket.

### 4.1 Polymarket Integration
- Ethereum wallet (private key in `.env`, never hardcoded)
- Polymarket py-clob-client Python SDK
- Trades on Polygon network (~$0.01 gas per trade)

### 4.2 Position Sizing
Copied from whale patterns, scaled to user budget:
- Base bet = 2% of portfolio per trade (mirrors whale average)
- Scaled by confidence: Score 70 = 1x, Score 85 = 1.5x, Score 100 = 2x
- Hard cap: never exceed 10% of remaining capital per trade

### 4.3 Execution Flow
```
Signal fires (score >= 70)
  -> Risk Manager check (drawdown OK? positions OK? not paused?)
  -> Calculate position size
  -> Place limit order at current best price
  -> Not filled in 30s -> cancel and skip
  -> Filled -> log trade, notify Telegram
  -> Monitor -> auto-resolve on 5-min expiry
```

### 4.4 Order Policy
- Limit orders only (no market orders — avoids slippage)
- Placed at slightly better than current mid-price
- Cancelled if price moves away before fill

### 4.5 Trade Tracking
- Every trade logged to SQLite: timestamp, market, side, size, entry price, outcome, P&L
- Running portfolio value updated after each resolution

## Module 5: Notifier (Telegram)

### 5.1 Trade Alerts
- Every auto-executed trade: market, direction, size, confidence score
- Every moderate signal (50-69): "Signal detected, want me to take it?"
- Trade outcomes as they resolve: win/loss, P&L

### 5.2 Commands

| Command | Action |
|---------|--------|
| `/status` | Current P&L, open positions, tracked wallets |
| `/pause` | Pause all trading (keeps monitoring) |
| `/resume` | Resume trading |
| `/kill` | Emergency stop — cancel all orders, stop everything |
| `/today` | Today's trades and P&L summary |
| `/history` | Last 7 days performance |
| `/balance` | Current portfolio value |

### 5.3 Daily Summary (auto-sent at midnight UTC)
- Total trades, win rate, P&L
- Best and worst trade
- Top performing tracked wallet
- Portfolio value vs starting capital

## Module 6: Risk Manager

### 6.1 Drawdown Protection
- Hard stop: portfolio drops 30% from peak → pause all trading + alert
- Soft stop: drops 15% → reduce position sizes by 50% + notify
- Daily loss limit: down 10% in single day → stop for the day

### 6.2 Position Limits
- Max 10 concurrent positions
- Max 10% of capital per trade
- Max 30% of capital exposed at any time
- Max 3 trades same direction within 5 minutes

### 6.3 Kill Switch
- Telegram `/kill` command cancels all open orders and stops the bot
- `/pause` stops new trades but keeps monitoring
- `/resume` restarts trading

### 6.4 Logging
- All decisions logged with reasoning (signal taken/skipped and why)
- Useful for reviewing and tuning over time

## Deployment & Setup

### Phase 1: Local Setup (Day 1)
```
1. Clone the project
2. Create .env with: wallet private key, Telegram bot token, Polymarket API key
3. Run: python setup.py
4. Run: python polybot.py --paper-mode
```

### Phase 2: Paper Trading (Days 1-3)
- Full pipeline, fake money
- No real trades — logs what it would have done
- Review via Telegram `/history`
- Validates system before real money

### Phase 3: Go Live (Day 3+)
- Fund Polymarket account ($25-100 USDC on Polygon)
- Switch: `python polybot.py --live`
- Monitor via Telegram

### Phase 4: Cloud Migration (when profitable)
- Deploy to $5/mo VPS (DigitalOcean or Railway)
- Runs 24/7
- Same codebase

## Project Structure

```
MakeMoney/
├── polybot.py              # Main entry point
├── setup.py                # One-command installer
├── config.py               # Settings (thresholds, limits, tunables)
├── .env                    # Secrets (never committed)
├── data/
│   └── polybot.db          # SQLite database
├── modules/
│   ├── data_collector.py   # Polymarket + Binance API integrations
│   ├── wallet_scanner.py   # Wallet analysis & scoring
│   ├── signal_engine.py    # Signal generation & confidence scoring
│   ├── trade_executor.py   # Polymarket trade placement
│   ├── risk_manager.py     # Capital protection & drawdown logic
│   └── notifier.py         # Telegram bot integration
├── utils/
│   ├── logger.py           # Structured logging
│   └── db.py               # SQLite database helpers
└── tests/
    └── ...                 # Tests for each module
```

## Future Expansion
- Add SOL and other markets based on wallet analysis data
- Web dashboard for visual performance tracking
- Multiple strategy profiles (conservative, moderate, aggressive)
- Machine learning model trained on historical signal outcomes
