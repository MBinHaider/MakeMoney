# PolyBot 5M — Design Spec

**Date**: 2026-04-04
**Status**: Approved
**Author**: Claude + Mohammad

## Overview

PolyBot 5M is a rapid trading bot for Polymarket's 5-minute crypto UP/DOWN prediction markets. It trades BTC, ETH, and SOL binary outcomes every 5 minutes using a hybrid signal strategy combining Binance price momentum, Polymarket orderbook imbalance, and volume spike detection.

Third independent bot in the MakeMoney repo alongside PolyBot (slow markets) and BinanceBot (spot trading).

## Key Decisions

- **Capital**: $25 paper balance, $5 max per trade
- **Assets**: BTC, ETH, SOL 5-minute UP/DOWN markets
- **Strategy**: Hybrid 2-of-3 signal agreement (momentum + orderbook imbalance + volume spikes)
- **Entry timing**: Adaptive — enter as soon as signals agree with sufficient confidence
- **Window management**: Selective + cooldown (skip weak signals, pause after 3 consecutive losses)
- **Notifications**: Every trade + settlement result via Telegram
- **Architecture**: PMXT SDK for Polymarket access, ported PolyRec indicator math

## Architecture

```
polybot5m.py                    <- main entry point
fivemin_modules/
├── market_data.py              <- PMXT market discovery + Binance price feed
├── indicators.py               <- Ported PolyRec math (imbalance, microprice, volume, momentum)
├── signal_engine.py            <- 2-of-3 hybrid + adaptive entry logic
├── trade_executor.py           <- PMXT order placement, paper/live mode
├── risk_manager.py             <- $5 cap, cooldown, daily limits
└── notifier.py                 <- Telegram: every trade + settlement result
config.py                       <- extended with FIVEMIN_* settings
utils/fivemin_db.py             <- SQLite for trades, signals, P&L
data/polybot5m.db               <- database file
```

### Dependencies

- `pmxt` — SDK for Polymarket market discovery, orderbook streaming, order placement
- `aiohttp` — Binance WebSocket price feed (already in requirements.txt)
- `python-telegram-bot` — notifications (already in requirements.txt)
- `python-dotenv` — env vars (already in requirements.txt)
- Node.js on PATH — required by PMXT's sidecar server

## Market Data Module

`fivemin_modules/market_data.py`

### Polymarket (via PMXT)

- Compute deterministic market slugs: `btc-updown-5m-{timestamp}` where timestamp = `now - (now % 300)`. Same for ETH/SOL.
- `exchange.fetchMarkets()` to get UP/DOWN outcome IDs and current prices
- `exchange.watchOrderBook(outcomeId)` for both UP and DOWN on each asset
- Maintain rolling snapshot: top 5 bid/ask levels per outcome

### Binance (via aiohttp WebSocket)

- Connect to `wss://stream.binance.com:9443/ws/btcusdt@kline_1s` (and ethusdt, solusdt)
- Extract: close price, high, low, quote volume per 1-second candle
- Maintain rolling deques (60 items) for returns, VWAP, ATR, volume MA

### PMXT Auth

```python
exchange = pmxt.Polymarket(
    private_key=Config.PRIVATE_KEY,
    proxy_address=Config.POLYMARKET_PROXY_ADDRESS,
    signature_type='gnosis-safe'
)
```

Proxied through WARP on port 40000 for geo-bypass.

### Shared State

`MarketState` dataclass per asset:
- `window_open_price` — Binance price at window start
- `current_price` — latest Binance price
- `orderbook_up` / `orderbook_down` — top 5 levels each
- `volume_history` — rolling 1s volumes
- `price_history` — rolling 1s closes
- `window_start_ts` / `seconds_remaining`

### Window Lifecycle

When `seconds_remaining` hits 0: freeze state, wait for settlement, reset for next window. Auto-discover new market slugs.

## Indicators Module

`fivemin_modules/indicators.py` — pure math functions. No network calls, no state. Takes `MarketState`, returns indicator values.

### Signal 1: Binance Price Momentum

- `momentum_delta = (current_price - window_open_price) / window_open_price`
- delta >= 0.02% -> UP, <= -0.02% -> DOWN
- Stronger deltas (>0.15%) = higher confidence
- Returns: direction (UP/DOWN/NEUTRAL) + confidence (0.0-1.0)

### Signal 2: Orderbook Imbalance

- `imbalance = (sum_bid_sizes - sum_ask_sizes) / (sum_bid_sizes + sum_ask_sizes)` across top 5 levels
- `microprice = (ask_price * bid_size + bid_price * ask_size) / (bid_size + ask_size)` at best level
- `bid_slope = top2_bid_size / total5_bid_size` — depth concentration
- Combined: UP imbalance > 0.15 AND microprice > midpoint AND bid_slope > 0.5 -> signal UP
- Mirror logic for DOWN
- Returns: direction + confidence

### Signal 3: Volume Spike

- `volume_ma_30s = mean(last 30 volume readings)`
- `volume_spike = current_1s_volume / volume_ma_30s`
- Spike > 2.0 AND price moving in a direction -> confirms that direction
- Spike alone without directional move -> NEUTRAL
- Returns: direction + confidence

All functions stateless and independently testable.

## Signal Engine

`fivemin_modules/signal_engine.py`

### Adaptive Entry

Evaluate indicators on every data tick (~1s). Three phases per window:

| Phase | Time | Threshold |
|-------|------|-----------|
| Early | 0:00-2:00 | All 3 signals agree, confidence > 0.75 |
| Mid | 2:00-4:00 | 2-of-3 agree, confidence > 0.60 |
| Late | 4:00-4:50 | 2-of-3 agree, confidence > 0.55 |
| Cutoff | 4:50-5:00 | No new entries |

### Asset Selection

When multiple assets signal simultaneously:
1. Highest composite confidence
2. Tiebreaker: deepest orderbook
3. Max one trade per window

### Signal Output

```python
@dataclass
class Signal:
    asset: str          # "BTC", "ETH", "SOL"
    direction: str      # "UP" or "DOWN"
    confidence: float   # 0.0-1.0
    phase: str          # "early", "mid", "late"
    indicators: dict    # which signals agreed and their individual scores
    timestamp: float
```

### No-Trade Conditions

- No 2-of-3 agreement by T-10s
- Cooldown active
- Daily loss limit hit

## Trade Executor

`fivemin_modules/trade_executor.py`

### Paper Mode (Default)

- No real orders. Simulate fills using current PMXT orderbook prices.
- Snapshot best ask price for chosen outcome on signal
- Record as filled at that price in SQLite
- At window settlement: calculate P&L
  - Win: profit = `(1.00 - entry_price) * shares`
  - Loss: loss = `entry_price * shares`

### Live Mode (Future)

- `exchange.createOrder({marketId, outcomeId, side: 'buy', type: 'limit', price, amount})`
- Fill-or-kill with 5s timeout. Retry once at market. Skip window if no fill.
- Winning shares auto-resolve to $1.00 USDC via Chainlink oracle.

### Position Sizing

- `shares = min(max_trade_amount, risk_approved) / ask_price`
- Example: $5 budget, UP ask at $0.55 -> 9 shares. Win = $4.05. Lose = $4.95.

### Trade Record

```python
@dataclass
class Trade:
    id: str
    asset: str              # "BTC"
    direction: str          # "UP"
    entry_price: float      # 0.55
    shares: float           # 9.09
    cost: float             # 5.00
    result: str             # "win" / "loss" / "pending"
    pnl: float              # +4.05 or -4.95
    window_ts: int          # unix timestamp of window start
    signal_confidence: float
    signal_phase: str       # "early", "mid", "late"
```

## Risk Manager

`fivemin_modules/risk_manager.py`

### Per-Trade Limits

- Max $5 per trade
- Must have sufficient paper balance

### Cooldown System

- 3 consecutive losses -> pause 15 minutes (3 windows skipped)
- Resets on first win after resuming

### Daily Limits

- Daily loss limit: 20% of starting balance ($5 on $25)
- Once hit -> stop trading until midnight UTC, still monitor and log signals
- Daily trade count cap: 50

### Exposure Control

- Max 1 position at a time (one trade per window, binary, no overlap)
- No compounding in paper mode — fixed $5 max regardless of balance growth

### Risk Check Flow

```
signal_fires -> risk_manager.can_trade() -> checks:
  1. Cooldown not active?
  2. Daily loss limit not hit?
  3. Daily trade count under cap?
  4. Sufficient balance?
  -> returns (approved: bool, reason: str, max_amount: float)
```

Streak tracking stored in SQLite. Survives bot restarts.

## Notifier

`fivemin_modules/notifier.py`

All messages prefixed `[5M]` to distinguish from `[POLY]` and `[BNB]`.

| Event | Format |
|-------|--------|
| Trade entry | `[5M] BUY UP BTC @ $0.55 (9 shares, $5.00) \| Confidence: 0.72 \| Phase: mid \| Signals: momentum+orderbook` |
| Win | `[5M] WIN BTC UP +$4.05 \| Balance: $29.05 \| Streak: W3` |
| Loss | `[5M] LOSS BTC DOWN -$4.95 \| Balance: $20.05 \| Streak: L2` |
| Cooldown | `[5M] PAUSED — 3 consecutive losses. Resuming in 15min` |
| Daily limit | `[5M] DAILY LIMIT HIT — lost $5.00 today. Stopped until midnight UTC` |
| Bot start | `[5M] PolyBot 5M started — paper mode, $25.00 balance` |
| Bot stop | `[5M] PolyBot 5M stopped` |
| Skip | Silent — no message when no signal meets threshold |

## Database

`utils/fivemin_db.py` — SQLite at `data/polybot5m.db`

### Tables

- `trades` — full trade records (entry, result, P&L, signal details, window timestamp)
- `signals` — all evaluated signals per window, even no-trades (for backtesting)
- `daily_stats` — aggregated daily P&L, win rate, trade count, best/worst trade
- `cooldowns` — cooldown events with start/end timestamps

## Config Additions

In `config.py`:

```python
# PolyBot 5M
FIVEMIN_TRADING_MODE = os.getenv("FIVEMIN_TRADING_MODE", "paper")
FIVEMIN_ASSETS = ["BTC", "ETH", "SOL"]
FIVEMIN_STARTING_BALANCE = 25.00
FIVEMIN_MAX_PER_TRADE = 5.00
FIVEMIN_CONFIDENCE_EARLY = 0.75
FIVEMIN_CONFIDENCE_MID = 0.60
FIVEMIN_CONFIDENCE_LATE = 0.55
FIVEMIN_ENTRY_CUTOFF_SEC = 10
FIVEMIN_COOLDOWN_LOSSES = 3
FIVEMIN_COOLDOWN_MINUTES = 15
FIVEMIN_DAILY_LOSS_LIMIT_PCT = 0.20
FIVEMIN_DAILY_TRADE_CAP = 50
FIVEMIN_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "polybot5m.db")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS", "")
```

`.env` additions:
```
POLYMARKET_PROXY_ADDRESS=your_polymarket_proxy_wallet
```

## Entry Point

```
python polybot5m.py                 # default paper mode
python polybot5m.py --mode paper    # explicit paper
python polybot5m.py --mode live     # future: real trading
```

### Main Loop

1. Init PMXT exchange connection (through WARP proxy)
2. Init Binance WebSocket streams for BTC/ETH/SOL
3. Send Telegram startup message
4. Loop forever:
   - Calculate current window timestamps
   - Discover active markets for all 3 assets
   - Stream data, evaluate signals on each tick
   - Signal fires -> risk check -> execute -> notify
   - Window close -> poll settlement -> record result -> notify
   - Sleep until next window opens
5. Graceful shutdown: Ctrl+C closes connections, sends "bot stopped"
