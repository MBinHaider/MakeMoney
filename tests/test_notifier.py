import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from modules.notifier import Notifier
from config import Config

TEST_DB = "data/test_notifier.db"


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.TELEGRAM_BOT_TOKEN = "fake_token"
    cfg.TELEGRAM_CHAT_ID = "123456"
    return cfg


@pytest.fixture
def notifier(config):
    return Notifier(config)


def test_format_trade_alert(notifier):
    trade = {"side": "BUY", "size": 2.50, "entry_price": 0.55, "market_id": "mkt_btc_up"}
    signal_score = 78.5
    msg = notifier.format_trade_alert(trade, signal_score)
    assert "BUY" in msg
    assert "$2.50" in msg
    assert "78.5" in msg


def test_format_trade_outcome(notifier):
    msg = notifier.format_trade_outcome(market_id="mkt_btc_up", won=True, pnl=1.50, portfolio_value=101.50)
    assert "WON" in msg
    assert "$1.50" in msg
    assert "$101.50" in msg


def test_format_daily_summary(notifier):
    stats = {
        "current_value": 105.0, "starting_capital": 100.0, "total_pnl": 5.0,
        "total_trades": 10, "win_rate": 0.70, "daily_pnl": 3.0,
        "open_positions": 2, "is_paused": False,
    }
    msg = notifier.format_daily_summary(stats)
    assert "$105.00" in msg
    assert "70.0%" in msg
    assert "$3.00" in msg


def test_format_status(notifier):
    stats = {
        "current_value": 95.0, "starting_capital": 100.0, "total_pnl": -5.0,
        "total_trades": 8, "win_rate": 0.50, "drawdown": 0.05,
        "daily_pnl": -2.0, "open_positions": 1, "is_paused": False,
    }
    msg = notifier.format_status(stats)
    assert "$95.00" in msg
    assert "-$5.00" in msg
