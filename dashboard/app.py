import asyncio
import json
import time
import os
import signal
import subprocess
from datetime import datetime, timezone

import aiohttp
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
        self.btc_candles = []
        self._tick = 0
        self._live_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        self._prev_prices = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        self._live_state = None

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
        return {
            "BTC": {"value": self._live_prices["BTC"], "change": self._live_prices["BTC"] - self._prev_prices["BTC"]},
            "ETH": {"value": self._live_prices["ETH"], "change": self._live_prices["ETH"] - self._prev_prices["ETH"]},
            "SOL": {"value": self._live_prices["SOL"], "change": self._live_prices["SOL"] - self._prev_prices["SOL"]},
        }

    def _get_bots_running(self) -> dict:
        result = {"5M": False, "BN": False, "POLY": False}
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
                        result["POLY"] = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return result

    def _get_signal_data(self) -> list[dict]:
        state = self._live_state
        if state:
            return state.get("signals", [
                {"asset": "BTC", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
                {"asset": "ETH", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
                {"asset": "SOL", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
            ])
        return [
            {"asset": "BTC", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
            {"asset": "ETH", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
            {"asset": "SOL", "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0},
        ]

    def _get_orderbook_data(self) -> tuple[dict, str]:
        state = self._live_state
        if state and state.get("orderbook"):
            return state["orderbook"], state.get("orderbook_asset", "BTC")
        return {"bids": [], "asks": []}, "BTC"

    async def _fetch_live_prices(self) -> None:
        """Fetch live prices from Binance REST API."""
        symbols = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL"}
        try:
            async with aiohttp.ClientSession() as session:
                for symbol, asset in symbols.items():
                    async with session.get(BINANCE_PRICE_URL, params={"symbol": symbol}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = float(data["price"])
                            self._prev_prices[asset] = self._live_prices[asset]
                            self._live_prices[asset] = price
        except Exception:
            pass

    def _read_bot_state(self) -> None:
        """Read PolyBot 5M state file if it exists."""
        state_path = os.path.join(os.path.dirname(self.config.FIVEMIN_DB_PATH), "polybot5m_state.json")
        try:
            if os.path.exists(state_path):
                mtime = os.path.getmtime(state_path)
                if time.time() - mtime < 10:  # Only use if updated within 10s
                    with open(state_path) as f:
                        self._live_state = json.load(f)
                else:
                    self._live_state = None
        except Exception:
            self._live_state = None

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
            try:
                self.btc_candles = await fetch_btc_candles()
            except Exception:
                pass
            await asyncio.sleep(60)

    async def fetch_prices_loop(self) -> None:
        while self.running:
            await self._fetch_live_prices()
            self._read_bot_state()
            await asyncio.sleep(2)

    async def run(self) -> None:
        self.start_caffeinate()
        self.running = True

        # Fetch initial data
        try:
            self.btc_candles = await fetch_btc_candles()
        except Exception:
            self.btc_candles = []
        await self._fetch_live_prices()

        console = Console()

        # Start background fetchers
        candle_task = asyncio.create_task(self.fetch_candles_loop())
        price_task = asyncio.create_task(self.fetch_prices_loop())

        try:
            with Live(console=console, refresh_per_second=1, screen=True, auto_refresh=False) as live:
                while self.running:
                    self._tick += 1
                    try:
                        display = self.build_display()
                        live.update(display, refresh=True)
                    except Exception as e:
                        live.update(f"[red]Render error: {e}[/]", refresh=True)
                    await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            candle_task.cancel()
            price_task.cancel()
            self.stop_caffeinate()
