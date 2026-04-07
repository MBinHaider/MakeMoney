import pytest
from collections import deque
from fivemin_modules.indicators import trends_align


def test_all_three_trends_up_aligned():
    """Steadily rising prices: all 3 trends should agree on UP."""
    prices = [100.0 + i * 0.1 for i in range(350)]  # 100.0 → 134.9
    history = deque(prices, maxlen=350)
    assert trends_align(history, "UP") is True
    assert trends_align(history, "DOWN") is False


def test_all_three_trends_down_aligned():
    """Steadily falling prices: all 3 trends should agree on DOWN."""
    prices = [200.0 - i * 0.1 for i in range(350)]
    history = deque(prices, maxlen=350)
    assert trends_align(history, "DOWN") is True
    assert trends_align(history, "UP") is False


def test_mixed_trends_returns_false():
    """30s up, 2m down, 5m flat: should NOT align."""
    prices = []
    prices += [100.0] * 50
    for i in range(180):
        prices.append(100.0 + (i / 180) * 10)
    for i in range(90):
        prices.append(110.0 - (i / 90) * 5)
    for i in range(30):
        prices.append(105.0 + (i / 30) * 1)
    history = deque(prices, maxlen=350)
    assert trends_align(history, "UP") is False
    assert trends_align(history, "DOWN") is False


def test_insufficient_history_returns_false():
    """Less than 300 data points: cannot evaluate 5m trend, return False."""
    history = deque([100.0] * 50, maxlen=350)
    assert trends_align(history, "UP") is False
    assert trends_align(history, "DOWN") is False


def test_flat_prices_returns_false():
    """Perfectly flat prices: no trend in any direction."""
    history = deque([100.0] * 350, maxlen=350)
    assert trends_align(history, "UP") is False
    assert trends_align(history, "DOWN") is False
