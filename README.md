# PolyBot - Automated Polymarket Trading Bot

An autonomous trading bot that monitors top-performing wallets on [Polymarket](https://polymarket.com) and copies their trades using AI-powered signal scoring.

## What It Does

PolyBot watches what the most profitable traders on Polymarket are doing, scores each trade opportunity, and automatically places paper (simulated) or live trades when the signal is strong enough.

**Current status: Paper trading mode (no real money yet)**

## How It Works

### The Pipeline

```
1. DISCOVER  -->  2. ANALYZE  -->  3. SCORE  -->  4. TRADE  -->  5. REPORT
   Markets &        Wallet          Signal         Paper or       Telegram
   Wallets          P&L             Engine         Live           Updates
```

### Step by Step

**1. Market Discovery**
- Fetches all active markets from Polymarket's Gamma API (politics, sports, crypto, world events)
- Filters out lopsided markets (>90% one side) where there's no profit potential
- Currently tracking ~130 markets with real trading volume

**2. Whale Wallet Discovery**
- Finds wallets that are actively trading on high-volume markets via `data-api.polymarket.com`
- Fetches each wallet's position history and calculates real P&L (profit/loss)
- Discovers 700+ wallets, profiles the top 50, tracks the best 20

**3. Wallet Scoring**
- Each wallet is scored on: profitability (real P&L), win rate, trade volume, activity, and recency
- Wallets with positive P&L and high win rates get tracked for copy-trading
- Scoring updates daily

**4. Signal Engine**
- When a tracked whale makes a new trade, the bot generates a signal (0-100 score)
- **Whale Score (0-40)**: Wallet rank + bet conviction + profitability
- **Market Score (0-35)**: Price momentum + volatility + volume
- **Confluence Score (0-25)**: Multiple whales trading same direction
- Score >= 50: Auto-execute paper trade
- Score 35-49: Telegram alert only
- Score < 35: Logged silently

**5. Trade Execution**
- Paper mode: Simulates trades in SQLite database
- Live mode: Places real orders via Polymarket's CLOB API (py-clob-client)
- Position sizing: 2% of portfolio per trade, scaled by signal confidence
- Trades resolve after 5 minutes by comparing entry price to current market price

**6. Risk Management**
- Hard stop: Pauses if portfolio drops 30% from peak
- Soft stop: Halves position sizes at 15% drawdown
- Daily loss limit: Stops trading if down 10% in one day
- Max 10 concurrent positions, max 30% total exposure
- Kill switch via Telegram `/kill` command

**7. Telegram Bot**
- Every 5 minutes: Maturity progress report with learning metrics
- Real-time alerts for trade executions and resolutions (win/loss)
- Commands: `/status`, `/pause`, `/resume`, `/kill`, `/today`, `/history`, `/balance`

## Architecture

```
MakeMoney/
├── polybot.py              # Main entry point, async event loops
├── config.py               # All tunables (thresholds, limits, intervals)
├── setup.py                # One-command installer
├── .env                    # Secrets (never committed)
├── data/
│   └── polybot.db          # SQLite database
├── modules/
│   ├── data_collector.py   # Polymarket + Binance API integrations
│   ├── wallet_scanner.py   # Wallet P&L analysis & ranking
│   ├── signal_engine.py    # Signal generation & scoring
│   ├── trade_executor.py   # Paper + live trade execution
│   ├── risk_manager.py     # Capital protection & position sizing
│   └── notifier.py         # Telegram bot (alerts + commands)
├── utils/
│   ├── logger.py           # Structured logging
│   └── db.py               # SQLite schema (8 tables + indexes)
├── tests/                  # 39 tests covering all modules
└── docs/
    └── superpowers/
        ├── specs/          # Design specification
        └── plans/          # Implementation plan
```

## Tech Stack

- **Python 3.11+**
- **py-clob-client** - Polymarket's official trading SDK
- **aiohttp + aiohttp-socks** - Async HTTP with SOCKS5 proxy support
- **python-telegram-bot** - Telegram integration
- **SQLite** - Local database (no server needed)
- **Cloudflare WARP** - SOCKS5 proxy for geo-blocked regions

## Setup

### Prerequisites

- Python 3.11+
- A Telegram bot (create via [@BotFather](https://t.me/BotFather))
- An Ethereum wallet (for live trading, not needed for paper mode)
- Cloudflare WARP (if Polymarket is geo-blocked in your region)

### Installation

```bash
git clone https://github.com/MBinHaider/MakeMoney.git
cd MakeMoney
python setup.py
```

This installs dependencies, creates the database, and runs tests.

### Configuration

Edit `.env` with your credentials:

```
PRIVATE_KEY=your_ethereum_private_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TRADING_MODE=paper
```

### Proxy Setup (if geo-blocked)

```bash
warp-cli mode proxy    # Set WARP to SOCKS5 proxy mode
warp-cli connect       # Connect
# Proxy runs on socks5://127.0.0.1:40000
```

### Running

```bash
# Paper trading (recommended to start)
python polybot.py --mode paper --capital 100

# Live trading (after paper validation)
python polybot.py --mode live --capital 25
```

## Polymarket MCP Server (Optional)

The project includes integration with a [Polymarket MCP server](https://github.com/caiovicentino/polymarket-mcp-server) that gives Claude Code 18+ tools for searching, analyzing, and monitoring Polymarket markets directly.

Setup is in `.mcp.json` - requires separate installation of the MCP server.

## Current Performance (Honest Assessment)

| Metric | Value |
|--------|-------|
| Markets tracked | ~130 |
| Wallets discovered | ~735 |
| Top wallets tracked | 20 |
| Best whale P&L | $10,327 (78% WR) |
| Bot paper trades | Generating |
| Bot win rate | Under evaluation |
| Ready for real money | **Not yet** |

The bot is in the **data collection and validation phase**. It needs 50+ paper trades with a 55%+ win rate before real money should be considered.

## What's Working

- Market discovery across all Polymarket categories
- Whale wallet profiling with real P&L data
- Signal scoring with whale + market + confluence components
- Paper trade execution and resolution
- Telegram notifications and kill switch
- Maturity tracking (shows learning progress)
- Cloudflare WARP proxy for geo-blocked access

## Known Limitations

- **No 5-minute crypto markets**: The rapid-fire BTC/ETH up/down markets from viral tweets don't appear to be available through Polymarket's current API
- **Slow-moving markets**: Most Polymarket markets resolve over weeks/months, not minutes — price changes in 5 minutes are tiny
- **Paper trade PnL is small**: Because market prices barely move in 5-minute resolution windows
- **Wallet scoring bootstraps on volume**: Until enough win/loss data accumulates, wallets are ranked by trading volume, not profitability

## Next Steps

1. **Validate paper trading** - Run for 3-5 days, collect 50+ trades, measure actual win rate
2. **Tune signal thresholds** - Adjust based on which scores correlate with profitable trades
3. **Improve trade resolution** - Track actual market outcomes instead of 5-min price snapshots
4. **Cloud deployment** - Move to a $5/mo VPS for 24/7 operation without proxy issues
5. **Go live with $25** - Only after paper trading proves consistent profitability

## Disclaimer

This is an experimental trading bot. Prediction markets involve real financial risk. Past performance of tracked wallets does not guarantee future results. Never trade with money you can't afford to lose. The bot is provided as-is with no guarantees of profitability.

## License

MIT
