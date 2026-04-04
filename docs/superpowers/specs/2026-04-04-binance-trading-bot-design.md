# BinanceBot — Rapid BTC/ETH Trading Bot Design Spec

**Date**: 2026-04-04
**Status**: Approved
**Author**: Claude + Mohammad

## Overview

A rapid trading bot that trades BTC/USDT and ETH/USDT on Binance spot market using 1-minute and 5-minute candles with technical indicator signals. Starts in paper mode. Sends Telegram notifications on every trade plus periodic summaries.

Separate bot from PolyBot. Same repo, independent process.

## Requirements

- **Capital**: $25-50 starting balance
- **Pairs**: BTC/USDT, ETH/USDT
- **Timeframes**: 1-minute (entry timing), 5-minute (trend confirmation)
- **Risk tolerance**: Moderate (2-5% daily target)
- **Mode**: Paper first, live when proven
- **Notifications**: Instant trade alerts + 15-minute summaries + daily report

## Architecture

### File Structure

```
binancebot.py              # Entry point — main loop
binance_modules/
  __init__.py
  market_data.py           # Fetch candles + prices from Binance REST API
  indicators.py            # RSI, MACD, Bollinger Bands (hand-rolled, no deps)
  signal_engine.py         # Combine indicators into buy/sell/hold signals
  trade_executor.py        # Paper + live order execution
  risk_manager.py          # Position sizing, stop-loss, daily limits
  notifier.py              # Telegram alerts (trade + summary + daily)
config.py                  # Add Binance-specific settings (shared file)
.env                       # Add BINANCE_API_KEY + BINANCE_API_SECRET
data/binancebot.db         # SQLite database (separate from polybot.db)
```

### Flow

Every 60 seconds:
1. `market_data.py` fetches latest 1m and 5m candles for BTC/USDT and ETH/USDT
2. `indicators.py` computes RSI(14), MACD(12,26,9), Bollinger Bands(20,2) on both timeframes
3. `signal_engine.py` scores signals — 2-of-3 indicator agreement required, both timeframes must agree
4. `risk_manager.py` checks if trade is allowed (position limits, daily loss, cooldowns)
5. `trade_executor.py` executes trade (paper: simulate at market price + slippage; live: Binance API)
6. `notifier.py` sends Telegram alert
7. Check open positions for take-profit/stop-loss/trailing-stop hits

Every 15 minutes: Send summary to Telegram.
End of day: Send daily report to Telegram.

## Trading Strategy

### Indicators

| Indicator | Buy Signal | Sell Signal | Period |
|-----------|-----------|-------------|--------|
| RSI(14) | RSI < 30 | RSI > 70 | 14 candles |
| MACD(12,26,9) | MACD line crosses above signal | MACD line crosses below signal | 12/26/9 |
| Bollinger Bands(20,2) | Price touches lower band | Price touches upper band | 20 candles, 2 std dev |

### Signal Logic

- **Buy**: 2 of 3 indicators say buy AND 5m trend confirms (not bearish)
- **Strong buy**: 3 of 3 indicators agree — 30% of capital (max). 2-of-3 agreement uses 20% of capital.
- **Sell**: Take-profit hit, stop-loss hit, trailing stop triggered, or opposing signal
- **Hold**: Fewer than 2 indicators agree — do nothing

### Timeframe Confirmation

- 1-minute candles generate entry signals (fast)
- 5-minute candles confirm trend direction (filter false signals)
- Only enter when both timeframes agree

### Trade Lifecycle

1. Signal fires -> check risk limits -> place buy order
2. Set take-profit at +1.5% and stop-loss at -1%
3. Trailing stop moves up in 0.5% increments as price rises
4. Exit on: take-profit, stop-loss, trailing stop, or opposing signal

## Risk Management

| Rule | Value | Rationale |
|------|-------|-----------|
| Max per trade | 30% of capital (~$10-15) | Small capital needs meaningful sizes |
| Max open positions | 3 | Prevents overexposure |
| Stop-loss | -1% per trade | Caps downside ~$0.10-0.15 |
| Take-profit | +1.5% per trade | 1.5:1 reward-to-risk |
| Trailing stop | 0.5% step increments | Locks in gains |
| Daily loss limit | -5% of portfolio | Stops trading for the day |
| Consecutive loss pause | 3 losses -> 15min cooldown | Avoids tilt trading |
| Min time between trades | 2 minutes | Prevents rapid-fire overtrading |
| Fee buffer | 0.1% per trade factored in | Signal must exceed fees to trigger |

## Telegram Notifications

All messages prefixed with "BinanceBot" to distinguish from PolyBot.

### Instant Trade Alerts

On every buy:
```
BinanceBot 🟢 BUY BTC/USDT @ $68,432.50
Size: $12.00 | Signal: RSI(28) + MACD cross + BB lower
TP: $69,458 (+1.5%) | SL: $67,748 (-1%)
Open positions: 2/3 | Portfolio: $47.32
```

On every sell:
```
BinanceBot 🔴 SELL ETH/USDT @ $3,521.40
P&L: +$0.38 (+1.2%) | Hold time: 7m
Reason: Take-profit hit
Open positions: 1/3 | Portfolio: $47.70
```

### 15-Minute Summary

```
BinanceBot 📊 Status
Portfolio: $47.70 (started: $45.00)
Today P&L: +$2.70 (+6.0%)
Trades today: 8 (5W/3L, 62.5% win rate)
Open: 1 BTC long @ $68,432
Signals: BTC neutral | ETH watching RSI(35)
```

### Daily Report

```
BinanceBot 📈 Daily Report
Net P&L: +$2.70 (+6.0%)
Total trades: 14 (9W/5L)
Best: ETH +$0.52 | Worst: BTC -$0.14
Running total: $47.70 (from $45.00 start)
```

## Data & Storage

### Binance API Endpoints (no auth for market data)

- `GET /api/v3/klines` — candle data (1m, 5m)
- `GET /api/v3/ticker/price` — current price
- `POST /api/v3/order` — place orders (auth required, live mode only)
- `GET /api/v3/account` — balance check (auth required, live mode only)

No proxy needed — Binance is not geo-blocked.

### SQLite Database: `data/binancebot.db`

| Table | Columns | Purpose |
|-------|---------|---------|
| `candles` | symbol, interval, open_time, open, high, low, close, volume | Cached price data |
| `signals` | timestamp, symbol, rsi, macd, macd_signal, bb_upper, bb_lower, score, action | Signal history |
| `trades` | id, timestamp, symbol, side, price, size, tp, sl, status, exit_price, exit_time, pnl, fees, reason | All trades |
| `portfolio` | timestamp, balance, daily_pnl, total_trades, wins, losses | Daily snapshots |

### Paper Mode

- Simulates fills at current price + 0.1% slippage
- Deducts 0.1% fee per trade
- Identical code path to live — only order placement is swapped
- Portfolio tracked in SQLite

## Dependencies

Zero new dependencies. Uses existing:
- `aiohttp` — HTTP calls to Binance API
- `python-telegram-bot` — Telegram notifications
- `python-dotenv` — Environment variables

Indicators (RSI, MACD, Bollinger Bands) are hand-rolled — simple math, no library needed.

## Config Additions

Added to existing `config.py`:

```python
# Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_API_URL = "https://api.binance.com"  # already exists

# BinanceBot trading
BINANCE_TRADING_MODE = os.getenv("BINANCE_TRADING_MODE", "paper")
BINANCE_PAIRS = ["BTCUSDT", "ETHUSDT"]
BINANCE_CANDLE_INTERVAL_1M = "1m"
BINANCE_CANDLE_INTERVAL_5M = "5m"
BINANCE_POLL_INTERVAL_SEC = 60
BINANCE_SUMMARY_INTERVAL_SEC = 900  # 15 minutes

# BinanceBot risk
BINANCE_MAX_PER_TRADE_PCT = 0.30
BINANCE_MAX_POSITIONS = 3
BINANCE_STOP_LOSS_PCT = 0.01
BINANCE_TAKE_PROFIT_PCT = 0.015
BINANCE_TRAILING_STOP_STEP_PCT = 0.005
BINANCE_DAILY_LOSS_LIMIT_PCT = 0.05
BINANCE_CONSECUTIVE_LOSS_PAUSE = 3
BINANCE_PAUSE_DURATION_MIN = 15
BINANCE_MIN_TRADE_INTERVAL_SEC = 120
BINANCE_FEE_PCT = 0.001
BINANCE_SLIPPAGE_PCT = 0.001

# BinanceBot portfolio
BINANCE_STARTING_BALANCE = 45.00  # Paper mode starting balance
```

## .env Additions

```
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TRADING_MODE=paper
```

## Future Extensions (not in v1)

- Copy-trading top Binance traders (if API supports it)
- Additional pairs (SOL/USDT, DOGE/USDT)
- Longer timeframes (15m, 1h) for swing trading
- Web dashboard for monitoring
- Cloud deployment (same VPS as PolyBot)
