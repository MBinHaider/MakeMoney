from utils.logger import get_logger
from config import Config

log = get_logger("binance_signal_engine")


class SignalEngine:
    def __init__(self, config: Config):
        self.config = config

    def _count_buy_signals(self, indicators: dict, current_price: float) -> int:
        count = 0
        rsi = indicators.get("rsi")
        if rsi is not None and rsi < 30:
            count += 1
        histogram = indicators.get("macd_histogram")
        if histogram is not None and histogram > 0:
            count += 1
        bb_lower = indicators.get("bb_lower")
        if bb_lower is not None and current_price <= bb_lower:
            count += 1
        return count

    def _count_sell_signals(self, indicators: dict, current_price: float) -> int:
        count = 0
        rsi = indicators.get("rsi")
        if rsi is not None and rsi > 70:
            count += 1
        histogram = indicators.get("macd_histogram")
        if histogram is not None and histogram < 0:
            count += 1
        bb_upper = indicators.get("bb_upper")
        if bb_upper is not None and current_price >= bb_upper:
            count += 1
        return count

    def _is_5m_bearish(self, indicators_5m: dict) -> bool:
        rsi = indicators_5m.get("rsi")
        histogram = indicators_5m.get("macd_histogram")
        if rsi is not None and rsi > 70 and histogram is not None and histogram < 0:
            return True
        return False

    def _is_5m_bullish_or_neutral(self, indicators_5m: dict) -> bool:
        return not self._is_5m_bearish(indicators_5m)

    def evaluate(self, symbol, indicators_1m, indicators_5m, current_price) -> dict:
        buy_count_1m = self._count_buy_signals(indicators_1m, current_price)
        sell_count_1m = self._count_sell_signals(indicators_1m, current_price)

        if buy_count_1m >= 2 and self._is_5m_bullish_or_neutral(indicators_5m):
            strength = "strong" if buy_count_1m == 3 else "normal"
            log.info(f"{symbol} BUY signal: {buy_count_1m}/3 indicators, strength={strength}")
            return {
                "action": "buy", "strength": strength, "score": buy_count_1m,
                "symbol": symbol, "price": current_price,
                "indicators_1m": indicators_1m, "indicators_5m": indicators_5m,
            }

        if sell_count_1m >= 2:
            strength = "strong" if sell_count_1m == 3 else "normal"
            log.info(f"{symbol} SELL signal: {sell_count_1m}/3 indicators, strength={strength}")
            return {
                "action": "sell", "strength": strength, "score": sell_count_1m,
                "symbol": symbol, "price": current_price,
                "indicators_1m": indicators_1m, "indicators_5m": indicators_5m,
            }

        return {
            "action": "hold", "strength": "none", "score": 0,
            "symbol": symbol, "price": current_price,
            "indicators_1m": indicators_1m, "indicators_5m": indicators_5m,
        }
