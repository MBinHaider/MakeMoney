import os
import tempfile
import pytest
from fivemin_modules.trade_executor import FiveMinTradeExecutor
from fivemin_modules.signal_engine import Signal
from utils.fivemin_db import init_fivemin_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test5m.db")
        config = Config()
        config.FIVEMIN_DB_PATH = db_path
        config.FIVEMIN_TRADING_MODE = "paper"
        init_fivemin_db(db_path)
        executor = FiveMinTradeExecutor(config)
        yield executor, db_path


class TestPaperExecution:
    def test_execute_paper_trade(self, setup):
        executor, db_path = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 1700000000.0)
        result = executor.execute(signal, amount=5.0, ask_price=0.55)
        assert result["status"] == "filled"
        assert result["asset"] == "BTC"
        assert result["direction"] == "UP"
        assert result["entry_price"] == 0.55
        assert result["shares"] == pytest.approx(5.0 / 0.55, rel=0.01)
        assert result["cost"] == 5.0

    def test_trade_saved_to_db(self, setup):
        executor, db_path = setup
        signal = Signal("ETH", "DOWN", 0.65, "late", {}, 1700000300.0)
        executor.execute(signal, amount=5.0, ask_price=0.60)
        conn = get_connection(db_path)
        trades = conn.execute("SELECT * FROM fm_trades").fetchall()
        conn.close()
        assert len(trades) == 1
        t = dict(trades[0])
        assert t["asset"] == "ETH"
        assert t["direction"] == "DOWN"
        assert t["result"] == "pending"

    def test_zero_ask_price_rejected(self, setup):
        executor, _ = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 0.0)
        result = executor.execute(signal, amount=5.0, ask_price=0.0)
        assert result["status"] == "error"


class TestSettlement:
    def test_settle_win(self, setup):
        executor, db_path = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 1700000000.0)
        trade = executor.execute(signal, amount=5.0, ask_price=0.55)
        result = executor.settle(trade["trade_id"], won=True)
        assert result["result"] == "win"
        assert result["pnl"] == pytest.approx((1.0 - 0.55) * (5.0 / 0.55), rel=0.01)

    def test_settle_loss(self, setup):
        executor, db_path = setup
        signal = Signal("BTC", "DOWN", 0.60, "mid", {}, 1700000000.0)
        trade = executor.execute(signal, amount=5.0, ask_price=0.60)
        result = executor.settle(trade["trade_id"], won=False)
        assert result["result"] == "loss"
        assert result["pnl"] == pytest.approx(-(0.60 * (5.0 / 0.60)), rel=0.01)

    def test_settle_updates_db(self, setup):
        executor, db_path = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 1700000000.0)
        trade = executor.execute(signal, amount=5.0, ask_price=0.55)
        executor.settle(trade["trade_id"], won=True)
        conn = get_connection(db_path)
        row = conn.execute("SELECT * FROM fm_trades WHERE id = ?", (trade["trade_id"],)).fetchone()
        conn.close()
        assert dict(row)["result"] == "win"

    def test_get_pending_trade(self, setup):
        executor, _ = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 1700000000.0)
        executor.execute(signal, amount=5.0, ask_price=0.55)
        pending = executor.get_pending_trade()
        assert pending is not None
        assert pending["asset"] == "BTC"

    def test_no_pending_when_settled(self, setup):
        executor, _ = setup
        signal = Signal("BTC", "UP", 0.72, "mid", {}, 1700000000.0)
        trade = executor.execute(signal, amount=5.0, ask_price=0.55)
        executor.settle(trade["trade_id"], won=True)
        assert executor.get_pending_trade() is None
