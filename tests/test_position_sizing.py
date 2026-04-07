import os
import tempfile
import pytest
from fivemin_modules.risk_manager import FiveMinRiskManager
from utils.fivemin_db import init_fivemin_db
from config import Config


@pytest.fixture
def rm():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        config = Config()
        config.FIVEMIN_DB_PATH = db_path
        init_fivemin_db(db_path)
        rm = FiveMinRiskManager(config)
        rm.init_portfolio(20.0)
        yield rm


def test_3of3_high_confidence(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.90)
    assert size == 10.0


def test_3of3_medium_confidence(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.75)
    assert size == 7.0


def test_2of3_high_confidence(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.80)
    assert size == 5.0


def test_2of3_low_confidence(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.60)
    assert size == 3.0


def test_weak_signal_returns_zero(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.50)
    assert size == 0.0


def test_size_capped_by_balance(rm):
    rm.init_portfolio(4.0)  # only $4 in balance
    size = rm.calc_position_size_for_signal(score=3, confidence=0.95)
    assert size == 4.0  # capped at balance, not $10


def test_3of3_boundary_85(rm):
    """Exactly 0.85 confidence should still get high tier."""
    size = rm.calc_position_size_for_signal(score=3, confidence=0.85)
    assert size == 10.0


def test_3of3_boundary_70(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.70)
    assert size == 7.0
