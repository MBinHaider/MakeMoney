"""Hand-rolled technical indicators. No external dependencies."""

import math


def compute_rsi(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None

    closes = [c["close"] for c in candles]
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for i in range(1, len(values)):
        ema_values.append(values[i] * multiplier + ema_values[-1] * (1 - multiplier))
    return ema_values


def compute_macd(
    candles: list[dict],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[float | None, float | None, float | None]:
    if len(candles) < slow + signal_period:
        return (None, None, None)

    closes = [c["close"] for c in candles]
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)

    macd_line_values = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_values = _ema(macd_line_values[slow - 1:], signal_period)

    if not signal_values:
        return (None, None, None)

    macd_line = macd_line_values[-1]
    signal_line = signal_values[-1]
    histogram = macd_line - signal_line

    return (macd_line, signal_line, histogram)


def compute_bollinger_bands(
    candles: list[dict],
    period: int = 20,
    num_std: int = 2,
) -> tuple[float | None, float | None, float | None]:
    if len(candles) < period:
        return (None, None, None)

    closes = [c["close"] for c in candles[-period:]]
    mid = sum(closes) / len(closes)
    variance = sum((c - mid) ** 2 for c in closes) / len(closes)
    std = math.sqrt(variance)

    upper = mid + num_std * std
    lower = mid - num_std * std

    return (upper, mid, lower)


def compute_all(candles: list[dict]) -> dict:
    rsi = compute_rsi(candles, period=14)
    macd_line, macd_signal, macd_histogram = compute_macd(candles)
    bb_upper, bb_mid, bb_lower = compute_bollinger_bands(candles)

    return {
        "rsi": rsi,
        "macd": macd_line,
        "macd_signal": macd_signal,
        "macd_histogram": macd_histogram,
        "bb_upper": bb_upper,
        "bb_mid": bb_mid,
        "bb_lower": bb_lower,
    }
