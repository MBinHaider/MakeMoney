import json
from datetime import datetime, timezone
from fivemin_modules.signal_engine import Signal
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_trade_executor")


class FiveMinTradeExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.FIVEMIN_DB_PATH

    def execute(self, signal: Signal, amount: float, ask_price: float) -> dict:
        """Execute a paper trade. Returns trade details."""
        if ask_price <= 0:
            return {"status": "error", "reason": "Invalid ask price"}

        if self.config.FIVEMIN_TRADING_MODE == "paper":
            return self._execute_paper(signal, amount, ask_price)
        else:
            log.warning("Live trading not yet implemented")
            return {"status": "error", "reason": "Live trading not implemented"}

    def _execute_paper(self, signal: Signal, amount: float, ask_price: float) -> dict:
        shares = amount / ask_price
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO fm_trades
               (asset, direction, entry_price, shares, cost, result,
                window_ts, signal_confidence, signal_phase, signal_details, timestamp)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (signal.asset, signal.direction, ask_price, shares, amount,
             int(signal.timestamp), signal.confidence, signal.phase,
             json.dumps(signal.indicators), now),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(
            f"PAPER BUY {signal.direction} {signal.asset} "
            f"{shares:.2f} shares @ ${ask_price} (${amount:.2f})"
        )

        return {
            "trade_id": trade_id,
            "status": "filled",
            "asset": signal.asset,
            "direction": signal.direction,
            "entry_price": ask_price,
            "shares": shares,
            "cost": amount,
        }

    def settle(self, trade_id: int, won: bool) -> dict:
        """Settle a trade after the 5-min window closes."""
        conn = get_connection(self.db_path)
        trade = dict(conn.execute(
            "SELECT * FROM fm_trades WHERE id = ?", (trade_id,)
        ).fetchone())

        entry_price = trade["entry_price"]
        shares = trade["shares"]
        now = datetime.now(timezone.utc).isoformat()

        if won:
            pnl = (1.0 - entry_price) * shares
            result = "win"
        else:
            pnl = -(entry_price * shares)
            result = "loss"

        conn.execute(
            "UPDATE fm_trades SET result = ?, pnl = ?, resolved_at = ? WHERE id = ?",
            (result, round(pnl, 4), now, trade_id),
        )
        conn.commit()
        conn.close()

        log.info(f"SETTLED {trade['asset']} {trade['direction']}: {result} PnL=${pnl:.2f}")

        return {
            "trade_id": trade_id,
            "asset": trade["asset"],
            "direction": trade["direction"],
            "result": result,
            "pnl": round(pnl, 4),
            "entry_price": entry_price,
            "shares": shares,
        }

    def get_pending_trade(self) -> dict | None:
        """Get the current pending (unsettled) trade, if any."""
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM fm_trades WHERE result = 'pending' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)
