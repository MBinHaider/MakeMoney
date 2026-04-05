import pytest
import time
from fivemin_modules.market_data import (
    MarketState,
    compute_window_ts,
    compute_seconds_elapsed,
    compute_market_slug,
)


class TestWindowTimestamp:
    def test_aligns_to_300(self):
        ts = compute_window_ts(1700000123)
        assert ts % 300 == 0
        assert ts == 1700000100

    def test_exact_boundary(self):
        ts = compute_window_ts(1700000100)
        assert ts == 1700000100

    def test_just_before_boundary(self):
        ts = compute_window_ts(1700000399)
        assert ts == 1700000100


class TestSecondsElapsed:
    def test_calculates_correctly(self):
        window_ts = 1700000100
        now = 1700000220.0
        assert compute_seconds_elapsed(window_ts, now) == 120.0

    def test_at_start(self):
        window_ts = 1700000100
        assert compute_seconds_elapsed(window_ts, float(window_ts)) == 0.0


class TestMarketSlug:
    def test_btc_slug(self):
        slug = compute_market_slug("BTC", 1700000100)
        assert slug == "btc-updown-5m-1700000100"

    def test_eth_slug(self):
        slug = compute_market_slug("ETH", 1700000100)
        assert slug == "eth-updown-5m-1700000100"

    def test_sol_slug(self):
        slug = compute_market_slug("SOL", 1700000100)
        assert slug == "sol-updown-5m-1700000100"


class TestMarketState:
    def test_initial_state(self):
        state = MarketState(asset="BTC", window_ts=1700000100)
        assert state.asset == "BTC"
        assert state.window_open_price == 0.0
        assert state.current_price == 0.0
        assert len(state.volumes) == 0
        assert len(state.price_history) == 0

    def test_reset(self):
        state = MarketState(asset="BTC", window_ts=1700000100)
        state.current_price = 100.0
        state.window_open_price = 99.0
        state.volumes.append(10.0)
        state.reset(1700000400)
        assert state.window_ts == 1700000400
        assert state.current_price == 0.0
        assert state.window_open_price == 0.0
        assert len(state.volumes) == 0

    def test_to_signal_dict(self):
        state = MarketState(asset="BTC", window_ts=1700000100)
        state.current_price = 100.05
        state.window_open_price = 100.00
        state.orderbook_up = {"bids": [(0.55, 100)], "asks": [(0.56, 50)]}
        state.orderbook_down = {"bids": [(0.44, 50)], "asks": [(0.45, 100)]}
        d = state.to_signal_dict()
        assert d["current_price"] == 100.05
        assert d["window_open_price"] == 100.00
        assert "orderbook_up" in d
        assert "orderbook_down" in d
        assert "volumes" in d
