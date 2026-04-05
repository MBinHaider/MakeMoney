import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field

import aiohttp

from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_market_data")

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"
BINANCE_SYMBOLS = {"BTC": "btcusdt", "ETH": "ethusdt", "SOL": "solusdt"}


def compute_window_ts(unix_ts: int) -> int:
    """Align a unix timestamp to the 5-minute window start."""
    return unix_ts - (unix_ts % 300)


def compute_seconds_elapsed(window_ts: int, now: float) -> float:
    """Seconds elapsed since window start."""
    return now - float(window_ts)


def compute_market_slug(asset: str, window_ts: int) -> str:
    """Deterministic Polymarket slug for a 5-min window."""
    return f"{asset.lower()}-updown-5m-{window_ts}"


@dataclass
class MarketState:
    asset: str
    window_ts: int
    window_open_price: float = 0.0
    current_price: float = 0.0
    orderbook_up: dict = field(default_factory=lambda: {"bids": [], "asks": []})
    orderbook_down: dict = field(default_factory=lambda: {"bids": [], "asks": []})
    volumes: deque = field(default_factory=lambda: deque(maxlen=60))
    price_history: deque = field(default_factory=lambda: deque(maxlen=60))

    def reset(self, new_window_ts: int) -> None:
        """Reset state for a new 5-min window."""
        self.window_ts = new_window_ts
        self.window_open_price = 0.0
        self.current_price = 0.0
        self.orderbook_up = {"bids": [], "asks": []}
        self.orderbook_down = {"bids": [], "asks": []}
        self.volumes = deque(maxlen=60)
        self.price_history = deque(maxlen=60)

    def to_signal_dict(self) -> dict:
        """Convert to dict for signal engine evaluation."""
        return {
            "current_price": self.current_price,
            "window_open_price": self.window_open_price,
            "volumes": list(self.volumes),
            "orderbook_up": self.orderbook_up,
            "orderbook_down": self.orderbook_down,
        }


class FiveMinMarketData:
    """Manages Binance WS price feeds and PMXT orderbook streams."""

    def __init__(self, config: Config):
        self.config = config
        self.states: dict[str, MarketState] = {}
        self._running = False

    def init_states(self, window_ts: int) -> None:
        """Initialize market states for all configured assets."""
        for asset in self.config.FIVEMIN_ASSETS:
            self.states[asset] = MarketState(asset=asset, window_ts=window_ts)

    async def start_binance_feeds(self) -> None:
        """Connect to Binance 1s kline WebSockets for all assets."""
        self._running = True
        tasks = []
        for asset in self.config.FIVEMIN_ASSETS:
            symbol = BINANCE_SYMBOLS.get(asset)
            if symbol:
                tasks.append(asyncio.create_task(self._binance_ws(asset, symbol)))
        await asyncio.gather(*tasks)

    async def _binance_ws(self, asset: str, symbol: str) -> None:
        """Single Binance WebSocket connection for 1s klines."""
        url = f"{BINANCE_WS_BASE}/{symbol}@kline_1s"
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url) as ws:
                        log.info(f"Binance WS connected: {symbol}")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                self._handle_binance_msg(asset, json.loads(msg.data))
                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                                break
            except Exception as e:
                log.error(f"Binance WS error ({symbol}): {e}")
                if self._running:
                    await asyncio.sleep(5)

    def _handle_binance_msg(self, asset: str, data: dict) -> None:
        """Process a Binance kline message."""
        kline = data.get("k", {})
        if not kline:
            return

        state = self.states.get(asset)
        if state is None:
            return

        close = float(kline.get("c", 0))
        volume = float(kline.get("q", 0))

        state.current_price = close
        state.price_history.append(close)
        state.volumes.append(volume)

        if state.window_open_price == 0.0 and close > 0:
            state.window_open_price = close

    async def fetch_orderbooks(self, exchange) -> None:
        """Fetch orderbooks from PMXT for all assets in the current window."""
        for asset in self.config.FIVEMIN_ASSETS:
            state = self.states.get(asset)
            if state is None:
                continue
            slug = compute_market_slug(asset, state.window_ts)
            try:
                markets = await asyncio.to_thread(
                    exchange.fetch_markets, {"slug": slug}
                )
                if not markets:
                    log.warning(f"No market found for {slug}")
                    continue

                market = markets[0]
                outcomes = market.get("outcomes", [])
                for outcome in outcomes:
                    label = outcome.get("label", "").upper()
                    outcome_id = outcome.get("outcomeId", "")
                    if not outcome_id:
                        continue
                    try:
                        book = await asyncio.to_thread(
                            exchange.fetch_order_book, outcome_id
                        )
                        parsed = self._parse_orderbook(book)
                        if label == "UP":
                            state.orderbook_up = parsed
                        elif label == "DOWN":
                            state.orderbook_down = parsed
                    except Exception as e:
                        log.error(f"Orderbook error {asset} {label}: {e}")
            except Exception as e:
                log.error(f"Market fetch error {slug}: {e}")

    def _parse_orderbook(self, book: dict) -> dict:
        """Parse PMXT orderbook into {bids: [(price, size)], asks: [(price, size)]}."""
        bids = [(float(b[0]), float(b[1])) for b in book.get("bids", [])[:5]]
        asks = [(float(a[0]), float(a[1])) for a in book.get("asks", [])[:5]]
        return {"bids": bids, "asks": asks}

    def stop(self) -> None:
        self._running = False
