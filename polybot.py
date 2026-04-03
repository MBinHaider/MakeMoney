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

    async def status_update_loop(self):
        """Send status update to Telegram every 5 minutes."""
        while self.running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                stats = self.risk_manager.get_status()

                conn = get_connection(self.config.DB_PATH)
                recent_signals = conn.execute(
                    "SELECT COUNT(*) as cnt FROM signals WHERE timestamp > datetime('now', '-5 minutes')"
                ).fetchone()["cnt"]
                tracked_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM tracked_wallets"
                ).fetchone()["cnt"]
                market_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM markets WHERE active = 1"
                ).fetchone()["cnt"]
                conn.close()

                msg = (
                    f"<b>5-Min Update</b>\n"
                    f"Portfolio: ${stats['current_value']:.2f}\n"
                    f"P&L: ${stats['total_pnl']:.2f}\n"
                    f"Trades: {stats['total_trades']} (W:{stats['win_rate']:.0%})\n"
                    f"Open: {stats['open_positions']}\n"
                    f"Signals (5m): {recent_signals}\n"
                    f"Markets: {market_count} | Wallets: {tracked_count}\n"
                    f"Status: {'PAUSED' if stats['is_paused'] else 'ACTIVE'}"
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
