from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("wallet_scanner")


class WalletScanner:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_wallet_trades(self, address: str) -> list[dict]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM wallet_trades WHERE wallet_address = ? ORDER BY timestamp DESC",
            (address,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def score_wallet(self, address: str) -> dict:
        trades = self._get_wallet_trades(address)
        total = len(trades)

        result = {
            "address": address,
            "total_trades": total,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "consistency_score": 0.0,
            "frequency_score": 0.0,
            "recency_score": 0.0,
            "composite_score": 0.0,
        }

        if total < self.config.MIN_WALLET_TRADES:
            return result

        wins = sum(1 for t in trades if t["outcome"] == "won")
        losses = total - wins
        win_rate = wins / total if total > 0 else 0
        total_pnl = sum(t["pnl"] for t in trades)

        if win_rate < self.config.MIN_WALLET_WIN_RATE:
            result["wins"] = wins
            result["losses"] = losses
            result["win_rate"] = win_rate
            result["total_pnl"] = total_pnl
            return result

        # Consistency: standard deviation of PnL per trade (lower = more consistent)
        avg_pnl = total_pnl / total if total > 0 else 0
        variance = sum((t["pnl"] - avg_pnl) ** 2 for t in trades) / total
        std_pnl = variance ** 0.5
        consistency = max(0, 1 - (std_pnl / (abs(avg_pnl) + 1))) * 100

        # Frequency: trades per day over lookback period
        lookback_days = self.config.WALLET_LOOKBACK_DAYS
        frequency = min(100, (total / max(1, lookback_days)) * 10)

        # Recency: weight recent trades higher
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=7)
        recent_trades = [
            t for t in trades
            if t["timestamp"] and t["timestamp"] > recent_cutoff.isoformat()
        ]
        recent_ratio = len(recent_trades) / total if total > 0 else 0
        recency = recent_ratio * 100

        # Composite score (weighted)
        composite = (
            win_rate * 100 * 0.25
            + consistency * 0.25
            + min(100, total_pnl / 100) * 0.20
            + frequency * 0.15
            + recency * 0.15
        )

        result.update({
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "consistency_score": consistency,
            "frequency_score": frequency,
            "recency_score": recency,
            "composite_score": composite,
        })

        # Persist to wallets table
        conn = get_connection(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO wallets
               (address, total_trades, wins, losses, win_rate, total_pnl,
                avg_bet_size, consistency_score, frequency_score, recency_score,
                composite_score, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                address, total, wins, losses, win_rate, total_pnl,
                sum(t["size"] for t in trades) / total,
                consistency, frequency, recency, composite,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return result

    def get_all_wallet_addresses(self) -> list[str]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT DISTINCT wallet_address FROM wallet_trades"
        ).fetchall()
        conn.close()
        return [r["wallet_address"] for r in rows]

    def rank_and_track(self) -> list[dict]:
        addresses = self.get_all_wallet_addresses()
        scored = []
        for addr in addresses:
            s = self.score_wallet(addr)
            if s["composite_score"] > 0:
                scored.append(s)

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        top = scored[: self.config.TOP_TRACKED_WALLETS]

        conn = get_connection(self.db_path)
        conn.execute("DELETE FROM tracked_wallets")
        now = datetime.now(timezone.utc).isoformat()
        for rank, wallet in enumerate(top, 1):
            conn.execute(
                "INSERT INTO tracked_wallets (address, rank, added_at) VALUES (?, ?, ?)",
                (wallet["address"], rank, now),
            )
        conn.commit()
        conn.close()

        log.info(f"Tracked {len(top)} wallets out of {len(addresses)} total")
        return top
