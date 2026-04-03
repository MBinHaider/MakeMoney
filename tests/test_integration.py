# tests/test_integration.py
import os
import pytest
from datetime import datetime, timezone, timedelta
from config import Config
from utils.db import init_db, get_connection
from modules.data_collector import DataCollector
from modules.wallet_scanner import WalletScanner
from modules.signal_engine import SignalEngine
from modules.trade_executor import TradeExecutor
from modules.risk_manager import RiskManager
from modules.notifier import Notifier

TEST_DB = "data/test_integration.db"


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
    cfg.TRADING_MODE = "paper"
    cfg.TELEGRAM_BOT_TOKEN = ""
    cfg.MIN_WALLET_TRADES = 5
    cfg.TOP_TRACKED_WALLETS = 2
    return cfg


def _seed_test_data(db_path):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)

    # Portfolio
    conn.execute(
        """INSERT INTO portfolio
           (id, starting_capital, current_value, peak_value, daily_pnl_date, updated_at)
           VALUES (1, 100, 100, 100, ?, ?)""",
        (now.strftime("%Y-%m-%d"), now.isoformat()),
    )

    # A good wallet — first insert into wallets table (FK requirement)
    conn.execute(
        "INSERT OR IGNORE INTO wallets (address) VALUES ('0xGOOD')"
    )

    # Then insert trades for that wallet
    for i in range(8):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES ('0xGOOD', ?, 'BUY', 50, 0.55, 'won', 40, ?)""",
            (f"mkt_{i}", (now - timedelta(hours=i)).isoformat()),
        )
    for i in range(2):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES ('0xGOOD', ?, 'BUY', 50, 0.55, 'lost', -50, ?)""",
            (f"mkt_loss_{i}", (now - timedelta(hours=10 + i)).isoformat()),
        )

    # An active market
    conn.execute(
        """INSERT INTO markets
           (condition_id, question, token_id_yes, token_id_no,
            asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES ('mkt_live', 'Will BTC go up?', 'tok_y', 'tok_n',
                   'BTC', 0.55, 0.45, 80000, ?, 1, ?)""",
        ((now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )

    # Price candles (uptrend)
    for i in range(10):
        conn.execute(
            """INSERT INTO price_candles
               (asset, open, high, low, close, volume, timestamp)
               VALUES ('BTC', ?, ?, ?, ?, 1000, ?)""",
            (100 + i, 110 + i, 90 + i, 101 + i,
             (now - timedelta(minutes=10 - i)).isoformat()),
        )

    conn.commit()
    conn.close()


def test_full_pipeline(config):
    _seed_test_data(TEST_DB)

    # Step 1: Wallet Scanner ranks wallets
    scanner = WalletScanner(config)
    tracked = scanner.rank_and_track()
    assert len(tracked) >= 1
    assert tracked[0]["address"] == "0xGOOD"

    # Step 2: Signal Engine generates signal from whale trade
    engine = SignalEngine(config)
    whale_trade = {
        "wallet_address": "0xGOOD",
        "side": "BUY",
        "size": 100.0,
        "market_id": "mkt_live",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal is not None
    assert signal["total_score"] > 0

    # Step 3: Risk Manager checks if trade is allowed
    risk_mgr = RiskManager(config)
    can = risk_mgr.can_trade()
    assert can["allowed"] is True

    # Step 4: Risk Manager calculates position size
    size = risk_mgr.calc_position_size(signal["total_score"])
    assert size > 0
    assert size <= 10.0

    # Step 5: Trade Executor places paper trade
    executor = TradeExecutor(config)
    market = {
        "condition_id": "mkt_live",
        "token_id_yes": "tok_y",
        "token_id_no": "tok_n",
        "price_yes": 0.55,
        "price_no": 0.45,
    }
    result = executor.execute(signal, market, size)
    assert result["status"] == "filled"

    # Step 6: Resolve trade as win
    pnl = executor.resolve_trade(result["trade_id"], won=True)
    assert pnl > 0

    # Step 7: Risk Manager records outcome
    risk_mgr.record_trade_outcome(pnl)
    status = risk_mgr.get_status()
    assert status["current_value"] > 100
    assert status["total_trades"] == 1
    assert status["win_rate"] == 1.0

    # Step 8: Notifier formats the result
    notifier = Notifier(config)
    msg = notifier.format_trade_outcome("mkt_live", True, pnl, status["current_value"])
    assert "WON" in msg
