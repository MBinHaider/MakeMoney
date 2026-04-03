import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from modules.data_collector import DataCollector
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_collector.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    return cfg


@pytest.fixture
def collector(config):
    return DataCollector(config)


MOCK_GAMMA_EVENTS = [
    {
        "title": "Bitcoin price prediction",
        "markets": [
            {
                "conditionId": "0xabc123",
                "question": "Will BTC go up in the next 5 minutes?",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.55", "0.45"]',
                "clobTokenIds": '["tok_yes_1", "tok_no_1"]',
                "endDate": "2026-04-03T14:05:00Z",
                "volumeNum": 50000.0,
                "active": True,
                "closed": False,
            }
        ],
    }
]


@pytest.mark.asyncio
async def test_fetch_markets_stores_in_db(collector):
    with patch.object(collector, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MOCK_GAMMA_EVENTS
        await collector.fetch_active_markets()

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM markets").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["condition_id"] == "0xabc123"
    assert rows[0]["asset"] == "BTC"
    assert rows[0]["price_yes"] == 0.55


@pytest.mark.asyncio
async def test_fetch_markets_filters_non_crypto(collector):
    non_crypto = [
        {
            "title": "Weather prediction",
            "markets": [
                {
                    "conditionId": "0xdef456",
                    "question": "Will it rain tomorrow?",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.60", "0.40"]',
                    "clobTokenIds": '["tok_yes_2", "tok_no_2"]',
                    "endDate": "2026-04-04T00:00:00Z",
                    "volumeNum": 1000.0,
                    "active": True,
                    "closed": False,
                }
            ],
        }
    ]
    with patch.object(collector, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = non_crypto
        await collector.fetch_active_markets()

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM markets").fetchall()
    conn.close()
    assert len(rows) == 0
