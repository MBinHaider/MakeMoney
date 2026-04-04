import aiohttp
from utils.logger import get_logger
from config import Config

log = get_logger("binance_market_data")


class MarketData:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.BINANCE_API_URL

    def parse_klines(self, raw: list) -> list[dict]:
        candles = []
        for k in raw:
            candles.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        return candles

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 100) -> list[dict]:
        url = f"{self.base_url}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with aiohttp.ClientSession() as session:
            resp = await session.get(url, params=params)
            if resp.status != 200:
                log.error(f"Binance klines error: {resp.status}")
                return []
            raw = await resp.json()
            return self.parse_klines(raw)

    async def fetch_price(self, symbol: str) -> float:
        url = f"{self.base_url}/api/v3/ticker/price"
        params = {"symbol": symbol}
        async with aiohttp.ClientSession() as session:
            resp = await session.get(url, params=params)
            if resp.status != 200:
                log.error(f"Binance price error: {resp.status}")
                return 0.0
            data = await resp.json()
            return float(data["price"])

    async def fetch_all_candles(self) -> dict[str, dict[str, list[dict]]]:
        """Fetch 1m and 5m candles for all configured pairs.
        Returns: {symbol: {"1m": [candles], "5m": [candles]}}
        """
        result = {}
        for symbol in self.config.BINANCE_PAIRS:
            candles_1m = await self.fetch_klines(
                symbol, self.config.BINANCE_CANDLE_INTERVAL_1M, limit=100
            )
            candles_5m = await self.fetch_klines(
                symbol, self.config.BINANCE_CANDLE_INTERVAL_5M, limit=100
            )
            result[symbol] = {"1m": candles_1m, "5m": candles_5m}
        return result
