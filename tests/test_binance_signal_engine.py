import pytest
from binance_modules.signal_engine import SignalEngine
from config import Config


@pytest.fixture
def engine():
    return SignalEngine(Config())


class TestSignalGeneration:
    def test_strong_buy_all_three_agree(self, engine):
        indicators_1m = {
            "rsi": 25, "macd_histogram": 0.5,
            "bb_lower": 100, "bb_mid": 105, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 35, "macd_histogram": 0.3,
            "bb_lower": 99, "bb_mid": 104, "bb_upper": 109,
            "macd": 0.8, "macd_signal": 0.5,
        }
        current_price = 99.5  # below BB lower band
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "buy"
        assert signal["strength"] == "strong"
        assert signal["score"] == 3

    def test_normal_buy_two_of_three(self, engine):
        indicators_1m = {
            "rsi": 25, "macd_histogram": 0.5,
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 40, "macd_histogram": 0.2,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": 0.5, "macd_signal": 0.3,
        }
        current_price = 95.0  # not at BB lower
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "buy"
        assert signal["strength"] == "normal"
        assert signal["score"] == 2

    def test_hold_when_only_one_indicator(self, engine):
        indicators_1m = {
            "rsi": 25, "macd_histogram": -0.5,
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": -1.0, "macd_signal": -0.5,
        }
        indicators_5m = {
            "rsi": 50, "macd_histogram": -0.2,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -0.5, "macd_signal": -0.3,
        }
        current_price = 100.0
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "hold"

    def test_hold_when_5m_trend_bearish(self, engine):
        indicators_1m = {
            "rsi": 25, "macd_histogram": 0.5,
            "bb_lower": 100, "bb_mid": 105, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 75, "macd_histogram": -2.0,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -1.0, "macd_signal": 1.0,
        }
        current_price = 99.5
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "hold"

    def test_sell_signal_overbought(self, engine):
        indicators_1m = {
            "rsi": 75, "macd_histogram": -0.5,
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": -1.0, "macd_signal": -0.5,
        }
        indicators_5m = {
            "rsi": 65, "macd_histogram": -0.3,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -0.5, "macd_signal": -0.3,
        }
        current_price = 111.0  # above BB upper
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "sell"

    def test_returns_none_indicators(self, engine):
        indicators_1m = {
            "rsi": None, "macd_histogram": None,
            "bb_lower": None, "bb_mid": None, "bb_upper": None,
            "macd": None, "macd_signal": None,
        }
        indicators_5m = {
            "rsi": None, "macd_histogram": None,
            "bb_lower": None, "bb_mid": None, "bb_upper": None,
            "macd": None, "macd_signal": None,
        }
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, 100.0)
        assert signal["action"] == "hold"
