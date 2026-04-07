import asyncio
import argparse
import json
import os
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
        self.notifier = FiveMinNotifier(config)
        self.exchange = None
        self.executor = None  # initialized after exchange setup
        self._traded_this_window = False

    async def startup(self) -> None:
        log.info(f"Starting PolyBot 5M in {self.config.FIVEMIN_TRADING_MODE} mode")
        init_fivemin_db(self.config.FIVEMIN_DB_PATH)
        self.risk_manager.init_portfolio(self.config.FIVEMIN_STARTING_BALANCE)

        # Init PMXT exchange (needed for live trading)
        if self.config.FIVEMIN_TRADING_MODE == "live":
            try:
                import pmxt
                self.exchange = pmxt.Polymarket({
                    "privateKey": self.config.PRIVATE_KEY,
                    "proxyAddress": self.config.POLYMARKET_PROXY_ADDRESS,
                })
                log.info("PMXT exchange connected (LIVE MODE)")
            except Exception as e:
                log.error(f"PMXT init failed — cannot trade live: {e}")
                log.info("Falling back to paper mode")
                self.config.FIVEMIN_TRADING_MODE = "paper"
                self.exchange = None
        else:
            self.exchange = None

        self.executor = FiveMinTradeExecutor(self.config, self.exchange)

        # Init market states
        window_ts = compute_window_ts(int(time.time()))
        self.market_data.init_states(window_ts)

        # Startup message — only log, don't spam Telegram
        log.info(
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
                signal_display = []
                for asset in self.config.FIVEMIN_ASSETS:
                    state = self.market_data.states.get(asset)
                    if state is None or state.current_price == 0:
                        signal_display.append({"asset": asset, "momentum": "", "orderbook": "", "volume": "", "signal": "", "confidence": 0})
                        continue

                    sd = state.to_signal_dict()
                    sig = self.signal_engine.evaluate(asset, sd, seconds_elapsed)

                    # Build display data from indicators
                    from fivemin_modules.indicators import calc_momentum, calc_orderbook_imbalance, calc_volume_spike
                    mom = calc_momentum(sd["current_price"], sd["window_open_price"])
                    imb = calc_orderbook_imbalance(sd["orderbook_up"], sd["orderbook_down"])
                    pd_val = (sd["current_price"] - sd["window_open_price"]) / sd["window_open_price"] if sd["window_open_price"] > 0 else 0
                    vol = calc_volume_spike(sd["volumes"], pd_val)

                    entry = {
                        "asset": asset,
                        "momentum": mom.direction,
                        "orderbook": imb.direction,
                        "volume": vol.direction,
                        "signal": sig.direction if sig else "",
                        "agree_count": sum(1 for i in [mom, imb, vol] if sig and i.direction == sig.direction) if sig else 0,
                        "confidence": sig.confidence if sig else 0,
                    }
                    signal_display.append(entry)

                    if sig is not None:
                        sig.timestamp = float(current_window)
                        signals.append(sig)

                # Write state file for dashboard
                self._write_state(signal_display)

                # Pick best signal
                best = self.signal_engine.select_best(signals)
                if best is None:
                    await asyncio.sleep(1)
                    continue

                # Risk check
                can_trade = self.risk_manager.can_trade()
                if not can_trade["approved"]:
                    log.info(f"Trade blocked: {can_trade['reason']}")
                    await asyncio.sleep(1)
                    continue

                # Get ask price for the chosen direction
                ask_price = self._get_ask_price(best.asset, best.direction)
                if ask_price <= 0:
                    log.warning(f"No ask price for {best.asset} {best.direction}")
                    await asyncio.sleep(1)
                    continue

                # Price filter: only for paper mode (live uses limit orders at fair price)
                if self.config.FIVEMIN_TRADING_MODE == "paper":
                    if ask_price > 0.70 or ask_price < 0.05:
                        log.info(f"Skipping {best.asset} {best.direction}: ask ${ask_price:.2f} outside range [$0.05-$0.70]")
                        await asyncio.sleep(1)
                        continue

                # Position sizing: confidence-scaled $3-$10 (Stage 1)
                agreeing = sum(1 for v in best.indicators.values()
                               if isinstance(v, dict) and v.get("direction") == best.direction)
                trade_amount = self.risk_manager.calc_position_size_for_signal(
                    score=agreeing,
                    confidence=best.confidence,
                )
                trade_amount = min(trade_amount, can_trade["max_amount"])
                if trade_amount <= 0:
                    log.info(f"Skipping {best.asset} {best.direction}: signal too weak for sizing")
                    await asyncio.sleep(1)
                    continue

                # Get token ID for live trading
                state = self.market_data.states.get(best.asset)
                token_id = ""
                if state:
                    token_id = state.token_id_up if best.direction == "UP" else state.token_id_down

                # Execute trade
                result = self.executor.execute(best, trade_amount, ask_price, token_id=token_id)
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

    def _write_state(self, signal_display: list[dict]) -> None:
        """Write current state to JSON file for dashboard to read."""
        try:
            # Find best signal's orderbook
            best_asset = "BTC"
            best_ob = {"bids": [], "asks": []}
            best_conf = 0
            for s in signal_display:
                if s.get("confidence", 0) > best_conf:
                    best_conf = s["confidence"]
                    best_asset = s["asset"]

            state = self.market_data.states.get(best_asset)
            if state:
                best_ob = {
                    "bids": [(p, s) for p, s in state.orderbook_up.get("bids", [])[:5]],
                    "asks": [(p, s) for p, s in state.orderbook_up.get("asks", [])[:5]],
                }

            state_data = {
                "signals": signal_display,
                "orderbook": best_ob,
                "orderbook_asset": best_asset,
                "timestamp": time.time(),
            }
            state_path = os.path.join(os.path.dirname(self.config.FIVEMIN_DB_PATH), "polybot5m_state.json")
            with open(state_path, "w") as f:
                json.dump(state_data, f)
        except Exception:
            pass

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
                log.info("PolyBot 5M shutdown")
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
