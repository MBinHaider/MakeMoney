# MBH Trading Bots Command Center — Design Spec

**Date**: 2026-04-05
**Status**: Approved
**Author**: Claude + Mohammad

## Overview

A rich CLI terminal dashboard that monitors all 3 trading bots (PolyBot 5M, BinanceBot, PolyBot) in real-time. Launched with a single command, prevents laptop from sleeping, and displays live charts, signals, trades, and analytics.

## Key Decisions

- **Name**: MBH Trading Bots Command Center
- **Scope**: All 3 bots — PolyBot 5M, BinanceBot, PolyBot
- **UI Library**: Python `rich` (terminal rendering with colors, tables, panels, live updates)
- **Charts**: `asciichartpy` for time-series P&L lines, custom block characters for candlesticks and heatmap
- **Sleep Prevention**: macOS `caffeinate` process spawned on startup
- **One-button start**: Single `python dashboard.py` command that launches bots + dashboard

## Architecture

```
dashboard.py                    <- main entry point (one command to start everything)
dashboard/
├── app.py                      <- Rich Live layout, 1-second refresh loop
├── panels/
│   ├── header.py               <- "MBH Trading Bots Command Center" + uptime + status
│   ├── bot_stats.py            <- 3 bot stat panels (balance, P&L, record, win%, mode badge)
│   ├── pnl_chart.py            <- 24h P&L time-series (combined + per-bot lines)
│   ├── price_chart.py          <- BTC candlestick chart
│   ├── signals.py              <- Live signal table (momentum, orderbook, volume per asset)
│   ├── orderbook.py            <- Bid/ask depth bars for best signal
│   ├── daily_comparison.py     <- Today vs yesterday vs best/worst day
│   ├── hour_heatmap.py         <- Win rate by hour (24 colored blocks)
│   ├── signal_hitrate.py       <- Funnel: generated → skipped → traded → won
│   ├── trades.py               <- Recent trades table (all bots, with mode column)
│   ├── cooldown_banner.py      <- Yellow alert bar when bot is paused
│   └── footer.py               <- Prices, next window timer, caffeinate status
└── data_reader.py              <- Reads from all 3 SQLite databases + live bot state
```

## Panels (top to bottom)

### 1. Header
- Title: "MBH Trading Bots Command Center"
- Subtitle: current UTC time, uptime, sleep lock status, "Press Q to quit"

### 2. Cooldown Banner (conditional)
- Only shown when PolyBot 5M is paused
- Yellow border, text: "PAUSED — 3 consecutive losses │ Resuming in MM:SS"
- Hidden when not in cooldown

### 3. Bot Stats Row (3 panels side by side)

**PolyBot 5M** (yellow border):
- Mode badge: PAPER (yellow) or LIVE (green)
- Balance, P&L, Record (W/L), Win%, Window countdown

**BinanceBot** (blue border):
- Mode badge: PAPER or LIVE
- Balance, P&L, Record, Win%, Open positions count

**PolyBot** (purple border):
- Mode badge: PAPER or LIVE
- Markets tracked, Active signals, Whales tracked

### 4. Charts Row (2 panels side by side)

**P&L Time Series (24h)**:
- 3 colored lines: Combined (green), 5M (yellow), BinanceBot (blue)
- Y-axis: dollar values, X-axis: time (00:00 to now)
- Library: `asciichartpy` for line rendering
- Data: query fm_trades and bn_trades, compute cumulative P&L per hour

**BTC Price Chart (12h)**:
- Candlestick-style using block characters (green/red bodies, thin wicks)
- Current price with dashed line marker
- Data: Binance kline API (1h candles) or from bot's market data

### 5. Daily Comparison + Hour Heatmap Row

**Daily P&L Comparison** (table):
- Rows: Today (bold), Yesterday, Best day, Worst day
- Columns: P&L, Trades, Win%, Best trade, Worst trade
- Data: fm_daily_stats + bn_trades grouped by date

**Win Rate by Hour Heatmap**:
- 24 colored blocks (00-23 UTC)
- Colors: dark gray (no data), red (<40%), medium green (40-70%), bright green (>70%)
- Data: fm_trades grouped by hour, compute win rate per hour
- Purpose: identifies best/worst trading hours for future time-slot filter

### 6. Signals + Orderbook + Hit Rate Row (3 panels)

**Live Signals Table**:
- Columns: Asset, Momentum, Orderbook, Volume, Signal, Confidence
- Rows: BTC, ETH, SOL
- Updated every second from bot's current state
- Data source: read live from PolyBot 5M's MarketState (shared memory or re-compute from DB)

**Orderbook Depth** (for best signal asset):
- Top 3 bids with green bars, top 3 asks with red bars
- Imbalance score at bottom
- Data: from PolyBot 5M's last orderbook fetch

**Signal Hit Rate** (today):
- Lines: Generated, Skipped (price), Skipped (risk), Traded, Won
- Visual funnel bar at bottom
- Data: fm_signals table (action_taken column) + fm_trades

### 7. Recent Trades Table
- Columns: Time, Bot, Mode, Asset, Direction, Entry, Size, Result, P&L, Confidence
- Bot column color-coded: 5M=yellow, BN=blue, POLY=purple
- Mode column: PAPER badge (yellow) or LIVE badge (green)
- Last 10 trades from all bots combined, sorted by time descending
- Data: fm_trades + bn_trades + bot_trades

### 8. Footer
- Left: Live prices (BTC, ETH, SOL) with green/red coloring
- Center: Next 5M window countdown
- Right: caffeinate PID status, all bots running status

## Data Flow

The dashboard does NOT run the bots. Bots run independently as separate processes. The dashboard reads from:

1. **SQLite databases**: `polybot5m.db`, `binancebot.db`, `polybot.db` — for trades, portfolio, signals, daily stats
2. **Binance REST API**: for current prices (simple GET, no auth needed)
3. **Process table**: check if bot PIDs are running via `psutil` or `os.kill(pid, 0)`
4. **Bot state files** (optional): bots can write a JSON state file with current signals/orderbook for live display

Refresh rate: 1 second for stats/signals, 5 seconds for charts, 30 seconds for daily/heatmap.

## One-Button Start

`python dashboard.py` does:
1. Check if bots are already running (by PID file or process name)
2. If not running, start them as background subprocesses
3. Spawn `caffeinate -d` to prevent display sleep
4. Launch the Rich Live dashboard
5. On Ctrl+C: stop dashboard (bots keep running), kill caffeinate

Optional flags:
- `python dashboard.py --bots-only` — start bots without dashboard
- `python dashboard.py --dashboard-only` — dashboard only, assume bots are running
- `python dashboard.py --stop` — stop all bots and dashboard

## Dependencies

- `rich` — terminal UI rendering (panels, tables, layouts, live updates)
- `asciichartpy` — ASCII line charts for P&L time series
- `psutil` — process management (check if bots running, get PIDs)

All lightweight, pure Python. No heavy frameworks.

## Sleep Prevention

On startup, dashboard spawns `caffeinate -d` (macOS) which prevents display sleep. PID tracked and shown in footer. Killed on dashboard exit.

Fallback for non-macOS: skip caffeinate, show "Sleep Lock: N/A" in footer.

## Terminal Requirements

- Minimum width: 120 columns (standard terminal)
- Minimum height: 40 rows
- True color support recommended (most modern terminals)
- Works in: Terminal.app, iTerm2, VS Code terminal
