import pytest
from fivemin_modules.indicators import (
    calc_momentum,
    calc_orderbook_imbalance,
    calc_volume_spike,
    IndicatorResult,
)


class TestMomentum:
    def test_up_signal(self):
        result = calc_momentum(current_price=100.05, window_open_price=100.00)
        assert result.direction == "UP"
        assert result.confidence > 0.0

    def test_down_signal(self):
        result = calc_momentum(current_price=99.95, window_open_price=100.00)
        assert result.direction == "DOWN"
        assert result.confidence > 0.0

    def test_neutral_small_delta(self):
        result = calc_momentum(current_price=100.01, window_open_price=100.00)
        assert result.direction == "NEUTRAL"
        assert result.confidence == 0.0

    def test_high_confidence_large_delta(self):
        result = calc_momentum(current_price=100.20, window_open_price=100.00)
        assert result.direction == "UP"
        assert result.confidence >= 0.8

    def test_zero_open_price_returns_neutral(self):
        result = calc_momentum(current_price=100.0, window_open_price=0.0)
        assert result.direction == "NEUTRAL"


class TestOrderbookImbalance:
    def test_up_imbalance(self):
        orderbook_up = {
            "bids": [(0.55, 100), (0.54, 80), (0.53, 60), (0.52, 40), (0.51, 30)],
            "asks": [(0.56, 20), (0.57, 15), (0.58, 10), (0.59, 10), (0.60, 5)],
        }
        orderbook_down = {
            "bids": [(0.44, 20), (0.43, 15), (0.42, 10), (0.41, 10), (0.40, 5)],
            "asks": [(0.45, 100), (0.46, 80), (0.47, 60), (0.48, 40), (0.49, 30)],
        }
        result = calc_orderbook_imbalance(orderbook_up, orderbook_down)
        assert result.direction == "UP"
        assert result.confidence > 0.0

    def test_down_imbalance(self):
        orderbook_up = {
            "bids": [(0.44, 20), (0.43, 15), (0.42, 10), (0.41, 10), (0.40, 5)],
            "asks": [(0.45, 100), (0.46, 80), (0.47, 60), (0.48, 40), (0.49, 30)],
        }
        orderbook_down = {
            "bids": [(0.55, 100), (0.54, 80), (0.53, 60), (0.52, 40), (0.51, 30)],
            "asks": [(0.56, 20), (0.57, 15), (0.58, 10), (0.59, 10), (0.60, 5)],
        }
        result = calc_orderbook_imbalance(orderbook_up, orderbook_down)
        assert result.direction == "DOWN"
        assert result.confidence > 0.0

    def test_empty_orderbook_returns_neutral(self):
        empty = {"bids": [], "asks": []}
        result = calc_orderbook_imbalance(empty, empty)
        assert result.direction == "NEUTRAL"
        assert result.confidence == 0.0

    def test_balanced_orderbook_neutral(self):
        balanced = {
            "bids": [(0.50, 50), (0.49, 50), (0.48, 50), (0.47, 50), (0.46, 50)],
            "asks": [(0.51, 50), (0.52, 50), (0.53, 50), (0.54, 50), (0.55, 50)],
        }
        result = calc_orderbook_imbalance(balanced, balanced)
        assert result.direction == "NEUTRAL"


class TestVolumeSpike:
    def test_spike_with_up_move(self):
        volumes = [10.0] * 29 + [25.0]
        price_delta = 0.001
        result = calc_volume_spike(volumes, price_delta)
        assert result.direction == "UP"
        assert result.confidence > 0.0

    def test_spike_with_down_move(self):
        volumes = [10.0] * 29 + [25.0]
        price_delta = -0.001
        result = calc_volume_spike(volumes, price_delta)
        assert result.direction == "DOWN"
        assert result.confidence > 0.0

    def test_spike_without_direction_neutral(self):
        volumes = [10.0] * 29 + [25.0]
        price_delta = 0.0
        result = calc_volume_spike(volumes, price_delta)
        assert result.direction == "NEUTRAL"

    def test_no_spike_neutral(self):
        volumes = [10.0] * 30
        price_delta = 0.001
        result = calc_volume_spike(volumes, price_delta)
        assert result.direction == "NEUTRAL"

    def test_empty_volumes_neutral(self):
        result = calc_volume_spike([], 0.001)
        assert result.direction == "NEUTRAL"
        assert result.confidence == 0.0

    def test_single_volume_neutral(self):
        result = calc_volume_spike([10.0], 0.001)
        assert result.direction == "NEUTRAL"
        assert result.confidence == 0.0
