import os
import tempfile
from collections import deque
import pytest
from config import Config
from utils.fivemin_db import init_fivemin_db
from fivemin_modules.indicators import calc_momentum, calc_orderbook_imbalance, calc_volume_spike
from fivemin_modules.signal_engine import FiveMinSignalEngine
from fivemin_modules.risk_manager import FiveMinRiskManager
from fivemin_modules.trade_executor import FiveMinTradeExecutor
from fivemin_modules.notifier import FiveMinNotifier


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test5m.db")
        config = Config()
        config.FIVEMIN_DB_PATH = db_path
        config.FIVEMIN_TRADING_MODE = "paper"
        config.TELEGRAM_BOT_TOKEN = ""
        config.TELEGRAM_CHAT_ID = ""
        init_fivemin_db(db_path)
        yield config, db_path


class TestFullTradeFlow:
    def test_signal_to_settlement_win(self, setup):
        """End-to-end: indicators -> signal -> risk check -> trade -> settle (win)."""
        config, db_path = setup
        engine = FiveMinSignalEngine(config)
        risk = FiveMinRiskManager(config)
        executor = FiveMinTradeExecutor(config)
        risk.init_portfolio(25.0)

        # Build a state where all 3 indicators agree UP
        state = {
            "current_price": 100.20,
            "window_open_price": 100.00,
            "volumes": [10.0] * 29 + [30.0],
            "orderbook_up": {
                "bids": [(0.55, 100), (0.54, 80), (0.53, 60), (0.52, 40), (0.51, 30)],
                "asks": [(0.56, 20), (0.57, 15), (0.58, 10), (0.59, 10), (0.60, 5)],
            },
            "orderbook_down": {
                "bids": [(0.44, 20), (0.43, 15), (0.42, 10), (0.41, 10), (0.40, 5)],
                "asks": [(0.45, 100), (0.46, 80), (0.47, 60), (0.48, 40), (0.49, 30)],
            },
            "price_history": deque([100.0 + i * 0.05 for i in range(350)], maxlen=350),
        }

        # Evaluate signal (early phase, need all 3)
        signal = engine.evaluate("BTC", state, seconds_elapsed=60)
        assert signal is not None
        assert signal.direction == "UP"

        # Risk check
        can_trade = risk.can_trade()
        assert can_trade["approved"] is True

        # Execute paper trade
        trade = executor.execute(signal, can_trade["max_amount"], ask_price=0.56)
        assert trade["status"] == "filled"
        assert trade["asset"] == "BTC"

        # Settle as win (close >= open)
        result = executor.settle(trade["trade_id"], won=True)
        assert result["result"] == "win"
        assert result["pnl"] > 0

        # Update portfolio
        risk.record_trade_outcome(result["pnl"])
        status = risk.get_status()
        assert status["balance"] > 25.0
        assert status["total_wins"] == 1

    def test_signal_to_settlement_loss(self, setup):
        """End-to-end: trade -> settle as loss -> cooldown after 3."""
        config, db_path = setup
        risk = FiveMinRiskManager(config)
        executor = FiveMinTradeExecutor(config)
        engine = FiveMinSignalEngine(config)
        risk.init_portfolio(25.0)

        state = {
            "current_price": 100.20,
            "window_open_price": 100.00,
            "volumes": [10.0] * 29 + [30.0],
            "orderbook_up": {
                "bids": [(0.55, 100), (0.54, 80), (0.53, 60), (0.52, 40), (0.51, 30)],
                "asks": [(0.56, 20), (0.57, 15), (0.58, 10), (0.59, 10), (0.60, 5)],
            },
            "orderbook_down": {
                "bids": [(0.44, 20), (0.43, 15), (0.42, 10), (0.41, 10), (0.40, 5)],
                "asks": [(0.45, 100), (0.46, 80), (0.47, 60), (0.48, 40), (0.49, 30)],
            },
            "price_history": deque([100.0 + i * 0.05 for i in range(350)], maxlen=350),
        }

        # 3 small losses trigger cooldown (use $1 trades to stay under daily loss limit)
        for i in range(3):
            signal = engine.evaluate("BTC", state, seconds_elapsed=60)
            assert signal is not None
            trade = executor.execute(signal, 1.0, ask_price=0.56)
            result = executor.settle(trade["trade_id"], won=False)
            risk.record_trade_outcome(result["pnl"])

        can_trade = risk.can_trade()
        assert can_trade["approved"] is False
        assert "cooldown" in can_trade["reason"].lower() or "consecutive" in can_trade["reason"].lower()

    def test_notifier_formatting(self, setup):
        """Verify all notification formats produce valid strings."""
        config, _ = setup
        notifier = FiveMinNotifier(config)

        msg = notifier.format_startup("paper", 25.0, ["BTC", "ETH", "SOL"])
        assert "[5M]" in msg

        trade = {"asset": "BTC", "direction": "UP", "entry_price": 0.55, "shares": 9.09, "cost": 5.0}
        signal_info = {"confidence": 0.72, "phase": "mid", "indicators": {"momentum": "UP"}}
        msg = notifier.format_trade_entry(trade, signal_info)
        assert "BUY UP BTC" in msg

        result = {"asset": "BTC", "direction": "UP", "result": "win", "pnl": 4.05, "entry_price": 0.55}
        status = {"balance": 29.05, "consecutive_losses": 0, "total_wins": 1, "total_trades": 1}
        msg = notifier.format_settlement(result, status)
        assert "WIN" in msg

        msg = notifier.format_shutdown()
        assert "[5M]" in msg
