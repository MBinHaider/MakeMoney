import pytest
from fivemin_modules.notifier import FiveMinNotifier
from config import Config


@pytest.fixture
def notifier():
    config = Config()
    config.TELEGRAM_BOT_TOKEN = ""
    config.TELEGRAM_CHAT_ID = ""
    return FiveMinNotifier(config)


class TestFormatMessages:
    def test_trade_entry_message(self, notifier):
        trade = {
            "asset": "BTC", "direction": "UP", "entry_price": 0.55,
            "shares": 9.09, "cost": 5.00,
        }
        signal_info = {"confidence": 0.72, "phase": "mid", "indicators": {"momentum": "UP", "imbalance": "UP"}}
        msg = notifier.format_trade_entry(trade, signal_info)
        assert "[5M]" in msg
        assert "BUY UP BTC" in msg
        assert "0.55" in msg

    def test_win_message(self, notifier):
        result = {
            "asset": "BTC", "direction": "UP", "result": "win",
            "pnl": 4.05, "entry_price": 0.55,
        }
        status = {"balance": 29.05, "consecutive_losses": 0, "total_wins": 1, "total_trades": 1}
        msg = notifier.format_settlement(result, status)
        assert "[5M]" in msg
        assert "WIN" in msg
        assert "4.05" in msg

    def test_loss_message(self, notifier):
        result = {
            "asset": "BTC", "direction": "DOWN", "result": "loss",
            "pnl": -4.95, "entry_price": 0.55,
        }
        status = {"balance": 20.05, "consecutive_losses": 1, "total_wins": 0, "total_trades": 1}
        msg = notifier.format_settlement(result, status)
        assert "[5M]" in msg
        assert "LOSS" in msg

    def test_cooldown_message(self, notifier):
        msg = notifier.format_cooldown(3, 15)
        assert "[5M]" in msg
        assert "PAUSED" in msg
        assert "15" in msg

    def test_daily_limit_message(self, notifier):
        msg = notifier.format_daily_limit(5.0)
        assert "[5M]" in msg
        assert "DAILY LIMIT" in msg

    def test_startup_message(self, notifier):
        msg = notifier.format_startup("paper", 25.0, ["BTC", "ETH", "SOL"])
        assert "[5M]" in msg
        assert "paper" in msg
        assert "25.00" in msg
