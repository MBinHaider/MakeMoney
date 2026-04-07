import pytest
from collections import deque
from fivemin_modules.signal_engine import FiveMinSignalEngine
from config import Config


@pytest.fixture
def engine():
    return FiveMinSignalEngine(Config())


def _build_state(price_history, current_price, window_open):
    """Build a state dict matching what signal_engine.evaluate expects.

    Volumes include a 3x spike on the last bar so volume indicator fires UP
    when price_delta > 0, giving 3/3 indicator agreement in early phase.
    """
    return {
        "current_price": current_price,
        "window_open_price": window_open,
        "volumes": [100.0] * 59 + [300.0],
        "orderbook_up": {
            "bids": [(0.50, 100), (0.49, 100)],
            "asks": [(0.55, 100), (0.56, 100)],
        },
        "orderbook_down": {
            "bids": [(0.45, 100), (0.44, 100)],
            "asks": [(0.50, 100), (0.51, 100)],
        },
        "price_history": price_history,
    }


def test_signal_blocked_when_trends_misaligned(engine):
    """Strong UP indicators but trends are flat: signal should NOT fire."""
    flat_history = deque([100.0] * 350, maxlen=350)
    state = _build_state(flat_history, current_price=105.0, window_open=100.0)
    state["orderbook_up"] = {
        "bids": [(0.50, 5000), (0.49, 5000)],
        "asks": [(0.55, 100)],
    }
    state["orderbook_down"] = {
        "bids": [(0.45, 100)],
        "asks": [(0.50, 5000), (0.51, 5000)],
    }
    signal = engine.evaluate("BTC", state, seconds_elapsed=60)
    assert signal is None, "Trend not aligned, signal should be blocked"


def test_signal_fires_when_trends_aligned_up(engine):
    """Strong UP indicators AND aligned uptrend: signal should fire."""
    rising = deque([100.0 + i * 0.05 for i in range(350)], maxlen=350)
    state = _build_state(rising, current_price=117.45, window_open=100.0)
    state["orderbook_up"] = {
        "bids": [(0.50, 5000), (0.49, 5000)],
        "asks": [(0.55, 100)],
    }
    state["orderbook_down"] = {
        "bids": [(0.45, 100)],
        "asks": [(0.50, 5000), (0.51, 5000)],
    }
    signal = engine.evaluate("BTC", state, seconds_elapsed=60)
    assert signal is not None
    assert signal.direction == "UP"


def test_trend_check_can_be_disabled(engine):
    """When config.FIVEMIN_TREND_REQUIRE_ALIGN is False, trends are not checked."""
    engine.config.FIVEMIN_TREND_REQUIRE_ALIGN = False
    flat_history = deque([100.0] * 350, maxlen=350)
    state = _build_state(flat_history, current_price=105.0, window_open=100.0)
    state["orderbook_up"] = {
        "bids": [(0.50, 5000), (0.49, 5000)],
        "asks": [(0.55, 100)],
    }
    state["orderbook_down"] = {
        "bids": [(0.45, 100)],
        "asks": [(0.50, 5000), (0.51, 5000)],
    }
    signal = engine.evaluate("BTC", state, seconds_elapsed=60)
    assert signal is not None
    engine.config.FIVEMIN_TREND_REQUIRE_ALIGN = True
