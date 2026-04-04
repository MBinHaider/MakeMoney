import pytest
from binance_modules.notifier import BinanceNotifier
from config import Config


@pytest.fixture
def notifier():
    return BinanceNotifier(Config())


class TestFormatBuyAlert:
    def test_buy_alert_format(self, notifier):
        trade = {
            "side": "buy", "symbol": "BTCUSDT", "entry_price": 68432.50,
            "size": 12.00, "tp": 69458.85, "sl": 67748.18,
        }
        indicators = {"rsi": 28, "macd_histogram": 0.5}
        status = {"open_positions": 2, "balance": 47.32}
        msg = notifier.format_buy_alert(trade, indicators, status)
        assert "BinanceBot" in msg
        assert "BUY" in msg
        assert "BTCUSDT" in msg
        assert "68,432.50" in msg
        assert "12.00" in msg


class TestFormatSellAlert:
    def test_sell_alert_format(self, notifier):
        closed = {
            "symbol": "ETHUSDT", "exit_price": 3521.40,
            "pnl": 0.38, "hold_time": "7m", "reason": "take_profit",
        }
        status = {"open_positions": 1, "balance": 47.70}
        msg = notifier.format_sell_alert(closed, status)
        assert "BinanceBot" in msg
        assert "SELL" in msg or "CLOSED" in msg
        assert "ETHUSDT" in msg
        assert "0.38" in msg


class TestFormatSummary:
    def test_summary_format(self, notifier):
        status = {
            "balance": 47.70, "starting_balance": 45.00,
            "daily_pnl": 2.70, "total_trades": 8, "total_wins": 5,
            "win_rate": 0.625, "open_positions": 1, "is_paused": False,
        }
        open_trades = [
            {"symbol": "BTCUSDT", "side": "buy", "price": 68432, "size": 12},
        ]
        msg = notifier.format_summary(status, open_trades)
        assert "BinanceBot" in msg
        assert "47.70" in msg
        assert "45.00" in msg


class TestFormatDailyReport:
    def test_daily_report_format(self, notifier):
        status = {
            "balance": 47.70, "starting_balance": 45.00,
            "daily_pnl": 2.70, "total_pnl": 2.70,
            "total_trades": 14, "total_wins": 9,
            "win_rate": 0.643, "open_positions": 0,
        }
        today_trades = [
            {"symbol": "ETHUSDT", "pnl": 0.52},
            {"symbol": "BTCUSDT", "pnl": -0.14},
        ]
        msg = notifier.format_daily_report(status, today_trades)
        assert "BinanceBot" in msg
        assert "Daily" in msg
        assert "47.70" in msg
