# MBH Trading Bots Command Center — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rich CLI terminal dashboard that monitors all 3 trading bots in real-time with charts, signals, and analytics.

**Architecture:** Single `dashboard.py` entry point that reads from existing SQLite databases and Binance API. Uses `rich` for terminal rendering with a 1-second refresh loop. Each panel is a separate module returning a Rich renderable. `caffeinate` prevents Mac sleep.

**Tech Stack:** Python, rich, asciichartpy, psutil, aiohttp

---

### Task 1: Install dependencies and create package

**Files:**
- Modify: `requirements.txt`
- Create: `dashboard/__init__.py`
- Create: `dashboard/panels/__init__.py`

- [ ] **Step 1: Add dependencies to requirements.txt**

Add these lines to the end of `requirements.txt`:

```
rich>=13.0
asciichartpy>=1.5.25
psutil>=5.9
```

- [ ] **Step 2: Install dependencies**

Run: `pip install rich asciichartpy psutil`
Expected: Successfully installed

- [ ] **Step 3: Create package directories**

Create `dashboard/__init__.py`:

```python
```

Create `dashboard/panels/__init__.py`:

```python
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from rich.live import Live; from rich.table import Table; from rich.panel import Panel; from rich.layout import Layout; import asciichartpy; import psutil; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt dashboard/__init__.py dashboard/panels/__init__.py
git commit -m "feat(dashboard): add dependencies and create dashboard package"
```

---

### Task 2: Data reader — reads from all 3 databases

**Files:**
- Create: `dashboard/data_reader.py`
- Test: `tests/test_dashboard_data_reader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dashboard_data_reader.py`:

```python
import os
import tempfile
import pytest
from datetime import datetime, timezone
from dashboard.data_reader import DashboardDataReader
from utils.fivemin_db import init_fivemin_db
from utils.binance_db import init_binance_db
from utils.db import init_db, get_connection


@pytest.fixture
def setup_dbs():
    with tempfile.TemporaryDirectory() as tmpdir:
        fm_path = os.path.join(tmpdir, "fm.db")
        bn_path = os.path.join(tmpdir, "bn.db")
        pb_path = os.path.join(tmpdir, "pb.db")
        init_fivemin_db(fm_path)
        init_binance_db(bn_path)
        init_db(pb_path)
        reader = DashboardDataReader(fm_path, bn_path, pb_path)
        yield reader, fm_path, bn_path, pb_path


class TestFiveMinStats:
    def test_empty_db_returns_defaults(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        # Init portfolio
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 25.0, 25.0, 25.0, 0.0, ?, 0, 0, 0.0, 0, 0, 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        stats = reader.get_fivemin_stats()
        assert stats["balance"] == 25.0
        assert stats["total_trades"] == 0
        assert stats["is_paused"] is False
        assert stats["mode"] == "paper"

    def test_with_trades(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc)
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 27.44, 25.0, 27.44, 2.44, ?, 1, 1, 2.44, 0, 1, 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn.commit()
        conn.close()
        stats = reader.get_fivemin_stats()
        assert stats["balance"] == 27.44
        assert stats["total_trades"] == 1
        assert stats["total_wins"] == 1


class TestBinanceStats:
    def test_empty_db_returns_defaults(self, setup_dbs):
        reader, _, bn_path, _ = setup_dbs
        conn = get_connection(bn_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, 45.0, 45.0, 45.0, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        stats = reader.get_binance_stats()
        assert stats["balance"] == 45.0
        assert stats["total_trades"] == 0


class TestRecentTrades:
    def test_combined_trades(self, setup_dbs):
        reader, fm_path, bn_path, _ = setup_dbs
        # Add fivemin portfolio + trade
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc)
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 27.44, 25.0, 27.44, 2.44, ?, 1, 1, 2.44, 0, 1, 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn.execute(
            """INSERT INTO fm_trades
               (asset, direction, entry_price, shares, cost, result, pnl,
                window_ts, signal_confidence, signal_phase, signal_details, timestamp)
               VALUES ('ETH', 'UP', 0.67, 7.46, 5.0, 'win', 2.44, 1700000000, 1.0, 'mid', '{}', ?)""",
            (now.isoformat(),),
        )
        conn.commit()
        conn.close()
        # Add binance portfolio + trade
        conn2 = get_connection(bn_path)
        conn2.execute(
            """INSERT INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, 45.0, 45.0, 45.0, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn2.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, status, pnl, fees)
               VALUES (?, 'BTCUSDT', 'buy', 83000, 9.0, 84000, 82000, 'closed', 0.52, 0.01)""",
            (now.isoformat(),),
        )
        conn2.commit()
        conn2.close()
        trades = reader.get_recent_trades(limit=10)
        assert len(trades) == 2
        assert trades[0]["bot"] in ("5M", "BN")


class TestCooldownStatus:
    def test_no_cooldown(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 25.0, 25.0, 25.0, 0.0, ?, 0, 0, 0.0, 0, 0, 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        cooldown = reader.get_cooldown_status()
        assert cooldown["active"] is False

    def test_active_cooldown(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        from datetime import timedelta
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 20.0, 25.0, 25.0, -5.0, ?, 3, 0, -5.0, 3, 3, 1, ?, ?)""",
            (now[:10], future, now),
        )
        conn.commit()
        conn.close()
        cooldown = reader.get_cooldown_status()
        assert cooldown["active"] is True
        assert cooldown["seconds_remaining"] > 0


class TestPnlHistory:
    def test_empty_returns_zeros(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        history = reader.get_pnl_history(hours=24)
        assert isinstance(history, dict)
        assert "fivemin" in history
        assert "binance" in history
        assert "combined" in history


class TestSignalHitRate:
    def test_empty(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        rate = reader.get_signal_hitrate()
        assert rate["generated"] == 0
        assert rate["traded"] == 0
        assert rate["won"] == 0


class TestHourlyWinRate:
    def test_empty(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        hourly = reader.get_hourly_winrate()
        assert len(hourly) == 24
        assert all(h["trades"] == 0 for h in hourly)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_data_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard.data_reader'`

- [ ] **Step 3: Write the implementation**

Create `dashboard/data_reader.py`:

```python
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from config import Config


class DashboardDataReader:
    def __init__(self, fm_db_path: str, bn_db_path: str, pb_db_path: str):
        self.fm_db = fm_db_path
        self.bn_db = bn_db_path
        self.pb_db = pb_db_path
        self.config = Config()

    def get_fivemin_stats(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            row = conn.execute("SELECT * FROM fm_portfolio WHERE id = 1").fetchone()
            conn.close()
            if row is None:
                return self._empty_fivemin_stats()
            p = dict(row)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return {
                "balance": p["balance"],
                "starting_balance": p["starting_balance"],
                "pnl": p["total_pnl"],
                "total_trades": p["total_trades"],
                "total_wins": p["total_wins"],
                "win_rate": p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0,
                "consecutive_losses": p["consecutive_losses"],
                "daily_pnl": p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0,
                "is_paused": bool(p["is_paused"]),
                "pause_until": p["pause_until"],
                "mode": self.config.FIVEMIN_TRADING_MODE,
            }
        except Exception:
            return self._empty_fivemin_stats()

    def _empty_fivemin_stats(self) -> dict:
        return {
            "balance": 0, "starting_balance": 0, "pnl": 0, "total_trades": 0,
            "total_wins": 0, "win_rate": 0, "consecutive_losses": 0,
            "daily_pnl": 0, "is_paused": False, "pause_until": "",
            "mode": "paper",
        }

    def get_binance_stats(self) -> dict:
        try:
            conn = get_connection(self.bn_db)
            row = conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
            ).fetchone()["cnt"]
            conn.close()
            if row is None:
                return self._empty_binance_stats()
            p = dict(row)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return {
                "balance": p["balance"],
                "starting_balance": p["starting_balance"],
                "pnl": p["total_pnl"],
                "total_trades": p["total_trades"],
                "total_wins": p["total_wins"],
                "win_rate": p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0,
                "open_positions": open_count,
                "daily_pnl": p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0,
                "is_paused": bool(p["is_paused"]),
                "mode": self.config.BINANCE_TRADING_MODE,
            }
        except Exception:
            return self._empty_binance_stats()

    def _empty_binance_stats(self) -> dict:
        return {
            "balance": 0, "starting_balance": 0, "pnl": 0, "total_trades": 0,
            "total_wins": 0, "win_rate": 0, "open_positions": 0,
            "daily_pnl": 0, "is_paused": False, "mode": "paper",
        }

    def get_polybot_stats(self) -> dict:
        try:
            conn = get_connection(self.pb_db)
            markets = conn.execute("SELECT COUNT(*) as cnt FROM markets WHERE active = 1").fetchone()["cnt"]
            signals = conn.execute("SELECT COUNT(*) as cnt FROM signals WHERE date(timestamp) = date('now')").fetchone()["cnt"]
            whales = conn.execute("SELECT COUNT(*) as cnt FROM tracked_wallets").fetchone()["cnt"]
            conn.close()
            return {
                "markets": markets, "signals": signals, "whales": whales,
                "mode": self.config.TRADING_MODE,
            }
        except Exception:
            return {"markets": 0, "signals": 0, "whales": 0, "mode": "paper"}

    def get_recent_trades(self, limit: int = 10) -> list[dict]:
        trades = []
        try:
            conn = get_connection(self.fm_db)
            fm_trades = conn.execute(
                "SELECT * FROM fm_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            for t in fm_trades:
                t = dict(t)
                trades.append({
                    "time": t["timestamp"][:16], "bot": "5M",
                    "mode": self.config.FIVEMIN_TRADING_MODE,
                    "asset": t["asset"], "direction": t["direction"],
                    "entry": t["entry_price"], "size": t["cost"],
                    "result": t["result"], "pnl": t["pnl"],
                    "confidence": t["signal_confidence"],
                    "sort_ts": t["timestamp"],
                })
        except Exception:
            pass

        try:
            conn = get_connection(self.bn_db)
            bn_trades = conn.execute(
                "SELECT * FROM bn_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            for t in bn_trades:
                t = dict(t)
                result = "open" if t["status"] == "open" else ("win" if t.get("pnl", 0) > 0 else "loss")
                trades.append({
                    "time": t["timestamp"][:16], "bot": "BN",
                    "mode": self.config.BINANCE_TRADING_MODE,
                    "asset": t["symbol"], "direction": t["side"].upper(),
                    "entry": t["price"], "size": t["size"],
                    "result": result, "pnl": t.get("pnl", 0),
                    "confidence": 0,
                    "sort_ts": t["timestamp"],
                })
        except Exception:
            pass

        trades.sort(key=lambda x: x["sort_ts"], reverse=True)
        return trades[:limit]

    def get_cooldown_status(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            row = conn.execute("SELECT is_paused, pause_until, consecutive_losses FROM fm_portfolio WHERE id = 1").fetchone()
            conn.close()
            if row is None or not row["is_paused"]:
                return {"active": False, "seconds_remaining": 0, "consecutive_losses": 0}
            pause_until = row["pause_until"]
            if not pause_until:
                return {"active": True, "seconds_remaining": 0, "consecutive_losses": row["consecutive_losses"]}
            try:
                end = datetime.fromisoformat(pause_until)
                remaining = (end - datetime.now(timezone.utc)).total_seconds()
                return {
                    "active": True,
                    "seconds_remaining": max(0, int(remaining)),
                    "consecutive_losses": row["consecutive_losses"],
                }
            except ValueError:
                return {"active": True, "seconds_remaining": 0, "consecutive_losses": row["consecutive_losses"]}
        except Exception:
            return {"active": False, "seconds_remaining": 0, "consecutive_losses": 0}

    def get_pnl_history(self, hours: int = 24) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=hours)).isoformat()
        fm_pnls = []
        bn_pnls = []

        try:
            conn = get_connection(self.fm_db)
            rows = conn.execute(
                "SELECT pnl, timestamp FROM fm_trades WHERE result != 'pending' AND timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            ).fetchall()
            conn.close()
            running = 0.0
            for r in rows:
                running += r["pnl"]
                fm_pnls.append(round(running, 2))
        except Exception:
            pass

        try:
            conn = get_connection(self.bn_db)
            rows = conn.execute(
                "SELECT pnl, timestamp FROM bn_trades WHERE status = 'closed' AND timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            ).fetchall()
            conn.close()
            running = 0.0
            for r in rows:
                running += r["pnl"]
                bn_pnls.append(round(running, 2))
        except Exception:
            pass

        # Pad to same length
        max_len = max(len(fm_pnls), len(bn_pnls), 2)
        fm_pnls = fm_pnls or [0.0]
        bn_pnls = bn_pnls or [0.0]
        while len(fm_pnls) < max_len:
            fm_pnls.append(fm_pnls[-1])
        while len(bn_pnls) < max_len:
            bn_pnls.append(bn_pnls[-1])

        combined = [round(f + b, 2) for f, b in zip(fm_pnls, bn_pnls)]
        return {"fivemin": fm_pnls, "binance": bn_pnls, "combined": combined}

    def get_signal_hitrate(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            generated = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_signals WHERE date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            traded = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_signals WHERE action_taken = 'traded' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            won = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_trades WHERE result = 'win' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            total_traded = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_trades WHERE result != 'pending' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            conn.close()
            skipped = generated - traded
            return {
                "generated": generated,
                "skipped_price": max(0, skipped),
                "skipped_risk": 0,
                "traded": total_traded,
                "won": won,
            }
        except Exception:
            return {"generated": 0, "skipped_price": 0, "skipped_risk": 0, "traded": 0, "won": 0}

    def get_hourly_winrate(self) -> list[dict]:
        hourly = [{"hour": h, "trades": 0, "wins": 0, "rate": 0.0} for h in range(24)]
        try:
            conn = get_connection(self.fm_db)
            rows = conn.execute(
                "SELECT timestamp, result FROM fm_trades WHERE result IN ('win', 'loss')"
            ).fetchall()
            conn.close()
            for r in rows:
                try:
                    hour = int(r["timestamp"][11:13])
                    hourly[hour]["trades"] += 1
                    if r["result"] == "win":
                        hourly[hour]["wins"] += 1
                except (ValueError, IndexError):
                    pass
            for h in hourly:
                if h["trades"] > 0:
                    h["rate"] = h["wins"] / h["trades"]
        except Exception:
            pass
        return hourly

    def get_daily_comparison(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            def day_stats(date_str):
                rows = conn.execute(
                    "SELECT pnl, result FROM fm_trades WHERE date(timestamp) = ? AND result != 'pending'",
                    (date_str,),
                ).fetchall()
                if not rows:
                    return {"pnl": 0, "trades": 0, "win_rate": 0, "best": 0, "worst": 0}
                pnls = [r["pnl"] for r in rows]
                wins = sum(1 for r in rows if r["result"] == "win")
                return {
                    "pnl": round(sum(pnls), 2),
                    "trades": len(pnls),
                    "win_rate": wins / len(pnls) if pnls else 0,
                    "best": round(max(pnls), 2) if pnls else 0,
                    "worst": round(min(pnls), 2) if pnls else 0,
                }

            all_rows = conn.execute(
                "SELECT date(timestamp) as d, SUM(pnl) as total FROM fm_trades WHERE result != 'pending' GROUP BY d ORDER BY total"
            ).fetchall()
            conn.close()

            worst_date = all_rows[0]["d"] if all_rows else today
            best_date = all_rows[-1]["d"] if all_rows else today

            conn = get_connection(self.fm_db)
            result = {
                "today": day_stats(today),
                "yesterday": day_stats(yesterday),
                "best": day_stats(best_date),
                "worst": day_stats(worst_date),
            }
            conn.close()
            return result
        except Exception:
            empty = {"pnl": 0, "trades": 0, "win_rate": 0, "best": 0, "worst": 0}
            return {"today": empty, "yesterday": empty, "best": empty, "worst": empty}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_data_reader.py -v`
Expected: All 10 tests pass

- [ ] **Step 5: Commit**

```bash
git add dashboard/data_reader.py tests/test_dashboard_data_reader.py
git commit -m "feat(dashboard): add data reader for all 3 bot databases"
```

---

### Task 3: Panel modules — header, footer, bot stats, cooldown

**Files:**
- Create: `dashboard/panels/header.py`
- Create: `dashboard/panels/footer.py`
- Create: `dashboard/panels/bot_stats.py`
- Create: `dashboard/panels/cooldown_banner.py`

- [ ] **Step 1: Create header panel**

Create `dashboard/panels/header.py`:

```python
from datetime import datetime, timezone
from rich.text import Text
from rich.align import Align


def render_header(start_time: datetime, caffeinate_pid: int | None) -> Text:
    now = datetime.now(timezone.utc)
    uptime = now - start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    sleep_status = "ON" if caffeinate_pid else "N/A"
    time_str = now.strftime("%b %d %Y %H:%M:%S UTC")

    title = Text()
    title.append("━━━ ", style="yellow")
    title.append("MBH Trading Bots Command Center", style="bold bright_blue")
    title.append(" ━━━", style="yellow")
    title.append(f"\n{time_str} │ Uptime: {uptime_str} │ Sleep Lock: {sleep_status} │ Press Q to quit", style="dim")
    title.stylize("bold", 4, 35)
    return Align.center(title)
```

- [ ] **Step 2: Create footer panel**

Create `dashboard/panels/footer.py`:

```python
import time
from rich.columns import Columns
from rich.text import Text


def render_footer(prices: dict, caffeinate_pid: int | None, bots_running: dict) -> Text:
    footer = Text()

    # Prices
    for symbol, price in prices.items():
        color = "green" if price.get("change", 0) >= 0 else "red"
        footer.append(f"{symbol} ", style="dim")
        footer.append(f"${price['value']:,.0f}", style=color)
        footer.append(" │ ", style="dim")

    # Next 5M window
    now = int(time.time())
    window_end = now - (now % 300) + 300
    remaining = window_end - now
    mins = remaining // 60
    secs = remaining % 60
    footer.append(f"Next 5M: ", style="dim")
    footer.append(f"{mins}:{secs:02d}", style="yellow")
    footer.append(" │ ", style="dim")

    # Status
    cafe_str = "ON" if caffeinate_pid else "OFF"
    cafe_color = "green" if caffeinate_pid else "red"
    footer.append("caffeinate: ", style="dim")
    footer.append(f"●{cafe_str}", style=cafe_color)
    footer.append(" │ ", style="dim")

    all_running = all(bots_running.values())
    run_color = "green" if all_running else "yellow"
    running_count = sum(1 for v in bots_running.values() if v)
    footer.append(f"Bots: ", style="dim")
    footer.append(f"●{running_count}/{len(bots_running)}", style=run_color)

    return footer
```

- [ ] **Step 3: Create bot stats panels**

Create `dashboard/panels/bot_stats.py`:

```python
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.table import Table


def _mode_badge(mode: str) -> Text:
    if mode == "live":
        return Text(" LIVE ", style="bold white on green")
    return Text(" PAPER ", style="bold yellow on dark_goldenrod")


def render_fivemin_stats(stats: dict, window_remaining: int) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    pnl_color = "green" if stats["pnl"] >= 0 else "red"
    pnl_sign = "+" if stats["pnl"] >= 0 else ""
    wr_color = "green" if stats["win_rate"] >= 0.5 else "red"
    wins = stats["total_wins"]
    losses = stats["total_trades"] - wins
    mins = window_remaining // 60
    secs = window_remaining % 60

    table.add_row(
        Text("BALANCE\n", style="dim") + Text(f"${stats['balance']:.2f}", style=f"bold {pnl_color}"),
        Text("P&L\n", style="dim") + Text(f"{pnl_sign}${stats['pnl']:.2f}", style=pnl_color),
        Text("RECORD\n", style="dim") + Text(f"{wins}W/{losses}L"),
        Text("WIN%\n", style="dim") + Text(f"{stats['win_rate']:.0%}", style=wr_color),
        Text("WINDOW\n", style="dim") + Text(f"{mins}:{secs:02d}", style="yellow"),
    )

    title = Text()
    title.append("⚡ POLYBOT 5M ", style="bold yellow")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="yellow", expand=True)


def render_binance_stats(stats: dict) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    pnl_color = "green" if stats["pnl"] >= 0 else "red"
    pnl_sign = "+" if stats["pnl"] >= 0 else ""
    wr_color = "green" if stats["win_rate"] >= 0.5 else "red"
    wins = stats["total_wins"]
    losses = stats["total_trades"] - wins

    table.add_row(
        Text("BALANCE\n", style="dim") + Text(f"${stats['balance']:.2f}", style=f"bold {pnl_color}"),
        Text("P&L\n", style="dim") + Text(f"{pnl_sign}${stats['pnl']:.2f}", style=pnl_color),
        Text("RECORD\n", style="dim") + Text(f"{wins}W/{losses}L"),
        Text("WIN%\n", style="dim") + Text(f"{stats['win_rate']:.0%}", style=wr_color),
        Text("OPEN\n", style="dim") + Text(f"{stats['open_positions']}", style="bright_blue"),
    )

    title = Text()
    title.append("📊 BINANCEBOT ", style="bold bright_blue")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="bright_blue", expand=True)


def render_polybot_stats(stats: dict) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    table.add_row(
        Text("MARKETS\n", style="dim") + Text(f"{stats['markets']}"),
        Text("SIGNALS\n", style="dim") + Text(f"{stats['signals']}", style="yellow"),
        Text("WHALES\n", style="dim") + Text(f"{stats['whales']}"),
    )

    title = Text()
    title.append("🔮 POLYBOT ", style="bold medium_purple")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="medium_purple", expand=True)
```

- [ ] **Step 4: Create cooldown banner**

Create `dashboard/panels/cooldown_banner.py`:

```python
from rich.panel import Panel
from rich.text import Text
from rich.align import Align


def render_cooldown_banner(cooldown: dict) -> Panel | None:
    if not cooldown["active"]:
        return None

    secs = cooldown["seconds_remaining"]
    mins = secs // 60
    remaining_secs = secs % 60
    losses = cooldown["consecutive_losses"]

    msg = Text()
    msg.append("⏸ POLYBOT 5M PAUSED", style="bold yellow")
    msg.append(f" — {losses} consecutive losses │ Resuming in ", style="dim")
    msg.append(f"{mins}:{remaining_secs:02d}", style="bold yellow")

    return Panel(
        Align.center(msg),
        border_style="yellow",
        style="on #2d1b00",
    )
```

- [ ] **Step 5: Verify panels render**

Run: `python -c "
from dashboard.panels.header import render_header
from dashboard.panels.footer import render_footer
from dashboard.panels.bot_stats import render_fivemin_stats, render_binance_stats, render_polybot_stats
from dashboard.panels.cooldown_banner import render_cooldown_banner
from datetime import datetime, timezone
from rich.console import Console
c = Console()
c.print(render_header(datetime.now(timezone.utc), 12345))
c.print(render_fivemin_stats({'balance':27.44,'pnl':2.44,'total_trades':1,'total_wins':1,'win_rate':1.0,'consecutive_losses':0,'mode':'paper'}, 180))
c.print(render_binance_stats({'balance':47.70,'pnl':2.70,'total_trades':14,'total_wins':9,'win_rate':0.64,'open_positions':2,'mode':'paper'}))
c.print(render_polybot_stats({'markets':12,'signals':3,'whales':20,'mode':'paper'}))
print('All panels OK')
"`
Expected: Panels render in terminal, "All panels OK"

- [ ] **Step 6: Commit**

```bash
git add dashboard/panels/header.py dashboard/panels/footer.py dashboard/panels/bot_stats.py dashboard/panels/cooldown_banner.py
git commit -m "feat(dashboard): add header, footer, bot stats, and cooldown panels"
```

---

### Task 4: Chart panels — P&L time series and BTC price

**Files:**
- Create: `dashboard/panels/pnl_chart.py`
- Create: `dashboard/panels/price_chart.py`

- [ ] **Step 1: Create P&L chart panel**

Create `dashboard/panels/pnl_chart.py`:

```python
import asciichartpy
from rich.panel import Panel
from rich.text import Text


def render_pnl_chart(pnl_history: dict) -> Panel:
    fm = pnl_history.get("fivemin", [0])
    bn = pnl_history.get("binance", [0])
    combined = pnl_history.get("combined", [0])

    # Ensure at least 2 points for charting
    if len(combined) < 2:
        combined = [0, 0]
    if len(fm) < 2:
        fm = [0, 0]
    if len(bn) < 2:
        bn = [0, 0]

    # Trim to last 50 points for readability
    combined = combined[-50:]
    fm = fm[-50:]
    bn = bn[-50:]

    try:
        chart = asciichartpy.plot(
            [combined, fm, bn],
            {"height": 8, "colors": [
                asciichartpy.green,
                asciichartpy.yellow,
                asciichartpy.blue,
            ]},
        )
    except Exception:
        chart = "No data yet"

    legend = Text()
    legend.append("━ Combined  ", style="green")
    legend.append("━ 5M  ", style="yellow")
    legend.append("━ BN", style="bright_blue")

    content = Text(chart + "\n")
    content.append(legend)

    return Panel(content, title="P&L OVER TIME (24h)", title_align="left", border_style="dim")


```

- [ ] **Step 2: Create BTC price chart panel**

Create `dashboard/panels/price_chart.py`:

```python
import aiohttp
import asyncio
from rich.panel import Panel
from rich.text import Text


def render_price_chart(candles: list[dict]) -> Panel:
    if not candles or len(candles) < 2:
        return Panel("Waiting for price data...", title="BTC/USD", title_align="left", border_style="dim")

    # Find price range
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price_max = max(highs)
    price_min = min(lows)
    price_range = price_max - price_min or 1

    chart_height = 8
    lines = [[] for _ in range(chart_height)]

    for c in candles[-24:]:
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        is_green = cl >= o

        body_top = max(o, cl)
        body_bot = min(o, cl)

        for row in range(chart_height):
            price_at_row = price_max - (row / (chart_height - 1)) * price_range
            in_wick = l <= price_at_row <= h
            in_body = body_bot <= price_at_row <= body_top

            if in_body:
                lines[row].append("█" if is_green else "█")
            elif in_wick:
                lines[row].append("│")
            else:
                lines[row].append(" ")

    chart_text = Text()
    for i, line in enumerate(lines):
        price_label = price_max - (i / (chart_height - 1)) * price_range
        chart_text.append(f"${price_label:,.0f} ", style="dim")
        for j, ch in enumerate(line):
            candle = candles[-24:][j] if j < len(candles[-24:]) else None
            if candle and ch == "█":
                color = "green" if candle["close"] >= candle["open"] else "red"
                chart_text.append(ch + " ", style=color)
            elif ch == "│":
                chart_text.append(ch + " ", style="dim")
            else:
                chart_text.append(ch + " ")
        chart_text.append("\n")

    # Current price
    if candles:
        last = candles[-1]["close"]
        chart_text.append(f"Current: ${last:,.2f}", style="yellow")

    return Panel(chart_text, title="BTC/USD (1h candles)", title_align="left", border_style="dim")


async def fetch_btc_candles() -> list[dict]:
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "1h", "limit": 24}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                raw = await resp.json()
                return [
                    {"open": float(k[1]), "high": float(k[2]),
                     "low": float(k[3]), "close": float(k[4])}
                    for k in raw
                ]
    except Exception:
        return []
```

- [ ] **Step 3: Verify charts render**

Run: `python -c "
from dashboard.panels.pnl_chart import render_pnl_chart
from dashboard.panels.price_chart import render_price_chart
from rich.console import Console
c = Console()
c.print(render_pnl_chart({'fivemin': [0,1,2,3,2,4,5], 'binance': [0,0.5,1,1.5,1,2,2.5], 'combined': [0,1.5,3,4.5,3,6,7.5]}))
c.print(render_price_chart([{'open':83000,'high':83500,'low':82800,'close':83200},{'open':83200,'high':83800,'low':83100,'close':83600},{'open':83600,'high':83900,'low':83000,'close':83100}]))
print('Charts OK')
"`
Expected: ASCII chart and candlestick chart render in terminal

- [ ] **Step 4: Commit**

```bash
git add dashboard/panels/pnl_chart.py dashboard/panels/price_chart.py
git commit -m "feat(dashboard): add P&L time-series and BTC candlestick chart panels"
```

---

### Task 5: Analytics panels — daily comparison, heatmap, signals, orderbook, hit rate, trades

**Files:**
- Create: `dashboard/panels/daily_comparison.py`
- Create: `dashboard/panels/hour_heatmap.py`
- Create: `dashboard/panels/signals.py`
- Create: `dashboard/panels/orderbook.py`
- Create: `dashboard/panels/signal_hitrate.py`
- Create: `dashboard/panels/trades.py`

- [ ] **Step 1: Create daily comparison panel**

Create `dashboard/panels/daily_comparison.py`:

```python
from rich.panel import Panel
from rich.table import Table


def render_daily_comparison(daily: dict) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("", style="dim", width=10)
    table.add_column("P&L", justify="right")
    table.add_column("TRADES", justify="center")
    table.add_column("WIN%", justify="center")
    table.add_column("BEST", justify="right")
    table.add_column("WORST", justify="right")

    for label, key, style in [
        ("TODAY", "today", "bold bright_blue"),
        ("Yesterday", "yesterday", "dim"),
        ("Best day", "best", "dim"),
        ("Worst day", "worst", "dim"),
    ]:
        d = daily[key]
        pnl_color = "green" if d["pnl"] >= 0 else "red"
        pnl_sign = "+" if d["pnl"] >= 0 else ""
        wr_color = "green" if d["win_rate"] >= 0.5 else "red"
        best_str = f"+${d['best']:.2f}" if d["best"] > 0 else "—"
        worst_str = f"${d['worst']:.2f}" if d["worst"] < 0 else "—"

        table.add_row(
            f"[{style}]{label}[/]",
            f"[{pnl_color}]{pnl_sign}${d['pnl']:.2f}[/]",
            str(d["trades"]),
            f"[{wr_color}]{d['win_rate']:.0%}[/]",
            f"[green]{best_str}[/]",
            f"[red]{worst_str}[/]",
        )

    return Panel(table, title="DAILY P&L COMPARISON", title_align="left", border_style="dim")
```

- [ ] **Step 2: Create hour heatmap panel**

Create `dashboard/panels/hour_heatmap.py`:

```python
from rich.panel import Panel
from rich.text import Text


def render_hour_heatmap(hourly: list[dict]) -> Panel:
    heatmap = Text()

    for h in hourly:
        hour_label = f"{h['hour']:02d}"
        if h["trades"] == 0:
            heatmap.append(f" {hour_label} ", style="dim on #161b22")
        elif h["rate"] >= 0.7:
            heatmap.append(f" {hour_label} ", style="bold white on #26a641")
        elif h["rate"] >= 0.4:
            heatmap.append(f" {hour_label} ", style="on #0e4429")
        else:
            heatmap.append(f" {hour_label} ", style="white on #da3633")
        heatmap.append(" ")

    heatmap.append("\n\n")
    heatmap.append(" ░ ", style="dim on #161b22")
    heatmap.append(" none ", style="dim")
    heatmap.append(" ░ ", style="white on #da3633")
    heatmap.append(" <40% ", style="dim")
    heatmap.append(" ░ ", style="on #0e4429")
    heatmap.append(" 40-70% ", style="dim")
    heatmap.append(" ░ ", style="bold white on #26a641")
    heatmap.append(" >70%", style="dim")

    return Panel(heatmap, title="WIN RATE BY HOUR (UTC) — 5M", title_align="left", border_style="dim")
```

- [ ] **Step 3: Create signals panel**

Create `dashboard/panels/signals.py`:

```python
from rich.panel import Panel
from rich.table import Table


def render_signals(signal_data: list[dict]) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("ASSET", width=5)
    table.add_column("MOM", justify="center", width=5)
    table.add_column("OB", justify="center", width=5)
    table.add_column("VOL", justify="center", width=5)
    table.add_column("SIGNAL", justify="center")
    table.add_column("CONF", justify="center", width=5)

    for s in signal_data:
        asset_colors = {"BTC": "#f7931a", "ETH": "#627eea", "SOL": "#00ffa3"}
        asset_style = asset_colors.get(s["asset"], "white")

        def dir_cell(d):
            if d == "UP":
                return "[green]UP↑[/]"
            elif d == "DOWN":
                return "[red]DN↓[/]"
            return "[dim]—[/]"

        signal_str = f"[dim]—[/]"
        conf_str = f"[dim]—[/]"
        if s.get("signal"):
            count = s.get("agree_count", 0)
            sig_color = "green" if s["signal"] == "UP" else "red"
            signal_str = f"[bold {sig_color}]{count}/3 {s['signal']}[/]"
            conf_color = "green" if s.get("confidence", 0) >= 0.7 else "yellow"
            conf_str = f"[{conf_color}]{s.get('confidence', 0):.2f}[/]"

        table.add_row(
            f"[{asset_style}]{s['asset']}[/]",
            dir_cell(s.get("momentum", "")),
            dir_cell(s.get("orderbook", "")),
            dir_cell(s.get("volume", "")),
            signal_str,
            conf_str,
        )

    return Panel(table, title="LIVE SIGNALS (5M)", title_align="left", border_style="dim")
```

- [ ] **Step 4: Create orderbook panel**

Create `dashboard/panels/orderbook.py`:

```python
from rich.panel import Panel
from rich.text import Text


def render_orderbook(book: dict, asset: str) -> Panel:
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if not bids and not asks:
        return Panel("[dim]No orderbook data[/]", title="ORDERBOOK", title_align="left", border_style="dim")

    max_size = max(
        [s for _, s in bids[:3]] + [s for _, s in asks[:3]] + [1]
    )

    content = Text()
    content.append("BIDS\n", style="green")
    for price, size in bids[:3]:
        bar_len = int((size / max_size) * 8)
        content.append(f"${price:.2f} ", style="dim")
        content.append("█" * bar_len, style="green")
        content.append(f" {size:.0f}\n")

    content.append("\nASKS\n", style="red")
    for price, size in asks[:3]:
        bar_len = int((size / max_size) * 8)
        content.append(f"${price:.2f} ", style="dim")
        content.append("█" * bar_len, style="red")
        content.append(f" {size:.0f}\n")

    # Imbalance
    total_bid = sum(s for _, s in bids[:5])
    total_ask = sum(s for _, s in asks[:5])
    total = total_bid + total_ask
    if total > 0:
        imbalance = (total_bid - total_ask) / total
        imb_color = "green" if imbalance > 0 else "red"
        content.append(f"\nImbalance: ", style="dim")
        content.append(f"{imbalance:+.2f}", style=imb_color)

    return Panel(content, title=f"ORDERBOOK ({asset} UP)", title_align="left", border_style="dim")
```

- [ ] **Step 5: Create signal hit rate panel**

Create `dashboard/panels/signal_hitrate.py`:

```python
from rich.panel import Panel
from rich.text import Text


def render_signal_hitrate(rate: dict) -> Panel:
    content = Text()

    rows = [
        ("Generated", rate["generated"], "bright_blue"),
        ("Skipped (price)", rate["skipped_price"], "yellow"),
        ("Skipped (risk)", rate["skipped_risk"], "yellow"),
        ("Traded", rate["traded"], "bright_blue"),
    ]

    for label, value, color in rows:
        content.append(f"{label:<16}", style="dim")
        content.append(f"{value:>4}\n", style=color)

    # Won line (bold)
    won = rate["won"]
    traded = rate["traded"]
    pct = f"{won/traded:.0%}" if traded > 0 else "—"
    content.append("─" * 20 + "\n", style="dim")
    content.append(f"Won              ", style="dim")
    content.append(f"{won:>4}", style="bold green")
    content.append(f" ({pct})\n", style="green")

    # Funnel bar
    gen = rate["generated"] or 1
    traded_pct = int((rate["traded"] / gen) * 20)
    skipped_pct = 20 - traded_pct
    content.append("\n")
    content.append("█" * traded_pct, style="green")
    content.append("█" * skipped_pct, style="yellow")

    return Panel(content, title="SIGNAL HIT RATE (today)", title_align="left", border_style="dim")
```

- [ ] **Step 6: Create trades table panel**

Create `dashboard/panels/trades.py`:

```python
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_trades(trades: list[dict]) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("TIME", width=6, style="dim")
    table.add_column("BOT", width=4)
    table.add_column("MODE", width=7)
    table.add_column("ASSET", width=8)
    table.add_column("DIR", width=5)
    table.add_column("ENTRY", justify="right", width=9)
    table.add_column("SIZE", justify="right", width=5)
    table.add_column("RESULT", width=6)
    table.add_column("P&L", justify="right", width=8)
    table.add_column("CONF", justify="center", width=5)

    bot_colors = {"5M": "yellow", "BN": "bright_blue", "POLY": "medium_purple"}

    for t in trades[:10]:
        bot_color = bot_colors.get(t["bot"], "white")
        mode_style = "yellow" if t["mode"] == "paper" else "green"

        if t["result"] == "win":
            result_str = "[green]WIN[/]"
        elif t["result"] == "loss":
            result_str = "[red]LOSS[/]"
        elif t["result"] == "open":
            result_str = "[yellow]OPEN[/]"
        else:
            result_str = "[dim]...[/]"

        pnl = t["pnl"]
        pnl_str = f"[green]+${pnl:.2f}[/]" if pnl > 0 else f"[red]${pnl:.2f}[/]" if pnl < 0 else "[dim]—[/]"

        entry = t["entry"]
        if entry > 1000:
            entry_str = f"${entry:,.0f}"
        else:
            entry_str = f"${entry:.2f}"

        conf = t["confidence"]
        conf_str = f"{conf:.2f}" if conf > 0 else "—"

        table.add_row(
            t["time"][11:16] if len(t["time"]) > 11 else t["time"],
            f"[{bot_color}]{t['bot']}[/]",
            f"[{mode_style}]PAPER[/]" if t["mode"] == "paper" else f"[{mode_style}]LIVE[/]",
            t["asset"],
            t["direction"],
            entry_str,
            f"${t['size']:.0f}",
            result_str,
            pnl_str,
            conf_str,
        )

    return Panel(table, title="RECENT TRADES", title_align="left", border_style="dim")
```

- [ ] **Step 7: Verify all panels render**

Run: `python -c "
from dashboard.panels.daily_comparison import render_daily_comparison
from dashboard.panels.hour_heatmap import render_hour_heatmap
from dashboard.panels.signals import render_signals
from dashboard.panels.orderbook import render_orderbook
from dashboard.panels.signal_hitrate import render_signal_hitrate
from dashboard.panels.trades import render_trades
from rich.console import Console
c = Console()

empty = {'pnl':0,'trades':0,'win_rate':0,'best':0,'worst':0}
c.print(render_daily_comparison({'today':{'pnl':3.44,'trades':5,'win_rate':0.8,'best':2.44,'worst':-1.5},'yesterday':empty,'best':empty,'worst':empty}))
c.print(render_hour_heatmap([{'hour':h,'trades':h%3,'wins':h%2,'rate':(h%2)/(h%3) if h%3 else 0} for h in range(24)]))
c.print(render_signals([{'asset':'BTC','momentum':'UP','orderbook':'UP','volume':'','signal':'UP','agree_count':2,'confidence':0.67},{'asset':'ETH','momentum':'','orderbook':'DOWN','volume':'','signal':'','confidence':0},{'asset':'SOL','momentum':'UP','orderbook':'UP','volume':'UP','signal':'UP','agree_count':3,'confidence':0.89}]))
c.print(render_orderbook({'bids':[(0.55,100),(0.54,80),(0.53,60)],'asks':[(0.56,20),(0.57,15),(0.58,10)]},'SOL'))
c.print(render_signal_hitrate({'generated':47,'skipped_price':31,'skipped_risk':6,'traded':5,'won':4}))
c.print(render_trades([{'time':'2026-04-05T14:25','bot':'5M','mode':'paper','asset':'ETH','direction':'UP','entry':0.67,'size':5,'result':'win','pnl':2.44,'confidence':1.0}]))
print('All analytics panels OK')
"`
Expected: All 6 panels render, "All analytics panels OK"

- [ ] **Step 8: Commit**

```bash
git add dashboard/panels/daily_comparison.py dashboard/panels/hour_heatmap.py dashboard/panels/signals.py dashboard/panels/orderbook.py dashboard/panels/signal_hitrate.py dashboard/panels/trades.py
git commit -m "feat(dashboard): add analytics panels - daily, heatmap, signals, orderbook, hitrate, trades"
```

---

### Task 6: Main app — Rich Live layout with refresh loop

**Files:**
- Create: `dashboard/app.py`

- [ ] **Step 1: Create the main app**

Create `dashboard/app.py`:

```python
import asyncio
import time
import os
import signal
import subprocess
from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.columns import Columns

from config import Config
from dashboard.data_reader import DashboardDataReader
from dashboard.panels.header import render_header
from dashboard.panels.footer import render_footer
from dashboard.panels.bot_stats import render_fivemin_stats, render_binance_stats, render_polybot_stats
from dashboard.panels.cooldown_banner import render_cooldown_banner
from dashboard.panels.pnl_chart import render_pnl_chart
from dashboard.panels.price_chart import render_price_chart, fetch_btc_candles
from dashboard.panels.daily_comparison import render_daily_comparison
from dashboard.panels.hour_heatmap import render_hour_heatmap
from dashboard.panels.signals import render_signals
from dashboard.panels.orderbook import render_orderbook
from dashboard.panels.signal_hitrate import render_signal_hitrate
from dashboard.panels.trades import render_trades


class DashboardApp:
    def __init__(self, config: Config):
        self.config = config
        self.reader = DashboardDataReader(
            config.FIVEMIN_DB_PATH, config.BINANCE_DB_PATH, config.DB_PATH
        )
        self.start_time = datetime.now(timezone.utc)
        self.caffeinate_pid = None
        self.running = False
        self.btc_candles = []
        self._tick = 0

    def start_caffeinate(self) -> None:
        try:
            proc = subprocess.Popen(
                ["caffeinate", "-d", "-i"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.caffeinate_pid = proc.pid
        except FileNotFoundError:
            self.caffeinate_pid = None

    def stop_caffeinate(self) -> None:
        if self.caffeinate_pid:
            try:
                os.kill(self.caffeinate_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.caffeinate_pid = None

    def _get_window_remaining(self) -> int:
        now = int(time.time())
        window_end = now - (now % 300) + 300
        return window_end - now

    def _get_prices(self) -> dict:
        if self.btc_candles:
            btc = self.btc_candles[-1]["close"]
        else:
            btc = 0
        return {
            "BTC": {"value": btc, "change": 0},
            "ETH": {"value": 0, "change": 0},
            "SOL": {"value": 0, "change": 0},
        }

    def _get_bots_running(self) -> dict:
        return {"5M": True, "BN": True, "POLY": True}

    def _get_signal_data(self) -> list[dict]:
        return [
            {"asset": "BTC", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
            {"asset": "ETH", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
            {"asset": "SOL", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
        ]

    def _get_orderbook_data(self) -> tuple[dict, str]:
        return {"bids": [], "asks": []}, "BTC"

    def build_display(self) -> Layout:
        layout = Layout()

        # Fetch data
        fm_stats = self.reader.get_fivemin_stats()
        bn_stats = self.reader.get_binance_stats()
        pb_stats = self.reader.get_polybot_stats()
        cooldown = self.reader.get_cooldown_status()
        trades = self.reader.get_recent_trades()
        window_remaining = self._get_window_remaining()

        # Slow-refresh data (every 5 seconds)
        if self._tick % 5 == 0:
            self._cached_pnl = self.reader.get_pnl_history()
            self._cached_signals = self._get_signal_data()
            self._cached_orderbook, self._cached_ob_asset = self._get_orderbook_data()

        # Very slow refresh (every 30 seconds)
        if self._tick % 30 == 0:
            self._cached_daily = self.reader.get_daily_comparison()
            self._cached_hourly = self.reader.get_hourly_winrate()
            self._cached_hitrate = self.reader.get_signal_hitrate()

        pnl = getattr(self, "_cached_pnl", {"fivemin": [0], "binance": [0], "combined": [0]})
        signal_data = getattr(self, "_cached_signals", self._get_signal_data())
        ob_data = getattr(self, "_cached_orderbook", {"bids": [], "asks": []})
        ob_asset = getattr(self, "_cached_ob_asset", "BTC")
        daily = getattr(self, "_cached_daily", None)
        hourly = getattr(self, "_cached_hourly", None)
        hitrate = getattr(self, "_cached_hitrate", None)

        if daily is None:
            empty = {"pnl": 0, "trades": 0, "win_rate": 0, "best": 0, "worst": 0}
            daily = {"today": empty, "yesterday": empty, "best": empty, "worst": empty}
        if hourly is None:
            hourly = [{"hour": h, "trades": 0, "wins": 0, "rate": 0} for h in range(24)]
        if hitrate is None:
            hitrate = {"generated": 0, "skipped_price": 0, "skipped_risk": 0, "traded": 0, "won": 0}

        # Build layout sections
        sections = []

        # Header
        sections.append(render_header(self.start_time, self.caffeinate_pid))

        # Cooldown banner
        banner = render_cooldown_banner(cooldown)
        if banner:
            sections.append(banner)

        # Bot stats row
        sections.append(Columns([
            render_fivemin_stats(fm_stats, window_remaining),
            render_binance_stats(bn_stats),
            render_polybot_stats(pb_stats),
        ], expand=True))

        # Charts row
        sections.append(Columns([
            render_pnl_chart(pnl),
            render_price_chart(self.btc_candles),
        ], expand=True))

        # Daily + heatmap row
        sections.append(Columns([
            render_daily_comparison(daily),
            render_hour_heatmap(hourly),
        ], expand=True))

        # Signals + orderbook + hitrate row
        sections.append(Columns([
            render_signals(signal_data),
            render_orderbook(ob_data, ob_asset),
            render_signal_hitrate(hitrate),
        ], expand=True))

        # Trades
        sections.append(render_trades(trades))

        # Footer
        sections.append(render_footer(
            self._get_prices(), self.caffeinate_pid, self._get_bots_running()
        ))

        from rich.console import Group
        return Group(*sections)

    async def fetch_candles_loop(self) -> None:
        while self.running:
            self.btc_candles = await fetch_btc_candles()
            # Update prices from candles
            await asyncio.sleep(60)

    async def run(self) -> None:
        self.start_caffeinate()
        self.running = True
        self.btc_candles = await fetch_btc_candles()

        console = Console()

        # Start candle fetcher
        candle_task = asyncio.create_task(self.fetch_candles_loop())

        try:
            with Live(console=console, refresh_per_second=1, screen=True) as live:
                while self.running:
                    self._tick += 1
                    display = self.build_display()
                    live.update(display)
                    await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            candle_task.cancel()
            self.stop_caffeinate()
```

- [ ] **Step 2: Verify app imports**

Run: `python -c "from dashboard.app import DashboardApp; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dashboard/app.py
git commit -m "feat(dashboard): add main app with Rich Live layout and refresh loop"
```

---

### Task 7: Main entry point — one-button start

**Files:**
- Create: `dashboard.py`

- [ ] **Step 1: Create dashboard.py**

Create `dashboard.py`:

```python
import asyncio
import argparse
import sys

from config import Config
from dashboard.app import DashboardApp


def main():
    parser = argparse.ArgumentParser(description="MBH Trading Bots Command Center")
    parser.add_argument("--dashboard-only", action="store_true", help="Dashboard only, don't start bots")
    parser.add_argument("--bots-only", action="store_true", help="Start bots only, no dashboard")
    parser.add_argument("--stop", action="store_true", help="Stop all bots")
    args = parser.parse_args()

    config = Config()

    if args.stop:
        print("Stopping bots...")
        import subprocess
        subprocess.run(["pkill", "-f", "polybot5m.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "binancebot.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "polybot.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "caffeinate"], capture_output=True)
        print("All bots stopped.")
        return

    if args.bots_only:
        import subprocess
        print("Starting bots in background...")
        subprocess.Popen([sys.executable, "polybot5m.py", "--mode", "paper"],
                        stdout=open("polybot5m.log", "a"), stderr=subprocess.STDOUT)
        print("PolyBot 5M started (polybot5m.log)")
        print("Use --stop to stop all bots")
        return

    if not args.dashboard_only:
        import subprocess
        import os
        # Start bots if not already running
        try:
            import psutil
            running = [p.name() for p in psutil.process_iter(["name"])]
        except Exception:
            running = []

        if "polybot5m.py" not in str(running):
            subprocess.Popen([sys.executable, "polybot5m.py", "--mode", "paper"],
                            stdout=open("polybot5m.log", "a"), stderr=subprocess.STDOUT)
            print("Started PolyBot 5M")

    app = DashboardApp(config)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nDashboard stopped. Bots continue running in background.")
        print("Use 'python dashboard.py --stop' to stop everything.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the dashboard launches**

Run: `python -c "from dashboard.app import DashboardApp; from config import Config; app = DashboardApp(Config()); print(f'App created, caffeinate will use PID'); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat(dashboard): add one-button entry point with bot management"
```

---

### Task 8: Run full test suite and verify dashboard

- [ ] **Step 1: Run all tests**

Run: `pytest tests/test_dashboard_data_reader.py tests/test_fivemin_*.py -v`
Expected: All tests pass

- [ ] **Step 2: Test dashboard visually**

Run: `python dashboard.py --dashboard-only`
Expected: Full dashboard renders in terminal with all panels. Press Ctrl+C to exit.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(dashboard): MBH Trading Bots Command Center - complete CLI dashboard"
```
