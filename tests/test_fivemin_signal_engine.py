import pytest
from collections import deque
from fivemin_modules.signal_engine import FiveMinSignalEngine, Signal
from fivemin_modules.indicators import IndicatorResult
from config import Config


@pytest.fixture
def engine():
    return FiveMinSignalEngine(Config())


def _make_market_state(
    current_price=100.05,
    window_open_price=100.00,
    volumes=None,
    orderbook_up=None,
    orderbook_down=None,
    price_history=None,
):
    if volumes is None:
        volumes = [10.0] * 30
    if orderbook_up is None:
        orderbook_up = {
            "bids": [(0.55, 100), (0.54, 80), (0.53, 60), (0.52, 40), (0.51, 30)],
            "asks": [(0.56, 20), (0.57, 15), (0.58, 10), (0.59, 10), (0.60, 5)],
        }
    if orderbook_down is None:
        orderbook_down = {
            "bids": [(0.44, 20), (0.43, 15), (0.42, 10), (0.41, 10), (0.40, 5)],
            "asks": [(0.45, 100), (0.46, 80), (0.47, 60), (0.48, 40), (0.49, 30)],
        }
    if price_history is None:
        price_history = deque([100.0 + i * 0.05 for i in range(350)], maxlen=350)
    return {
        "current_price": current_price,
        "window_open_price": window_open_price,
        "volumes": volumes,
        "orderbook_up": orderbook_up,
        "orderbook_down": orderbook_down,
        "price_history": price_history,
    }


class TestEvaluate:
    def test_strong_up_signal_early_phase(self, engine):
        """All 3 agree UP + high confidence -> signal in early phase."""
        state = _make_market_state(
            current_price=100.20,
            volumes=[10.0] * 29 + [30.0],
        )
        signal = engine.evaluate("BTC", state, seconds_elapsed=60)
        assert signal is not None
        assert signal.direction == "UP"
        assert signal.phase == "early"

    def test_two_of_three_mid_phase(self, engine):
        """2-of-3 agree in mid phase with moderate confidence."""
        state = _make_market_state(
            current_price=100.05,
            volumes=[10.0] * 30,
        )
        signal = engine.evaluate("BTC", state, seconds_elapsed=150)
        if signal is not None:
            assert signal.direction == "UP"
            assert signal.phase == "mid"

    def test_no_signal_in_cutoff(self, engine):
        """No signals in last 10 seconds."""
        state = _make_market_state(current_price=100.20)
        signal = engine.evaluate("BTC", state, seconds_elapsed=295)
        assert signal is None

    def test_neutral_when_disagreement(self, engine):
        """No signal when indicators disagree."""
        state = _make_market_state(
            current_price=100.01,
            volumes=[10.0] * 30,
            orderbook_up={"bids": [(0.50, 50)], "asks": [(0.51, 50)]},
            orderbook_down={"bids": [(0.50, 50)], "asks": [(0.51, 50)]},
        )
        signal = engine.evaluate("BTC", state, seconds_elapsed=150)
        assert signal is None


class TestSelectBestAsset:
    def test_picks_highest_confidence(self, engine):
        signals = [
            Signal("BTC", "UP", 0.65, "mid", {}, 0.0),
            Signal("ETH", "UP", 0.80, "mid", {}, 0.0),
            Signal("SOL", "DOWN", 0.55, "mid", {}, 0.0),
        ]
        best = engine.select_best(signals)
        assert best.asset == "ETH"
        assert best.confidence == 0.80

    def test_returns_none_for_empty(self, engine):
        assert engine.select_best([]) is None
