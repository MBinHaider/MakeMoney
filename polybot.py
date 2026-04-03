# polybot.py
import asyncio
import argparse
import signal
import sys
from datetime import datetime, timezone

from config import Config
from utils.db import init_db, get_connection
from utils.logger import get_logger
from modules.data_collector import DataCollector
from modules.wallet_scanner import WalletScanner
from modules.signal_engine import SignalEngine
from modules.trade_executor import TradeExecutor
from modules.risk_manager import RiskManager
from modules.notifier import Notifier

log = get_logger("polybot")


class PolyBot:
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.collector = DataCollector(config)
        self.scanner = WalletScanner(config)
        self.signal_engine = SignalEngine(config)
        self.executor = TradeExecutor(config)
        self.risk_manager = RiskManager(config)
        self.notifier = Notifier(config)
        self.notifier.set_callbacks(
            on_pause=self.risk_manager.pause,
            on_resume=self.risk_manager.resume,
            on_kill=self.stop,
            get_status=self.risk_manager.get_status,
        )

    async def startup(self, starting_capital: float):
        log.info(f"Starting PolyBot in {self.config.TRADING_MODE} mode")
        log.info(f"Starting capital: ${starting_capital}")
        init_db(self.config.DB_PATH)
        self.risk_manager.init_portfolio(starting_capital)
        await self.notifier.start_polling()
        await self.notifier.send_message(
            f"PolyBot started in <b>{self.config.TRADING_MODE}</b> mode\nCapital: ${starting_capital:.2f}"
        )
        self.running = True

    async def initial_scan(self):
        log.info("Running initial wallet scan...")
        await self.notifier.send_message("Running initial scan...")
        try:
            # Step 1: Find crypto markets
            markets = await self.collector.fetch_active_markets()
            await self.notifier.send_message(f"Found {len(markets)} crypto markets")

            # Step 2: Fetch price data
            for asset in self.config.TARGET_MARKETS:
                await self.collector.fetch_price_candles(asset)

            # Step 3: Discover whale wallets from market trades
            wallets = await self.collector.discover_whale_wallets()
            if wallets:
                await self.notifier.send_message(f"Discovered {len(wallets)} wallets. Analyzing...")
                # Fetch trade history AND positions (P&L) for each wallet
                for addr in wallets[:50]:  # Cap at 50 to avoid rate limits
                    await self.collector.fetch_wallet_trades_public(addr)
                    await self.collector.fetch_wallet_positions(addr)

                # Step 4: Score and rank wallets
                tracked = self.scanner.rank_and_track()
                await self.notifier.send_message(
                    f"Tracking {len(tracked)} top wallets. Bot is now monitoring."
                )
            else:
                await self.notifier.send_message("No wallets found yet. Will keep scanning.")

            log.info("Initial scan complete.")
        except Exception as e:
            log.warning(f"Initial scan failed (will retry in loops): {e}")
            await self.notifier.send_message(f"Initial scan failed, will retry: {type(e).__name__}")

    async def market_loop(self):
        while self.running:
            try:
                await self.collector.fetch_active_markets()
                await asyncio.sleep(self.config.MARKET_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Market loop error: {e}")
                await asyncio.sleep(5)

    async def price_loop(self):
        while self.running:
            try:
                for asset in self.config.TARGET_MARKETS:
                    await self.collector.fetch_price_candles(asset, limit=10)
                await asyncio.sleep(self.config.PRICE_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Price loop error: {e}")
                await asyncio.sleep(5)

    async def trade_resolution_loop(self):
        """Resolve paper trades every 2 minutes and update portfolio."""
        while self.running:
            try:
                await asyncio.sleep(120)  # Check every 2 minutes
                resolved = self.executor.resolve_paper_trades()
                for r in resolved:
                    self.risk_manager.record_trade_outcome(r["pnl"])
                    won_str = "WON" if r["won"] else "LOST"
                    stats = self.risk_manager.get_status()
                    msg = (
                        f"<b>Trade {won_str}!</b>\n"
                        f"Market: {str(r['market'])[:40]}\n"
                        f"Direction: {r['side']}\n"
                        f"Entry: {r['entry_price']:.4f} → Exit: {r['exit_price']:.4f}\n"
                        f"P&L: ${r['pnl']:.2f}\n"
                        f"Portfolio: ${stats['current_value']:.2f}"
                    )
                    await self.notifier.send_message(msg)
                if resolved:
                    log.info(f"Resolved {len(resolved)} trades")
            except Exception as e:
                log.error(f"Trade resolution error: {e}")
                await asyncio.sleep(30)

    async def wallet_monitor_loop(self):
        while self.running:
            try:
                new_trades = await self.collector.poll_tracked_wallets()
                # Only process trades on our tracked crypto markets
                from utils.db import get_connection
                conn = get_connection(self.config.DB_PATH)
                tracked_markets = set(
                    r["condition_id"] for r in
                    conn.execute("SELECT condition_id FROM markets WHERE active = 1").fetchall()
                )
                conn.close()

                crypto_trades = [t for t in new_trades if t.get("market_id") in tracked_markets]
                if crypto_trades:
                    log.info(f"Processing {len(crypto_trades)} crypto trades (filtered from {len(new_trades)} total)")
                for trade in crypto_trades:
                    await self.process_whale_trade(trade)
                await asyncio.sleep(self.config.WALLET_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Wallet monitor error: {e}")
                await asyncio.sleep(5)

    def _calc_maturity_level(self, conn) -> dict:
        """Calculate how mature/ready the bot is across key dimensions."""
        # 1. Data coverage: how many wallets have P&L data
        total_wallets = conn.execute("SELECT COUNT(*) as cnt FROM wallets WHERE total_trades > 0").fetchone()["cnt"]
        wallets_with_pnl = conn.execute("SELECT COUNT(*) as cnt FROM wallets WHERE wins + losses > 0").fetchone()["cnt"]
        data_pct = (wallets_with_pnl / max(1, total_wallets)) * 100

        # 2. Signal quality: avg score of recent signals
        avg_score_row = conn.execute(
            "SELECT AVG(total_score) as avg, COUNT(*) as cnt FROM signals"
        ).fetchone()
        avg_signal_score = avg_score_row["avg"] or 0
        total_signals = avg_score_row["cnt"] or 0

        # 3. Trade experience: how many paper trades executed
        total_trades = conn.execute("SELECT COUNT(*) as cnt FROM bot_trades").fetchone()["cnt"]
        resolved_trades = conn.execute("SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome != 'pending'").fetchone()["cnt"]
        winning_trades = conn.execute("SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome = 'won'").fetchone()["cnt"]

        # 4. Whale intelligence: quality of tracked wallets
        top_wallets = conn.execute(
            "SELECT address, win_rate, total_pnl FROM wallets WHERE composite_score > 0 ORDER BY composite_score DESC LIMIT 5"
        ).fetchall()
        profitable_whales = sum(1 for w in top_wallets if w["total_pnl"] > 0)

        # 5. Market coverage
        market_count = conn.execute("SELECT COUNT(*) as cnt FROM markets WHERE active = 1").fetchone()["cnt"]

        # Overall maturity score (0-100)
        data_score = min(25, data_pct * 0.25)  # max 25
        signal_score = min(25, (total_signals / 100) * 25)  # max 25 at 100+ signals
        trade_score = min(25, (total_trades / 20) * 25)  # max 25 at 20+ trades
        whale_score = min(25, (profitable_whales / 3) * 25)  # max 25 at 3+ profitable whales

        maturity = data_score + signal_score + trade_score + whale_score

        # Maturity level label
        if maturity >= 80:
            level = "READY FOR LIVE"
            bar = "████████████████████ 🟢"
        elif maturity >= 60:
            level = "ALMOST READY"
            bar = "████████████████░░░░ 🟡"
        elif maturity >= 40:
            level = "LEARNING"
            bar = "████████████░░░░░░░░ 🟠"
        elif maturity >= 20:
            level = "EARLY STAGE"
            bar = "████████░░░░░░░░░░░░ 🔴"
        else:
            level = "JUST STARTED"
            bar = "████░░░░░░░░░░░░░░░░ 🔴"

        return {
            "maturity": maturity,
            "level": level,
            "bar": bar,
            "data_pct": data_pct,
            "total_wallets": total_wallets,
            "wallets_with_pnl": wallets_with_pnl,
            "total_signals": total_signals,
            "avg_signal_score": avg_signal_score,
            "total_trades": total_trades,
            "resolved_trades": resolved_trades,
            "winning_trades": winning_trades,
            "profitable_whales": profitable_whales,
            "top_whales": top_wallets,
            "market_count": market_count,
            "data_score": data_score,
            "signal_score": signal_score,
            "trade_score": trade_score,
            "whale_score": whale_score,
        }

    async def status_update_loop(self):
        """Send learning progress update to Telegram every 5 minutes."""
        first_run = True
        while self.running:
            try:
                if first_run:
                    await asyncio.sleep(60)  # First update after 1 minute
                    first_run = False
                else:
                    await asyncio.sleep(300)  # Then every 5 minutes
                log.info("Sending 5-min progress report...")
                stats = self.risk_manager.get_status()
                conn = get_connection(self.config.DB_PATH)
                m = self._calc_maturity_level(conn)
                conn.close()

                # Top whale summary
                whale_lines = ""
                for w in m["top_whales"][:3]:
                    pnl = w["total_pnl"]
                    wr = w["win_rate"]
                    addr = w["address"][:8]
                    emoji = "✅" if pnl > 0 else "❌"
                    whale_lines += f"  {emoji} {addr}.. ${pnl:,.0f} ({wr:.0%})\n"

                msg = (
                    f"<b>📊 5-Min Progress Report</b>\n"
                    f"\n"
                    f"<b>Maturity: {m['level']}</b>\n"
                    f"{m['bar']} {m['maturity']:.0f}/100\n"
                    f"\n"
                    f"<b>Learning Progress:</b>\n"
                    f"  📈 Data: {m['wallets_with_pnl']}/{m['total_wallets']} wallets profiled ({m['data_pct']:.0f}%)\n"
                    f"  🔍 Signals: {m['total_signals']} analyzed (avg score: {m['avg_signal_score']:.1f})\n"
                    f"  💰 Trades: {m['total_trades']} paper ({m['winning_trades']}W/{m['resolved_trades'] - m['winning_trades']}L)\n"
                    f"  🐋 Profitable whales: {m['profitable_whales']}/5 tracked\n"
                    f"\n"
                    f"<b>Score Breakdown:</b>\n"
                    f"  Data: {m['data_score']:.0f}/25 | Signals: {m['signal_score']:.0f}/25\n"
                    f"  Trades: {m['trade_score']:.0f}/25 | Whales: {m['whale_score']:.0f}/25\n"
                    f"\n"
                    f"<b>Top Whales:</b>\n"
                    f"{whale_lines}"
                    f"\n"
                    f"<b>Portfolio:</b> ${stats['current_value']:.2f} (P&L: ${stats['total_pnl']:.2f})\n"
                    f"Markets: {m['market_count']} | Status: {'⏸ PAUSED' if stats['is_paused'] else '▶ ACTIVE'}"
                )
                await self.notifier.send_message(msg)
            except Exception as e:
                log.error(f"Status update error: {e}")
                await asyncio.sleep(60)

    async def daily_refresh(self):
        while self.running:
            try:
                tracked = self.scanner.rank_and_track()
                if tracked:
                    addrs = ", ".join(t["address"][:8] + "..." for t in tracked[:5])
                    await self.notifier.send_message(
                        f"Daily refresh: tracking {len(tracked)} wallets\nTop 5: {addrs}"
                    )
                stats = self.risk_manager.get_status()
                summary = self.notifier.format_daily_summary(stats)
                await self.notifier.send_message(summary)
                await asyncio.sleep(86400)
            except Exception as e:
                log.error(f"Daily refresh error: {e}")
                await asyncio.sleep(3600)

    async def process_whale_trade(self, trade: dict):
        # Get market name for better logging
        market_name = trade.get("title", trade.get("slug", trade.get("market_id", "unknown")))[:40]
        wallet = trade.get("wallet_address", "")[:10]

        signal = self.signal_engine.generate_signal(trade)
        if signal is None:
            return

        action = signal["action"]
        score = signal["total_score"]

        if action == "auto_trade":
            can = self.risk_manager.can_trade()
            if not can["allowed"]:
                log.info(f"Trade blocked: {can['reason']}")
                await self.notifier.send_message(
                    f"Signal blocked: {can['reason']}\nScore: {score:.1f}"
                )
                return
            size = self.risk_manager.calc_position_size(score)
            from utils.db import get_connection
            conn = get_connection(self.config.DB_PATH)
            market = conn.execute(
                "SELECT * FROM markets WHERE condition_id = ?",
                (signal["market_id"],),
            ).fetchone()
            conn.close()
            if market is None:
                log.warning(f"Market not found for auto-trade: {signal['market_id'][:10]}")
                return
            market = dict(market)
            result = self.executor.execute(signal, market, size)
            if result["status"] == "filled":
                result["market_id"] = market.get("question", signal["market_id"][:20])
                msg = self.notifier.format_trade_alert(result, score)
                await self.notifier.send_message(msg)

        elif action == "alert":
            # Only send Telegram alerts for high-quality signals (score >= 55)
            if score >= 55:
                await self.notifier.send_message(
                    f"<b>SIGNAL ALERT</b>\n"
                    f"Whale: {wallet}...\n"
                    f"Direction: {signal['direction']}\n"
                    f"Market: {market_name}\n"
                    f"Score: {score:.1f}/100\n"
                    f"W:{signal['whale_score']:.0f} M:{signal['market_score']:.0f} C:{signal['confluence_score']:.0f}"
                )

    def stop(self):
        log.info("Stopping PolyBot...")
        self.running = False

    async def run(self, starting_capital: float):
        await self.startup(starting_capital)
        await self.initial_scan()
        tasks = [
            asyncio.create_task(self.market_loop()),
            asyncio.create_task(self.price_loop()),
            asyncio.create_task(self.wallet_monitor_loop()),
            asyncio.create_task(self.trade_resolution_loop()),
            asyncio.create_task(self.status_update_loop()),
            asyncio.create_task(self.daily_refresh()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            await self.notifier.stop()
            log.info("PolyBot stopped")


def main():
    parser = argparse.ArgumentParser(description="PolyBot - Polymarket Trading Bot")
    parser.add_argument("--mode", choices=["paper", "live"], default=None, help="Trading mode (overrides .env)")
    parser.add_argument("--capital", type=float, default=100.0, help="Starting capital in USDC (default: 100)")
    args = parser.parse_args()
    config = Config()
    if args.mode:
        config.TRADING_MODE = args.mode
    bot = PolyBot(config)
    def signal_handler(sig, frame):
        bot.stop()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    asyncio.run(bot.run(args.capital))


if __name__ == "__main__":
    main()
