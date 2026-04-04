import os
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("trade_executor")


class TradeExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH
        self._clob_client = None
        # Set proxy env vars so py-clob-client (httpx) routes through WARP
        if config.PROXY_URL:
            os.environ["ALL_PROXY"] = config.PROXY_URL
            os.environ["HTTPS_PROXY"] = config.PROXY_URL

    def _signal_id_exists(self, conn, signal_id) -> bool:
        """Return True only if signal_id is not None and exists in the signals table."""
        if signal_id is None:
            return False
        row = conn.execute("SELECT id FROM signals WHERE id = ?", (signal_id,)).fetchone()
        return row is not None

    def _get_clob_client(self):
        if self._clob_client is None and self.config.TRADING_MODE == "live":
            from py_clob_client.client import ClobClient
            self._clob_client = ClobClient(
                self.config.POLYMARKET_API_URL,
                key=self.config.PRIVATE_KEY,
                chain_id=self.config.CHAIN_ID,
            )
            creds = self._clob_client.create_or_derive_api_creds()
            self._clob_client.set_api_creds(creds)
            log.info("Polymarket CLOB client initialized")
        return self._clob_client

    def execute_paper_trade(self, signal: dict, market: dict, size: float) -> dict:
        direction = signal["direction"]
        if direction == "BUY":
            entry_price = market["price_yes"]
            token_id = market["token_id_yes"]
        else:
            entry_price = market["price_no"]
            token_id = market["token_id_no"]
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(self.db_path)
        # Use NULL for signal_id FK to avoid constraint failures when the
        # signal row may not yet be persisted (e.g. paper trades from tests).
        signal_id = signal.get("id") if self._signal_id_exists(conn, signal.get("id")) else None
        cursor = conn.execute(
            """INSERT INTO bot_trades
               (market_id, side, size, entry_price, outcome, pnl,
                signal_score, signal_id, order_id, timestamp)
               VALUES (?, ?, ?, ?, 'pending', 0.0, ?, ?, ?, ?)""",
            (signal["market_id"], direction, size, entry_price,
             signal["total_score"], signal_id, f"paper_{now}", now),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        log.info(f"PAPER TRADE: {direction} ${size:.2f} on {signal['market_id'][:10]} @ {entry_price:.4f}")
        return {
            "trade_id": trade_id,
            "status": "filled",
            "side": direction,
            "size": size,
            "entry_price": entry_price,
            "token_id": token_id,
            "order_id": f"paper_{now}",
        }

    def execute_live_trade(self, signal: dict, market: dict, size: float) -> dict:
        client = self._get_clob_client()
        if client is None:
            return {"status": "error", "reason": "CLOB client not initialized"}
        direction = signal["direction"]
        if direction == "BUY":
            token_id = market["token_id_yes"]
            price = market["price_yes"]
        else:
            token_id = market["token_id_no"]
            price = market["price_no"]
        try:
            order = client.create_order(token_id=token_id, price=price, size=size, side="BUY")
            resp = client.post_order(order)
            order_id = resp.get("orderID", "")
            now = datetime.now(timezone.utc).isoformat()
            conn = get_connection(self.db_path)
            signal_id = signal.get("id") if self._signal_id_exists(conn, signal.get("id")) else None
            conn.execute(
                """INSERT INTO bot_trades
                   (market_id, side, size, entry_price, outcome, pnl,
                    signal_score, signal_id, order_id, timestamp)
                   VALUES (?, ?, ?, ?, 'pending', 0.0, ?, ?, ?, ?)""",
                (signal["market_id"], direction, size, price,
                 signal["total_score"], signal_id, order_id, now),
            )
            conn.commit()
            conn.close()
            return {
                "trade_id": order_id,
                "status": "filled",
                "side": direction,
                "size": size,
                "entry_price": price,
                "token_id": token_id,
                "order_id": order_id,
            }
        except Exception as e:
            log.error(f"Live trade failed: {e}")
            return {"status": "error", "reason": str(e)}

    def execute(self, signal: dict, market: dict, size: float) -> dict:
        if self.config.TRADING_MODE == "paper":
            return self.execute_paper_trade(signal, market, size)
        else:
            return self.execute_live_trade(signal, market, size)

    def resolve_trade(self, trade_id: int, won: bool) -> float:
        conn = get_connection(self.db_path)
        trade = conn.execute("SELECT * FROM bot_trades WHERE id = ?", (trade_id,)).fetchone()
        if trade is None:
            conn.close()
            return 0.0
        size = trade["size"]
        entry_price = trade["entry_price"]
        if won:
            shares = size / entry_price
            pnl = shares * (1.0 - entry_price)
        else:
            pnl = -size
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE bot_trades SET outcome = ?, pnl = ?, resolved_at = ? WHERE id = ?",
            ("won" if won else "lost", pnl, now, trade_id),
        )
        conn.commit()
        conn.close()
        log.info(f"Trade {trade_id} resolved: {'WON' if won else 'LOST'} | PnL: ${pnl:.2f}")
        return pnl

    def resolve_paper_trades(self) -> list[dict]:
        """Resolve paper trades using Polymarket's real payout model.

        How Polymarket works:
        - You buy YES at $0.15 → If event happens, you get $1.00 → PnL = +$0.85/share
        - You buy NO at $0.20 → If event doesn't happen, you get $1.00 → PnL = +$0.80/share
        - If wrong → token worth $0 → PnL = -entry_price/share

        For paper mode, we check if the market has closed/resolved.
        If still open, we track unrealized PnL based on current price movement.
        """
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc)

        # Get all pending paper trades
        pending = conn.execute(
            """SELECT bt.*, m.price_yes, m.price_no, m.question, m.active as market_active,
                      m.end_time
               FROM bot_trades bt
               LEFT JOIN markets m ON bt.market_id = m.condition_id
               WHERE bt.outcome = 'pending'"""
        ).fetchall()

        results = []
        for trade in pending:
            trade = dict(trade)
            side = trade["side"]
            entry_price = trade["entry_price"]
            size = trade["size"]
            trade_age_min = (now - datetime.fromisoformat(trade["timestamp"].replace("Z", "+00:00"))).total_seconds() / 60

            # Get current market price
            current_yes = trade.get("price_yes") or 0.5
            current_no = trade.get("price_no") or 0.5

            if side == "BUY":
                current_price = current_yes
            else:
                current_price = current_no

            # Calculate shares bought
            shares = size / entry_price if entry_price > 0 else 0

            # Check if market is resolved (closed and price is 0 or 1)
            market_resolved = False
            if trade.get("market_active") == 0:
                market_resolved = True
            elif current_price <= 0.01 or current_price >= 0.99:
                market_resolved = True

            if market_resolved:
                # Market resolved — real Polymarket payout
                if current_price >= 0.99:
                    # Our side won: each share pays $1
                    pnl = shares * (1.0 - entry_price)
                    won = True
                elif current_price <= 0.01:
                    # Our side lost: shares worth $0
                    pnl = -size
                    won = False
                else:
                    # Market closed at some intermediate price
                    pnl = shares * (current_price - entry_price)
                    won = pnl > 0

                outcome = "won" if won else "lost"
                conn.execute(
                    "UPDATE bot_trades SET outcome = ?, pnl = ?, resolved_at = ? WHERE id = ?",
                    (outcome, round(pnl, 2), now.isoformat(), trade["id"]),
                )

                question = trade.get("question", trade["market_id"][:20])
                results.append({
                    "trade_id": trade["id"],
                    "market": question,
                    "side": side,
                    "size": size,
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "pnl": pnl,
                    "won": won,
                    "resolved": True,
                })

                log.info(
                    f"Paper trade #{trade['id']} RESOLVED: {'WON' if won else 'LOST'} | "
                    f"Entry: {entry_price:.4f} → Final: {current_price:.4f} | "
                    f"PnL: ${pnl:.2f} ({shares:.1f} shares)"
                )

            elif trade_age_min > 30:
                # Trade is 30+ min old, still open — report unrealized P&L
                unrealized_pnl = shares * (current_price - entry_price)
                pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

                # Potential payout if we win
                potential_win = shares * (1.0 - entry_price)

                question = trade.get("question", trade["market_id"][:20])
                results.append({
                    "trade_id": trade["id"],
                    "market": question,
                    "side": side,
                    "size": size,
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "pnl": unrealized_pnl,
                    "won": unrealized_pnl > 0,
                    "resolved": False,
                    "potential_win": potential_win,
                    "age_hours": trade_age_min / 60,
                })

        conn.commit()
        conn.close()
        return results
