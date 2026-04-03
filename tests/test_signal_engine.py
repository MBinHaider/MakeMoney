# tests/test_signal_engine.py
import os
import pytest
from datetime import datetime, timezone, timedelta
from modules.signal_engine import SignalEngine
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_signal.db"


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
    cfg.SIGNAL_AUTO_TRADE_THRESHOLD = 70
    cfg.SIGNAL_ALERT_THRESHOLD = 50
    return cfg


@pytest.fixture
def engine(config):
    return SignalEngine(config)


def _setup_tracked_wallet(db_path, address, rank):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO wallets (address, win_rate, total_pnl, avg_bet_size, composite_score, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (address, 0.75, 5000.0, 50.0, 80.0, now),
    )
    conn.execute(
        "INSERT OR REPLACE INTO tracked_wallets (address, rank, added_at) VALUES (?, ?, ?)",
        (address, rank, now),
    )
    conn.commit()
    conn.close()


def _insert_price_candles(db_path, asset, prices):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)
    for i, price in enumerate(prices):
        conn.execute(
            """INSERT INTO price_candles (asset, open, high, low, close, volume, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (asset, price, price + 10, price - 10, price,
             1000.0, (now - timedelta(minutes=len(prices) - i)).isoformat()),
        )
    conn.commit()
    conn.close()


def test_whale_score_top5_wallet(engine):
    _setup_tracked_wallet(TEST_DB, "0xWHALE", rank=3)
    whale_trade = {
        "wallet_address": "0xWHALE",
        "side": "BUY",
        "size": 100.0,
        "market_id": "market_1",
    }
    score = engine._calc_whale_score(whale_trade)
    assert score > 0
    assert score <= 40


def test_whale_score_top20_wallet(engine):
    _setup_tracked_wallet(TEST_DB, "0xMID", rank=15)
    whale_trade = {
        "wallet_address": "0xMID",
        "side": "BUY",
        "size": 50.0,
        "market_id": "market_1",
    }
    score = engine._calc_whale_score(whale_trade)
    assert score > 0
    assert score <= 40


def test_generate_signal_returns_scored_signal(engine):
    _setup_tracked_wallet(TEST_DB, "0xTOP", rank=1)
    _insert_price_candles(TEST_DB, "BTC", [100, 101, 102, 103, 104])

    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO markets (condition_id, question, token_id_yes, token_id_no,
           asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        ("mkt_1", "Will BTC go up?", "tok_y", "tok_n", "BTC",
         0.55, 0.45, 100000, (now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()

    whale_trade = {
        "wallet_address": "0xTOP",
        "side": "BUY",
        "size": 100.0,
        "market_id": "mkt_1",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal is not None
    assert "total_score" in signal
    assert signal["total_score"] > 0
    assert signal["direction"] == "BUY"


def test_generate_signal_action_auto_trade(engine):
    _setup_tracked_wallet(TEST_DB, "0xBIG", rank=1)
    _insert_price_candles(TEST_DB, "BTC", [100, 101, 102, 103, 104])

    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO markets (condition_id, question, token_id_yes, token_id_no,
           asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        ("mkt_2", "Will BTC go up?", "tok_y2", "tok_n2", "BTC",
         0.52, 0.48, 200000, (now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()

    whale_trade = {
        "wallet_address": "0xBIG",
        "side": "BUY",
        "size": 200.0,
        "market_id": "mkt_2",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal["action"] in ("auto_trade", "alert", "logged")
