"""
web_dashboard.py — MBH Trading Bots Web Dashboard V2
Flask + Socket.IO WebSocket dashboard with responsive layout, fixed charts,
live/paper mode toggle, paper vs real comparison, and wallet balance display.

Run:
    python web_dashboard.py
"""

import json
import os
import sqlite3
import sys
import time
import threading
from datetime import datetime, timezone

import requests
from flask import Flask, render_template_string
from flask_socketio import SocketIO

# ── Path setup ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import Config
from dashboard.data_reader import DashboardDataReader

# ── Config ─────────────────────────────────────────────────────────────────
config = Config()
reader = DashboardDataReader(
    config.FIVEMIN_DB_PATH, config.BINANCE_DB_PATH, config.DB_PATH
)
BINANCE_BASE = os.environ.get("BINANCE_API_URL", "https://data-api.binance.vision")
STATE_PATH = os.path.join(os.path.dirname(config.FIVEMIN_DB_PATH), "polybot5m_state.json")

# ── Flask + SocketIO ────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "mbh-trading-dashboard"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ── Shared state (updated by background threads) ───────────────────────────
_state = {
    "prices": {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0},
    "prev_prices": {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0},
    "btc_candles": [],
    "live_signals": None,
    "tick": 0,
    # DB-sourced (refreshed periodically)
    "fm": None,
    "bn": None,
    "trades": [],
    "cooldown": None,
    "pnl": None,
    "hourly": None,
    "hitrate": None,
    "daily": None,
    # Wallet balance
    "wallet_balance": None,
    "wallet_status": "disconnected",
    # Paper vs real comparison
    "paper_vs_real": None,
}
_lock = threading.Lock()


# ── Helper: bot process detection ─────────────────────────────────────────
def _bots_running() -> dict:
    result = {"5M": False, "BN": False, "PB": False}
    try:
        import psutil
        for proc in psutil.process_iter(["cmdline"]):
            try:
                cmd = " ".join(proc.info.get("cmdline") or [])
                if "polybot5m" in cmd and "web_dashboard" not in cmd:
                    result["5M"] = True
                elif "binancebot" in cmd and "web_dashboard" not in cmd:
                    result["BN"] = True
                elif "polybot.py" in cmd and "polybot5m" not in cmd and "web_dashboard" not in cmd:
                    result["PB"] = True
            except Exception:
                pass
    except Exception:
        pass
    return result


# ── Helper: ensure trading_mode column exists ─────────────────────────────
def _ensure_trading_mode_column(db_path: str, table: str):
    """Add trading_mode column if it doesn't exist."""
    try:
        from utils.db import get_connection
        conn = get_connection(db_path)
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN trading_mode TEXT DEFAULT 'paper'")
            conn.commit()
        except Exception:
            pass  # Column already exists
        conn.close()
    except Exception:
        pass


# ── Helper: ensure trade_mode column on trades tables ─────────────────────
def _ensure_trade_mode_column(db_path: str, table: str):
    """Add trade_mode column to trades table if it doesn't exist."""
    try:
        from utils.db import get_connection
        conn = get_connection(db_path)
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN trade_mode TEXT DEFAULT 'paper'")
            conn.commit()
        except Exception:
            pass  # Column already exists
        conn.close()
    except Exception:
        pass


# ── Helper: get paper vs real comparison stats ────────────────────────────
def _get_paper_vs_real() -> dict:
    """Query trade stats grouped by trade_mode from both DBs."""
    result = {"paper": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
              "real": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}}
    for db_path, trades_table in [(config.FIVEMIN_DB_PATH, "fm_trades"),
                                   (config.BINANCE_DB_PATH, "bn_trades")]:
        try:
            from utils.db import get_connection
            conn = get_connection(db_path)
            rows = conn.execute(
                f"SELECT trade_mode, COUNT(*) as trades, "
                f"SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins, "
                f"COALESCE(SUM(pnl), 0) as total_pnl "
                f"FROM {trades_table} GROUP BY trade_mode"
            ).fetchall()
            conn.close()
            for row in rows:
                r = dict(row)
                mode = r.get("trade_mode", "paper") or "paper"
                key = "real" if mode == "live" else "paper"
                result[key]["trades"] += r.get("trades", 0)
                result[key]["wins"] += r.get("wins", 0) or 0
                result[key]["pnl"] += r.get("total_pnl", 0) or 0
        except Exception:
            pass
    # Compute losses and win rates
    for key in ["paper", "real"]:
        t = result[key]["trades"]
        w = result[key]["wins"]
        result[key]["losses"] = t - w
        result[key]["win_rate"] = (w / t * 100) if t > 0 else 0.0
    return result


# ── Helper: get current trading mode from DB ──────────────────────────────
def _get_trading_mode(db_path: str, table: str) -> str:
    """Read trading_mode from portfolio table."""
    try:
        from utils.db import get_connection
        conn = get_connection(db_path)
        row = conn.execute(f"SELECT trading_mode FROM {table} WHERE id = 1").fetchone()
        conn.close()
        if row:
            return dict(row).get("trading_mode", "paper") or "paper"
    except Exception:
        pass
    return "paper"


# ── Data refresh ────────────────────────────────────────────────────────────
def _refresh_db(tick: int):
    """Read DB data on appropriate intervals."""
    with _lock:
        # Stats and trades every tick (1s)
        _state["fm"] = reader.get_fivemin_stats()
        _state["bn"] = reader.get_binance_stats()
        _state["cooldown"] = reader.get_cooldown_status()
        _state["trades"] = reader.get_recent_trades(limit=20)

        if tick % 5 == 0:
            _state["pnl"] = reader.get_pnl_history()
            _state["hitrate"] = reader.get_signal_hitrate()
            _state["paper_vs_real"] = _get_paper_vs_real()

        if tick % 30 == 0 or _state["hourly"] is None:
            _state["hourly"] = reader.get_hourly_winrate()
            _state["daily"] = reader.get_daily_comparison()

    # Live state file
    try:
        if os.path.exists(STATE_PATH) and time.time() - os.path.getmtime(STATE_PATH) < 10:
            with open(STATE_PATH) as f:
                with _lock:
                    _state["live_signals"] = json.load(f)
        else:
            with _lock:
                _state["live_signals"] = None
    except Exception:
        with _lock:
            _state["live_signals"] = None


def _fetch_prices():
    """Fetch BTC/ETH/SOL prices from Binance."""
    try:
        for symbol, asset in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]:
            r = requests.get(
                f"{BINANCE_BASE}/api/v3/ticker/price",
                params={"symbol": symbol},
                timeout=5,
            )
            if r.status_code == 200:
                price = float(r.json()["price"])
                with _lock:
                    _state["prev_prices"][asset] = _state["prices"][asset]
                    _state["prices"][asset] = price
    except Exception:
        pass


def _fetch_candles():
    """Fetch 24 hourly BTC candles from Binance."""
    try:
        r = requests.get(
            f"{BINANCE_BASE}/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1h", "limit": 24},
            timeout=10,
        )
        if r.status_code == 200:
            raw = r.json()
            candles = [
                {
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in raw
            ]
            with _lock:
                _state["btc_candles"] = candles
    except Exception:
        pass


def _fetch_wallet_balance():
    """Try to check wallet connection status."""
    try:
        if hasattr(config, 'PRIVATE_KEY') and config.PRIVATE_KEY:
            with _lock:
                _state["wallet_status"] = "connected"
        else:
            with _lock:
                _state["wallet_status"] = "no_key"
    except Exception:
        with _lock:
            _state["wallet_status"] = "disconnected"


# ── Background thread: push data every second ──────────────────────────────
def _background_loop():
    _fetch_prices()
    _fetch_candles()
    _fetch_wallet_balance()
    price_tick = 0
    candle_tick = 0
    wallet_tick = 0

    while True:
        tick = _state["tick"] + 1
        _state["tick"] = tick

        # DB refresh every tick
        _refresh_db(tick)

        # Prices every 1 second
        price_tick += 1
        if price_tick >= 1:
            _fetch_prices()
            price_tick = 0

        # Candles every 60 seconds
        candle_tick += 1
        if candle_tick >= 60:
            _fetch_candles()
            candle_tick = 0

        # Wallet balance every 15 seconds
        wallet_tick += 1
        if wallet_tick >= 15:
            _fetch_wallet_balance()
            wallet_tick = 0

        # Build payload and emit
        payload = _build_payload()
        socketio.emit("dashboard_update", payload)

        time.sleep(1)


def _build_payload() -> dict:
    with _lock:
        fm = _state["fm"] or {}
        bn = _state["bn"] or {}
        prices = dict(_state["prices"])
        prev = dict(_state["prev_prices"])
        candles = list(_state["btc_candles"])
        live_signals = _state["live_signals"]
        trades = list(_state["trades"])
        cooldown = _state["cooldown"] or {}
        pnl = _state["pnl"] or {"fivemin": [0, 0], "binance": [0, 0], "combined": [0, 0]}
        hourly = _state["hourly"] or [{"hour": h, "trades": 0, "wins": 0, "rate": 0.0} for h in range(24)]
        hitrate = _state["hitrate"] or {"generated": 0, "skipped_price": 0, "skipped_risk": 0, "traded": 0, "won": 0}
        daily = _state["daily"] or {}
        wallet_status = _state["wallet_status"]
        paper_vs_real = _state["paper_vs_real"] or {
            "paper": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "win_rate": 0.0},
            "real": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "win_rate": 0.0},
        }

    now = datetime.now(timezone.utc)
    now_ts = int(time.time())
    # Countdown to next 5-minute window
    wr = (now_ts - (now_ts % 300) + 300) - now_ts

    bots = _bots_running()

    # Read trading modes from DB
    fm_mode = _get_trading_mode(config.FIVEMIN_DB_PATH, "fm_portfolio")
    bn_mode = _get_trading_mode(config.BINANCE_DB_PATH, "bn_portfolio")

    # Price arrows
    price_data = {}
    for asset in ["BTC", "ETH", "SOL"]:
        p = prices[asset]
        pp = prev[asset]
        ch = p - pp
        price_data[asset] = {
            "price": p,
            "change": ch,
            "arrow": "▲" if ch > 0 else "▼" if ch < 0 else "─",
            "color": "green" if ch >= 0 else "red",
            "fmt": f"${p:,.0f}" if p > 100 else f"${p:.4f}",
        }

    # FM card extras
    fm_pnl = fm.get("pnl", 0)
    fm_start = fm.get("starting_balance", 0)
    fm_pct = (fm_pnl / fm_start * 100) if fm_start > 0 else 0
    fm_wins = fm.get("total_wins", 0)
    fm_trades = fm.get("total_trades", 0)
    fm_losses = fm_trades - fm_wins
    fm_wr = fm.get("win_rate", 0) * 100

    # BN card extras
    bn_pnl = bn.get("pnl", 0)
    bn_start = bn.get("starting_balance", 0)
    bn_pct = (bn_pnl / bn_start * 100) if bn_start > 0 else 0
    bn_wins = bn.get("total_wins", 0)
    bn_trades = bn.get("total_trades", 0)
    bn_losses = bn_trades - bn_wins
    bn_wr = bn.get("win_rate", 0) * 100

    # Daily stats
    today = daily.get("today", {})
    yesterday = daily.get("yesterday", {})

    # Hitrate
    gen = hitrate.get("generated", 0)
    skipped = hitrate.get("skipped_price", 0) + hitrate.get("skipped_risk", 0)
    traded = hitrate.get("traded", 0)
    won = hitrate.get("won", 0)

    # Signals
    signals = []
    if live_signals:
        signals = live_signals.get("signals", [])

    # Trades formatted
    trades_fmt = []
    for tr in trades:
        pnl_val = tr.get("pnl", 0) or 0
        entry = tr.get("entry", 0) or 0
        size = tr.get("size", 0) or 0
        trade_mode = tr.get("trade_mode", "paper") or "paper"
        trades_fmt.append({
            "time": tr.get("time", "")[-8:] if len(tr.get("time", "")) > 8 else tr.get("time", ""),
            "bot": tr.get("bot", ""),
            "asset": tr.get("asset", ""),
            "direction": tr.get("direction", ""),
            "entry": f"${entry:,.0f}" if entry > 100 else f"${entry:.4f}",
            "size": f"${size:.2f}",
            "result": tr.get("result", ""),
            "pnl": pnl_val,
            "pnl_fmt": f"+${pnl_val:.2f}" if pnl_val > 0 else f"${pnl_val:.2f}" if pnl_val < 0 else "\u2014",
            "trade_mode": trade_mode,
        })

    return {
        "time": now.strftime("%H:%M:%S UTC"),
        "date": now.strftime("%Y-%m-%d"),
        "bots": bots,
        "prices": price_data,
        "candles": candles,
        "pnl_chart": {
            "fivemin": pnl.get("fivemin", [0, 0])[-60:],
            "binance": pnl.get("binance", [0, 0])[-60:],
            "combined": pnl.get("combined", [0, 0])[-60:],
        },
        "hourly": hourly,
        "cooldown": cooldown,
        "fm": {
            "balance": fm.get("balance", 0),
            "pnl": fm_pnl,
            "pnl_pct": fm_pct,
            "wins": fm_wins,
            "losses": fm_losses,
            "trades": fm_trades,
            "win_rate": fm_wr,
            "mode": fm_mode,
            "is_paused": fm.get("is_paused", False),
            "daily_pnl": fm.get("daily_pnl", 0),
            "window_countdown": f"{wr // 60}:{wr % 60:02d}",
            "consecutive_losses": fm.get("consecutive_losses", 0),
        },
        "bn": {
            "balance": bn.get("balance", 0),
            "pnl": bn_pnl,
            "pnl_pct": bn_pct,
            "wins": bn_wins,
            "losses": bn_losses,
            "trades": bn_trades,
            "win_rate": bn_wr,
            "open_positions": bn.get("open_positions", 0),
            "mode": bn_mode,
            "is_paused": bn.get("is_paused", False),
            "daily_pnl": bn.get("daily_pnl", 0),
        },
        "streak": {
            "consecutive_losses": fm.get("consecutive_losses", 0),
            "total_trades": fm_trades,
        },
        "today": today,
        "yesterday": yesterday,
        "hitrate": {
            "generated": gen,
            "skipped": skipped,
            "traded": traded,
            "won": won,
        },
        "signals": signals,
        "trades": trades_fmt,
        "wallet_status": wallet_status,
        "paper_vs_real": paper_vs_real,
    }


# ── HTML template ───────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MBH Trading Bots Command Center</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
/* ── Reset & Base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:       #0a0a0f;
  --bg-live:  #0a0f0a;
  --card:     #12121a;
  --border:   #1a1a2e;
  --green:    #00ff88;
  --red:      #ff4444;
  --cyan:     #00aaff;
  --yellow:   #ffaa00;
  --dim:      #555;
  --text:     #e0e0e0;
  --text-dim: #888;
}
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  line-height: 1.5;
  width: 100vw;
  height: 100vh;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 8px;
  transition: background 0.5s ease;
}
body.live-mode {
  background: var(--bg-live);
}

/* ── Header ── */
#header {
  text-align: center;
  padding: 10px 0 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
#header h1 {
  font-size: 1.2em;
  color: var(--cyan);
  letter-spacing: 1px;
  margin-bottom: 4px;
}
#header .meta {
  color: var(--text-dim);
  font-size: 0.85em;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.bot-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.9em;
}
.dot { font-size: 0.75em; }
.dot.on  { color: var(--green); }
.dot.off { color: var(--red); }
.wallet-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: bold;
}
.wallet-connected { background: #003300; color: var(--green); border: 1px solid var(--green); }
.wallet-disconnected { background: #330000; color: var(--red); border: 1px solid var(--red); }
.wallet-nokey { background: #332200; color: var(--yellow); border: 1px solid var(--yellow); }

/* ── Cooldown Banner ── */
#cooldown-banner {
  background: #2d1b00;
  border: 1px solid var(--yellow);
  border-radius: 6px;
  padding: 8px 14px;
  text-align: center;
  color: var(--yellow);
  font-weight: bold;
  margin-bottom: 10px;
  display: none;
}

/* ── Grid Layout ── */
.grid-top {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 10px;
  margin-bottom: 10px;
}
.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.grid-3 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
@media (max-width: 900px) {
  .grid-top {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 600px) {
  .grid-top, .grid-2, .grid-3 {
    grid-template-columns: 1fr;
  }
}

/* ── Card ── */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  overflow: hidden;
  transition: border-color 0.3s, box-shadow 0.3s;
}
.card.live-glow {
  border-color: var(--green);
  box-shadow: 0 0 15px rgba(0, 255, 136, 0.3);
}
.card-title {
  color: var(--cyan);
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 6px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.badge {
  font-size: 0.75em;
  padding: 1px 7px;
  border-radius: 3px;
  font-weight: bold;
}
.badge-live  { background: #003300; color: var(--green); border: 1px solid var(--green); }
.badge-paper { background: #332200; color: var(--yellow); border: 1px solid var(--yellow); }

/* ── Mode Toggle Switch ── */
.mode-toggle-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}
.mode-label {
  font-size: 0.75em;
  text-transform: uppercase;
  font-weight: bold;
}
.mode-label.paper-label { color: var(--yellow); }
.mode-label.live-label { color: var(--green); }
.mode-switch {
  position: relative;
  width: 40px;
  height: 20px;
  cursor: pointer;
}
.mode-switch input { display: none; }
.mode-slider {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: #332200;
  border: 1px solid var(--yellow);
  border-radius: 10px;
  transition: background 0.3s, border-color 0.3s;
}
.mode-slider::before {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  left: 2px;
  top: 2px;
  background: var(--yellow);
  border-radius: 50%;
  transition: transform 0.3s, background 0.3s;
}
.mode-switch input:checked + .mode-slider {
  background: #003300;
  border-color: var(--green);
}
.mode-switch input:checked + .mode-slider::before {
  transform: translateX(20px);
  background: var(--green);
}
/* Pulse animation for live mode */
@keyframes pulse-glow {
  0%, 100% { box-shadow: 0 0 4px rgba(0, 255, 136, 0.4); }
  50% { box-shadow: 0 0 12px rgba(0, 255, 136, 0.8); }
}
.mode-switch.live-pulse .mode-slider {
  animation: pulse-glow 1.5s ease-in-out infinite;
}

/* ── Bot Card Stats ── */
.bot-balance {
  font-size: 1.4em;
  font-weight: bold;
  margin-bottom: 2px;
}
.bot-pnl { font-size: 1em; margin-bottom: 6px; }
.bot-row {
  display: flex;
  justify-content: space-between;
  color: var(--text-dim);
  font-size: 0.85em;
  margin-top: 2px;
}
.bot-row span:last-child { color: var(--text); }

/* ── Colors ── */
.green  { color: var(--green); }
.red    { color: var(--red); }
.yellow { color: var(--yellow); }
.cyan   { color: var(--cyan); }
.dim    { color: var(--text-dim); }

/* ── Prices ── */
.price-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 0.95em;
}
.price-asset { font-weight: bold; color: var(--text); min-width: 36px; }
.price-val   { font-weight: bold; font-size: 1.05em; }
.price-arrow { font-size: 0.85em; }

/* ── Charts ── */
.chart-wrap {
  position: relative;
  height: 140px;
  width: 100%;
}

/* ── Streak/Daily ── */
.streak-label { color: var(--text-dim); font-size: 0.85em; }
.streak-val   { font-weight: bold; font-size: 1.1em; }
.daily-row    { display: flex; justify-content: space-between; font-size: 0.85em; padding: 2px 0; }
.daily-row .lbl { color: var(--text-dim); }

/* ── Signal funnel ── */
.funnel-bar {
  height: 10px;
  border-radius: 4px;
  background: var(--border);
  margin-top: 6px;
  overflow: hidden;
  display: flex;
}
.funnel-won    { background: var(--green); }
.funnel-traded { background: var(--red); }

/* ── Heatmap ── */
.heatmap-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 4px;
}
.hm-cell {
  width: calc((100% - 69px) / 24);
  min-width: 24px;
  height: 28px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7em;
  font-weight: bold;
  color: var(--text);
  cursor: default;
}
.hm-none   { background: #161b22; color: var(--dim); }
.hm-high   { background: #26a641; color: #fff; }
.hm-mid    { background: #0e4429; }
.hm-low    { background: #da3633; }
.hm-legend { display: flex; gap: 10px; margin-top: 6px; font-size: 0.72em; color: var(--text-dim); align-items: center; flex-wrap: wrap; }
.hm-swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }

/* ── Signals ── */
.signal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.88em;
  flex-wrap: wrap;
}
.signal-row:last-child { border-bottom: none; }
.sig-asset { font-weight: bold; min-width: 32px; }
.sig-ind   { display: flex; gap: 3px; }
.sig-arrow { font-size: 1em; }
.sig-dir   { font-weight: bold; margin-left: 4px; }
.sig-conf  { color: var(--yellow); font-size: 0.85em; }
.up-color   { color: var(--green); }
.down-color { color: var(--red); }
.neut-color { color: var(--dim); }

/* ── Paper vs Real Comparison ── */
.compare-grid {
  display: grid;
  grid-template-columns: auto 1fr 1fr;
  gap: 0;
  font-size: 0.85em;
}
.compare-grid .compare-header {
  font-weight: bold;
  text-align: center;
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
}
.compare-grid .compare-label {
  color: var(--text-dim);
  padding: 3px 8px;
  border-right: 1px solid var(--border);
}
.compare-grid .compare-val {
  text-align: center;
  padding: 3px 8px;
  font-weight: bold;
}
.compare-paper-hdr { color: var(--yellow); }
.compare-real-hdr { color: var(--green); }

/* ── Trades Table ── */
.trades-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.82em; }
th {
  text-align: left;
  color: var(--cyan);
  border-bottom: 1px solid var(--border);
  padding: 5px 6px;
  font-size: 0.8em;
  text-transform: uppercase;
  white-space: nowrap;
}
td {
  padding: 4px 6px;
  border-bottom: 1px solid #0f0f18;
  white-space: nowrap;
}
tr:hover td { background: #15151f; }
.bot-5m   { color: var(--yellow); }
.bot-bn   { color: var(--cyan); }
.bot-poly { color: #cc88ff; }
.res-win  { color: var(--green); font-weight: bold; }
.res-loss { color: var(--red); font-weight: bold; }
.res-open { color: var(--yellow); }
.res-pend { color: var(--dim); }
.pnl-pos  { color: var(--green); }
.pnl-neg  { color: var(--red); }
.pnl-zero { color: var(--dim); }
/* Mode tags in trades table */
.mode-tag {
  display: inline-block;
  font-size: 0.75em;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: bold;
}
.mode-tag-real { background: #003300; color: var(--green); border: 1px solid var(--green); }
.mode-tag-paper { background: #332200; color: var(--yellow); border: 1px solid var(--yellow); }

/* ── Connection indicator ── */
#conn-dot {
  position: fixed;
  top: 8px;
  right: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--red);
  transition: background 0.3s;
  z-index: 100;
}
#conn-dot.connected { background: var(--green); }

/* ── Footer ── */
#footer {
  text-align: center;
  color: var(--dim);
  font-size: 0.75em;
  margin-top: 14px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
</style>
</head>
<body>

<div id="conn-dot" title="WebSocket connection"></div>

<!-- Header -->
<div id="header">
  <h1>&#9889; MBH Trading Bots Command Center &#9889;</h1>
  <div class="meta">
    <span id="utc-time">--:--:-- UTC</span>
    <span class="bot-indicator">5M <span id="dot-5m" class="dot off">&#9679;</span></span>
    <span class="bot-indicator">BN <span id="dot-bn" class="dot off">&#9679;</span></span>
    <span class="bot-indicator">PB <span id="dot-pb" class="dot off">&#9679;</span></span>
    <span id="wallet-display" class="wallet-badge wallet-disconnected">Wallet: --</span>
  </div>
</div>

<!-- Cooldown Banner -->
<div id="cooldown-banner">
  &#9208; PAUSED &mdash; <span id="cd-losses"></span> consecutive losses &nbsp;|&nbsp; Resume in: <span id="cd-timer"></span>
</div>

<!-- Row 1: Bot cards + Prices -->
<div class="grid-top">

  <!-- PolyBot 5M -->
  <div class="card" id="fm-card">
    <div class="card-title">
      <span>&#9889; POLYBOT 5M</span>
      <div class="mode-toggle-wrap">
        <span id="fm-badge" class="badge badge-paper">PAPER</span>
        <label class="mode-switch" id="fm-switch">
          <input type="checkbox" id="fm-toggle" onchange="handleModeSwitch('5m', this)">
          <span class="mode-slider"></span>
        </label>
      </div>
    </div>
    <div class="bot-balance" id="fm-balance">$0.00</div>
    <div class="bot-pnl dim" id="fm-pnl">+$0.00 (0.0%)</div>
    <div class="bot-row"><span>Win / Loss</span><span id="fm-wl">0W 0L</span></div>
    <div class="bot-row"><span>Win Rate</span><span id="fm-wr">0%</span></div>
    <div class="bot-row"><span>Daily P&L</span><span id="fm-daily">$0.00</span></div>
    <div class="bot-row"><span>Next Window</span><span id="fm-window" class="yellow">0:00</span></div>
  </div>

  <!-- BinanceBot -->
  <div class="card" id="bn-card">
    <div class="card-title">
      <span>&#128202; BINANCEBOT</span>
      <div class="mode-toggle-wrap">
        <span id="bn-badge" class="badge badge-paper">PAPER</span>
        <label class="mode-switch" id="bn-switch">
          <input type="checkbox" id="bn-toggle" onchange="handleModeSwitch('bn', this)">
          <span class="mode-slider"></span>
        </label>
      </div>
    </div>
    <div class="bot-balance" id="bn-balance">$0.00</div>
    <div class="bot-pnl dim" id="bn-pnl">+$0.00 (0.0%)</div>
    <div class="bot-row"><span>Win / Loss</span><span id="bn-wl">0W 0L</span></div>
    <div class="bot-row"><span>Win Rate</span><span id="bn-wr">0%</span></div>
    <div class="bot-row"><span>Daily P&L</span><span id="bn-daily">$0.00</span></div>
    <div class="bot-row"><span>Open Positions</span><span id="bn-open" class="yellow">0</span></div>
  </div>

  <!-- Prices -->
  <div class="card">
    <div class="card-title">Prices</div>
    <div class="price-row">
      <span class="price-asset">BTC</span>
      <span class="price-val" id="p-btc">$0</span>
      <span class="price-arrow" id="a-btc">&#8212;</span>
    </div>
    <div class="price-row">
      <span class="price-asset">ETH</span>
      <span class="price-val" id="p-eth">$0</span>
      <span class="price-arrow" id="a-eth">&#8212;</span>
    </div>
    <div class="price-row">
      <span class="price-asset">SOL</span>
      <span class="price-val" id="p-sol">$0</span>
      <span class="price-arrow" id="a-sol">&#8212;</span>
    </div>
  </div>
</div>

<!-- Row 2: P&L Chart + BTC Chart -->
<div class="grid-2">
  <div class="card">
    <div class="card-title">P&L Chart (24h)</div>
    <div class="chart-wrap">
      <canvas id="pnl-chart"></canvas>
    </div>
    <div style="margin-top:5px;font-size:0.75em;display:flex;gap:12px;">
      <span><span style="color:#00ff88">&#9135;</span> Combined</span>
      <span><span style="color:#ffaa00">&#9135;</span> 5M</span>
      <span><span style="color:#00aaff">&#9135;</span> Binance</span>
    </div>
  </div>
  <div class="card">
    <div class="card-title">BTC/USD (1h candles)</div>
    <div class="chart-wrap">
      <canvas id="btc-chart"></canvas>
    </div>
  </div>
</div>

<!-- Row 3: Streak/Daily + Signal Accuracy + Heatmap -->
<div class="grid-3">

  <!-- Streak & Daily -->
  <div class="card">
    <div class="card-title">Streak &amp; Daily</div>
    <div style="margin-bottom:8px;">
      <div class="streak-label">Current Streak</div>
      <div class="streak-val" id="streak-val">No trades yet</div>
    </div>
    <div class="daily-row"><span class="lbl">Today P&L</span><span id="today-pnl">$0.00</span></div>
    <div class="daily-row"><span class="lbl">Today Trades</span><span id="today-trades">0</span></div>
    <div class="daily-row"><span class="lbl">Today Win Rate</span><span id="today-wr">0%</span></div>
    <div class="daily-row" style="margin-top:4px;"><span class="lbl">Yesterday P&L</span><span id="yest-pnl">$0.00</span></div>
    <div class="daily-row"><span class="lbl">Yesterday Trades</span><span id="yest-trades">0</span></div>
  </div>

  <!-- Signal Accuracy -->
  <div class="card">
    <div class="card-title">Signal Accuracy</div>
    <div class="daily-row"><span class="lbl">Generated</span><span id="sig-gen" class="cyan">0</span></div>
    <div class="daily-row"><span class="lbl">Skipped</span><span id="sig-skip" class="yellow">0</span></div>
    <div class="daily-row"><span class="lbl">Traded</span><span id="sig-traded" class="cyan">0</span></div>
    <div class="daily-row"><span class="lbl">Won</span><span id="sig-won">&mdash;</span></div>
    <div class="funnel-bar" id="funnel-bar">
      <div class="funnel-won"  id="funnel-won-w"  style="width:0%"></div>
      <div class="funnel-traded" id="funnel-traded-w" style="width:0%"></div>
    </div>
    <div style="margin-top:5px;font-size:0.72em;color:var(--text-dim);display:flex;gap:8px;">
      <span><span style="color:var(--green)">&#9608;</span> Won</span>
      <span><span style="color:var(--red)">&#9608;</span> Loss</span>
      <span><span style="color:var(--dim)">&#9617;</span> Skipped</span>
    </div>
  </div>

  <!-- Heatmap -->
  <div class="card">
    <div class="card-title">Win Rate by Hour (UTC)</div>
    <div class="heatmap-grid" id="heatmap"></div>
    <div class="hm-legend">
      <span><span class="hm-swatch" style="background:#161b22"></span> None</span>
      <span><span class="hm-swatch" style="background:#da3633"></span> &lt;40%</span>
      <span><span class="hm-swatch" style="background:#0e4429"></span> 40-70%</span>
      <span><span class="hm-swatch" style="background:#26a641"></span> &gt;70%</span>
    </div>
  </div>
</div>

<!-- Live Signals -->
<div class="card" id="signals-card" style="margin-bottom:10px;display:none;">
  <div class="card-title" style="color:var(--cyan);">&#128225; Live Signals</div>
  <div id="signals-list"></div>
</div>

<!-- Paper vs Real Comparison -->
<div class="card" id="compare-card" style="margin-bottom:10px;">
  <div class="card-title">Paper vs Real Comparison</div>
  <div class="compare-grid" id="compare-grid">
    <div class="compare-label" style="border-bottom:1px solid var(--border);">&nbsp;</div>
    <div class="compare-header compare-paper-hdr" style="border-bottom:1px solid var(--border);">PAPER</div>
    <div class="compare-header compare-real-hdr" style="border-bottom:1px solid var(--border);">REAL</div>
    <div class="compare-label">Trades</div>
    <div class="compare-val" id="cmp-paper-trades">0</div>
    <div class="compare-val" id="cmp-real-trades">0</div>
    <div class="compare-label">Wins</div>
    <div class="compare-val" id="cmp-paper-wins">0</div>
    <div class="compare-val" id="cmp-real-wins">0</div>
    <div class="compare-label">Losses</div>
    <div class="compare-val" id="cmp-paper-losses">0</div>
    <div class="compare-val" id="cmp-real-losses">0</div>
    <div class="compare-label">Win Rate</div>
    <div class="compare-val" id="cmp-paper-wr">0%</div>
    <div class="compare-val" id="cmp-real-wr">0%</div>
    <div class="compare-label">P&L</div>
    <div class="compare-val" id="cmp-paper-pnl">$0.00</div>
    <div class="compare-val" id="cmp-real-pnl">$0.00</div>
  </div>
</div>

<!-- Trades Table -->
<div class="card" style="margin-bottom:10px;">
  <div class="card-title">Recent Trades</div>
  <div class="trades-wrap">
    <table id="trades-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>Bot</th>
          <th>Mode</th>
          <th>Asset</th>
          <th>Dir</th>
          <th>Entry</th>
          <th>Size</th>
          <th>Result</th>
          <th>P&amp;L</th>
        </tr>
      </thead>
      <tbody id="trades-body">
        <tr><td colspan="9" class="dim" style="text-align:center;padding:12px;">Waiting for trades...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div id="footer">MBH Trading Bots Command Center &bull; Dashboard V2 &bull; WebSocket live &bull; Port 8080</div>

<script>
// ── Socket.IO ─────────────────────────────────────────────────────────────
const socket = io();
const connDot = document.getElementById('conn-dot');

socket.on('connect',    () => connDot.classList.add('connected'));
socket.on('disconnect', () => connDot.classList.remove('connected'));

// ── Mode Switch Handler ──────────────────────────────────────────────────
function handleModeSwitch(bot, checkbox) {
  const newMode = checkbox.checked ? 'live' : 'paper';
  if (newMode === 'live') {
    if (!confirm('Switch to REAL MONEY trading?')) {
      checkbox.checked = false;
      return;
    }
  }
  const botKey = bot === '5m' ? '5m' : 'bn';
  socket.emit('switch_mode', { bot: botKey, mode: newMode });
}

// ── Chart instances ───────────────────────────────────────────────────────
let pnlChart = null;
let btcChart  = null;

function initPnlChart() {
  const ctx = document.getElementById('pnl-chart').getContext('2d');
  pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Combined', data: [], borderColor: '#00ff88', backgroundColor: 'transparent', borderWidth: 1.5, pointRadius: 0, tension: 0.3 },
        { label: '5M',       data: [], borderColor: '#ffaa00', backgroundColor: 'transparent', borderWidth: 1,   pointRadius: 0, tension: 0.3 },
        { label: 'Binance',  data: [], borderColor: '#00aaff', backgroundColor: 'transparent', borderWidth: 1,   pointRadius: 0, tension: 0.3 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
      scales: {
        x: { display: false },
        y: {
          grid: { color: '#1a1a2e' },
          ticks: { color: '#888', font: { size: 10 }, callback: v => '$' + v.toFixed(2) },
        },
      },
    },
  });
}

function initBtcChart() {
  const ctx = document.getElementById('btc-chart').getContext('2d');
  btcChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderColor: [], borderWidth: 1 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: {
        callbacks: {
          title: (items) => items[0] ? items[0].label : '',
          label: (ctx) => {
            const idx = ctx.dataIndex;
            const meta = btcChart._candleMeta || [];
            if (meta[idx]) {
              const m = meta[idx];
              return ['O: $' + m.o.toLocaleString(), 'H: $' + m.h.toLocaleString(), 'L: $' + m.l.toLocaleString(), 'C: $' + m.c.toLocaleString()];
            }
            return '$' + (ctx.parsed.y || 0).toLocaleString();
          }
        }
      }},
      scales: {
        x: { display: false },
        y: {
          grid: { color: '#1a1a2e' },
          ticks: { color: '#888', font: { size: 10 }, callback: v => '$' + v.toLocaleString() },
        },
      },
    },
  });
  btcChart._candleMeta = [];
}

initPnlChart();
initBtcChart();

// ── Utility ───────────────────────────────────────────────────────────────
function pnlClass(v) { return v > 0 ? 'green' : v < 0 ? 'red' : 'dim'; }
function pnlFmt(v)   { return (v >= 0 ? '+' : '') + '$' + Math.abs(v).toFixed(2); }
function setText(id, txt, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = txt;
  if (cls !== undefined) { el.className = cls; }
}

// Track current modes to avoid flicker on toggle
let currentFmMode = 'paper';
let currentBnMode = 'paper';

// ── Main update handler ───────────────────────────────────────────────────
socket.on('dashboard_update', function(d) {
  // Header
  setText('utc-time', d.time);

  // Bot dots
  const dots = { '5m': d.bots['5M'], 'bn': d.bots['BN'], 'pb': d.bots['PB'] };
  for (const [k, on] of Object.entries(dots)) {
    const el = document.getElementById('dot-' + k);
    if (el) { el.className = 'dot ' + (on ? 'on' : 'off'); }
  }

  // Wallet display
  const walletEl = document.getElementById('wallet-display');
  if (walletEl) {
    const ws = d.wallet_status || 'disconnected';
    if (ws === 'connected') {
      walletEl.textContent = 'Wallet: Connected';
      walletEl.className = 'wallet-badge wallet-connected';
    } else if (ws === 'no_key') {
      walletEl.textContent = 'Wallet: No Key';
      walletEl.className = 'wallet-badge wallet-nokey';
    } else {
      walletEl.textContent = 'Wallet: --';
      walletEl.className = 'wallet-badge wallet-disconnected';
    }
  }

  // Cooldown banner
  const cd = d.cooldown || {};
  const cdBanner = document.getElementById('cooldown-banner');
  if (cd.active && cd.seconds_remaining > 0) {
    cdBanner.style.display = 'block';
    setText('cd-losses', cd.consecutive_losses);
    const s = cd.seconds_remaining;
    setText('cd-timer', Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'));
  } else {
    cdBanner.style.display = 'none';
  }

  // PolyBot 5M card
  const fm = d.fm || {};
  const fmPnl = fm.pnl || 0;
  const fmMode = fm.mode || 'paper';
  currentFmMode = fmMode;

  const fmBadge = document.getElementById('fm-badge');
  if (fmBadge) {
    fmBadge.textContent = fmMode.toUpperCase();
    fmBadge.className = 'badge ' + (fmMode === 'live' ? 'badge-live' : 'badge-paper');
  }
  // Sync toggle state without triggering onchange
  const fmToggle = document.getElementById('fm-toggle');
  if (fmToggle && fmToggle !== document.activeElement) {
    fmToggle.checked = (fmMode === 'live');
  }
  // Toggle pulse class
  const fmSwitch = document.getElementById('fm-switch');
  if (fmSwitch) {
    if (fmMode === 'live') { fmSwitch.classList.add('live-pulse'); }
    else { fmSwitch.classList.remove('live-pulse'); }
  }
  // Card glow
  const fmCard = document.getElementById('fm-card');
  if (fmCard) {
    if (fmMode === 'live') { fmCard.classList.add('live-glow'); }
    else { fmCard.classList.remove('live-glow'); }
  }

  const fmBalEl = document.getElementById('fm-balance');
  if (fmBalEl) {
    fmBalEl.textContent = '$' + (fm.balance || 0).toFixed(2);
    fmBalEl.className = 'bot-balance ' + pnlClass(fm.balance - (fm.starting_balance || 0));
  }
  const fmPnlEl = document.getElementById('fm-pnl');
  if (fmPnlEl) {
    fmPnlEl.textContent = (fmPnl >= 0 ? '+' : '') + '$' + Math.abs(fmPnl).toFixed(2) + ' (' + (fm.pnl_pct >= 0 ? '+' : '') + (fm.pnl_pct || 0).toFixed(1) + '%)';
    fmPnlEl.className = 'bot-pnl ' + pnlClass(fmPnl);
  }
  setText('fm-wl', (fm.wins || 0) + 'W ' + (fm.losses || 0) + 'L');
  const fmWr = fm.win_rate || 0;
  const fmWrEl = document.getElementById('fm-wr');
  if (fmWrEl) {
    fmWrEl.textContent = fmWr.toFixed(1) + '%';
    fmWrEl.style.color = fmWr >= 50 ? 'var(--green)' : (fm.trades || 0) > 0 ? 'var(--red)' : 'var(--dim)';
  }
  const fmDailyEl = document.getElementById('fm-daily');
  if (fmDailyEl) {
    const dp = fm.daily_pnl || 0;
    fmDailyEl.textContent = (dp >= 0 ? '+' : '') + '$' + Math.abs(dp).toFixed(2);
    fmDailyEl.className = pnlClass(dp);
  }
  setText('fm-window', fm.window_countdown || '0:00');

  // BinanceBot card
  const bn = d.bn || {};
  const bnPnl = bn.pnl || 0;
  const bnMode = bn.mode || 'paper';
  currentBnMode = bnMode;

  const bnBadge = document.getElementById('bn-badge');
  if (bnBadge) {
    bnBadge.textContent = bnMode.toUpperCase();
    bnBadge.className = 'badge ' + (bnMode === 'live' ? 'badge-live' : 'badge-paper');
  }
  const bnToggle = document.getElementById('bn-toggle');
  if (bnToggle && bnToggle !== document.activeElement) {
    bnToggle.checked = (bnMode === 'live');
  }
  const bnSwitch = document.getElementById('bn-switch');
  if (bnSwitch) {
    if (bnMode === 'live') { bnSwitch.classList.add('live-pulse'); }
    else { bnSwitch.classList.remove('live-pulse'); }
  }
  const bnCard = document.getElementById('bn-card');
  if (bnCard) {
    if (bnMode === 'live') { bnCard.classList.add('live-glow'); }
    else { bnCard.classList.remove('live-glow'); }
  }

  const bnBalEl = document.getElementById('bn-balance');
  if (bnBalEl) {
    bnBalEl.textContent = '$' + (bn.balance || 0).toFixed(2);
  }
  const bnPnlEl = document.getElementById('bn-pnl');
  if (bnPnlEl) {
    bnPnlEl.textContent = (bnPnl >= 0 ? '+' : '') + '$' + Math.abs(bnPnl).toFixed(2) + ' (' + (bn.pnl_pct >= 0 ? '+' : '') + (bn.pnl_pct || 0).toFixed(1) + '%)';
    bnPnlEl.className = 'bot-pnl ' + pnlClass(bnPnl);
  }
  setText('bn-wl', (bn.wins || 0) + 'W ' + (bn.losses || 0) + 'L');
  const bnWr = bn.win_rate || 0;
  const bnWrEl = document.getElementById('bn-wr');
  if (bnWrEl) {
    bnWrEl.textContent = bnWr.toFixed(1) + '%';
    bnWrEl.style.color = bnWr >= 50 ? 'var(--green)' : (bn.trades || 0) > 0 ? 'var(--red)' : 'var(--dim)';
  }
  const bnDailyEl = document.getElementById('bn-daily');
  if (bnDailyEl) {
    const dp = bn.daily_pnl || 0;
    bnDailyEl.textContent = (dp >= 0 ? '+' : '') + '$' + Math.abs(dp).toFixed(2);
    bnDailyEl.className = pnlClass(dp);
  }
  setText('bn-open', bn.open_positions || 0);

  // Live mode body background
  if (fmMode === 'live' || bnMode === 'live') {
    document.body.classList.add('live-mode');
  } else {
    document.body.classList.remove('live-mode');
  }

  // Prices
  const assets = { btc: 'BTC', eth: 'ETH', sol: 'SOL' };
  for (const [key, sym] of Object.entries(assets)) {
    const pd = (d.prices || {})[sym] || {};
    const pEl = document.getElementById('p-' + key);
    const aEl = document.getElementById('a-' + key);
    if (pEl) {
      pEl.textContent = pd.fmt || '$0';
      pEl.className = 'price-val ' + (pd.color || '');
    }
    if (aEl) {
      aEl.textContent = pd.arrow || '\u2014';
      aEl.className = 'price-arrow ' + (pd.color || '');
    }
  }

  // P&L Chart - handle empty/single data points by padding with zeros
  const pc = d.pnl_chart || {};
  let combined = pc.combined || [];
  let fm5m     = pc.fivemin  || [];
  let binance  = pc.binance  || [];
  // Pad to at least 2 points for the chart to render a line
  if (combined.length < 2) combined = [0, ...combined, ...(combined.length === 0 ? [0] : [])];
  if (fm5m.length < 2) fm5m = [0, ...fm5m, ...(fm5m.length === 0 ? [0] : [])];
  if (binance.length < 2) binance = [0, ...binance, ...(binance.length === 0 ? [0] : [])];
  const maxLen   = Math.max(combined.length, fm5m.length, binance.length);
  // Pad shorter arrays with zeros at the beginning
  while (combined.length < maxLen) combined.unshift(0);
  while (fm5m.length < maxLen) fm5m.unshift(0);
  while (binance.length < maxLen) binance.unshift(0);
  const labels   = Array.from({ length: maxLen }, (_, i) => i + 1);
  if (pnlChart) {
    pnlChart.data.labels            = labels;
    pnlChart.data.datasets[0].data  = combined;
    pnlChart.data.datasets[1].data  = fm5m;
    pnlChart.data.datasets[2].data  = binance;
    pnlChart.update('none');
  }

  // BTC Chart - bar chart styled as candles (green=up, red=down)
  const candles = d.candles || [];
  if (btcChart && candles.length > 0) {
    const labels24 = candles.map((_, i) => {
      const h = new Date();
      h.setUTCHours(h.getUTCHours() - (candles.length - 1 - i));
      return h.getUTCHours() + ':00';
    });

    // Each bar represents the open-close range
    const barData = candles.map(c => {
      const bodyTop = Math.max(c.open, c.close);
      const bodyBottom = Math.min(c.open, c.close);
      return bodyTop - bodyBottom;  // bar height = absolute body size
    });

    const bgColors = candles.map(c => c.close >= c.open ? 'rgba(0,255,136,0.7)' : 'rgba(255,68,68,0.7)');
    const brdColors = candles.map(c => c.close >= c.open ? '#00ff88' : '#ff4444');

    // Store OHLC metadata for tooltips
    btcChart._candleMeta = candles.map(c => ({ o: c.open, h: c.high, l: c.low, c: c.close }));

    btcChart.data.labels = labels24;
    btcChart.data.datasets[0].data = barData;
    btcChart.data.datasets[0].backgroundColor = bgColors;
    btcChart.data.datasets[0].borderColor = brdColors;

    // Set y-axis to show body range context
    const allBodies = candles.map(c => Math.abs(c.close - c.open));
    const maxBody = Math.max(...allBodies);
    btcChart.options.scales.y.min = 0;
    btcChart.options.scales.y.max = maxBody * 1.2;
    btcChart.options.scales.y.ticks.callback = v => '$' + v.toFixed(0);
    btcChart.update('none');
  }

  // Streak & Daily
  const streak = d.streak || {};
  const strEl = document.getElementById('streak-val');
  if (strEl) {
    const cl = streak.consecutive_losses || 0;
    const tt = streak.total_trades || 0;
    if (cl > 0) {
      strEl.textContent = 'L' + cl + ' losing';
      strEl.className = 'streak-val red';
    } else if (tt > 0) {
      strEl.textContent = 'Winning';
      strEl.className = 'streak-val green';
    } else {
      strEl.textContent = 'No trades yet';
      strEl.className = 'streak-val dim';
    }
  }
  const today = d.today || {};
  const yest  = d.yesterday || {};
  const tdPnl = today.pnl || 0;
  const tdWr  = today.win_rate || 0;
  const ydPnl = yest.pnl || 0;
  const tdPnlEl = document.getElementById('today-pnl');
  if (tdPnlEl) {
    tdPnlEl.textContent = (tdPnl >= 0 ? '+' : '') + '$' + Math.abs(tdPnl).toFixed(2);
    tdPnlEl.className = pnlClass(tdPnl);
  }
  setText('today-trades', today.trades || 0);
  const tdWrEl = document.getElementById('today-wr');
  if (tdWrEl) {
    tdWrEl.textContent = (tdWr * 100).toFixed(1) + '%';
    tdWrEl.className = pnlClass(tdWr - 0.5);
  }
  const ydPnlEl = document.getElementById('yest-pnl');
  if (ydPnlEl) {
    ydPnlEl.textContent = (ydPnl >= 0 ? '+' : '') + '$' + Math.abs(ydPnl).toFixed(2);
    ydPnlEl.className = pnlClass(ydPnl);
  }
  setText('yest-trades', yest.trades || 0);

  // Signal Accuracy
  const hr = d.hitrate || {};
  const gen     = hr.generated || 0;
  const skipped = hr.skipped   || 0;
  const traded  = hr.traded    || 0;
  const won     = hr.won       || 0;
  setText('sig-gen',    gen);
  setText('sig-skip',   skipped);
  setText('sig-traded', traded);
  const sigWonEl = document.getElementById('sig-won');
  if (sigWonEl) {
    if (traded > 0) {
      sigWonEl.textContent = won + '/' + traded + ' (' + (won / traded * 100).toFixed(0) + '%)';
      sigWonEl.className   = won / traded >= 0.5 ? 'green' : 'red';
    } else {
      sigWonEl.textContent = '\u2014';
      sigWonEl.className   = 'dim';
    }
  }
  // Funnel bar
  if (gen > 0) {
    const wonW     = Math.round(won     / gen * 100);
    const tradedW  = Math.round(traded  / gen * 100) - wonW;
    const ww = document.getElementById('funnel-won-w');
    const tw = document.getElementById('funnel-traded-w');
    if (ww) ww.style.width = wonW + '%';
    if (tw) tw.style.width = Math.max(0, tradedW) + '%';
  }

  // Heatmap
  const hm = document.getElementById('heatmap');
  if (hm && d.hourly) {
    hm.innerHTML = '';
    for (const h of d.hourly) {
      const cell = document.createElement('div');
      cell.className = 'hm-cell ';
      if (h.trades === 0)      cell.className += 'hm-none';
      else if (h.rate >= 0.7)  cell.className += 'hm-high';
      else if (h.rate >= 0.4)  cell.className += 'hm-mid';
      else                     cell.className += 'hm-low';
      cell.textContent = String(h.hour).padStart(2, '0');
      const tooltip = h.trades === 0
        ? 'Hour ' + h.hour + ': No trades'
        : 'Hour ' + h.hour + ': ' + h.wins + '/' + h.trades + ' (' + (h.rate * 100).toFixed(0) + '%)';
      cell.title = tooltip;
      hm.appendChild(cell);
    }
  }

  // Live Signals
  const sigsCard = document.getElementById('signals-card');
  const sigsList = document.getElementById('signals-list');
  const sigs = d.signals || [];
  if (sigs.length > 0 && sigsCard && sigsList) {
    sigsCard.style.display = 'block';
    sigsList.innerHTML = '';
    for (const s of sigs) {
      const row = document.createElement('div');
      row.className = 'signal-row';
      const assetColors = { BTC: '#f7931a', ETH: '#627eea', SOL: '#00ffa3' };
      const ac = assetColors[s.asset] || '#fff';

      const indHtml = ['momentum', 'orderbook', 'volume'].map(k => {
        const v = s[k] || '';
        if (v === 'UP')   return '<span class="sig-arrow up-color">&#8593;</span>';
        if (v === 'DOWN') return '<span class="sig-arrow down-color">&#8595;</span>';
        return '<span class="sig-arrow neut-color">&middot;</span>';
      }).join('');

      let dirHtml = '';
      if (s.signal) {
        const dc = s.signal === 'UP' ? 'green' : 'red';
        const agree = s.agree_count || 0;
        const conf  = ((s.confidence || 0) * 100).toFixed(0);
        dirHtml = '<span class="sig-dir ' + dc + '">' + agree + '/3 ' + s.signal + '</span><span class="sig-conf"> (' + conf + '%)</span>';
      }

      row.innerHTML = '<span class="sig-asset" style="color:' + ac + '">' + s.asset + '</span>' +
        '<span class="sig-ind">' + indHtml + '</span>' + dirHtml;
      sigsList.appendChild(row);
    }
  } else if (sigsCard) {
    sigsCard.style.display = 'none';
  }

  // Paper vs Real Comparison
  const pvr = d.paper_vs_real || {};
  const paper = pvr.paper || {};
  const real = pvr.real || {};
  setText('cmp-paper-trades', paper.trades || 0);
  setText('cmp-real-trades', real.trades || 0);
  setText('cmp-paper-wins', paper.wins || 0);
  setText('cmp-real-wins', real.wins || 0);
  setText('cmp-paper-losses', paper.losses || 0);
  setText('cmp-real-losses', real.losses || 0);
  const paperWr = paper.win_rate || 0;
  const realWr = real.win_rate || 0;
  const paperWrEl = document.getElementById('cmp-paper-wr');
  if (paperWrEl) {
    paperWrEl.textContent = paperWr.toFixed(1) + '%';
    paperWrEl.className = 'compare-val ' + ((paper.trades || 0) > 0 ? (paperWr >= 50 ? 'green' : 'red') : 'dim');
  }
  const realWrEl = document.getElementById('cmp-real-wr');
  if (realWrEl) {
    realWrEl.textContent = realWr.toFixed(1) + '%';
    realWrEl.className = 'compare-val ' + ((real.trades || 0) > 0 ? (realWr >= 50 ? 'green' : 'red') : 'dim');
  }
  const paperPnlEl = document.getElementById('cmp-paper-pnl');
  if (paperPnlEl) {
    const pp = paper.pnl || 0;
    paperPnlEl.textContent = pnlFmt(pp);
    paperPnlEl.className = 'compare-val ' + pnlClass(pp);
  }
  const realPnlEl = document.getElementById('cmp-real-pnl');
  if (realPnlEl) {
    const rp = real.pnl || 0;
    realPnlEl.textContent = pnlFmt(rp);
    realPnlEl.className = 'compare-val ' + pnlClass(rp);
  }

  // Trades Table with Mode column
  const tbody = document.getElementById('trades-body');
  if (tbody) {
    const trades = d.trades || [];
    if (trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="dim" style="text-align:center;padding:12px;">Waiting for trades...</td></tr>';
    } else {
      tbody.innerHTML = '';
      for (const tr of trades) {
        const botCls = tr.bot === '5M' ? 'bot-5m' : tr.bot === 'BN' ? 'bot-bn' : 'bot-poly';
        const resCls = tr.result === 'win' ? 'res-win' : tr.result === 'loss' ? 'res-loss' : tr.result === 'open' ? 'res-open' : 'res-pend';
        const resLabel = tr.result === 'win' ? 'WIN' : tr.result === 'loss' ? 'LOSS' : tr.result === 'open' ? 'OPEN' : '...';
        const pnlCls = tr.pnl > 0 ? 'pnl-pos' : tr.pnl < 0 ? 'pnl-neg' : 'pnl-zero';
        const dirArrow = tr.direction === 'LONG' || tr.direction === 'UP' ? '\u25B2' : tr.direction === 'SHORT' || tr.direction === 'DOWN' ? '\u25BC' : tr.direction;
        const tMode = tr.trade_mode || 'paper';
        const modeTag = tMode === 'live'
          ? '<span class="mode-tag mode-tag-real">\uD83D\uDFE2 REAL</span>'
          : '<span class="mode-tag mode-tag-paper">\uD83D\uDFE1 PAPER</span>';
        const row = document.createElement('tr');
        row.innerHTML =
          '<td class="dim">' + tr.time + '</td>' +
          '<td class="' + botCls + '">' + tr.bot + '</td>' +
          '<td>' + modeTag + '</td>' +
          '<td>' + dirArrow + '</td>' +
          '<td>' + (tr.asset || '') + '</td>' +
          '<td>' + tr.entry + '</td>' +
          '<td class="dim">' + tr.size + '</td>' +
          '<td class="' + resCls + '">' + resLabel + '</td>' +
          '<td class="' + pnlCls + '">' + tr.pnl_fmt + '</td>';
        tbody.appendChild(row);
      }
    }
  }
});
</script>
</body>
</html>
"""


# ── WebSocket event handlers ──────────────────────────────────────────────
@socketio.on('switch_mode')
def handle_switch_mode(data):
    """Handle mode switch from frontend."""
    bot = data.get('bot', '')
    mode = data.get('mode', 'paper')
    if mode not in ('live', 'paper'):
        return

    if bot == '5m':
        db_path = config.FIVEMIN_DB_PATH
        table = 'fm_portfolio'
    elif bot == 'bn':
        db_path = config.BINANCE_DB_PATH
        table = 'bn_portfolio'
    else:
        return

    # Ensure column exists
    _ensure_trading_mode_column(db_path, table)

    # Update the mode
    try:
        from utils.db import get_connection
        conn = get_connection(db_path)
        conn.execute(f"UPDATE {table} SET trading_mode = ? WHERE id = 1", (mode,))
        conn.commit()
        conn.close()
        print(f"[Dashboard] Mode switch: {bot.upper()} -> {mode.upper()}")
    except Exception as e:
        print(f"[Dashboard] Error switching mode for {bot}: {e}")


# ── Flask routes ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/data")
def api_data():
    """REST fallback - returns current dashboard snapshot as JSON."""
    from flask import jsonify
    return jsonify(_build_payload())


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting MBH Trading Bots Web Dashboard V2 on http://0.0.0.0:8080")
    print("Press Ctrl+C to stop.\n")

    # Ensure trading_mode columns exist
    _ensure_trading_mode_column(config.FIVEMIN_DB_PATH, "fm_portfolio")
    _ensure_trading_mode_column(config.BINANCE_DB_PATH, "bn_portfolio")
    _ensure_trade_mode_column(config.FIVEMIN_DB_PATH, "fm_trades")
    _ensure_trade_mode_column(config.BINANCE_DB_PATH, "bn_trades")

    # Seed initial DB data
    with _lock:
        _state["fm"]      = reader.get_fivemin_stats()
        _state["bn"]      = reader.get_binance_stats()
        _state["cooldown"] = reader.get_cooldown_status()
        _state["trades"]  = reader.get_recent_trades(limit=20)
        _state["pnl"]     = reader.get_pnl_history()
        _state["hitrate"] = reader.get_signal_hitrate()
        _state["hourly"]  = reader.get_hourly_winrate()
        _state["daily"]   = reader.get_daily_comparison()
        _state["paper_vs_real"] = _get_paper_vs_real()

    # Background push thread
    bg = threading.Thread(target=_background_loop, daemon=True)
    bg.start()

    socketio.run(app, host="0.0.0.0", port=8080, debug=False, allow_unsafe_werkzeug=True)
