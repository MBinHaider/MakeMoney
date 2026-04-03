import aiohttp
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

    async def _get_json(self, url: str, params: dict = None) -> list | dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json()

    def _detect_asset(self, question: str) -> str | None:
        q_lower = question.lower()
        for asset, keywords in TARGET_KEYWORDS.items():
            if asset in self.config.TARGET_MARKETS:
                for kw in keywords:
                    if kw in q_lower:
                        return asset
        return None

    async def fetch_active_markets(self) -> list[dict]:
        url = f"{self.config.GAMMA_API_URL}/markets"
        params = {"active": "true", "closed": "false", "limit": 100}
        markets = await self._get_json(url, params)

        stored = []
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()

        for m in markets:
            question = m.get("question", "")
            asset = self._detect_asset(question)
            if not asset:
                continue

            tokens = m.get("tokens", [])
            if len(tokens) < 2:
                continue

            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), tokens[0])
            no_token = next((t for t in tokens if t.get("outcome") == "No"), tokens[1])

            row = {
                "condition_id": m["conditionId"],
                "question": question,
                "token_id_yes": yes_token["token_id"],
                "token_id_no": no_token["token_id"],
                "asset": asset,
                "price_yes": float(yes_token.get("price", 0.5)),
                "price_no": float(no_token.get("price", 0.5)),
                "volume": float(m.get("volume", 0)),
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
            url = f"{self.config.POLYMARKET_API_URL}/trades"
            params = {"maker": address, "limit": 10}
            try:
                recent = await self._get_json(url, params)
                for t in recent:
                    t["wallet_address"] = address
                    new_trades.append(t)
            except Exception as e:
                log.error(f"Poll failed for {address[:10]}: {e}")

        log.info(f"Polled {len(tracked)} wallets, found {len(new_trades)} recent trades")
        return new_trades
