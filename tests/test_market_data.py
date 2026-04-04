import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from binance_modules.market_data import MarketData
from config import Config


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def sample_klines_response():
    """Binance klines response: [open_time, open, high, low, close, volume, ...]"""
    return [
        [1700000000000, "42000.00", "42100.00", "41900.00", "42050.00", "100.5",
         1700000059999, "4200000.00", 500, "50.0", "2100000.00", "0"],
        [1700000060000, "42050.00", "42200.00", "42000.00", "42150.00", "120.3",
         1700000119999, "5060000.00", 600, "60.0", "2530000.00", "0"],
    ]


def test_parse_klines(config, sample_klines_response):
    md = MarketData(config)
    candles = md.parse_klines(sample_klines_response)
    assert len(candles) == 2
    assert candles[0]["open"] == 42000.00
    assert candles[0]["high"] == 42100.00
    assert candles[0]["low"] == 41900.00
    assert candles[0]["close"] == 42050.00
    assert candles[0]["volume"] == 100.5
    assert candles[0]["open_time"] == 1700000000000


@pytest.mark.asyncio
async def test_fetch_klines_calls_api(config, sample_klines_response):
    md = MarketData(config)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=sample_klines_response)

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        candles = await md.fetch_klines("BTCUSDT", "1m", limit=2)

    assert len(candles) == 2
    assert candles[1]["close"] == 42150.00
    mock_session.get.assert_called_once()
    call_url = mock_session.get.call_args[0][0]
    assert "/api/v3/klines" in call_url


@pytest.mark.asyncio
async def test_fetch_price(config):
    md = MarketData(config)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"symbol": "BTCUSDT", "price": "42050.00"})

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        price = await md.fetch_price("BTCUSDT")

    assert price == 42050.00
