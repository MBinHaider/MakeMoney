from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from config import Config


class DashboardDataReader:
    def __init__(self, fm_db_path: str, bn_db_path: str, pb_db_path: str):
        self.fm_db = fm_db_path
        self.bn_db = bn_db_path
        self.pb_db = pb_db_path
        self.config = Config()

    def get_fivemin_stats(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            row = conn.execute("SELECT * FROM fm_portfolio WHERE id = 1").fetchone()
            conn.close()
            if row is None:
                return self._empty_fivemin_stats()
            p = dict(row)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return {
                "balance": p["balance"],
                "starting_balance": p["starting_balance"],
                "pnl": p["total_pnl"],
                "total_trades": p["total_trades"],
                "total_wins": p["total_wins"],
                "win_rate": p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0,
                "consecutive_losses": p["consecutive_losses"],
                "daily_pnl": p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0,
                "is_paused": bool(p["is_paused"]),
                "pause_until": p["pause_until"],
                "mode": self.config.FIVEMIN_TRADING_MODE,
            }
        except Exception:
            return self._empty_fivemin_stats()

    def _empty_fivemin_stats(self) -> dict:
        return {
            "balance": 0, "starting_balance": 0, "pnl": 0, "total_trades": 0,
            "total_wins": 0, "win_rate": 0, "consecutive_losses": 0,
            "daily_pnl": 0, "is_paused": False, "pause_until": "",
            "mode": "paper",
        }

    def get_binance_stats(self) -> dict:
        try:
            conn = get_connection(self.bn_db)
            row = conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone()
            open_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
            ).fetchone()["cnt"]
            conn.close()
            if row is None:
                return self._empty_binance_stats()
            p = dict(row)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return {
                "balance": p["balance"],
                "starting_balance": p["starting_balance"],
                "pnl": p["total_pnl"],
                "total_trades": p["total_trades"],
                "total_wins": p["total_wins"],
                "win_rate": p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0,
                "open_positions": open_count,
                "daily_pnl": p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0,
                "is_paused": bool(p["is_paused"]),
                "mode": self.config.BINANCE_TRADING_MODE,
            }
        except Exception:
            return self._empty_binance_stats()

    def _empty_binance_stats(self) -> dict:
        return {
            "balance": 0, "starting_balance": 0, "pnl": 0, "total_trades": 0,
            "total_wins": 0, "win_rate": 0, "open_positions": 0,
            "daily_pnl": 0, "is_paused": False, "mode": "paper",
        }

    def get_polybot_stats(self) -> dict:
        try:
            conn = get_connection(self.pb_db)
            markets = conn.execute("SELECT COUNT(*) as cnt FROM markets WHERE active = 1").fetchone()["cnt"]
            signals = conn.execute("SELECT COUNT(*) as cnt FROM signals WHERE date(timestamp) = date('now')").fetchone()["cnt"]
            whales = conn.execute("SELECT COUNT(*) as cnt FROM tracked_wallets").fetchone()["cnt"]
            conn.close()
            return {
                "markets": markets, "signals": signals, "whales": whales,
                "mode": self.config.TRADING_MODE,
            }
        except Exception:
            return {"markets": 0, "signals": 0, "whales": 0, "mode": "paper"}

    def get_recent_trades(self, limit: int = 10) -> list[dict]:
        trades = []
        try:
            conn = get_connection(self.fm_db)
            fm_trades = conn.execute(
                "SELECT * FROM fm_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            for t in fm_trades:
                t = dict(t)
                trades.append({
                    "time": t["timestamp"][:16], "bot": "5M",
                    "mode": self.config.FIVEMIN_TRADING_MODE,
                    "asset": t["asset"], "direction": t["direction"],
                    "entry": t["entry_price"], "size": t["cost"],
                    "result": t["result"], "pnl": t["pnl"],
                    "confidence": t["signal_confidence"],
                    "sort_ts": t["timestamp"],
                })
        except Exception:
            pass

        try:
            conn = get_connection(self.bn_db)
            bn_trades = conn.execute(
                "SELECT * FROM bn_trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            for t in bn_trades:
                t = dict(t)
                result = "open" if t["status"] == "open" else ("win" if t.get("pnl", 0) > 0 else "loss")
                trades.append({
                    "time": t["timestamp"][:16], "bot": "BN",
                    "mode": self.config.BINANCE_TRADING_MODE,
                    "asset": t["symbol"], "direction": t["side"].upper(),
                    "entry": t["price"], "size": t["size"],
                    "result": result, "pnl": t.get("pnl", 0),
                    "confidence": 0,
                    "sort_ts": t["timestamp"],
                })
        except Exception:
            pass

        trades.sort(key=lambda x: x["sort_ts"], reverse=True)
        return trades[:limit]

    def get_cooldown_status(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            row = conn.execute("SELECT is_paused, pause_until, consecutive_losses FROM fm_portfolio WHERE id = 1").fetchone()
            conn.close()
            if row is None or not row["is_paused"]:
                return {"active": False, "seconds_remaining": 0, "consecutive_losses": 0}
            pause_until = row["pause_until"]
            if not pause_until:
                return {"active": True, "seconds_remaining": 0, "consecutive_losses": row["consecutive_losses"]}
            try:
                end = datetime.fromisoformat(pause_until)
                remaining = (end - datetime.now(timezone.utc)).total_seconds()
                return {
                    "active": True,
                    "seconds_remaining": max(0, int(remaining)),
                    "consecutive_losses": row["consecutive_losses"],
                }
            except ValueError:
                return {"active": True, "seconds_remaining": 0, "consecutive_losses": row["consecutive_losses"]}
        except Exception:
            return {"active": False, "seconds_remaining": 0, "consecutive_losses": 0}

    def get_pnl_history(self, hours: int = 24) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=hours)).isoformat()
        fm_pnls = []
        bn_pnls = []

        try:
            conn = get_connection(self.fm_db)
            rows = conn.execute(
                "SELECT pnl, timestamp FROM fm_trades WHERE result != 'pending' AND timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            ).fetchall()
            conn.close()
            running = 0.0
            for r in rows:
                running += r["pnl"]
                fm_pnls.append(round(running, 2))
        except Exception:
            pass

        try:
            conn = get_connection(self.bn_db)
            rows = conn.execute(
                "SELECT pnl, timestamp FROM bn_trades WHERE status = 'closed' AND timestamp >= ? ORDER BY timestamp",
                (cutoff,),
            ).fetchall()
            conn.close()
            running = 0.0
            for r in rows:
                running += r["pnl"]
                bn_pnls.append(round(running, 2))
        except Exception:
            pass

        # Pad to same length
        max_len = max(len(fm_pnls), len(bn_pnls), 2)
        fm_pnls = fm_pnls or [0.0]
        bn_pnls = bn_pnls or [0.0]
        while len(fm_pnls) < max_len:
            fm_pnls.append(fm_pnls[-1])
        while len(bn_pnls) < max_len:
            bn_pnls.append(bn_pnls[-1])

        combined = [round(f + b, 2) for f, b in zip(fm_pnls, bn_pnls)]
        return {"fivemin": fm_pnls, "binance": bn_pnls, "combined": combined}

    def get_signal_hitrate(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            generated = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_signals WHERE date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            traded = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_signals WHERE action_taken = 'traded' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            won = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_trades WHERE result = 'win' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            total_traded = conn.execute(
                "SELECT COUNT(*) as cnt FROM fm_trades WHERE result != 'pending' AND date(timestamp) = ?", (today,)
            ).fetchone()["cnt"]
            conn.close()
            skipped = generated - traded
            return {
                "generated": generated,
                "skipped_price": max(0, skipped),
                "skipped_risk": 0,
                "traded": total_traded,
                "won": won,
            }
        except Exception:
            return {"generated": 0, "skipped_price": 0, "skipped_risk": 0, "traded": 0, "won": 0}

    def get_hourly_winrate(self) -> list[dict]:
        hourly = [{"hour": h, "trades": 0, "wins": 0, "rate": 0.0} for h in range(24)]
        try:
            conn = get_connection(self.fm_db)
            rows = conn.execute(
                "SELECT timestamp, result FROM fm_trades WHERE result IN ('win', 'loss')"
            ).fetchall()
            conn.close()
            for r in rows:
                try:
                    hour = int(r["timestamp"][11:13])
                    hourly[hour]["trades"] += 1
                    if r["result"] == "win":
                        hourly[hour]["wins"] += 1
                except (ValueError, IndexError):
                    pass
            for h in hourly:
                if h["trades"] > 0:
                    h["rate"] = h["wins"] / h["trades"]
        except Exception:
            pass
        return hourly

    def get_daily_comparison(self) -> dict:
        try:
            conn = get_connection(self.fm_db)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

            def day_stats(date_str):
                rows = conn.execute(
                    "SELECT pnl, result FROM fm_trades WHERE date(timestamp) = ? AND result != 'pending'",
                    (date_str,),
                ).fetchall()
                if not rows:
                    return {"pnl": 0, "trades": 0, "win_rate": 0, "best": 0, "worst": 0}
                pnls = [r["pnl"] for r in rows]
                wins = sum(1 for r in rows if r["result"] == "win")
                return {
                    "pnl": round(sum(pnls), 2),
                    "trades": len(pnls),
                    "win_rate": wins / len(pnls) if pnls else 0,
                    "best": round(max(pnls), 2) if pnls else 0,
                    "worst": round(min(pnls), 2) if pnls else 0,
                }

            all_rows = conn.execute(
                "SELECT date(timestamp) as d, SUM(pnl) as total FROM fm_trades WHERE result != 'pending' GROUP BY d ORDER BY total"
            ).fetchall()
            conn.close()

            worst_date = all_rows[0]["d"] if all_rows else today
            best_date = all_rows[-1]["d"] if all_rows else today

            conn = get_connection(self.fm_db)
            result = {
                "today": day_stats(today),
                "yesterday": day_stats(yesterday),
                "best": day_stats(best_date),
                "worst": day_stats(worst_date),
            }
            conn.close()
            return result
        except Exception:
            empty = {"pnl": 0, "trades": 0, "win_rate": 0, "best": 0, "worst": 0}
            return {"today": empty, "yesterday": empty, "best": empty, "worst": empty}
