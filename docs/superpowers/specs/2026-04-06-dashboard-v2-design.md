# Dashboard V2 — Full Web Dashboard Redesign

**Date**: 2026-04-06
**Status**: Approved
**Author**: Claude + Mohammad

## Overview

Rebuild the web dashboard (`web_dashboard.py`) to match the terminal Rich dashboard exactly, with additional features: responsive layout, working charts, live/paper mode toggle, real wallet balance display, and paper vs real trade comparison. Updates every second via WebSocket.

## Requirements

1. **Responsive layout** — fills 100vh/100vw, CSS Grid with `fr` units, wraps on mobile
2. **Fix P&L chart** — Chart.js line chart, 3 lines (combined/5M/binance), fill data gaps with zeros
3. **Fix BTC chart** — drop broken financial plugin, use bar chart styled as candles (green up, red down)
4. **Mode switch** — toggle on each bot card, writes flag to DB, bot reads every cycle (no restart)
5. **Confirmation popup** — before switching to live: "Switch to REAL MONEY trading?"
6. **Live mode background** — dark green tint `#0a0f0a` when any bot is live, card border glows green, switch pulses
7. **Real wallet balance** — always show actual Polymarket USDC balance at top, refreshed every 15 seconds
8. **Paper vs Real comparison** — trades tagged REAL/PAPER, side-by-side stats card comparing win rates
9. **All data updates every second** via WebSocket (heavy data on slower intervals)

## Architecture

Single file `web_dashboard.py` with embedded HTML/CSS/JS. Flask + flask-socketio (threading mode).

### Backend Data Flow

```
Background Thread (every 1s):
  ├── Read fm_portfolio, bn_portfolio from SQLite
  ├── Read recent trades (tagged paper/real)
  ├── Read live signals from polybot5m_state.json
  ├── Read cooldown, streak, daily stats
  ├── Read prices from Binance (every 1s)
  └── socketio.emit("update", payload)

Background Thread (every 15s):
  └── Query Polymarket CLOB API for real wallet USDC balance

Background Thread (every 60s):
  └── Fetch BTC 1h candles from Binance

Background Thread (every 5s):
  └── Refresh P&L chart history

Background Thread (every 30s):
  └── Refresh hourly heatmap
```

### Mode Switch Flow

1. User flips toggle on dashboard
2. Frontend shows confirmation popup (live only)
3. Frontend emits WebSocket event: `switch_mode {bot: "5m", mode: "live"}`
4. Server receives event, writes to DB:
   - 5M: `UPDATE fm_portfolio SET trading_mode = 'live' WHERE id = 1`
   - BN: `UPDATE bn_portfolio SET trading_mode = 'live' WHERE id = 1`
5. Bot reads `trading_mode` column every cycle (1s)
6. If live: place real orders via py-clob-client
7. If paper: simulate orders as before

### Database Changes

**fm_portfolio** — add column: `trading_mode TEXT DEFAULT 'paper'`
**bn_portfolio** — add column: `trading_mode TEXT DEFAULT 'paper'`
**fm_trades** — add column: `trade_mode TEXT DEFAULT 'paper'` (tags each trade permanently)
**bn_trades** — add column: `trade_mode TEXT DEFAULT 'paper'`

### Wallet Balance Query

Every 15 seconds, server calls:
```python
from py_clob_client.client import ClobClient
# Use existing key + proxy address from config
# Try client.get_balance_allowance() or fallback to on-chain query
```

If CLOB balance check fails, display "Wallet: --" (don't crash).

## Frontend Panels

### Header
- "MBH Trading Bots Command Center"
- UTC time (live)
- Bot status dots: 5M ● BN ● PB ● (green=running, red=stopped)
- Wallet balance: `Wallet: $XX.XX USDC`

### Bot Cards (2 side-by-side)
Each card has:
- Bot name + mode toggle switch (green=live, yellow=paper)
- Balance (bold, colored by P&L)
- P&L + percentage
- W/L count + win rate
- Daily P&L
- Extra: 5M shows window countdown, BN shows open positions

### Prices Panel
- BTC, ETH, SOL with ▲/▼ arrows, colored green/red

### P&L Chart
- Chart.js line chart, responsive
- 3 datasets: Combined (green), 5M (yellow), Binance (blue)
- X-axis: time, Y-axis: cumulative $ P&L

### BTC Chart
- Bar chart styled as candles
- Green bars (close > open), red bars (close < open)
- 24 hourly bars

### Streak & Daily
- Current streak (winning/losing)
- Today P&L + trades + win rate
- Yesterday P&L

### Signal Accuracy
- Generated, skipped, traded, won counts
- Visual bar (green=won, red=lost, gray=skipped)

### Win Rate Heatmap
- 24 cells (hours 00-23)
- Color: gray=none, red=<40%, dark green=40-70%, bright green=>70%

### Live Signals
- BTC/ETH/SOL: momentum ↑↓·, orderbook ↑↓·, volume ↑↓·
- Signal direction + confidence %

### Paper vs Real Comparison
Side-by-side card:
```
         PAPER   |   REAL
Trades:    15    |     3
Wins:      12    |     2
Losses:     3    |     1
Win Rate:  80%   |   67%
P&L:    +$8.50   | +$1.20
```

### Trades Table
- Columns: Time, Bot, Mode (REAL/PAPER tag), Asset, Direction, Entry, Size, Result, P&L
- REAL rows have green tag, PAPER rows have yellow tag
- Most recent first, limit 20

## Visual Theme

**Paper mode (default):**
- Background: `#0a0a0f`
- Cards: `#12121a`
- Borders: `#1a1a2e`
- Headers: `#00aaff`
- Positive: `#00ff88`
- Negative: `#ff4444`

**Live mode (any bot is live):**
- Background shifts to: `#0a0f0a` (dark green tint)
- Active bot card border: `#00ff88` glow
- Mode switch: pulses green

## Update Intervals

| Data | Interval |
|------|----------|
| Prices, signals, bot stats, trades, streak, cooldown, mode | 1 second |
| P&L chart history | 5 seconds |
| Wallet balance | 15 seconds |
| Hourly heatmap | 30 seconds |
| BTC candles | 60 seconds |

## Bot-Side Changes

Both `polybot5m.py` and `binancebot.py` need to:
1. Read `trading_mode` from their portfolio table at the start of each cycle
2. Use that value instead of `config.FIVEMIN_TRADING_MODE` / `config.BINANCE_TRADING_MODE`
3. Tag each trade with the current mode when inserting into the trades table

## Dependencies

No new dependencies. Uses existing: flask, flask-socketio, psutil, requests, py-clob-client.
Chart.js loaded from CDN.
