import asyncio
import json
import time
import os
import signal
import subprocess
from datetime import datetime, timezone

import aiohttp
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
import asciichartpy

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

        # Cached data (refreshed at different intervals)
        self._fm_stats = None
        self._bn_stats = None
        self._pb_stats = None
        self._trades = []
        self._pnl = None
        self._hourly = None
        self._cooldown = None

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

    def _refresh_data(self) -> None:
        """Refresh data at tiered intervals. Fast for what changes, slow for what doesn't."""
        # Every 2s: portfolio stats + cooldown
        if self._tick % 2 == 0:
            self._fm_stats = self.reader.get_fivemin_stats()
            self._bn_stats = self.reader.get_binance_stats()
            self._cooldown = self.reader.get_cooldown_status()

        # Every 5s: trades + P&L
        if self._tick % 5 == 0:
            self._trades = self.reader.get_recent_trades(limit=8)
            self._pnl = self.reader.get_pnl_history()

        # Every 30s: slow data
        if self._tick % 30 == 0:
            self._pb_stats = self.reader.get_polybot_stats()
            self._hourly = self.reader.get_hourly_winrate()

    # ── Rendering ──────────────────────────────────────────────

    def _render_header(self) -> Text:
        now = datetime.now(timezone.utc)
        uptime = now - self.start_time
        h = int(uptime.total_seconds() // 3600)
        m = int((uptime.total_seconds() % 3600) // 60)

        t = Text(justify="center")
        t.append("━━━ ", style="yellow bold")
        t.append("MBH Trading Bots Command Center", style="bold cyan")
        t.append(" ━━━\n", style="yellow bold")

        t.append(now.strftime("%b %d %Y %H:%M:%S UTC"), style="dim")
        t.append(" │ ", style="dim")
        t.append(f"Up: {h}h{m}m", style="dim")
        t.append(" │ ", style="dim")
        t.append("Sleep: ", style="dim")
        t.append("ON" if self.caffeinate_pid else "OFF", style="green" if self.caffeinate_pid else "red")
        t.append(" │ ", style="dim")
        t.append("Q to quit", style="dim")
        return t

    def _render_bot_card(self, name: str, icon: str, color: str, stats: dict, extra: str = "") -> Panel:
        if not stats:
            return Panel("[dim]Loading...[/]", title=f"{icon} {name}", border_style=color)

        mode = stats.get("mode", "paper")
        mode_badge = f"[bold green] LIVE [/]" if mode == "live" else f"[yellow] PAPER [/]"

        pnl = stats.get("pnl", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        pnl_sign = "+" if pnl >= 0 else ""
        bal = stats.get("balance", 0)
        wins = stats.get("total_wins", 0)
        total = stats.get("total_trades", 0)
        losses = total - wins
        wr = stats.get("win_rate", 0)
        wr_color = "green" if wr >= 0.5 else "red" if total > 0 else "dim"

        content = Text()
        content.append(f"${bal:.2f}", style=f"bold {pnl_color}")
        content.append(f"  {pnl_sign}${pnl:.2f}\n", style=pnl_color)
        content.append(f"{wins}W/{losses}L ", style="white")
        content.append(f"{wr:.0%}", style=wr_color)
        if extra:
            content.append(f"  {extra}", style="dim")

        title = Text()
        title.append(f"{icon} {name} ", style=f"bold {color}")
        title.append(mode_badge)
        return Panel(content, title=title, border_style=color, expand=True)

    def _render_prices(self) -> Panel:
        t = Text()
        for sym in ["BTC", "ETH", "SOL"]:
            price = self._prices[sym]
            change = price - self._prev_prices[sym]
            color = "green" if change >= 0 else "red"
            arrow = "▲" if change > 0 else "▼" if change < 0 else "─"
            t.append(f" {sym} ", style="bold white")
            t.append(f"${price:,.2f} ", style=f"bold {color}")
            t.append(f"{arrow} ", style=color)
        return Panel(t, title="PRICES", border_style="dim", expand=True)

    def _render_pnl_chart(self) -> Panel:
        pnl = self._pnl or {"combined": [0, 0], "fivemin": [0, 0], "binance": [0, 0]}
        combined = pnl["combined"][-40:] or [0, 0]
        if len(combined) < 2:
            combined = [0, 0]

        try:
            chart = asciichartpy.plot(combined, {"height": 6, "colors": [asciichartpy.green]})
            content = Text.from_ansi(chart)
        except Exception:
            content = Text("Collecting data...", style="dim")

        return Panel(content, title="P&L (24h)", border_style="dim", expand=True)

    def _render_window_timer(self) -> Panel:
        now = int(time.time())
        window_end = now - (now % 300) + 300
        remaining = window_end - now
        mins = remaining // 60
        secs = remaining % 60

        t = Text(justify="center")
        t.append(f"{mins}:{secs:02d}", style="bold yellow")
        t.append("\nnext window", style="dim")
        return Panel(t, title="5M", border_style="yellow", expand=True)

    def _render_cooldown(self) -> Panel | None:
        cd = self._cooldown
        if not cd or not cd["active"]:
            return None
        secs = cd["seconds_remaining"]
        m, s = secs // 60, secs % 60
        return Panel(
            f"[bold yellow]⏸ PAUSED[/] — {cd['consecutive_losses']} losses │ Resume: [yellow]{m}:{s:02d}[/]",
            border_style="yellow", style="on #2d1b00",
        )

    def _render_trades(self) -> Panel:
        table = Table(show_edge=False, pad_edge=False, expand=True, show_header=True)
        table.add_column("TIME", width=5, style="dim")
        table.add_column("BOT", width=3)
        table.add_column("ASSET", width=7)
        table.add_column("DIR", width=4)
        table.add_column("ENTRY", justify="right", width=8)
        table.add_column("RESULT", width=5)
        table.add_column("P&L", justify="right", width=7)

        bot_colors = {"5M": "yellow", "BN": "blue", "POLY": "magenta"}

        for t in (self._trades or [])[:8]:
            bc = bot_colors.get(t["bot"], "white")
            result = t["result"]
            r_str = f"[green]WIN[/]" if result == "win" else f"[red]LOSS[/]" if result == "loss" else f"[yellow]OPEN[/]"
            pnl = t["pnl"]
            p_str = f"[green]+${pnl:.2f}[/]" if pnl > 0 else f"[red]${pnl:.2f}[/]" if pnl < 0 else "[dim]—[/]"
            entry = f"${t['entry']:,.0f}" if t["entry"] > 100 else f"${t['entry']:.2f}"
            time_str = t["time"][11:16] if len(t["time"]) > 11 else t["time"][:5]

            table.add_row(time_str, f"[{bc}]{t['bot']}[/]", t["asset"], t["direction"], entry, r_str, p_str)

        if not self._trades:
            table.add_row("[dim]—[/]", "", "[dim]No trades yet[/]", "", "", "", "")

        return Panel(table, title="RECENT TRADES", border_style="dim", expand=True)

    def _render_heatmap(self) -> Panel:
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

    def _render_footer(self) -> Text:
        t = Text()
        # Bot status
        bots = self._get_bots_running()
        for name, running in bots.items():
            color = "green" if running else "red"
            t.append(f" {name}:", style="dim")
            t.append("●", style=color)
        t.append("  │  ", style="dim")
        t.append(f"caffeinate:", style="dim")
        t.append("●" if self.caffeinate_pid else "○", style="green" if self.caffeinate_pid else "red")
        return t

    def _get_bots_running(self) -> dict:
        result = {"5M": False, "BN": False, "PB": False}
        try:
            import psutil
            for proc in psutil.process_iter(["cmdline"]):
                try:
                    cmd = " ".join(proc.info.get("cmdline") or [])
                    if "polybot5m" in cmd:
                        result["5M"] = True
                    elif "binancebot" in cmd:
                        result["BN"] = True
                    elif "polybot.py" in cmd and "polybot5m" not in cmd:
                        result["PB"] = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return result

    def build_display(self) -> Group:
        self._refresh_data()

        fm = self._fm_stats or {}
        bn = self._bn_stats or {}
        pb = self._pb_stats or {}

        # Window timer
        now_ts = int(time.time())
        window_remaining = (now_ts - (now_ts % 300) + 300) - now_ts
        window_extra = f"{window_remaining // 60}:{window_remaining % 60:02d}"

        sections = []

        # Header
        sections.append(Align.center(self._render_header()))

        # Cooldown banner (only if active)
        cd = self._render_cooldown()
        if cd:
            sections.append(cd)

        # Row 1: Bot cards + prices
        from rich.columns import Columns
        sections.append(Columns([
            self._render_bot_card("POLYBOT 5M", "⚡", "yellow", fm, window_extra),
            self._render_bot_card("BINANCEBOT", "📊", "blue", bn,
                                  f"{bn.get('open_positions', 0)} open" if bn else ""),
            self._render_bot_card("POLYBOT", "🔮", "magenta", {
                "balance": 0, "pnl": 0, "total_trades": pb.get("signals", 0) if pb else 0,
                "total_wins": 0, "win_rate": 0, "mode": pb.get("mode", "paper") if pb else "paper",
            }, f"{pb.get('markets', 0)}mkts {pb.get('whales', 0)}🐋" if pb else ""),
            self._render_prices(),
        ], expand=True))

        # Row 2: P&L chart + trades
        mid_layout = Layout()
        mid_layout.split_row(
            Layout(self._render_pnl_chart(), ratio=2),
            Layout(self._render_trades(), ratio=3),
        )
        mid_layout.size = 12
        sections.append(mid_layout)

        # Row 3: Heatmap
        sections.append(self._render_heatmap())

        # Footer
        sections.append(self._render_footer())

        return Group(*sections)

    # ── Background tasks ──────────────────────────────────────

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
                            self._btc_candles = [
                                {"open": float(k[1]), "high": float(k[2]),
                                 "low": float(k[3]), "close": float(k[4])}
                                for k in raw
                            ]
            except Exception:
                pass
            await asyncio.sleep(60)

    async def run(self) -> None:
        self.start_caffeinate()
        self.running = True

        console = Console()

        # Start background fetchers
        price_task = asyncio.create_task(self._fetch_prices_loop())
        candle_task = asyncio.create_task(self._fetch_candles_loop())

        try:
            with Live(console=console, refresh_per_second=1, screen=True, auto_refresh=False) as live:
                while self.running:
                    self._tick += 1
                    try:
                        display = self.build_display()
                        live.update(display, refresh=True)
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
