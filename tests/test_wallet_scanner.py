import os
import pytest
from datetime import datetime, timezone, timedelta
from modules.wallet_scanner import WalletScanner
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_scanner.db"


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
    cfg.MIN_WALLET_TRADES = 5  # lower threshold for testing
    cfg.MIN_WALLET_WIN_RATE = 0.52
    cfg.TOP_TRACKED_WALLETS = 2
    return cfg


@pytest.fixture
def scanner(config):
    return WalletScanner(config)


def _insert_trades(db_path, wallet, num_wins, num_losses, avg_size=10.0):
    conn = get_connection(db_path)
    # Pre-seed wallets row to satisfy FK constraint on wallet_trades
    conn.execute(
        "INSERT OR IGNORE INTO wallets (address) VALUES (?)",
        (wallet,),
    )
    conn.commit()
    now = datetime.now(timezone.utc)
    for i in range(num_wins):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES (?, ?, 'BUY', ?, 0.55, 'won', ?, ?)""",
            (wallet, f"market_{i}", avg_size, avg_size * 0.8,
             (now - timedelta(hours=i)).isoformat()),
        )
    for i in range(num_losses):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES (?, ?, 'BUY', ?, 0.55, 'lost', ?, ?)""",
            (wallet, f"market_loss_{i}", avg_size, -avg_size,
             (now - timedelta(hours=num_wins + i)).isoformat()),
        )
    conn.commit()
    conn.close()


def test_score_wallet_high_win_rate(scanner):
    _insert_trades(TEST_DB, "0xAAA", num_wins=8, num_losses=2)
    score = scanner.score_wallet("0xAAA")
    assert score["win_rate"] == 0.8
    assert score["total_pnl"] > 0
    assert score["composite_score"] > 0


def test_score_wallet_below_min_trades_returns_zero(scanner):
    _insert_trades(TEST_DB, "0xBBB", num_wins=2, num_losses=1)
    score = scanner.score_wallet("0xBBB")
    assert score["composite_score"] == 0


def test_score_wallet_below_min_win_rate_returns_zero(scanner):
    _insert_trades(TEST_DB, "0xCCC", num_wins=2, num_losses=5)
    score = scanner.score_wallet("0xCCC")
    assert score["composite_score"] == 0


def test_rank_and_track_selects_top_wallets(scanner):
    _insert_trades(TEST_DB, "0xTOP1", num_wins=9, num_losses=1, avg_size=20.0)
    _insert_trades(TEST_DB, "0xTOP2", num_wins=7, num_losses=3, avg_size=15.0)
    _insert_trades(TEST_DB, "0xMED", num_wins=6, num_losses=4, avg_size=5.0)

    tracked = scanner.rank_and_track()
    assert len(tracked) == 2
    assert tracked[0]["address"] == "0xTOP1"
    assert tracked[1]["address"] == "0xTOP2"

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM tracked_wallets ORDER BY rank").fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0]["address"] == "0xTOP1"
