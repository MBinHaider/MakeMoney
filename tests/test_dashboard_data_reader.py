import os
import tempfile
import pytest
from datetime import datetime, timezone
from dashboard.data_reader import DashboardDataReader
from utils.fivemin_db import init_fivemin_db
from utils.binance_db import init_binance_db
from utils.db import init_db, get_connection


@pytest.fixture
def setup_dbs():
    with tempfile.TemporaryDirectory() as tmpdir:
        fm_path = os.path.join(tmpdir, "fm.db")
        bn_path = os.path.join(tmpdir, "bn.db")
        pb_path = os.path.join(tmpdir, "pb.db")
        init_fivemin_db(fm_path)
        init_binance_db(bn_path)
        init_db(pb_path)
        reader = DashboardDataReader(fm_path, bn_path, pb_path)
        yield reader, fm_path, bn_path, pb_path


class TestFiveMinStats:
    def test_empty_db_returns_defaults(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        # Init portfolio
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 25.0, 25.0, 25.0, 0.0, ?, 0, 0, 0.0, 0, 0, 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        stats = reader.get_fivemin_stats()
        assert stats["balance"] == 25.0
        assert stats["total_trades"] == 0
        assert stats["is_paused"] is False
        assert stats["mode"] == "paper"

    def test_with_trades(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc)
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 27.44, 25.0, 27.44, 2.44, ?, 1, 1, 2.44, 0, 1, 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn.commit()
        conn.close()
        stats = reader.get_fivemin_stats()
        assert stats["balance"] == 27.44
        assert stats["total_trades"] == 1
        assert stats["total_wins"] == 1


class TestBinanceStats:
    def test_empty_db_returns_defaults(self, setup_dbs):
        reader, _, bn_path, _ = setup_dbs
        conn = get_connection(bn_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, 45.0, 45.0, 45.0, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        stats = reader.get_binance_stats()
        assert stats["balance"] == 45.0
        assert stats["total_trades"] == 0


class TestRecentTrades:
    def test_combined_trades(self, setup_dbs):
        reader, fm_path, bn_path, _ = setup_dbs
        # Add fivemin portfolio + trade
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc)
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 27.44, 25.0, 27.44, 2.44, ?, 1, 1, 2.44, 0, 1, 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn.execute(
            """INSERT INTO fm_trades
               (asset, direction, entry_price, shares, cost, result, pnl,
                window_ts, signal_confidence, signal_phase, signal_details, timestamp)
               VALUES ('ETH', 'UP', 0.67, 7.46, 5.0, 'win', 2.44, 1700000000, 1.0, 'mid', '{}', ?)""",
            (now.isoformat(),),
        )
        conn.commit()
        conn.close()
        # Add binance portfolio + trade
        conn2 = get_connection(bn_path)
        conn2.execute(
            """INSERT INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, 45.0, 45.0, 45.0, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (now.strftime("%Y-%m-%d"), now.isoformat()),
        )
        conn2.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, status, pnl, fees)
               VALUES (?, 'BTCUSDT', 'buy', 83000, 9.0, 84000, 82000, 'closed', 0.52, 0.01)""",
            (now.isoformat(),),
        )
        conn2.commit()
        conn2.close()
        trades = reader.get_recent_trades(limit=10)
        assert len(trades) == 2
        assert trades[0]["bot"] in ("5M", "BN")


class TestCooldownStatus:
    def test_no_cooldown(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 25.0, 25.0, 25.0, 0.0, ?, 0, 0, 0.0, 0, 0, 0, '', ?)""",
            (now[:10], now),
        )
        conn.commit()
        conn.close()
        cooldown = reader.get_cooldown_status()
        assert cooldown["active"] is False

    def test_active_cooldown(self, setup_dbs):
        reader, fm_path, _, _ = setup_dbs
        from datetime import timedelta
        future = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        conn = get_connection(fm_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, 20.0, 25.0, 25.0, -5.0, ?, 3, 0, -5.0, 3, 3, 1, ?, ?)""",
            (now[:10], future, now),
        )
        conn.commit()
        conn.close()
        cooldown = reader.get_cooldown_status()
        assert cooldown["active"] is True
        assert cooldown["seconds_remaining"] > 0


class TestPnlHistory:
    def test_empty_returns_zeros(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        history = reader.get_pnl_history(hours=24)
        assert isinstance(history, dict)
        assert "fivemin" in history
        assert "binance" in history
        assert "combined" in history


class TestSignalHitRate:
    def test_empty(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        rate = reader.get_signal_hitrate()
        assert rate["generated"] == 0
        assert rate["traded"] == 0
        assert rate["won"] == 0


class TestHourlyWinRate:
    def test_empty(self, setup_dbs):
        reader, _, _, _ = setup_dbs
        hourly = reader.get_hourly_winrate()
        assert len(hourly) == 24
        assert all(h["trades"] == 0 for h in hourly)
