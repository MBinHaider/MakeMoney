import asyncio
import argparse
import signal
import sys
import time

from config import Config
from utils.fivemin_db import init_fivemin_db
from utils.logger import get_logger
from fivemin_modules.market_data import (
    FiveMinMarketData,
    compute_window_ts,
    compute_seconds_elapsed,
)
from fivemin_modules.signal_engine import FiveMinSignalEngine
from fivemin_modules.risk_manager import FiveMinRiskManager
from fivemin_modules.trade_executor import FiveMinTradeExecutor
from fivemin_modules.notifier import FiveMinNotifier

log = get_logger("polybot5m")


class PolyBot5M:
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.market_data = FiveMinMarketData(config)
        self.signal_engine = FiveMinSignalEngine(config)
        self.risk_manager = FiveMinRiskManager(config)
        self.executor = FiveMinTradeExecutor(config)
        self.notifier = FiveMinNotifier(config)
        self.exchange = None
        self._traded_this_window = False

    async def startup(self) -> None:
        log.info(f"Starting PolyBot 5M in {self.config.FIVEMIN_TRADING_MODE} mode")
        init_fivemin_db(self.config.FIVEMIN_DB_PATH)
        self.risk_manager.init_portfolio(self.config.FIVEMIN_STARTING_BALANCE)

        # Init PMXT exchange
        try:
            import pmxt
            self.exchange = pmxt.Polymarket({
                "privateKey": self.config.PRIVATE_KEY,
                "proxyAddress": self.config.POLYMARKET_PROXY_ADDRESS,
            })
            log.info("PMXT exchange connected")
        except Exception as e:
            log.warning(f"PMXT init failed (paper mode will simulate): {e}")
            self.exchange = None

        # Init market states
        window_ts = compute_window_ts(int(time.time()))
        self.market_data.init_states(window_ts)

        await self.notifier.send_message(
            self.notifier.format_startup(
                self.config.FIVEMIN_TRADING_MODE,
                self.config.FIVEMIN_STARTING_BALANCE,
                self.config.FIVEMIN_ASSETS,
            )
        )
        self.running = True

    async def trading_loop(self) -> None:
        """Main loop: runs every ~1 second, evaluates signals within each 5-min window."""
        while self.running:
            try:
                now = time.time()
                current_window = compute_window_ts(int(now))
                seconds_elapsed = compute_seconds_elapsed(current_window, now)

                # Check for new window
                for asset, state in self.market_data.states.items():
                    if state.window_ts != current_window:
                        # Settle any pending trade from previous window
                        await self._settle_pending_trade(state.window_ts)
                        state.reset(current_window)
                        self._traded_this_window = False
                        log.info(f"New window: {current_window} for {asset}")

                # Skip if already traded this window
                if self._traded_this_window:
                    await asyncio.sleep(1)
                    continue

                # Fetch orderbooks periodically (every ~5s)
                if int(seconds_elapsed) % 5 == 0:
                    await self.market_data.fetch_orderbooks()

                # Evaluate signals for each asset
                signals = []
                for asset in self.config.FIVEMIN_ASSETS:
                    state = self.market_data.states.get(asset)
                    if state is None or state.current_price == 0:
                        continue
                    sig = self.signal_engine.evaluate(
                        asset, state.to_signal_dict(), seconds_elapsed
                    )
                    if sig is not None:
                        sig.timestamp = float(current_window)
                        signals.append(sig)

                # Pick best signal
                best = self.signal_engine.select_best(signals)
                if best is None:
                    await asyncio.sleep(1)
                    continue

                # Risk check
                can_trade = self.risk_manager.can_trade()
                if not can_trade["approved"]:
                    log.info(f"Trade blocked: {can_trade['reason']}")
                    if "consecutive" in can_trade["reason"].lower() or "cooldown" in can_trade["reason"].lower():
                        await self.notifier.send_message(
                            self.notifier.format_cooldown(
                                self.config.FIVEMIN_COOLDOWN_LOSSES,
                                self.config.FIVEMIN_COOLDOWN_MINUTES,
                            )
                        )
                    elif "daily" in can_trade["reason"].lower():
                        status = self.risk_manager.get_status()
                        await self.notifier.send_message(
                            self.notifier.format_daily_limit(-status["daily_pnl"])
                        )
                    await asyncio.sleep(1)
                    continue

                # Get ask price for the chosen direction
                ask_price = self._get_ask_price(best.asset, best.direction)
                if ask_price <= 0:
                    log.warning(f"No ask price for {best.asset} {best.direction}")
                    await asyncio.sleep(1)
                    continue

                # Price filter: skip if ask > $0.70 (bad risk/reward) or < $0.05 (no liquidity)
                if ask_price > 0.70 or ask_price < 0.05:
                    log.info(f"Skipping {best.asset} {best.direction}: ask ${ask_price:.2f} outside range [$0.05-$0.70]")
                    await asyncio.sleep(1)
                    continue

                # Position sizing: $5 for 3/3 agreement, $3 for 2/3
                agreeing = sum(1 for v in best.indicators.values()
                               if isinstance(v, dict) and v.get("direction") == best.direction)
                trade_amount = min(can_trade["max_amount"], 5.0 if agreeing >= 3 else 3.0)

                # Execute trade
                result = self.executor.execute(best, trade_amount, ask_price)
                if result["status"] == "filled":
                    self._traded_this_window = True
                    signal_info = {
                        "confidence": best.confidence,
                        "phase": best.phase,
                        "indicators": best.indicators,
                    }
                    await self.notifier.send_message(
                        self.notifier.format_trade_entry(result, signal_info)
                    )

                await asyncio.sleep(1)

            except Exception as e:
                log.error(f"Trading loop error: {e}")
                await asyncio.sleep(5)

    async def _settle_pending_trade(self, window_ts: int) -> None:
        """Settle the pending trade for a completed window."""
        pending = self.executor.get_pending_trade()
        if pending is None:
            return

        # Determine if UP or DOWN won
        state = self.market_data.states.get(pending["asset"])
        if state is None:
            return

        open_price = state.window_open_price
        close_price = state.current_price

        if open_price == 0 or close_price == 0:
            log.warning(f"Cannot settle: missing prices for {pending['asset']}")
            return

        # UP wins if close >= open
        up_won = close_price >= open_price
        trade_won = (pending["direction"] == "UP" and up_won) or \
                    (pending["direction"] == "DOWN" and not up_won)

        result = self.executor.settle(pending["id"], won=trade_won)
        self.risk_manager.record_trade_outcome(result["pnl"])

        status = self.risk_manager.get_status()
        await self.notifier.send_message(
            self.notifier.format_settlement(result, status)
        )

    def _get_ask_price(self, asset: str, direction: str) -> float:
        """Get the best ask price for the given direction from orderbook."""
        state = self.market_data.states.get(asset)
        if state is None:
            return 0.0

        if direction == "UP":
            book = state.orderbook_up
        else:
            book = state.orderbook_down

        asks = book.get("asks", [])
        if not asks:
            # Paper mode fallback: estimate from momentum delta
            if state.window_open_price > 0 and state.current_price > 0:
                delta = abs(state.current_price - state.window_open_price) / state.window_open_price
                return min(0.95, max(0.05, 0.50 + delta * 100))
            return 0.55  # default paper price

        return asks[0][0]

    def stop(self) -> None:
        log.info("Stopping PolyBot 5M...")
        self.running = False
        self.market_data.stop()

    async def run(self) -> None:
        await self.startup()
        tasks = [
            asyncio.create_task(self.trading_loop()),
            asyncio.create_task(self.market_data.start_binance_feeds()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            if self.notifier:
                await self.notifier.send_message(self.notifier.format_shutdown())
            log.info("PolyBot 5M stopped")


def main():
    parser = argparse.ArgumentParser(description="PolyBot 5M - 5-Minute Prediction Market Bot")
    parser.add_argument(
        "--mode", choices=["paper", "live"], default=None,
        help="Trading mode (overrides .env)",
    )
    args = parser.parse_args()

    config = Config()
    if args.mode:
        config.FIVEMIN_TRADING_MODE = args.mode

    bot = PolyBot5M(config)

    def signal_handler(sig, frame):
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
