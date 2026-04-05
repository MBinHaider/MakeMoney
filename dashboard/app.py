import asyncio
import json
import time
import os
import signal
import subprocess
from datetime import datetime, timezone

import aiohttp
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
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
        self._live_state = None

        # Cached data
        self._fm = None
        self._bn = None
        self._trades = []
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

    def _refresh(self) -> None:
        if self._tick % 2 == 0:
            self._fm = self.reader.get_fivemin_stats()
            self._bn = self.reader.get_binance_stats()
            self._cooldown = self.reader.get_cooldown_status()
            self._read_bot_state()
        if self._tick % 5 == 0:
            self._trades = self.reader.get_recent_trades(limit=12)

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

    # ── BUILD DISPLAY ──────────────────────────────────────────

    def build_display(self) -> Group:
        self._refresh()
        fm = self._fm or {}
        bn = self._bn or {}
        cd = self._cooldown or {}
        now_ts = int(time.time())
        window_remaining = (now_ts - (now_ts % 300) + 300) - now_ts

        sections = []

        # ── HEADER ──
        header = Text(justify="center")
        header.append("━━━ ", style="yellow")
        header.append("MBH Trading Bots Command Center", style="bold cyan")
        header.append(" ━━━", style="yellow")
        sections.append(Align.center(header))

        now = datetime.now(timezone.utc)
        sub = Text(justify="center")
        sub.append(now.strftime("%H:%M:%S UTC"), style="dim")
        sub.append("  │  ", style="dim")

        # Bot status
        bots = self._get_bots_running()
        for name, running in bots.items():
            sub.append(f"{name}", style="dim")
            sub.append("●" if running else "○", style="green" if running else "red")
            sub.append(" ", style="dim")
        sub.append(" │  ", style="dim")
        sub.append("Sleep:", style="dim")
        sub.append("ON" if self.caffeinate_pid else "OFF", style="green" if self.caffeinate_pid else "red")
        sections.append(Align.center(sub))
        sections.append(Text(""))

        # ── COOLDOWN ALERT ──
        if cd.get("active"):
            secs = cd["seconds_remaining"]
            m, s = secs // 60, secs % 60
            sections.append(Panel(
                Align.center(Text.assemble(
                    ("⏸ PAUSED ", "bold yellow"),
                    (f"— {cd['consecutive_losses']} losses │ Resume: ", "dim"),
                    (f"{m}:{s:02d}", "bold yellow"),
                )),
                border_style="yellow", style="on #2d1b00",
            ))

        # ── MONEY ROW ──
        fm_pnl = fm.get("pnl", 0)
        fm_bal = fm.get("balance", 0)
        fm_start = fm.get("starting_balance", 0)
        fm_pct = (fm_pnl / fm_start * 100) if fm_start > 0 else 0
        fm_color = "green" if fm_pnl >= 0 else "red"
        fm_sign = "+" if fm_pnl >= 0 else ""
        fm_wins = fm.get("total_wins", 0)
        fm_total = fm.get("total_trades", 0)
        fm_losses = fm_total - fm_wins
        fm_wr = fm.get("win_rate", 0)
        fm_mode = fm.get("mode", "paper")

        bn_pnl = bn.get("pnl", 0)
        bn_bal = bn.get("balance", 0)
        bn_color = "green" if bn_pnl >= 0 else "red"
        bn_sign = "+" if bn_pnl >= 0 else ""
        bn_wins = bn.get("total_wins", 0)
        bn_total = bn.get("total_trades", 0)
        bn_losses = bn_total - bn_wins

        # PolyBot 5M card
        fm_text = Text()
        fm_text.append(f"${fm_bal:.2f}", style=f"bold {fm_color}")
        fm_text.append(f"  {fm_sign}${fm_pnl:.2f} ({fm_sign}{fm_pct:.1f}%)\n", style=fm_color)
        fm_text.append(f"{fm_wins}W {fm_losses}L", style="white")
        fm_text.append(f"  {fm_wr:.0%} win rate\n", style="green" if fm_wr >= 0.5 else "red" if fm_total > 0 else "dim")
        fm_text.append(f"Window: ", style="dim")
        fm_text.append(f"{window_remaining // 60}:{window_remaining % 60:02d}", style="bold yellow")

        fm_title = Text()
        fm_title.append("⚡ POLYBOT 5M ", style="bold yellow")
        if fm_mode == "live":
            fm_title.append(" LIVE ", style="bold white on green")
        else:
            fm_title.append(" PAPER ", style="bold yellow on #3d2800")

        fm_panel = Panel(fm_text, title=fm_title, border_style="yellow", expand=True)

        # BinanceBot card
        bn_text = Text()
        bn_text.append(f"${bn_bal:.2f}", style=f"bold {bn_color}")
        bn_text.append(f"  {bn_sign}${bn_pnl:.2f}\n", style=bn_color)
        bn_text.append(f"{bn_wins}W {bn_losses}L", style="white")
        bn_wr = bn.get("win_rate", 0)
        bn_text.append(f"  {bn_wr:.0%} win rate\n", style="green" if bn_wr >= 0.5 else "red" if bn_total > 0 else "dim")
        bn_text.append(f"Open: {bn.get('open_positions', 0)}", style="dim")

        bn_title = Text()
        bn_title.append("📊 BINANCEBOT ", style="bold blue")
        bn_title.append(" PAPER ", style="bold yellow on #3d2800")
        bn_panel = Panel(bn_text, title=bn_title, border_style="blue", expand=True)

        # Prices card
        price_text = Text()
        for sym in ["BTC", "ETH", "SOL"]:
            p = self._prices[sym]
            change = p - self._prev_prices[sym]
            color = "green" if change >= 0 else "red"
            arrow = "▲" if change > 0 else "▼" if change < 0 else "─"
            if p > 1000:
                price_text.append(f"{sym} ", style="bold")
                price_text.append(f"${p:,.0f} ", style=f"bold {color}")
                price_text.append(f"{arrow}\n", style=color)
            else:
                price_text.append(f"{sym} ", style="bold")
                price_text.append(f"${p:,.2f} ", style=f"bold {color}")
                price_text.append(f"{arrow}\n", style=color)

        price_panel = Panel(price_text, title="LIVE PRICES", border_style="dim", expand=True)

        sections.append(Columns([fm_panel, bn_panel, price_panel], expand=True))

        # ── LIVE SIGNALS ──
        signals = []
        if self._live_state and self._live_state.get("signals"):
            signals = self._live_state["signals"]

        if signals:
            sig_text = Text()
            for s in signals:
                asset = s.get("asset", "?")
                mom = s.get("momentum", "")
                ob = s.get("orderbook", "")
                vol = s.get("volume", "")
                sig = s.get("signal", "")
                conf = s.get("confidence", 0)

                asset_colors = {"BTC": "#f7931a", "ETH": "#627eea", "SOL": "#00ffa3"}
                sig_text.append(f"  {asset} ", style=f"bold {asset_colors.get(asset, 'white')}")

                for label, val in [("mom", mom), ("ob", ob), ("vol", vol)]:
                    if val == "UP":
                        sig_text.append(f"↑", style="green")
                    elif val == "DOWN":
                        sig_text.append(f"↓", style="red")
                    else:
                        sig_text.append(f"·", style="dim")

                if sig:
                    agree = s.get("agree_count", 0)
                    sig_color = "green" if sig == "UP" else "red"
                    sig_text.append(f"  → {agree}/3 {sig}", style=f"bold {sig_color}")
                    sig_text.append(f" ({conf:.0%})", style="yellow")

                sig_text.append("    ")

            sections.append(Panel(sig_text, title="LIVE SIGNALS", border_style="cyan", expand=True))

        # ── TRADES TABLE ──
        table = Table(expand=True, show_edge=False, pad_edge=False)
        table.add_column("TIME", width=5, style="dim")
        table.add_column("BOT", width=3)
        table.add_column("ASSET", width=8)
        table.add_column("DIR", width=5)
        table.add_column("ENTRY", justify="right", width=9)
        table.add_column("SIZE", justify="right", width=6)
        table.add_column("RESULT", width=6)
        table.add_column("P&L", justify="right", width=8)

        bot_styles = {"5M": "yellow", "BN": "blue", "POLY": "magenta"}

        for t in (self._trades or []):
            bc = bot_styles.get(t["bot"], "white")
            result = t["result"]
            if result == "win":
                r_str = "[bold green]WIN[/]"
            elif result == "loss":
                r_str = "[bold red]LOSS[/]"
            elif result == "open":
                r_str = "[yellow]OPEN[/]"
            else:
                r_str = "[dim]...[/]"

            pnl = t["pnl"]
            if pnl > 0:
                p_str = f"[green]+${pnl:.2f}[/]"
            elif pnl < 0:
                p_str = f"[red]${pnl:.2f}[/]"
            else:
                p_str = "[dim]—[/]"

            entry = f"${t['entry']:,.0f}" if t["entry"] > 100 else f"${t['entry']:.2f}"
            time_str = t["time"][11:16] if len(t["time"]) > 11 else t["time"][:5]

            table.add_row(
                time_str, f"[{bc}]{t['bot']}[/]", t["asset"], t["direction"],
                entry, f"${t['size']:.0f}", r_str, p_str,
            )

        if not self._trades:
            table.add_row("", "", "[dim]Waiting for first trade...[/]", "", "", "", "", "")

        sections.append(Panel(table, title="TRADES", border_style="dim", expand=True))

        return Group(*sections)

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

    async def run(self) -> None:
        self.start_caffeinate()
        self.running = True
        console = Console()

        price_task = asyncio.create_task(self._fetch_prices_loop())

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
            self.stop_caffeinate()
