import os
import pytest
from datetime import datetime, timezone
from modules.risk_manager import RiskManager
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_risk.db"


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
    cfg.MAX_CONCURRENT_POSITIONS = 10
    cfg.MAX_CAPITAL_PER_TRADE_PCT = 0.10
    cfg.MAX_TOTAL_EXPOSURE_PCT = 0.30
    cfg.HARD_STOP_DRAWDOWN_PCT = 0.30
    cfg.SOFT_STOP_DRAWDOWN_PCT = 0.10
    cfg.DAILY_LOSS_LIMIT_PCT = 0.10
    cfg.BASE_BET_PCT = 0.02
    cfg.CONSECUTIVE_LOSS_PAUSE = 3
    return cfg


def _init_portfolio(db_path, capital=100.0):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO portfolio
           (id, starting_capital, current_value, peak_value, updated_at)
           VALUES (1, ?, ?, ?, ?)""",
        (capital, capital, capital, now),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def risk_mgr(config):
    _init_portfolio(TEST_DB, 100.0)
    return RiskManager(config)


def test_can_trade_returns_true_when_healthy(risk_mgr):
    result = risk_mgr.can_trade()
    assert result["allowed"] is True


def test_can_trade_blocked_when_paused(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute("UPDATE portfolio SET is_paused = 1 WHERE id = 1")
    conn.commit()
    conn.close()
    result = risk_mgr.can_trade()
    assert result["allowed"] is False
    assert "paused" in result["reason"]


def test_can_trade_blocked_hard_stop_drawdown(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute("UPDATE portfolio SET current_value = 65, peak_value = 100 WHERE id = 1")
    conn.commit()
    conn.close()
    result = risk_mgr.can_trade()
    assert result["allowed"] is False
    assert "hard stop" in result["reason"].lower()


def test_calc_position_size_base(risk_mgr):
    size = risk_mgr.calc_position_size(signal_score=70)
    assert size == pytest.approx(2.0, abs=0.1)


def test_calc_position_size_high_confidence(risk_mgr):
    size = risk_mgr.calc_position_size(signal_score=100)
    assert size == pytest.approx(4.0, abs=0.1)


def test_calc_position_size_capped_at_max(risk_mgr):
    size = risk_mgr.calc_position_size(signal_score=100)
    assert size <= 100 * 0.10


def test_calc_position_size_reduced_during_soft_stop(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute("UPDATE portfolio SET current_value = 87, peak_value = 100 WHERE id = 1")
    conn.commit()
    conn.close()
    size = risk_mgr.calc_position_size(signal_score=70)
    assert size == pytest.approx(1.0, abs=0.2)


def test_record_trade_outcome_updates_portfolio(risk_mgr):
    risk_mgr.record_trade_outcome(pnl=5.0)
    conn = get_connection(TEST_DB)
    row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
    conn.close()
    assert row["current_value"] == 105.0
    assert row["total_trades"] == 1
    assert row["total_wins"] == 1


def test_pause_and_resume(risk_mgr):
    risk_mgr.pause()
    assert risk_mgr.can_trade()["allowed"] is False
    risk_mgr.resume()
    assert risk_mgr.can_trade()["allowed"] is True
