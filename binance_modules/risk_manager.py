from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("binance_risk_manager")


class BinanceRiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.BINANCE_DB_PATH

    def _get_portfolio(self) -> dict:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("BinanceBot portfolio not initialized.")
        return dict(row)

    def init_portfolio(self, starting_balance: float) -> None:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, ?, ?, ?, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (starting_balance, starting_balance, starting_balance, now[:10], now),
        )
        conn.commit()
        conn.close()
        log.info(f"BinanceBot portfolio initialized: ${starting_balance}")

    def can_trade(self) -> dict:
        p = self._get_portfolio()

        if p["is_paused"]:
            if p["pause_until"]:
                try:
                    pause_end = datetime.fromisoformat(p["pause_until"])
                    if datetime.now(timezone.utc) >= pause_end:
                        self.resume()
                        p = self._get_portfolio()
                    else:
                        return {"allowed": False, "reason": f"Paused until {p['pause_until']}"}
                except ValueError:
                    pass
            else:
                return {"allowed": False, "reason": "Trading is paused"}

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        daily_loss_pct = -daily_pnl / p["starting_balance"] if p["starting_balance"] > 0 else 0
        if daily_loss_pct >= self.config.BINANCE_DAILY_LOSS_LIMIT_PCT:
            return {"allowed": False, "reason": f"Daily loss limit: {daily_loss_pct:.1%}"}

        if p["consecutive_losses"] >= self.config.BINANCE_CONSECUTIVE_LOSS_PAUSE:
            pause_until = datetime.now(timezone.utc) + timedelta(minutes=self.config.BINANCE_PAUSE_DURATION_MIN)
            self._set_pause(pause_until)
            return {"allowed": False, "reason": f"Consecutive losses ({p['consecutive_losses']}), pausing {self.config.BINANCE_PAUSE_DURATION_MIN}min"}

        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
        ).fetchone()["cnt"]
        conn.close()
        if open_count >= self.config.BINANCE_MAX_POSITIONS:
            return {"allowed": False, "reason": f"Max positions: {open_count}/{self.config.BINANCE_MAX_POSITIONS}"}

        if p["last_trade_time"]:
            try:
                last_trade = datetime.fromisoformat(p["last_trade_time"])
                elapsed = (datetime.now(timezone.utc) - last_trade).total_seconds()
                if elapsed < self.config.BINANCE_MIN_TRADE_INTERVAL_SEC:
                    remaining = int(self.config.BINANCE_MIN_TRADE_INTERVAL_SEC - elapsed)
                    return {"allowed": False, "reason": f"Min trade interval: {remaining}s remaining"}
            except ValueError:
                pass

        return {"allowed": True, "reason": "OK"}

    def calc_position_size(self, strength: str) -> float:
        p = self._get_portfolio()
        balance = p["balance"]
        if strength == "strong":
            pct = self.config.BINANCE_STRONG_SIGNAL_PCT
        else:
            pct = self.config.BINANCE_NORMAL_SIGNAL_PCT
        size = round(balance * pct, 2)
        return size

    def record_trade_outcome(self, pnl: float) -> None:
        conn = get_connection(self.db_path)
        p = dict(conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone())
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        new_balance = p["balance"] + pnl
        new_peak = max(p["peak_balance"], new_balance)
        total_trades = p["total_trades"] + 1
        total_wins = p["total_wins"] + (1 if pnl > 0 else 0)
        total_pnl = p["total_pnl"] + pnl
        consecutive_losses = 0 if pnl > 0 else p["consecutive_losses"] + 1

        if p["daily_pnl_date"] == today:
            daily_pnl = p["daily_pnl"] + pnl
        else:
            daily_pnl = pnl

        conn.execute(
            """UPDATE bn_portfolio SET
               balance = ?, peak_balance = ?, daily_pnl = ?, daily_pnl_date = ?,
               total_trades = ?, total_wins = ?, total_pnl = ?,
               consecutive_losses = ?, last_trade_time = ?, updated_at = ?
               WHERE id = 1""",
            (new_balance, new_peak, daily_pnl, today, total_trades, total_wins,
             total_pnl, consecutive_losses, now.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()
        log.info(f"Trade outcome: PnL=${pnl:.2f} | Balance=${new_balance:.2f}")

    def _set_pause(self, until: datetime) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE bn_portfolio SET is_paused = 1, pause_until = ? WHERE id = 1",
            (until.isoformat(),),
        )
        conn.commit()
        conn.close()

    def pause(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE bn_portfolio SET is_paused = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        log.warning("BinanceBot trading PAUSED")

    def resume(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE bn_portfolio SET is_paused = 0, pause_until = '', consecutive_losses = 0 WHERE id = 1"
        )
        conn.commit()
        conn.close()
        log.info("BinanceBot trading RESUMED")

    def get_status(self) -> dict:
        p = self._get_portfolio()
        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
        ).fetchone()["cnt"]
        conn.close()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        win_rate = p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0

        return {
            "balance": p["balance"],
            "starting_balance": p["starting_balance"],
            "peak_balance": p["peak_balance"],
            "total_pnl": p["total_pnl"],
            "daily_pnl": daily_pnl,
            "total_trades": p["total_trades"],
            "total_wins": p["total_wins"],
            "win_rate": win_rate,
            "open_positions": open_count,
            "consecutive_losses": p["consecutive_losses"],
            "is_paused": bool(p["is_paused"]),
        }
