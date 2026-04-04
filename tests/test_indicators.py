import pytest
from binance_modules.indicators import compute_rsi, compute_macd, compute_bollinger_bands, compute_all


def _make_closes(values: list[float]) -> list[dict]:
    return [{"close": v} for v in values]


class TestRSI:
    def test_rsi_with_all_gains(self):
        closes = _make_closes([float(i) for i in range(1, 16)])
        rsi = compute_rsi(closes, period=14)
        assert rsi > 95

    def test_rsi_with_all_losses(self):
        closes = _make_closes([float(i) for i in range(15, 0, -1)])
        rsi = compute_rsi(closes, period=14)
        assert rsi < 5

    def test_rsi_with_mixed_data(self):
        closes = _make_closes([100, 101, 100, 101, 100, 101, 100, 101,
                               100, 101, 100, 101, 100, 101, 100])
        rsi = compute_rsi(closes, period=14)
        assert 40 < rsi < 60

    def test_rsi_insufficient_data(self):
        closes = _make_closes([100, 101, 102])
        rsi = compute_rsi(closes, period=14)
        assert rsi is None


class TestMACD:
    def test_macd_bullish_trend(self):
        closes = _make_closes([float(100 + i * 2) for i in range(35)])
        macd_line, signal_line, histogram = compute_macd(closes)
        assert macd_line is not None
        assert histogram > 0

    def test_macd_bearish_trend(self):
        closes = _make_closes([float(200 - i * 2) for i in range(35)])
        macd_line, signal_line, histogram = compute_macd(closes)
        assert histogram < 0

    def test_macd_insufficient_data(self):
        closes = _make_closes([100, 101, 102])
        result = compute_macd(closes)
        assert result == (None, None, None)


class TestBollingerBands:
    def test_bb_basic(self):
        closes = _make_closes([100.0] * 25)
        upper, mid, lower = compute_bollinger_bands(closes, period=20, num_std=2)
        assert mid == pytest.approx(100.0)
        assert upper == pytest.approx(100.0)
        assert lower == pytest.approx(100.0)

    def test_bb_with_volatility(self):
        closes = _make_closes([100, 110, 90, 110, 90, 100, 110, 90, 110, 90,
                               100, 110, 90, 110, 90, 100, 110, 90, 110, 90,
                               100, 110, 90, 110, 100])
        upper, mid, lower = compute_bollinger_bands(closes, period=20, num_std=2)
        assert upper > mid > lower
        assert upper - lower > 10

    def test_bb_insufficient_data(self):
        closes = _make_closes([100, 101])
        result = compute_bollinger_bands(closes, period=20, num_std=2)
        assert result == (None, None, None)


class TestComputeAll:
    def test_compute_all_returns_all_indicators(self):
        closes = _make_closes([100 + i * 0.5 for i in range(40)])
        result = compute_all(closes)
        assert "rsi" in result
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result
        assert "bb_upper" in result
        assert "bb_mid" in result
        assert "bb_lower" in result
        assert result["rsi"] is not None
        assert result["macd"] is not None
