import json
import asyncio
from datetime import datetime, timezone
from fivemin_modules.signal_engine import Signal
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_trade_executor")


class FiveMinTradeExecutor:
    def __init__(self, config: Config, exchange=None):
        self.config = config
        self.db_path = config.FIVEMIN_DB_PATH
        self.exchange = exchange

    def execute(self, signal: Signal, amount: float, ask_price: float,
                token_id: str = "", condition_id: str = "") -> dict:
        """Execute a trade. Paper or live depending on config."""
        if ask_price <= 0:
            return {"status": "error", "reason": "Invalid ask price"}

        if self.config.FIVEMIN_TRADING_MODE == "paper":
            return self._execute_paper(signal, amount, ask_price)
        else:
            return self._execute_live(signal, amount, ask_price, token_id, condition_id)

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

    def _execute_live(self, signal: Signal, amount: float, ask_price: float,
                      token_id: str, condition_id: str) -> dict:
        """Place a real order on Polymarket via PMXT."""
        if not self.exchange:
            log.error("LIVE: No exchange connection")
            return {"status": "error", "reason": "No exchange connection"}

        if not token_id:
            log.error("LIVE: No token ID for order")
            return {"status": "error", "reason": "No token ID"}

        shares = amount / ask_price
        now = datetime.now(timezone.utc).isoformat()

        try:
            # Place limit order at ask price
            log.info(f"LIVE PLACING ORDER: BUY {signal.direction} {signal.asset} "
                     f"{shares:.2f} shares @ ${ask_price:.4f}")

            order = self.exchange.create_order(
                outcome_id=token_id,
                side="buy",
                type="limit",
                amount=shares,
                price=ask_price,
            )

            order_id = order.id if hasattr(order, 'id') else str(order)
            filled = order.filled if hasattr(order, 'filled') else shares
            status = order.status if hasattr(order, 'status') else "submitted"

            log.info(f"LIVE ORDER {order_id}: status={status} filled={filled}")

            # Wait briefly for fill
            if status not in ("filled", "matched"):
                import time
                time.sleep(3)
                try:
                    updated = self.exchange.fetch_order(order_id)
                    status = updated.status if hasattr(updated, 'status') else status
                    filled = updated.filled if hasattr(updated, 'filled') else filled
                except Exception as e:
                    log.warning(f"Could not check order status: {e}")

            # If not filled, cancel
            if status not in ("filled", "matched") and filled == 0:
                try:
                    self.exchange.cancel_order(order_id)
                    log.info(f"LIVE ORDER CANCELLED (not filled): {order_id}")
                except Exception:
                    pass
                return {"status": "error", "reason": "Order not filled"}

            actual_shares = filled if filled > 0 else shares
            actual_cost = actual_shares * ask_price

            # Record in database
            conn = get_connection(self.db_path)
            cursor = conn.execute(
                """INSERT INTO fm_trades
                   (asset, direction, entry_price, shares, cost, result,
                    window_ts, signal_confidence, signal_phase, signal_details, timestamp)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
                (signal.asset, signal.direction, ask_price, actual_shares, actual_cost,
                 int(signal.timestamp), signal.confidence, signal.phase,
                 json.dumps({"order_id": order_id, **signal.indicators}), now),
            )
            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()

            log.info(
                f"LIVE FILLED: BUY {signal.direction} {signal.asset} "
                f"{actual_shares:.2f} shares @ ${ask_price} (${actual_cost:.2f}) "
                f"order={order_id}"
            )

            return {
                "trade_id": trade_id,
                "status": "filled",
                "asset": signal.asset,
                "direction": signal.direction,
                "entry_price": ask_price,
                "shares": actual_shares,
                "cost": actual_cost,
                "order_id": order_id,
            }

        except Exception as e:
            log.error(f"LIVE ORDER FAILED: {e}")
            return {"status": "error", "reason": str(e)}

    def settle(self, trade_id: int, won: bool) -> dict:
        """Settle a trade after the 5-min window closes.
        For live trades, winning shares auto-resolve to $1.00 on-chain.
        We just record the P&L locally.
        """
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
