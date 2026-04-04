import os
import tempfile
import pytest
from datetime import datetime, timezone
from binance_modules.trade_executor import BinanceTradeExecutor
from utils.binance_db import init_binance_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = Config()
        config.BINANCE_DB_PATH = db_path
        config.BINANCE_TRADING_MODE = "paper"
        init_binance_db(db_path)
        executor = BinanceTradeExecutor(config)
        yield executor, db_path


class TestPaperTrade:
    def test_paper_buy_creates_trade(self, setup):
        executor, db_path = setup
        signal = {
            "action": "buy", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        assert result["status"] == "filled"
        assert result["side"] == "buy"
        assert result["size"] == 10.0
        assert result["tp"] == pytest.approx(42000 * 1.001 * 1.015, rel=1e-3)
        assert result["sl"] == pytest.approx(42000 * 1.001 * 0.99, rel=1e-3)

        conn = get_connection(db_path)
        trade = conn.execute("SELECT * FROM bn_trades WHERE id = ?", (result["trade_id"],)).fetchone()
        conn.close()
        assert trade is not None
        assert trade["status"] == "open"
        assert trade["symbol"] == "BTCUSDT"

    def test_paper_buy_applies_slippage(self, setup):
        executor, _ = setup
        signal = {
            "action": "buy", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        expected_price = 42000.0 * (1 + 0.001)
        assert result["entry_price"] == pytest.approx(expected_price)

    def test_paper_sell_applies_slippage(self, setup):
        executor, _ = setup
        signal = {
            "action": "sell", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        expected_price = 42000.0 * (1 - 0.001)
        assert result["entry_price"] == pytest.approx(expected_price)


class TestCheckOpenPositions:
    def test_take_profit_hit(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        closed = executor.check_open_positions({"BTCUSDT": 42700.0})
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"
        assert closed[0]["pnl"] > 0

    def test_stop_loss_hit(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        closed = executor.check_open_positions({"BTCUSDT": 41500.0})
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"
        assert closed[0]["pnl"] < 0

    def test_trailing_stop_updates(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        closed = executor.check_open_positions({"BTCUSDT": 42400.0})
        assert len(closed) == 0

        conn = get_connection(db_path)
        trade = conn.execute("SELECT trailing_sl FROM bn_trades WHERE id = 1").fetchone()
        conn.close()
        assert trade["trailing_sl"] > 41580
