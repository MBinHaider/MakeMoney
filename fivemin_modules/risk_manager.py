from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_risk_manager")


class FiveMinRiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.FIVEMIN_DB_PATH

    def _get_portfolio(self) -> dict:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM fm_portfolio WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("PolyBot 5M portfolio not initialized.")
        return dict(row)

    def init_portfolio(self, starting_balance: float) -> None:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO fm_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, daily_trade_count,
                is_paused, pause_until, updated_at)
               VALUES (1, ?, ?, ?, 0.0, ?, 0, 0, 0.0, 0, 0, 0, '', ?)""",
            (starting_balance, starting_balance, starting_balance, now[:10], now),
        )
        conn.commit()
        conn.close()
        log.info(f"PolyBot 5M portfolio initialized: ${starting_balance}")

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
                        return {"approved": False, "reason": f"Paused until {p['pause_until']}", "max_amount": 0.0}
                except ValueError:
                    pass
            else:
                return {"approved": False, "reason": "Trading is paused", "max_amount": 0.0}

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        daily_loss_pct = -daily_pnl / p["starting_balance"] if p["starting_balance"] > 0 else 0
        if daily_loss_pct >= self.config.FIVEMIN_DAILY_LOSS_LIMIT_PCT:
            return {"approved": False, "reason": f"Daily loss limit hit: {daily_loss_pct:.1%}", "max_amount": 0.0}

        if p["consecutive_losses"] >= self.config.FIVEMIN_COOLDOWN_LOSSES:
            pause_until = datetime.now(timezone.utc) + timedelta(minutes=self.config.FIVEMIN_COOLDOWN_MINUTES)
            self._set_pause(pause_until)
            conn = get_connection(self.db_path)
            conn.execute(
                "INSERT INTO fm_cooldowns (start_time, end_time, reason, consecutive_losses) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), pause_until.isoformat(),
                 "consecutive_losses", p["consecutive_losses"]),
            )
            conn.commit()
            conn.close()
            return {"approved": False, "reason": f"Cooldown: {p['consecutive_losses']} consecutive losses", "max_amount": 0.0}

        daily_count = p["daily_trade_count"] if p["daily_pnl_date"] == today else 0
        if daily_count >= self.config.FIVEMIN_DAILY_TRADE_CAP:
            return {"approved": False, "reason": f"Daily trade cap: {daily_count}/{self.config.FIVEMIN_DAILY_TRADE_CAP}", "max_amount": 0.0}

        if p["balance"] < 1.0:
            return {"approved": False, "reason": f"Insufficient balance: ${p['balance']:.2f}", "max_amount": 0.0}

        max_amount = min(self.config.FIVEMIN_MAX_PER_TRADE, p["balance"])
        return {"approved": True, "reason": "OK", "max_amount": max_amount}

    def record_trade_outcome(self, pnl: float) -> None:
        conn = get_connection(self.db_path)
        p = dict(conn.execute("SELECT * FROM fm_portfolio WHERE id = 1").fetchone())
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
            daily_count = p["daily_trade_count"] + 1
        else:
            daily_pnl = pnl
            daily_count = 1

        conn.execute(
            """UPDATE fm_portfolio SET
               balance = ?, peak_balance = ?, daily_pnl = ?, daily_pnl_date = ?,
               total_trades = ?, total_wins = ?, total_pnl = ?,
               consecutive_losses = ?, daily_trade_count = ?, updated_at = ?
               WHERE id = 1""",
            (new_balance, new_peak, daily_pnl, today, total_trades, total_wins,
             total_pnl, consecutive_losses, daily_count, now.isoformat()),
        )
        conn.commit()
        conn.close()
        log.info(f"Trade outcome: PnL=${pnl:.2f} | Balance=${new_balance:.2f}")

    def _set_pause(self, until: datetime) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE fm_portfolio SET is_paused = 1, pause_until = ? WHERE id = 1",
            (until.isoformat(),),
        )
        conn.commit()
        conn.close()

    def pause(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE fm_portfolio SET is_paused = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        log.warning("PolyBot 5M trading PAUSED")

    def resume(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE fm_portfolio SET is_paused = 0, pause_until = '', consecutive_losses = 0 WHERE id = 1"
        )
        conn.commit()
        conn.close()
        log.info("PolyBot 5M trading RESUMED")

    def get_status(self) -> dict:
        p = self._get_portfolio()
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
            "consecutive_losses": p["consecutive_losses"],
            "daily_trade_count": p["daily_trade_count"] if p["daily_pnl_date"] == today else 0,
            "is_paused": bool(p["is_paused"]),
        }
