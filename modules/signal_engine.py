# modules/signal_engine.py
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("signal_engine")


class SignalEngine:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_wallet_info(self, address: str) -> dict | None:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM wallets WHERE address = ?", (address,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def _get_wallet_rank(self, address: str) -> int | None:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT rank FROM tracked_wallets WHERE address = ?", (address,)).fetchone()
        conn.close()
        return row["rank"] if row else None

    def _get_market_info(self, market_id: str) -> dict | None:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM markets WHERE condition_id = ?", (market_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def _get_recent_candles(self, asset: str, limit: int = 10) -> list[dict]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM price_candles WHERE asset = ? ORDER BY timestamp DESC LIMIT ?",
            (asset, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _calc_whale_score(self, trade: dict) -> float:
        address = trade["wallet_address"]
        rank = self._get_wallet_rank(address)
        if rank is None:
            return 0.0
        wallet = self._get_wallet_info(address)
        if wallet is None:
            return 0.0

        # Rank score (0-12)
        if rank <= 5:
            rank_pts = 12.0
        elif rank <= 10:
            rank_pts = 8.0
        else:
            rank_pts = 4.0

        # Conviction score (0-10): bet size relative to average
        avg_bet = wallet.get("avg_bet_size", 1.0) or 1.0
        size_ratio = trade.get("size", 0) / avg_bet
        conviction_pts = min(10.0, size_ratio * 3.0)

        # Profitability score (0-18): real P&L weighted heavily
        total_pnl = wallet.get("total_pnl", 0) or 0
        wr = wallet.get("win_rate", 0) or 0
        if total_pnl > 0 and wr > 0.5:
            # Profitable wallet with winning record
            profit_pts = min(18.0, 10.0 + (wr * 8.0))
        elif total_pnl > 0:
            profit_pts = 8.0
        elif wr > 0:
            profit_pts = wr * 6.0
        else:
            profit_pts = 3.0  # Unknown profitability, small baseline

        return min(40.0, rank_pts + conviction_pts + profit_pts)

    def _calc_market_score(self, market_id: str, direction: str) -> float:
        market = self._get_market_info(market_id)
        if market is None:
            return 0.0
        asset = market.get("asset", "")
        candles = self._get_recent_candles(asset, 10)
        if len(candles) < 2:
            return 10.0
        prices = [c["close"] for c in reversed(candles)]
        momentum = (prices[-1] - prices[0]) / (prices[0] + 0.01)
        is_aligned = (momentum > 0 and direction == "BUY") or (momentum < 0 and direction == "SELL")
        momentum_pts = 15.0 if is_aligned else 5.0
        high_low_ranges = [(c["high"] - c["low"]) / (c["low"] + 0.01) for c in candles]
        avg_range = sum(high_low_ranges) / len(high_low_ranges)
        if 0.001 < avg_range < 0.01:
            vol_pts = 10.0
        elif avg_range <= 0.001:
            vol_pts = 3.0
        else:
            vol_pts = 5.0
        volume = market.get("volume", 0)
        if volume > 100000:
            vol_market_pts = 10.0
        elif volume > 50000:
            vol_market_pts = 7.0
        elif volume > 10000:
            vol_market_pts = 5.0
        else:
            vol_market_pts = 2.0
        return min(35.0, momentum_pts + vol_pts + vol_market_pts)

    def _calc_confluence_score(self, market_id: str, direction: str) -> float:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc)
        two_min_ago = (now - timedelta(minutes=2)).isoformat()
        rows = conn.execute(
            """SELECT COUNT(*) as cnt FROM signals
               WHERE market_id = ? AND direction = ? AND timestamp > ?""",
            (market_id, direction, two_min_ago),
        ).fetchone()
        conn.close()
        same_direction_count = rows["cnt"] if rows else 0
        if same_direction_count >= 3:
            confluence_pts = 15.0
        elif same_direction_count >= 1:
            confluence_pts = 8.0
        else:
            confluence_pts = 0.0
        pattern_pts = 5.0
        return min(25.0, confluence_pts + pattern_pts)

    def generate_signal(self, whale_trade: dict) -> dict | None:
        address = whale_trade.get("wallet_address", "")
        market_id = whale_trade.get("market_id", "")
        direction = whale_trade.get("side", "BUY")

        # Skip lopsided markets — no profit potential if one side is >85%
        market = self._get_market_info(market_id)
        if market:
            price_yes = market.get("price_yes", 0.5)
            price_no = market.get("price_no", 0.5)
            if price_yes > 0.85 or price_no > 0.85:
                return None  # Market already decided, skip

        whale_score = self._calc_whale_score(whale_trade)
        market_score = self._calc_market_score(market_id, direction)
        confluence_score = self._calc_confluence_score(market_id, direction)
        total_score = whale_score + market_score + confluence_score
        if total_score >= self.config.SIGNAL_AUTO_TRADE_THRESHOLD:
            action = "auto_trade"
        elif total_score >= self.config.SIGNAL_ALERT_THRESHOLD:
            action = "alert"
        else:
            action = "logged"
        signal = {
            "market_id": market_id,
            "direction": direction,
            "whale_score": whale_score,
            "market_score": market_score,
            "confluence_score": confluence_score,
            "total_score": total_score,
            "action": action,
            "triggering_wallet": address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO signals
               (market_id, direction, whale_score, market_score, confluence_score,
                total_score, action_taken, triggering_wallet, timestamp)
               VALUES (:market_id, :direction, :whale_score, :market_score,
                       :confluence_score, :total_score, :action, :triggering_wallet,
                       :timestamp)""",
            signal,
        )
        signal["id"] = cursor.lastrowid
        conn.commit()
        conn.close()
        log.info(
            f"Signal: {direction} on {market_id[:10]} | "
            f"Score: {total_score:.1f} (W:{whale_score:.1f} M:{market_score:.1f} C:{confluence_score:.1f}) | "
            f"Action: {action}"
        )
        return signal
