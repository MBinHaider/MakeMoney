import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from modules.trade_executor import TradeExecutor
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_executor.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO portfolio
           (id, starting_capital, current_value, peak_value, updated_at)
           VALUES (1, 100, 100, 100, ?)""",
        (now,),
    )
    conn.commit()
    conn.close()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.TRADING_MODE = "paper"
    return cfg


@pytest.fixture
def executor(config):
    return TradeExecutor(config)


def test_paper_trade_logs_to_db(executor):
    signal = {"id": 1, "market_id": "mkt_1", "direction": "BUY", "total_score": 75.0}
    market = {"condition_id": "mkt_1", "token_id_yes": "tok_y", "token_id_no": "tok_n", "price_yes": 0.55, "price_no": 0.45}
    result = executor.execute_paper_trade(signal, market, size=2.0)
    assert result["status"] == "filled"
    assert result["size"] == 2.0
    conn = get_connection(TEST_DB)
    trades = conn.execute("SELECT * FROM bot_trades").fetchall()
    conn.close()
    assert len(trades) == 1
    assert trades[0]["side"] == "BUY"
    assert trades[0]["size"] == 2.0


def test_paper_trade_buy_uses_yes_price(executor):
    signal = {"id": 1, "market_id": "mkt_1", "direction": "BUY", "total_score": 80.0}
    market = {"condition_id": "mkt_1", "token_id_yes": "tok_y", "token_id_no": "tok_n", "price_yes": 0.60, "price_no": 0.40}
    result = executor.execute_paper_trade(signal, market, size=5.0)
    assert result["entry_price"] == 0.60


def test_paper_trade_sell_uses_no_price(executor):
    signal = {"id": 2, "market_id": "mkt_2", "direction": "SELL", "total_score": 72.0}
    market = {"condition_id": "mkt_2", "token_id_yes": "tok_y2", "token_id_no": "tok_n2", "price_yes": 0.55, "price_no": 0.45}
    result = executor.execute_paper_trade(signal, market, size=3.0)
    assert result["entry_price"] == 0.45
    assert result["side"] == "SELL"
