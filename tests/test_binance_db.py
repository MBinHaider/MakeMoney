import os
import tempfile
import pytest
from utils.binance_db import BINANCE_SCHEMA, init_binance_db
from utils.db import get_connection


def test_init_binance_db_creates_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_binance.db")
        init_binance_db(db_path)
        conn = get_connection(db_path)
        tables = [
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        conn.close()
        assert "candles" in tables
        assert "bn_signals" in tables
        assert "bn_trades" in tables
        assert "bn_portfolio" in tables


def test_init_binance_db_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_binance.db")
        init_binance_db(db_path)
        init_binance_db(db_path)  # should not raise
        conn = get_connection(db_path)
        tables = [
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        conn.close()
        assert "candles" in tables
