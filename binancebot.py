# binancebot.py
import asyncio
import argparse
import signal
import sys
from datetime import datetime, timezone

from config import Config
from utils.binance_db import init_binance_db
from utils.db import get_connection
from utils.logger import get_logger
from binance_modules.market_data import MarketData
from binance_modules.indicators import compute_all
from binance_modules.signal_engine import SignalEngine
from binance_modules.risk_manager import BinanceRiskManager
from binance_modules.trade_executor import BinanceTradeExecutor
from binance_modules.notifier import BinanceNotifier

log = get_logger("binancebot")


class BinanceBot:
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.market_data = MarketData(config)
        self.signal_engine = SignalEngine(config)
        self.risk_manager = BinanceRiskManager(config)
        self.executor = BinanceTradeExecutor(config)
        self.notifier = BinanceNotifier(config)

    async def startup(self, starting_balance: float):
        log.info(f"Starting BinanceBot in {self.config.BINANCE_TRADING_MODE} mode")
        init_binance_db(self.config.BINANCE_DB_PATH)
        self.risk_manager.init_portfolio(starting_balance)
        await self.notifier.send_message(
            f"BinanceBot started in <b>{self.config.BINANCE_TRADING_MODE}</b> mode\n"
            f"Capital: ${starting_balance:.2f}\n"
            f"Pairs: {', '.join(self.config.BINANCE_PAIRS)}\n"
            f"Strategy: RSI + MACD + BB (2-of-3 agreement)"
        )
        self.running = True

    async def trading_loop(self):
        """Main loop: fetch candles, compute indicators, generate signals, execute trades."""
        while self.running:
            try:
                all_candles = await self.market_data.fetch_all_candles()

                current_prices = {}
                for symbol in self.config.BINANCE_PAIRS:
                    if symbol in all_candles and all_candles[symbol]["1m"]:
                        current_prices[symbol] = all_candles[symbol]["1m"][-1]["close"]

                # Log prices each cycle
                price_str = " | ".join(f"{s}: ${p:,.2f}" for s, p in current_prices.items())
                log.info(f"Tick: {price_str}")

                closed_trades = self.executor.check_open_positions(current_prices)
                for closed in closed_trades:
                    self.risk_manager.record_trade_outcome(closed["pnl"])
                    status = self.risk_manager.get_status()
                    msg = self.notifier.format_sell_alert(closed, status)
                    await self.notifier.send_message(msg)

                for symbol in self.config.BINANCE_PAIRS:
                    if symbol not in all_candles:
                        continue

                    candles_1m = all_candles[symbol].get("1m", [])
                    candles_5m = all_candles[symbol].get("5m", [])

                    if len(candles_1m) < 35 or len(candles_5m) < 35:
                        continue

                    indicators_1m = compute_all(candles_1m)
                    indicators_5m = compute_all(candles_5m)
                    current_price = current_prices.get(symbol, 0)

                    if current_price == 0:
                        continue

                    signal = self.signal_engine.evaluate(
                        symbol, indicators_1m, indicators_5m, current_price
                    )

                    # Log indicator readings
                    rsi = indicators_1m.get("rsi")
                    macd_h = indicators_1m.get("macd_histogram")
                    bb_l = indicators_1m.get("bb_lower")
                    bb_u = indicators_1m.get("bb_upper")
                    rsi_str = f"{rsi:.1f}" if rsi else "N/A"
                    log.info(
                        f"{symbol} RSI:{rsi_str} MACD_H:{macd_h:.4f} "
                        f"BB:[{bb_l:,.0f}-{bb_u:,.0f}] → {signal['action'].upper()}"
                        if macd_h and bb_l and bb_u else
                        f"{symbol} indicators not ready yet"
                    )

                    if signal["action"] == "hold":
                        continue

                    if signal["action"] == "sell":
                        open_positions = self.executor.get_open_positions()
                        buy_positions = [p for p in open_positions if p["symbol"] == symbol and p["side"] == "buy"]
                        if buy_positions:
                            closed = self.executor.close_by_signal(symbol, current_price, "opposing_signal")
                            for c in closed:
                                self.risk_manager.record_trade_outcome(c["pnl"])
                                status = self.risk_manager.get_status()
                                msg = self.notifier.format_sell_alert(c, status)
                                await self.notifier.send_message(msg)
                        continue

                    can_trade = self.risk_manager.can_trade()
                    if not can_trade["allowed"]:
                        log.info(f"Trade blocked: {can_trade['reason']}")
                        continue

                    size = self.risk_manager.calc_position_size(signal["strength"])

                    if size < 5.0:
                        log.info(f"Position too small: ${size:.2f} < $5 minimum")
                        continue

                    result = self.executor.execute_trade(signal, size)
                    if result["status"] == "filled":
                        status = self.risk_manager.get_status()
                        msg = self.notifier.format_buy_alert(
                            result, indicators_1m, status
                        )
                        await self.notifier.send_message(msg)

                await asyncio.sleep(self.config.BINANCE_POLL_INTERVAL_SEC)

            except Exception as e:
                log.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)

    async def summary_loop(self):
        """Send periodic summaries every 15 minutes."""
        while self.running:
            try:
                await asyncio.sleep(self.config.BINANCE_SUMMARY_INTERVAL_SEC)
                status = self.risk_manager.get_status()
                open_trades = self.executor.get_open_positions()
                msg = self.notifier.format_summary(status, open_trades)
                await self.notifier.send_message(msg)
            except Exception as e:
                log.error(f"Summary loop error: {e}")
                await asyncio.sleep(60)

    async def daily_report_loop(self):
        """Send daily report."""
        while self.running:
            try:
                await asyncio.sleep(self.config.BINANCE_DAILY_REPORT_INTERVAL_SEC)
                status = self.risk_manager.get_status()
                conn = get_connection(self.config.BINANCE_DB_PATH)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                today_trades = conn.execute(
                    "SELECT * FROM bn_trades WHERE status = 'closed' AND date(exit_time) = ?",
                    (today,),
                ).fetchall()
                conn.close()
                today_trades = [dict(t) for t in today_trades]
                msg = self.notifier.format_daily_report(status, today_trades)
                await self.notifier.send_message(msg)
            except Exception as e:
                log.error(f"Daily report error: {e}")
                await asyncio.sleep(3600)

    def stop(self):
        log.info("Stopping BinanceBot...")
        self.running = False

    async def run(self, starting_balance: float):
        await self.startup(starting_balance)
        tasks = [
            asyncio.create_task(self.trading_loop()),
            asyncio.create_task(self.summary_loop()),
            asyncio.create_task(self.daily_report_loop()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            log.info("BinanceBot stopped")


def main():
    parser = argparse.ArgumentParser(description="BinanceBot - Rapid BTC/ETH Trading Bot")
    parser.add_argument(
        "--mode", choices=["paper", "live"], default=None,
        help="Trading mode (overrides .env)",
    )
    parser.add_argument(
        "--capital", type=float, default=45.0,
        help="Starting capital in USD (default: 45)",
    )
    args = parser.parse_args()

    config = Config()
    if args.mode:
        config.BINANCE_TRADING_MODE = args.mode

    bot = BinanceBot(config)

    def signal_handler(sig, frame):
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(bot.run(args.capital))


if __name__ == "__main__":
    main()
