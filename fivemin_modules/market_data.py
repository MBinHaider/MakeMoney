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
    token_id_up: str = ""
    token_id_down: str = ""
    condition_id: str = ""

    def reset(self, new_window_ts: int) -> None:
        """Reset state for a new 5-min window."""
        self.window_ts = new_window_ts
        self.window_open_price = 0.0
        self.current_price = 0.0
        self.orderbook_up = {"bids": [], "asks": []}
        self.orderbook_down = {"bids": [], "asks": []}
        self.volumes = deque(maxlen=60)
        self.price_history = deque(maxlen=60)
        self.token_id_up = ""
        self.token_id_down = ""
        self.condition_id = ""

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

    async def fetch_orderbooks(self, exchange=None) -> None:
        """Fetch orderbooks from Polymarket CLOB API.
        Tries direct first, falls back to SOCKS5 proxy if DNS fails."""

        for attempt in range(3):
            try:
                # Try direct first
                if attempt < 2:
                    session_ctx = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
                else:
                    # Fallback to proxy on 3rd attempt
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(self.config.PROXY_URL)
                    session_ctx = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10))

                async with session_ctx as session:
                    for asset in self.config.FIVEMIN_ASSETS:
                        state = self.states.get(asset)
                        if state is None:
                            continue

                        # Only fetch token IDs if we don't have them for this window
                        if not state.token_id_up or not state.token_id_down:
                            slug = compute_market_slug(asset, state.window_ts)
                            try:
                                token_ids = await self._fetch_token_ids(session, slug)
                                if token_ids:
                                    state.token_id_up = token_ids.get("UP", "")
                                    state.token_id_down = token_ids.get("DOWN", "")
                                    log.info(f"Got token IDs for {asset}: UP={state.token_id_up[:20]}...")
                            except Exception as e:
                                log.warning(f"Token ID fetch failed {asset}: {e}")

                        # Fetch orderbooks if we have token IDs
                        if state.token_id_up:
                            try:
                                state.orderbook_up = await self._fetch_clob_orderbook(session, state.token_id_up)
                            except Exception:
                                pass
                        if state.token_id_down:
                            try:
                                state.orderbook_down = await self._fetch_clob_orderbook(session, state.token_id_down)
                            except Exception:
                                pass
                return  # Success, no retry needed
            except Exception as e:
                if attempt < 2:
                    log.warning(f"Proxy attempt {attempt+1}/3 failed, retrying in 2s...")
                    await asyncio.sleep(2)
                else:
                    log.error(f"Proxy connection failed after 3 attempts: {e}")

    async def _fetch_token_ids(self, session: aiohttp.ClientSession, slug: str) -> dict:
        """Fetch UP/DOWN token IDs from Gamma API for a market slug."""
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {}
                events = await resp.json()
                if not events:
                    return {}

                # Parse outcomes from the event's markets
                event = events[0]
                markets = event.get("markets", [])
                token_ids = {}
                for market in markets:
                    tokens = market.get("tokens", [])
                    if not tokens:
                        # Try parsing from clobTokenIds string
                        outcomes_str = market.get("outcomes", "[]")
                        clob_str = market.get("clobTokenIds", "[]")
                        try:
                            import json as _json
                            outcomes = _json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                            clob_ids = _json.loads(clob_str) if isinstance(clob_str, str) else clob_str
                            for outcome, tid in zip(outcomes, clob_ids):
                                label = outcome.upper()
                                if label in ("UP", "YES"):
                                    token_ids["UP"] = tid
                                elif label in ("DOWN", "NO"):
                                    token_ids["DOWN"] = tid
                        except Exception:
                            pass
                    else:
                        for token in tokens:
                            outcome = token.get("outcome", "").upper()
                            tid = token.get("token_id", "")
                            if outcome in ("UP", "YES"):
                                token_ids["UP"] = tid
                            elif outcome in ("DOWN", "NO"):
                                token_ids["DOWN"] = tid

                if token_ids:
                    log.info(f"Found tokens for {slug}: {list(token_ids.keys())}")
                return token_ids
        except Exception as e:
            log.warning(f"Gamma API error for {slug}: {e}")
            return {}

    async def _fetch_clob_orderbook(self, session: aiohttp.ClientSession, token_id: str) -> dict:
        """Fetch orderbook from Polymarket CLOB API for a token."""
        url = f"https://clob.polymarket.com/book?token_id={token_id}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return {"bids": [], "asks": []}
                data = await resp.json()
                bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])[:5]]
                asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])[:5]]
                return {"bids": bids, "asks": asks}
        except Exception as e:
            log.warning(f"CLOB orderbook error: {e}")
            return {"bids": [], "asks": []}

    def stop(self) -> None:
        self._running = False
