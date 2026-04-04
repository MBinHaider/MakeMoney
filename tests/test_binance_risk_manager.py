import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from binance_modules.risk_manager import BinanceRiskManager
from utils.binance_db import init_binance_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = Config()
        config.BINANCE_DB_PATH = db_path
        init_binance_db(db_path)
        rm = BinanceRiskManager(config)
        rm.init_portfolio(45.0)
        yield rm, db_path


class TestInitPortfolio:
    def test_init_creates_portfolio(self, setup_db):
        rm, db_path = setup_db
        status = rm.get_status()
        assert status["balance"] == 45.0
        assert status["starting_balance"] == 45.0
        assert status["total_trades"] == 0
        assert status["is_paused"] is False


class TestCanTrade:
    def test_can_trade_when_clear(self, setup_db):
        rm, _ = setup_db
        result = rm.can_trade()
        assert result["allowed"] is True

    def test_blocked_when_paused(self, setup_db):
        rm, _ = setup_db
        rm.pause()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "paused" in result["reason"].lower()

    def test_blocked_at_max_positions(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            conn.execute(
                "INSERT INTO bn_trades (timestamp, symbol, side, price, size, tp, sl, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, "open"),
            )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "position" in result["reason"].lower()

    def test_blocked_by_daily_loss_limit(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-2.25)  # 5% of $45
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "daily" in result["reason"].lower()

    def test_blocked_by_consecutive_losses(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-0.10)
        rm.record_trade_outcome(-0.10)
        rm.record_trade_outcome(-0.10)
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "consecutive" in result["reason"].lower()

    def test_blocked_by_min_trade_interval(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE bn_portfolio SET last_trade_time = ? WHERE id = 1", (now,)
        )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "interval" in result["reason"].lower()


class TestPositionSizing:
    def test_normal_signal_size(self, setup_db):
        rm, _ = setup_db
        size = rm.calc_position_size("normal")
        assert size == pytest.approx(9.0)  # 20% of $45

    def test_strong_signal_size(self, setup_db):
        rm, _ = setup_db
        size = rm.calc_position_size("strong")
        assert size == pytest.approx(13.5)  # 30% of $45


class TestRecordOutcome:
    def test_win_updates_portfolio(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(0.50)
        status = rm.get_status()
        assert status["balance"] == 45.50
        assert status["total_trades"] == 1
        assert status["total_wins"] == 1
        assert status["consecutive_losses"] == 0

    def test_loss_updates_portfolio(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-0.15)
        status = rm.get_status()
        assert status["balance"] == 44.85
        assert status["total_trades"] == 1
        assert status["total_wins"] == 0
        assert status["consecutive_losses"] == 1
