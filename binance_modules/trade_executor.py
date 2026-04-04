from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("binance_trade_executor")


class BinanceTradeExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.BINANCE_DB_PATH

    def execute_trade(self, signal: dict, size: float) -> dict:
        if self.config.BINANCE_TRADING_MODE == "paper":
            return self._execute_paper(signal, size)
        else:
            return self._execute_live(signal, size)

    def _execute_paper(self, signal: dict, size: float) -> dict:
        price = signal["price"]
        side = signal["action"]
        symbol = signal["symbol"]

        if side == "buy":
            entry_price = price * (1 + self.config.BINANCE_SLIPPAGE_PCT)
            tp = entry_price * (1 + self.config.BINANCE_TAKE_PROFIT_PCT)
            sl = entry_price * (1 - self.config.BINANCE_STOP_LOSS_PCT)
        else:
            entry_price = price * (1 - self.config.BINANCE_SLIPPAGE_PCT)
            tp = entry_price * (1 - self.config.BINANCE_TAKE_PROFIT_PCT)
            sl = entry_price * (1 + self.config.BINANCE_STOP_LOSS_PCT)

        fees = size * self.config.BINANCE_FEE_PCT
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status, fees)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (now, symbol, side, entry_price, size, tp, sl, sl, fees),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(f"PAPER {side.upper()} {symbol} ${size:.2f} @ {entry_price:.2f} | TP:{tp:.2f} SL:{sl:.2f}")
        return {
            "trade_id": trade_id, "status": "filled", "side": side,
            "symbol": symbol, "entry_price": entry_price, "size": size,
            "tp": tp, "sl": sl, "fees": fees,
        }

    def _execute_live(self, signal: dict, size: float) -> dict:
        log.warning("Live trading not yet implemented")
        return {"status": "error", "reason": "Live trading not implemented"}

    def check_open_positions(self, current_prices: dict[str, float]) -> list[dict]:
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open'"
        ).fetchall()

        closed = []
        now = datetime.now(timezone.utc).isoformat()

        for trade in open_trades:
            trade = dict(trade)
            symbol = trade["symbol"]
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue

            side = trade["side"]
            tp = trade["tp"]
            sl = trade["sl"]
            trailing_sl = trade["trailing_sl"] or sl
            entry_price = trade["price"]
            size = trade["size"]

            reason = None
            exit_price = current_price

            if side == "buy":
                if current_price >= tp:
                    reason = "take_profit"
                elif current_price <= trailing_sl:
                    reason = "stop_loss" if trailing_sl == sl else "trailing_stop"
                else:
                    new_trailing = current_price * (1 - self.config.BINANCE_TRAILING_STOP_STEP_PCT)
                    if new_trailing > trailing_sl:
                        conn.execute(
                            "UPDATE bn_trades SET trailing_sl = ? WHERE id = ?",
                            (new_trailing, trade["id"]),
                        )
            else:
                if current_price <= tp:
                    reason = "take_profit"
                elif current_price >= trailing_sl:
                    reason = "stop_loss" if trailing_sl == sl else "trailing_stop"
                else:
                    new_trailing = current_price * (1 + self.config.BINANCE_TRAILING_STOP_STEP_PCT)
                    if new_trailing < trailing_sl:
                        conn.execute(
                            "UPDATE bn_trades SET trailing_sl = ? WHERE id = ?",
                            (new_trailing, trade["id"]),
                        )

            if reason:
                if side == "buy":
                    pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price
                pnl = size * pnl_pct - trade["fees"]

                conn.execute(
                    """UPDATE bn_trades SET
                       status = 'closed', exit_price = ?, exit_time = ?,
                       pnl = ?, reason = ?
                       WHERE id = ?""",
                    (exit_price, now, round(pnl, 4), reason, trade["id"]),
                )

                hold_time = ""
                try:
                    entry_time = datetime.fromisoformat(trade["timestamp"])
                    delta = datetime.fromisoformat(now) - entry_time
                    minutes = int(delta.total_seconds() / 60)
                    hold_time = f"{minutes}m"
                except (ValueError, TypeError):
                    pass

                closed.append({
                    "trade_id": trade["id"], "symbol": symbol, "side": side,
                    "entry_price": entry_price, "exit_price": exit_price,
                    "size": size, "pnl": round(pnl, 4), "reason": reason,
                    "hold_time": hold_time,
                })
                log.info(f"CLOSED {symbol} {side}: {reason} | PnL: ${pnl:.4f}")

        conn.commit()
        conn.close()
        return closed

    def close_by_signal(self, symbol: str, current_price: float, reason: str = "opposing_signal") -> list[dict]:
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open' AND symbol = ?",
            (symbol,),
        ).fetchall()

        closed = []
        now = datetime.now(timezone.utc).isoformat()

        for trade in open_trades:
            trade = dict(trade)
            entry_price = trade["price"]
            side = trade["side"]
            size = trade["size"]

            if side == "buy":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            pnl = size * pnl_pct - trade["fees"]

            conn.execute(
                """UPDATE bn_trades SET
                   status = 'closed', exit_price = ?, exit_time = ?,
                   pnl = ?, reason = ?
                   WHERE id = ?""",
                (current_price, now, round(pnl, 4), reason, trade["id"]),
            )
            closed.append({
                "trade_id": trade["id"], "symbol": symbol, "side": side,
                "entry_price": entry_price, "exit_price": current_price,
                "size": size, "pnl": round(pnl, 4), "reason": reason,
            })

        conn.commit()
        conn.close()
        return closed

    def get_open_positions(self) -> list[dict]:
        conn = get_connection(self.db_path)
        trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open' ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()
        return [dict(t) for t in trades]
