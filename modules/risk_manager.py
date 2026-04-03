from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("risk_manager")


class RiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_portfolio(self) -> dict:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("Portfolio not initialized.")
        return dict(row)

    def init_portfolio(self, starting_capital: float) -> None:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO portfolio
               (id, starting_capital, current_value, peak_value,
                total_trades, total_wins, total_pnl, daily_pnl,
                daily_pnl_date, is_paused, updated_at)
               VALUES (1, ?, ?, ?, 0, 0, 0.0, 0.0, ?, 0, ?)""",
            (starting_capital, starting_capital, starting_capital, now[:10], now),
        )
        conn.commit()
        conn.close()
        log.info(f"Portfolio initialized with ${starting_capital}")

    def can_trade(self) -> dict:
        p = self._get_portfolio()
        if p["is_paused"]:
            return {"allowed": False, "reason": "Bot is paused"}
        drawdown = 1 - (p["current_value"] / (p["peak_value"] or 1))
        if drawdown >= self.config.HARD_STOP_DRAWDOWN_PCT:
            self.pause()
            return {"allowed": False, "reason": f"Hard stop: {drawdown:.1%} drawdown from peak"}
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        daily_loss = -daily_pnl / (p["starting_capital"] or 1)
        if daily_loss >= self.config.DAILY_LOSS_LIMIT_PCT:
            return {"allowed": False, "reason": f"Daily loss limit: {daily_loss:.1%} loss today"}
        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["cnt"]
        conn.close()
        if open_count >= self.config.MAX_CONCURRENT_POSITIONS:
            return {"allowed": False, "reason": f"Max positions: {open_count}/{self.config.MAX_CONCURRENT_POSITIONS}"}
        conn = get_connection(self.db_path)
        total_exposure = conn.execute(
            "SELECT COALESCE(SUM(size), 0) as total FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["total"]
        conn.close()
        max_exposure = p["current_value"] * self.config.MAX_TOTAL_EXPOSURE_PCT
        if total_exposure >= max_exposure:
            return {"allowed": False, "reason": f"Max exposure: ${total_exposure:.2f} >= ${max_exposure:.2f}"}
        return {"allowed": True, "reason": "OK"}

    def calc_position_size(self, signal_score: float) -> float:
        p = self._get_portfolio()
        capital = p["current_value"]
        base = capital * self.config.BASE_BET_PCT
        multiplier = 1.0 + ((signal_score - 70) / 30)
        multiplier = max(1.0, min(2.0, multiplier))
        size = base * multiplier
        drawdown = 1 - (capital / (p["peak_value"] or 1))
        if drawdown >= self.config.SOFT_STOP_DRAWDOWN_PCT:
            size *= 0.5
            log.warning(f"Soft stop active: position size halved to ${size:.2f}")
        max_size = capital * self.config.MAX_CAPITAL_PER_TRADE_PCT
        size = min(size, max_size)
        return round(size, 2)

    def record_trade_outcome(self, pnl: float) -> None:
        conn = get_connection(self.db_path)
        p = dict(conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone())
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        new_value = p["current_value"] + pnl
        new_peak = max(p["peak_value"], new_value)
        total_trades = p["total_trades"] + 1
        total_wins = p["total_wins"] + (1 if pnl > 0 else 0)
        total_pnl = p["total_pnl"] + pnl
        if p["daily_pnl_date"] == today:
            daily_pnl = p["daily_pnl"] + pnl
        else:
            daily_pnl = pnl
        conn.execute(
            """UPDATE portfolio SET
               current_value = ?, peak_value = ?, total_trades = ?,
               total_wins = ?, total_pnl = ?, daily_pnl = ?,
               daily_pnl_date = ?, updated_at = ?
               WHERE id = 1""",
            (new_value, new_peak, total_trades, total_wins, total_pnl,
             daily_pnl, today, now.isoformat()),
        )
        conn.commit()
        conn.close()
        log.info(f"Trade outcome: PnL=${pnl:.2f} | Portfolio=${new_value:.2f}")

    def pause(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE portfolio SET is_paused = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        log.warning("Trading PAUSED")

    def resume(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE portfolio SET is_paused = 0 WHERE id = 1")
        conn.commit()
        conn.close()
        log.info("Trading RESUMED")

    def get_status(self) -> dict:
        p = self._get_portfolio()
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["cnt"]
        conn.close()
        drawdown = 1 - (p["current_value"] / (p["peak_value"] or 1))
        win_rate = p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0
        return {
            "current_value": p["current_value"],
            "starting_capital": p["starting_capital"],
            "total_pnl": p["total_pnl"],
            "total_trades": p["total_trades"],
            "win_rate": win_rate,
            "drawdown": drawdown,
            "daily_pnl": p["daily_pnl"],
            "open_positions": open_trades,
            "is_paused": bool(p["is_paused"]),
        }
