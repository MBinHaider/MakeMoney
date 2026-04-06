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
        self._clob_client = None

    def execute(self, signal: Signal, amount: float, ask_price: float,
                token_id: str = "", condition_id: str = "",
                limit_price: float = 0.0) -> dict:
        """Execute a trade. Paper or live depending on config.
        For live: uses limit_price (or calculates one from confidence).
        """
        if self.config.FIVEMIN_TRADING_MODE == "paper":
            if ask_price <= 0:
                return {"status": "error", "reason": "Invalid ask price"}
            return self._execute_paper(signal, amount, ask_price)
        else:
            # For live: place limit order at a fair price based on confidence
            if limit_price <= 0:
                # Map confidence to price: 0.60 conf → $0.50, 1.0 conf → $0.60
                limit_price = round(0.40 + signal.confidence * 0.20, 2)
                limit_price = max(0.40, min(0.65, limit_price))
            return self._execute_live(signal, amount, limit_price, token_id, condition_id)

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

    def _init_clob_client(self):
        """Initialize py-clob-client for live trading with SOCKS5 proxy."""
        if self._clob_client is not None:
            return

        # Route through WARP SOCKS5 proxy to bypass geo-block
        import socks
        import socket
        socks.set_default_proxy(socks.SOCKS5, '127.0.0.1', 40000)
        socket.socket = socks.socksocket

        from py_clob_client.client import ClobClient

        self._clob_client = ClobClient(
            'https://clob.polymarket.com',
            key=self.config.PRIVATE_KEY,
            chain_id=137,
            signature_type=1,  # POLY_GNOSIS_SAFE
            funder=self.config.POLYMARKET_PROXY_ADDRESS,
        )
        creds = self._clob_client.derive_api_key()
        self._clob_client.set_api_creds(creds)
        log.info("LIVE: py-clob-client authenticated (via SOCKS5 proxy)")

    def _execute_live(self, signal: Signal, amount: float, limit_price: float,
                      token_id: str, condition_id: str) -> dict:
        """Place a limit order on Polymarket via py-clob-client.
        Posts at a fair price (not the $0.99 ask) and waits for fill.
        """
        if not token_id:
            log.error("LIVE: No token ID for order")
            return {"status": "error", "reason": "No token ID"}

        try:
            self._init_clob_client()
        except Exception as e:
            log.error(f"LIVE: Auth failed: {e}")
            return {"status": "error", "reason": f"Auth failed: {e}"}

        shares = amount / limit_price
        now = datetime.now(timezone.utc).isoformat()

        try:
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY

            log.info(f"LIVE LIMIT ORDER: BUY {signal.direction} {signal.asset} "
                     f"{shares:.1f} shares @ ${limit_price:.2f} (${amount:.2f}) "
                     f"conf={signal.confidence:.2f}")

            order_args = OrderArgs(
                price=limit_price,
                size=shares,
                side=BUY,
                token_id=token_id,
            )
            signed_order = self._clob_client.create_order(order_args)
            resp = self._clob_client.post_order(signed_order)

            order_id = resp.get("orderID", resp.get("id", str(resp)))
            log.info(f"LIVE ORDER POSTED: {order_id}")

            # Wait up to 30 seconds for fill, checking every 5s
            import time
            filled = 0
            status = "LIVE"
            for check in range(6):
                time.sleep(5)
                try:
                    order_status = self._clob_client.get_order(order_id)
                    filled = float(order_status.get("size_matched", 0))
                    status = order_status.get("status", "unknown")
                    log.info(f"LIVE CHECK {check+1}/6: status={status} filled={filled:.1f}/{shares:.1f}")
                    if filled > 0:
                        break
                except Exception as e:
                    log.warning(f"Order check failed: {e}")

            # If not filled, cancel and move on
            if filled == 0:
                try:
                    self._clob_client.cancel(order_id)
                    log.info(f"LIVE ORDER CANCELLED (unfilled after 30s): {order_id}")
                except Exception:
                    pass
                return {"status": "error", "reason": "Limit order not filled in 30s"}

            actual_shares = filled
            actual_cost = actual_shares * limit_price

            # Record in database
            conn = get_connection(self.db_path)
            cursor = conn.execute(
                """INSERT INTO fm_trades
                   (asset, direction, entry_price, shares, cost, result,
                    window_ts, signal_confidence, signal_phase, signal_details, timestamp)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
                (signal.asset, signal.direction, limit_price, actual_shares, actual_cost,
                 int(signal.timestamp), signal.confidence, signal.phase,
                 json.dumps({"order_id": order_id}), now),
            )
            trade_id = cursor.lastrowid
            conn.commit()
            conn.close()

            log.info(
                f"LIVE FILLED: {signal.direction} {signal.asset} "
                f"{actual_shares:.1f} shares @ ${limit_price:.2f} (${actual_cost:.2f})"
            )

            return {
                "trade_id": trade_id,
                "status": "filled",
                "asset": signal.asset,
                "direction": signal.direction,
                "entry_price": limit_price,
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
