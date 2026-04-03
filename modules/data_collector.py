import aiohttp
from aiohttp_socks import ProxyConnector
from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("data_collector")

TARGET_KEYWORDS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}


class DataCollector:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH
        self._seen_trades = set()  # Dedup: track trade keys we've already processed

    def _needs_proxy(self, url: str) -> bool:
        return "polymarket.com" in url

    async def _get_json(self, url: str, params: dict = None) -> list | dict:
        if self._needs_proxy(url) and self.config.PROXY_URL:
            connector = ProxyConnector.from_url(self.config.PROXY_URL)
            session = aiohttp.ClientSession(connector=connector)
        else:
            session = aiohttp.ClientSession()
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json()
        finally:
            await session.close()

    def _is_crypto_market(self, question: str) -> str:
        """Return asset category if this is a crypto market, empty string if not."""
        q_lower = question.lower()
        for asset, keywords in TARGET_KEYWORDS.items():
            for kw in keywords:
                if kw in q_lower:
                    return asset
        # Broader crypto keywords
        crypto_terms = ["token", "airdrop", "defi", "nft", "stablecoin",
                        "usdc", "usdt", "metamask", "megaeth", "hyperliquid",
                        "pump.fun", "base launch", "chain"]
        for term in crypto_terms:
            if term in q_lower:
                return "CRYPTO"
        return ""

    async def fetch_active_markets(self) -> list[dict]:
        # Use events API with crypto tag to find crypto markets
        url = f"{self.config.GAMMA_API_URL}/events"
        params = {"active": "true", "closed": "false", "limit": 200, "tag": "crypto"}
        events = await self._get_json(url, params)

        stored = []
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()

        for event in events:
            markets = event.get("markets", [])
            for m in markets:
                if m.get("closed", True):
                    continue

                question = m.get("question", "")
                asset = self._is_crypto_market(question)
                if not asset:
                    # It's tagged crypto but question doesn't match — check event title
                    event_title = event.get("title", "")
                    asset = self._is_crypto_market(event_title)
                    if not asset:
                        continue

                outcomes = m.get("outcomes", "[]")
                if isinstance(outcomes, str):
                    import json as _json
                    try:
                        outcomes = _json.loads(outcomes)
                    except Exception:
                        outcomes = ["Yes", "No"]

                prices = m.get("outcomePrices", "[]")
                if isinstance(prices, str):
                    import json as _json
                    try:
                        prices = _json.loads(prices)
                    except Exception:
                        prices = ["0.5", "0.5"]

                price_yes = float(prices[0]) if len(prices) > 0 else 0.5
                price_no = float(prices[1]) if len(prices) > 1 else 0.5

                # Get token IDs from clobTokenIds
                clob_ids = m.get("clobTokenIds", "[]")
                if isinstance(clob_ids, str):
                    import json as _json
                    try:
                        clob_ids = _json.loads(clob_ids)
                    except Exception:
                        clob_ids = []

                if len(clob_ids) < 2:
                    continue

                row = {
                    "condition_id": m.get("conditionId", ""),
                    "question": question,
                    "token_id_yes": clob_ids[0],
                    "token_id_no": clob_ids[1],
                    "asset": asset,
                    "price_yes": price_yes,
                    "price_no": price_no,
                    "volume": float(m.get("volumeNum", m.get("volume", 0)) or 0),
                    "end_time": m.get("endDate", ""),
                    "active": 1,
                    "updated_at": now,
                }

                conn.execute(
                    """INSERT OR REPLACE INTO markets
                       (condition_id, question, token_id_yes, token_id_no, asset,
                        price_yes, price_no, volume, end_time, active, updated_at)
                       VALUES (:condition_id, :question, :token_id_yes, :token_id_no,
                               :asset, :price_yes, :price_no, :volume, :end_time,
                               :active, :updated_at)""",
                    row,
                )
                stored.append(row)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(stored)} active crypto markets")
        return stored

    async def discover_whale_wallets(self) -> list[str]:
        """Find top traders by fetching recent trades on our tracked markets via data-api."""
        conn = get_connection(self.db_path)
        markets = conn.execute(
            "SELECT condition_id FROM markets WHERE active = 1 ORDER BY volume DESC LIMIT 10"
        ).fetchall()
        conn.close()

        wallet_trades = {}  # wallet -> total volume
        for market in markets:
            cid = market["condition_id"]
            url = "https://data-api.polymarket.com/trades"
            params = {"market": cid, "limit": 100}
            try:
                trades = await self._get_json(url, params)
                for t in trades:
                    wallet = t.get("proxyWallet", "")
                    if wallet:
                        size = float(t.get("size", 0))
                        wallet_trades[wallet] = wallet_trades.get(wallet, 0) + size
            except Exception as e:
                log.error(f"Failed to fetch trades for market {cid[:10]}: {e}")

        # Sort by total volume and return top wallets
        sorted_wallets = sorted(wallet_trades.items(), key=lambda x: x[1], reverse=True)
        wallets = [w[0] for w in sorted_wallets]
        log.info(f"Discovered {len(wallets)} unique wallets from top crypto markets")
        return wallets

    async def fetch_wallet_trades_public(self, wallet_address: str) -> list[dict]:
        """Fetch trades for a wallet using the public data-api."""
        url = "https://data-api.polymarket.com/trades"
        params = {"user": wallet_address, "limit": 200}
        try:
            raw_trades = await self._get_json(url, params)
        except Exception as e:
            log.error(f"Failed to fetch trades for {wallet_address[:10]}: {e}")
            return []

        trades = []
        conn = get_connection(self.db_path)

        # Ensure wallet exists in wallets table (FK constraint)
        conn.execute("INSERT OR IGNORE INTO wallets (address) VALUES (?)", (wallet_address,))

        for t in raw_trades:
            side = t.get("side", "BUY")
            size = float(t.get("size", 0))
            price = float(t.get("price", 0))
            ts = t.get("timestamp", 0)
            if isinstance(ts, (int, float)):
                from datetime import datetime as dt
                timestamp = dt.fromtimestamp(ts, tz=timezone.utc).isoformat()
            else:
                timestamp = str(ts)

            # Determine outcome from price (resolved markets have price 0 or 1)
            outcome = "pending"
            pnl = 0.0

            trade = {
                "wallet_address": wallet_address,
                "market_id": t.get("conditionId", ""),
                "market_slug": t.get("slug", ""),
                "side": side,
                "size": size,
                "entry_price": price,
                "outcome": outcome,
                "pnl": pnl,
                "timestamp": timestamp,
            }
            conn.execute(
                """INSERT INTO wallet_trades
                   (wallet_address, market_id, market_slug, side, size,
                    entry_price, outcome, pnl, timestamp)
                   VALUES (:wallet_address, :market_id, :market_slug, :side,
                           :size, :entry_price, :outcome, :pnl, :timestamp)""",
                trade,
            )
            trades.append(trade)

        conn.commit()
        conn.close()
        if trades:
            log.info(f"Fetched {len(trades)} trades for wallet {wallet_address[:10]}...")
        return trades

    async def fetch_price_candles(self, asset: str, limit: int = 60) -> list[dict]:
        symbol = f"{asset}USDT"
        url = f"{self.config.BINANCE_API_URL}/api/v3/klines"
        params = {"symbol": symbol, "interval": "1m", "limit": limit}
        raw = await self._get_json(url, params)

        candles = []
        conn = get_connection(self.db_path)

        for k in raw:
            candle = {
                "asset": asset,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "timestamp": datetime.fromtimestamp(
                    k[0] / 1000, tz=timezone.utc
                ).isoformat(),
            }
            conn.execute(
                """INSERT INTO price_candles
                   (asset, open, high, low, close, volume, timestamp)
                   VALUES (:asset, :open, :high, :low, :close, :volume, :timestamp)""",
                candle,
            )
            candles.append(candle)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(candles)} {asset} candles")
        return candles

    async def fetch_wallet_trades(self, wallet_address: str) -> list[dict]:
        url = f"{self.config.POLYMARKET_API_URL}/trades"
        params = {"maker": wallet_address, "limit": 1000}
        try:
            raw_trades = await self._get_json(url, params)
        except Exception as e:
            log.error(f"Failed to fetch trades for {wallet_address}: {e}")
            return []

        trades = []
        conn = get_connection(self.db_path)

        for t in raw_trades:
            trade = {
                "wallet_address": wallet_address,
                "market_id": t.get("market", ""),
                "market_slug": t.get("matchTime", ""),
                "side": t.get("side", ""),
                "size": float(t.get("size", 0)),
                "entry_price": float(t.get("price", 0)),
                "outcome": t.get("outcome", "pending"),
                "pnl": float(t.get("pnl", 0)),
                "timestamp": t.get("matchTime", ""),
            }
            conn.execute(
                """INSERT INTO wallet_trades
                   (wallet_address, market_id, market_slug, side, size,
                    entry_price, outcome, pnl, timestamp)
                   VALUES (:wallet_address, :market_id, :market_slug, :side,
                           :size, :entry_price, :outcome, :pnl, :timestamp)""",
                trade,
            )
            trades.append(trade)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(trades)} trades for wallet {wallet_address[:10]}...")
        return trades

    async def poll_tracked_wallets(self) -> list[dict]:
        conn = get_connection(self.db_path)
        tracked = conn.execute(
            "SELECT address FROM tracked_wallets ORDER BY rank"
        ).fetchall()
        conn.close()

        new_trades = []
        for row in tracked:
            address = row["address"]
            url = "https://data-api.polymarket.com/trades"
            params = {"user": address, "limit": 5}
            try:
                recent = await self._get_json(url, params)
                for t in recent:
                    # Dedup: skip trades we've already seen
                    trade_ts = t.get("timestamp", 0)
                    trade_key = f"{address}_{t.get('conditionId','')}_{trade_ts}"
                    if trade_key in self._seen_trades:
                        continue
                    self._seen_trades.add(trade_key)

                    t["wallet_address"] = address
                    t["side"] = t.get("side", "BUY")
                    t["size"] = float(t.get("size", 0))
                    t["market_id"] = t.get("conditionId", "")
                    new_trades.append(t)
            except Exception as e:
                log.error(f"Poll failed for {address[:10]}: {e}")

        if new_trades:
            log.info(f"Polled {len(tracked)} wallets, found {len(new_trades)} NEW trades")
        # Cap seen trades cache to prevent memory growth
        if len(self._seen_trades) > 10000:
            # Keep only the most recent half
            self._seen_trades = set(list(self._seen_trades)[-5000:])
        return new_trades
