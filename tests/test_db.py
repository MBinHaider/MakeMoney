import os
import sqlite3
import pytest
from utils.db import init_db, get_connection

TEST_DB = "data/test_polybot.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_init_db_creates_tables():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "wallets" in tables
    assert "wallet_trades" in tables
    assert "tracked_wallets" in tables
    assert "signals" in tables
    assert "bot_trades" in tables
    assert "price_candles" in tables
    assert "markets" in tables


def test_init_db_wallets_schema():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute("PRAGMA table_info(wallets)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "address" in columns
    assert "total_trades" in columns
    assert "win_rate" in columns
    assert "total_pnl" in columns
    assert "composite_score" in columns


def test_init_db_bot_trades_schema():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute("PRAGMA table_info(bot_trades)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "market_id" in columns
    assert "side" in columns
    assert "size" in columns
    assert "entry_price" in columns
    assert "outcome" in columns
    assert "pnl" in columns
    assert "signal_score" in columns


def test_get_connection_returns_valid_connection():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()
