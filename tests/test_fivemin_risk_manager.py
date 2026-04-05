import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from fivemin_modules.risk_manager import FiveMinRiskManager
from utils.fivemin_db import init_fivemin_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test5m.db")
        config = Config()
        config.FIVEMIN_DB_PATH = db_path
        init_fivemin_db(db_path)
        rm = FiveMinRiskManager(config)
        rm.init_portfolio(25.0)
        yield rm, db_path


class TestInitPortfolio:
    def test_creates_portfolio(self, setup_db):
        rm, _ = setup_db
        status = rm.get_status()
        assert status["balance"] == 25.0
        assert status["starting_balance"] == 25.0
        assert status["total_trades"] == 0
        assert status["is_paused"] is False

    def test_reinit_resets(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(1.0)
        rm.init_portfolio(25.0)
        status = rm.get_status()
        assert status["balance"] == 25.0
        assert status["total_trades"] == 0


class TestCanTrade:
    def test_can_trade_when_clear(self, setup_db):
        rm, _ = setup_db
        result = rm.can_trade()
        assert result["approved"] is True

    def test_blocked_when_paused(self, setup_db):
        rm, _ = setup_db
        rm.pause()
        result = rm.can_trade()
        assert result["approved"] is False
        assert "paused" in result["reason"].lower()

    def test_blocked_by_daily_loss_limit(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-5.0)
        result = rm.can_trade()
        assert result["approved"] is False
        assert "daily" in result["reason"].lower()

    def test_blocked_by_consecutive_losses(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-1.0)
        rm.record_trade_outcome(-1.0)
        rm.record_trade_outcome(-1.0)
        result = rm.can_trade()
        assert result["approved"] is False
        assert "consecutive" in result["reason"].lower() or "cooldown" in result["reason"].lower()

    def test_blocked_by_daily_trade_cap(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        conn.execute(
            "UPDATE fm_portfolio SET daily_trade_count = 50, daily_pnl_date = ? WHERE id = 1",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d"),),
        )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["approved"] is False
        assert "cap" in result["reason"].lower() or "limit" in result["reason"].lower()

    def test_blocked_by_insufficient_balance(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        conn.execute("UPDATE fm_portfolio SET balance = 0.50 WHERE id = 1")
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["approved"] is False
        assert "balance" in result["reason"].lower()

    def test_cooldown_expires(self, setup_db):
        rm, db_path = setup_db
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        conn = get_connection(db_path)
        conn.execute(
            "UPDATE fm_portfolio SET is_paused = 1, pause_until = ? WHERE id = 1",
            (past,),
        )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["approved"] is True

    def test_max_amount_capped(self, setup_db):
        rm, _ = setup_db
        result = rm.can_trade()
        assert result["max_amount"] == 5.0


class TestRecordOutcome:
    def test_win(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(4.05)
        status = rm.get_status()
        assert status["balance"] == 29.05
        assert status["total_trades"] == 1
        assert status["total_wins"] == 1
        assert status["consecutive_losses"] == 0

    def test_loss(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-4.95)
        status = rm.get_status()
        assert status["balance"] == pytest.approx(20.05)
        assert status["total_trades"] == 1
        assert status["total_wins"] == 0
        assert status["consecutive_losses"] == 1

    def test_win_resets_consecutive_losses(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-1.0)
        rm.record_trade_outcome(-1.0)
        rm.record_trade_outcome(2.0)
        status = rm.get_status()
        assert status["consecutive_losses"] == 0
