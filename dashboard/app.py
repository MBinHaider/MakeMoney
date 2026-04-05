import asyncio
import json
import time
import os
import signal
import subprocess
from datetime import datetime, timezone, timedelta

import aiohttp
import asciichartpy
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.columns import Columns

from config import Config
from dashboard.data_reader import DashboardDataReader

BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"


class DashboardApp:
    def __init__(self, config: Config):
        self.config = config
        self.reader = DashboardDataReader(
            config.FIVEMIN_DB_PATH, config.BINANCE_DB_PATH, config.DB_PATH
        )
        self.start_time = datetime.now(timezone.utc)
        self.caffeinate_pid = None
        self.running = False
        self._tick = 0
        self._prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        self._prev_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        self._btc_candles = []
        self._live_state = None

        # Cached data
        self._fm = None
        self._bn = None
        self._trades = []
        self._cooldown = None
        self._pnl = None
        self._hourly = None
        self._hitrate = None
        self._daily = None

    def start_caffeinate(self) -> None:
        try:
            proc = subprocess.Popen(["caffeinate", "-d", "-i"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.caffeinate_pid = proc.pid
        except FileNotFoundError:
            self.caffeinate_pid = None

    def stop_caffeinate(self) -> None:
        if self.caffeinate_pid:
            try:
                os.kill(self.caffeinate_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _refresh(self) -> None:
        if self._tick % 2 == 0:
            self._fm = self.reader.get_fivemin_stats()
            self._bn = self.reader.get_binance_stats()
            self._cooldown = self.reader.get_cooldown_status()
            self._read_bot_state()
        if self._tick % 5 == 0:
            self._trades = self.reader.get_recent_trades(limit=10)
            self._pnl = self.reader.get_pnl_history()
            self._hitrate = self.reader.get_signal_hitrate()
        if self._tick % 30 == 0:
            self._hourly = self.reader.get_hourly_winrate()
            self._daily = self.reader.get_daily_comparison()

    def _read_bot_state(self) -> None:
        state_path = os.path.join(os.path.dirname(self.config.FIVEMIN_DB_PATH), "polybot5m_state.json")
        try:
            if os.path.exists(state_path) and time.time() - os.path.getmtime(state_path) < 10:
                with open(state_path) as f:
                    self._live_state = json.load(f)
            else:
                self._live_state = None
        except Exception:
            self._live_state = None

    # ── PANELS ─────────────────────────────────────────────────

    def _header(self) -> Text:
        now = datetime.now(timezone.utc)
        t = Text(justify="center")
        t.append("━━━ ", style="yellow")
        t.append("MBH Trading Bots Command Center", style="bold cyan")
        t.append(" ━━━\n", style="yellow")
        t.append(now.strftime("%H:%M:%S UTC"), style="dim")
        t.append("  │  ", style="dim")
        bots = self._get_bots_running()
        for name, running in bots.items():
            t.append(f"{name}", style="dim")
            t.append("●" if running else "○", style="green" if running else "red")
            t.append(" ")
        t.append(" │  Sleep:", style="dim")
        t.append("ON" if self.caffeinate_pid else "OFF", style="green" if self.caffeinate_pid else "red")
        return t

    def _cooldown_banner(self) -> Panel | None:
        cd = self._cooldown or {}
        if not cd.get("active"):
            return None
        s = cd["seconds_remaining"]
        return Panel(Align.center(Text.assemble(
            ("⏸ PAUSED ", "bold yellow"),
            (f"— {cd['consecutive_losses']} losses │ Resume: ", "dim"),
            (f"{s//60}:{s%60:02d}", "bold yellow"),
        )), border_style="yellow", style="on #2d1b00")

    def _bot_card(self, name, icon, color, stats, extra="") -> Panel:
        if not stats:
            return Panel("[dim]...[/]", title=f"{icon} {name}", border_style=color, expand=True)
        pnl = stats.get("pnl", 0)
        bal = stats.get("balance", 0)
        pc = "green" if pnl >= 0 else "red"
        s = "+" if pnl >= 0 else ""
        w, t = stats.get("total_wins", 0), stats.get("total_trades", 0)
        wr = stats.get("win_rate", 0)
        mode = stats.get("mode", "paper")
        start = stats.get("starting_balance", 0)
        pct = (pnl / start * 100) if start > 0 else 0

        txt = Text()
        txt.append(f"${bal:.2f}", style=f"bold {pc}")
        txt.append(f"  {s}${pnl:.2f} ({s}{pct:.1f}%)\n", style=pc)
        txt.append(f"{w}W {t-w}L  ", style="white")
        txt.append(f"{wr:.0%}", style="green" if wr >= 0.5 else "red" if t > 0 else "dim")
        if extra:
            txt.append(f"  {extra}", style="dim")

        title = Text()
        title.append(f"{icon} {name} ", style=f"bold {color}")
        if mode == "live":
            title.append(" LIVE ", style="bold white on green")
        else:
            title.append(" PAPER ", style="bold yellow on #3d2800")
        return Panel(txt, title=title, border_style=color, expand=True)

    def _prices_panel(self) -> Panel:
        t = Text()
        for sym in ["BTC", "ETH", "SOL"]:
            p = self._prices[sym]
            ch = p - self._prev_prices[sym]
            c = "green" if ch >= 0 else "red"
            a = "▲" if ch > 0 else "▼" if ch < 0 else "─"
            fmt = f"${p:,.0f}" if p > 100 else f"${p:.2f}"
            t.append(f"{sym} ", style="bold")
            t.append(f"{fmt} ", style=f"bold {c}")
            t.append(f"{a}\n", style=c)
        return Panel(t, title="PRICES", border_style="dim", expand=True)

    def _pnl_chart(self) -> Panel:
        pnl = self._pnl or {"combined": [0, 0], "fivemin": [0, 0], "binance": [0, 0]}
        fm_data = pnl["fivemin"][-40:] or [0, 0]
        bn_data = pnl["binance"][-40:] or [0, 0]
        combined = pnl["combined"][-40:] or [0, 0]
        if len(combined) < 2:
            combined = [0, 0]
        if len(fm_data) < 2:
            fm_data = [0, 0]
        if len(bn_data) < 2:
            bn_data = [0, 0]
        # Pad to same length
        ml = max(len(combined), len(fm_data), len(bn_data))
        while len(combined) < ml: combined.append(combined[-1])
        while len(fm_data) < ml: fm_data.append(fm_data[-1])
        while len(bn_data) < ml: bn_data.append(bn_data[-1])

        try:
            chart = asciichartpy.plot([combined, fm_data, bn_data], {
                "height": 6,
                "colors": [asciichartpy.green, asciichartpy.yellow, asciichartpy.blue],
            })
            content = Text.from_ansi(chart)
        except Exception:
            content = Text("Collecting data...", style="dim")
        content.append("\n")
        content.append("━ Combined  ", style="green")
        content.append("━ 5M  ", style="yellow")
        content.append("━ BN", style="blue")
        return Panel(content, title="P&L CHART (24h)", border_style="dim", expand=True)

    def _btc_chart(self) -> Panel:
        candles = self._btc_candles[-20:]
        if len(candles) < 3:
            return Panel("[dim]Loading candles...[/]", title="BTC/USD (1h)", border_style="dim", expand=True)

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        pmax, pmin = max(highs), min(lows)
        prange = pmax - pmin or 1
        height = 8

        def row(price): return int((pmax - price) / prange * (height - 1))

        txt = Text()
        for r in range(height):
            price = pmax - (r / (height - 1)) * prange
            txt.append(f"${price:>7,.0f} ", style="dim")
            for c in candles:
                o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
                color = "green" if cl >= o else "red"
                bt, bb = row(max(o, cl)), row(min(o, cl))
                wt, wb = row(h), row(l)
                if bt <= r <= bb:
                    txt.append("█", style=color)
                elif wt <= r <= wb:
                    txt.append("│", style=color)
                else:
                    txt.append(" ")
            txt.append("\n")
        txt.append(f"  Current: ", style="dim")
        txt.append(f"${candles[-1]['close']:,.2f}", style="bold yellow")
        return Panel(txt, title="BTC/USD (1h)", border_style="dim", expand=True)

    def _streak_panel(self) -> Panel:
        fm = self._fm or {}
        consec = fm.get("consecutive_losses", 0)
        w = fm.get("total_wins", 0)
        t = fm.get("total_trades", 0)

        txt = Text()
        if consec > 0:
            txt.append(f"Current: ", style="dim")
            txt.append(f"L{consec} ", style="bold red")
            txt.append("losing\n", style="red")
        elif t > 0:
            txt.append(f"Current: ", style="dim")
            txt.append(f"W ", style="bold green")
            txt.append("winning\n", style="green")
        else:
            txt.append("No trades yet\n", style="dim")

        # Today's P&L
        daily = self._daily or {}
        today = daily.get("today", {})
        td_pnl = today.get("pnl", 0)
        td_trades = today.get("trades", 0)
        td_wr = today.get("win_rate", 0)
        td_color = "green" if td_pnl >= 0 else "red"
        td_sign = "+" if td_pnl >= 0 else ""

        txt.append(f"Today: ", style="dim")
        txt.append(f"{td_sign}${td_pnl:.2f}", style=td_color)
        txt.append(f" ({td_trades} trades, {td_wr:.0%})\n", style="dim")

        # Yesterday
        yest = daily.get("yesterday", {})
        yd_pnl = yest.get("pnl", 0)
        yd_color = "green" if yd_pnl >= 0 else "red"
        yd_sign = "+" if yd_pnl >= 0 else ""
        txt.append(f"Yesterday: ", style="dim")
        txt.append(f"{yd_sign}${yd_pnl:.2f}", style=yd_color)

        return Panel(txt, title="STREAK & DAILY", border_style="dim", expand=True)

    def _hitrate_panel(self) -> Panel:
        hr = self._hitrate or {"generated": 0, "traded": 0, "won": 0, "skipped_price": 0, "skipped_risk": 0}
        gen = hr["generated"]
        traded = hr["traded"]
        won = hr["won"]
        skipped = hr["skipped_price"] + hr["skipped_risk"]

        txt = Text()
        txt.append(f"Signals: ", style="dim")
        txt.append(f"{gen}\n", style="cyan")
        txt.append(f"Skipped: ", style="dim")
        txt.append(f"{skipped}\n", style="yellow")
        txt.append(f"Traded:  ", style="dim")
        txt.append(f"{traded}\n", style="cyan")
        txt.append(f"Won:     ", style="dim")
        won_pct = f"{won}/{traded} ({won/traded:.0%})" if traded > 0 else "—"
        txt.append(f"{won_pct}\n", style="green" if traded > 0 and won/traded >= 0.5 else "red" if traded > 0 else "dim")

        # Visual funnel
        if gen > 0:
            bar_len = 20
            traded_len = int((traded / gen) * bar_len) if gen > 0 else 0
            won_len = int((won / gen) * bar_len) if gen > 0 else 0
            txt.append("█" * won_len, style="green")
            txt.append("█" * (traded_len - won_len), style="red")
            txt.append("░" * (bar_len - traded_len), style="dim")

        return Panel(txt, title="SIGNAL ACCURACY", border_style="dim", expand=True)

    def _heatmap(self) -> Panel:
        hourly = self._hourly or [{"hour": h, "trades": 0, "rate": 0} for h in range(24)]
        t = Text()
        for h in hourly:
            label = f"{h['hour']:02d}"
            if h["trades"] == 0:
                t.append(f" {label} ", style="dim on #161b22")
            elif h["rate"] >= 0.7:
                t.append(f" {label} ", style="bold white on #26a641")
            elif h["rate"] >= 0.4:
                t.append(f" {label} ", style="on #0e4429")
            else:
                t.append(f" {label} ", style="white on #da3633")
        t.append("\n")
        t.append(" ░ ", style="dim on #161b22")
        t.append("none ", style="dim")
        t.append(" ░ ", style="white on #da3633")
        t.append("<40% ", style="dim")
        t.append(" ░ ", style="on #0e4429")
        t.append("40-70% ", style="dim")
        t.append(" ░ ", style="bold white on #26a641")
        t.append(">70%", style="dim")
        return Panel(t, title="WIN RATE BY HOUR (UTC)", border_style="dim", expand=True)

    def _signals_panel(self) -> Panel | None:
        signals = self._live_state.get("signals", []) if self._live_state else []
        if not signals:
            return None
        t = Text()
        for s in signals:
            asset = s.get("asset", "?")
            colors = {"BTC": "#f7931a", "ETH": "#627eea", "SOL": "#00ffa3"}
            t.append(f" {asset} ", style=f"bold {colors.get(asset, 'white')}")
            for val in [s.get("momentum", ""), s.get("orderbook", ""), s.get("volume", "")]:
                if val == "UP": t.append("↑", style="green")
                elif val == "DOWN": t.append("↓", style="red")
                else: t.append("·", style="dim")
            sig = s.get("signal", "")
            if sig:
                sc = "green" if sig == "UP" else "red"
                t.append(f" →{s.get('agree_count',0)}/3 {sig}", style=f"bold {sc}")
                t.append(f"({s.get('confidence',0):.0%})", style="yellow")
            t.append("   ")
        return Panel(t, title="LIVE SIGNALS", border_style="cyan", expand=True)

    def _trades_table(self) -> Panel:
        table = Table(expand=True, show_edge=False, pad_edge=False)
        table.add_column("TIME", width=5, style="dim")
        table.add_column("BOT", width=3)
        table.add_column("ASSET", width=8)
        table.add_column("DIR", width=5)
        table.add_column("ENTRY", justify="right", width=9)
        table.add_column("SIZE", justify="right", width=6)
        table.add_column("RESULT", width=6)
        table.add_column("P&L", justify="right", width=8)

        styles = {"5M": "yellow", "BN": "blue", "POLY": "magenta"}
        for tr in (self._trades or []):
            bc = styles.get(tr["bot"], "white")
            r = tr["result"]
            r_str = "[bold green]WIN[/]" if r == "win" else "[bold red]LOSS[/]" if r == "loss" else "[yellow]OPEN[/]" if r == "open" else "[dim]...[/]"
            pnl = tr["pnl"]
            p_str = f"[green]+${pnl:.2f}[/]" if pnl > 0 else f"[red]${pnl:.2f}[/]" if pnl < 0 else "[dim]—[/]"
            entry = f"${tr['entry']:,.0f}" if tr["entry"] > 100 else f"${tr['entry']:.2f}"
            ts = tr["time"][11:16] if len(tr["time"]) > 11 else tr["time"][:5]
            table.add_row(ts, f"[{bc}]{tr['bot']}[/]", tr["asset"], tr["direction"], entry, f"${tr['size']:.0f}", r_str, p_str)

        if not self._trades:
            table.add_row("", "", "[dim]Waiting for trades...[/]", "", "", "", "", "")
        return Panel(table, title="TRADES", border_style="dim", expand=True)

    # ── BUILD ──────────────────────────────────────────────────

    def build_display(self) -> Group:
        self._refresh()
        fm = self._fm or {}
        bn = self._bn or {}
        now_ts = int(time.time())
        wr = (now_ts - (now_ts % 300) + 300) - now_ts

        sections = []

        # Header
        sections.append(Align.center(self._header()))
        sections.append(Text(""))

        # Cooldown
        cd = self._cooldown_banner()
        if cd:
            sections.append(cd)

        # Row 1: Bot cards + prices
        sections.append(Columns([
            self._bot_card("POLYBOT 5M", "⚡", "yellow", fm, f"{wr//60}:{wr%60:02d}"),
            self._bot_card("BINANCEBOT", "📊", "blue", bn, f"{bn.get('open_positions',0)} open"),
            self._prices_panel(),
        ], expand=True))

        # Row 2: P&L chart + BTC chart
        sections.append(Columns([
            self._pnl_chart(),
            self._btc_chart(),
        ], expand=True))

        # Row 3: Streak/daily + signal accuracy + heatmap
        sections.append(Columns([
            self._streak_panel(),
            self._hitrate_panel(),
            self._heatmap(),
        ], expand=True))

        # Live signals (only if data exists)
        sig = self._signals_panel()
        if sig:
            sections.append(sig)

        # Trades
        sections.append(self._trades_table())

        return Group(*sections)

    def _get_bots_running(self) -> dict:
        result = {"5M": False, "BN": False, "PB": False}
        try:
            import psutil
            for proc in psutil.process_iter(["cmdline"]):
                try:
                    cmd = " ".join(proc.info.get("cmdline") or [])
                    if "polybot5m" in cmd: result["5M"] = True
                    elif "binancebot" in cmd: result["BN"] = True
                    elif "polybot.py" in cmd and "polybot5m" not in cmd: result["PB"] = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return result

    async def _fetch_prices_loop(self) -> None:
        while self.running:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    for symbol, asset in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]:
                        async with session.get(BINANCE_PRICE_URL, params={"symbol": symbol}) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                self._prev_prices[asset] = self._prices[asset]
                                self._prices[asset] = float(data["price"])
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _fetch_candles_loop(self) -> None:
        while self.running:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    params = {"symbol": "BTCUSDT", "interval": "1h", "limit": 24}
                    async with session.get("https://api.binance.com/api/v3/klines", params=params) as resp:
                        if resp.status == 200:
                            raw = await resp.json()
                            self._btc_candles = [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4])} for k in raw]
            except Exception:
                pass
            await asyncio.sleep(60)

    async def run(self) -> None:
        self.start_caffeinate()
        self.running = True
        console = Console()
        price_task = asyncio.create_task(self._fetch_prices_loop())
        candle_task = asyncio.create_task(self._fetch_candles_loop())

        try:
            with Live(console=console, refresh_per_second=1, screen=True, auto_refresh=False) as live:
                while self.running:
                    self._tick += 1
                    try:
                        live.update(self.build_display(), refresh=True)
                    except Exception as e:
                        live.update(f"[red]Error: {e}[/]", refresh=True)
                    await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            price_task.cancel()
            candle_task.cancel()
            self.stop_caffeinate()
