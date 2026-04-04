import os
import tempfile
import pytest
from utils.fivemin_db import init_fivemin_db, FIVEMIN_SCHEMA
from utils.db import get_connection


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "test5m.db")
        yield path


class TestInitFiveMinDb:
    def test_creates_tables(self, db_path):
        init_fivemin_db(db_path)
        conn = get_connection(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        conn.close()
        assert "fm_trades" in table_names
        assert "fm_signals" in table_names
        assert "fm_daily_stats" in table_names
        assert "fm_cooldowns" in table_names
        assert "fm_portfolio" in table_names

    def test_idempotent(self, db_path):
        init_fivemin_db(db_path)
        init_fivemin_db(db_path)
        conn = get_connection(db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert len(tables) >= 5

    def test_portfolio_insert(self, db_path):
        init_fivemin_db(db_path)
        conn = get_connection(db_path)
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 25.0, 25.0, 25.0, 0.0, '2026-04-04', 0, 0, 0.0, 0, 0, 0, '', '')""",
        )
        conn.commit()
        row = conn.execute("SELECT * FROM fm_portfolio WHERE id = 1").fetchone()
        conn.close()
        assert row["balance"] == 25.0
        assert row["starting_balance"] == 25.0
