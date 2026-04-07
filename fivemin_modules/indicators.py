from dataclasses import dataclass


@dataclass
class IndicatorResult:
    direction: str   # "UP", "DOWN", "NEUTRAL"
    confidence: float  # 0.0 - 1.0


def calc_momentum(current_price: float, window_open_price: float) -> IndicatorResult:
    """Binance price momentum within the 5-min window.
    delta >= 0.02% -> UP, <= -0.02% -> DOWN, else NEUTRAL.
    Confidence scales linearly from 0.02% to 0.15% (mapped to 0.3-1.0).
    """
    if window_open_price == 0:
        return IndicatorResult("NEUTRAL", 0.0)

    delta = (current_price - window_open_price) / window_open_price
    abs_delta = abs(delta)

    if abs_delta < 0.0002:  # 0.02%
        return IndicatorResult("NEUTRAL", 0.0)

    direction = "UP" if delta > 0 else "DOWN"
    confidence = min(1.0, 0.3 + (abs_delta - 0.0002) / (0.0015 - 0.0002) * 0.7)
    return IndicatorResult(direction, round(confidence, 4))


def calc_orderbook_imbalance(orderbook_up: dict, orderbook_down: dict) -> IndicatorResult:
    """Polymarket orderbook imbalance analysis.
    UP signal: UP book has strong bid-side imbalance.
    DOWN signal: DOWN book has strong bid-side imbalance.
    """
    up_score = _score_book(orderbook_up)
    down_score = _score_book(orderbook_down)

    if up_score == 0 and down_score == 0:
        return IndicatorResult("NEUTRAL", 0.0)

    diff = up_score - down_score

    if abs(diff) < 0.1:
        return IndicatorResult("NEUTRAL", 0.0)

    direction = "UP" if diff > 0 else "DOWN"
    confidence = min(1.0, abs(diff))
    return IndicatorResult(direction, round(confidence, 4))


def _score_book(book: dict) -> float:
    """Score a single orderbook side. Higher = more buy pressure."""
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if not bids or not asks:
        return 0.0

    sum_bid_size = sum(size for _, size in bids)
    sum_ask_size = sum(size for _, size in asks)
    total = sum_bid_size + sum_ask_size

    if total == 0:
        return 0.0

    imbalance = (sum_bid_size - sum_ask_size) / total
    best_bid_price, best_bid_size = bids[0]
    best_ask_price, best_ask_size = asks[0]
    denom = best_bid_size + best_ask_size
    if denom > 0:
        microprice = (best_ask_price * best_bid_size + best_bid_price * best_ask_size) / denom
    else:
        microprice = (best_bid_price + best_ask_price) / 2
    midpoint = (best_bid_price + best_ask_price) / 2

    top2_bid = sum(size for _, size in bids[:2])
    bid_slope = top2_bid / sum_bid_size if sum_bid_size > 0 else 0

    score = 0.0
    if imbalance > 0.15:
        score += imbalance
    if microprice > midpoint:
        score += 0.2
    if bid_slope > 0.5:
        score += 0.2

    return score


def calc_volume_spike(volumes: list[float], price_delta: float) -> IndicatorResult:
    """Binance volume spike detection.
    Spike = current volume / 30s moving average > 2.0.
    Confirms direction only if price is also moving.
    """
    if len(volumes) < 2:
        return IndicatorResult("NEUTRAL", 0.0)

    current_vol = volumes[-1]
    history = volumes[:-1]

    if not history:
        return IndicatorResult("NEUTRAL", 0.0)

    vol_ma = sum(history) / len(history)

    if vol_ma == 0:
        return IndicatorResult("NEUTRAL", 0.0)

    spike_ratio = current_vol / vol_ma

    if spike_ratio < 2.0:
        return IndicatorResult("NEUTRAL", 0.0)

    if price_delta == 0:
        return IndicatorResult("NEUTRAL", 0.0)

    direction = "UP" if price_delta > 0 else "DOWN"
    confidence = min(1.0, 0.4 + (spike_ratio - 2.0) / (5.0 - 2.0) * 0.6)
    return IndicatorResult(direction, round(confidence, 4))


def _trend_at(price_history, seconds_back: int):
    """Compute price delta over the last `seconds_back` data points.

    price_history is a deque of prices sampled at ~1Hz.
    Returns None if not enough data, otherwise (current - past).
    """
    if len(price_history) < seconds_back + 1:
        return None
    history_list = list(price_history)
    current = history_list[-1]
    past = history_list[-seconds_back - 1]
    return current - past


def trends_align(price_history, direction: str) -> bool:
    """Check that 30s, 2m, and 5m trends all point the same direction.

    price_history: deque of prices (~1 sample per second)
    direction: "UP" or "DOWN"

    Returns True only when:
      - We have at least 301 data points (5 minutes of history)
      - All three trends are non-zero
      - All three trends match the requested direction
    """
    t30 = _trend_at(price_history, 30)
    t2m = _trend_at(price_history, 120)
    t5m = _trend_at(price_history, 300)

    if t30 is None or t2m is None or t5m is None:
        return False

    if direction == "UP":
        return t30 > 0 and t2m > 0 and t5m > 0
    elif direction == "DOWN":
        return t30 < 0 and t2m < 0 and t5m < 0
    return False
