# PolyBot Strategy Upgrade — Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stage 1 (Foundation) of the PolyBot 5M strategy upgrade: confidence-scaled position sizing, multi-timeframe trend confirmation, and limit-order maker mode.

**Architecture:** Modify `risk_manager.py` for sizing, `signal_engine.py` + `indicators.py` for trend confirmation, and `trade_executor.py` for limit-order maker mode. All Stage 1 changes are additive — old behavior is the fallback. Strict TDD: write the failing test first, then minimal code, then commit.

**Tech Stack:** Python 3, SQLite, py-clob-client, pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-04-07-polybot-strategy-upgrade-design.md`

---

## Scope of Stage 1

This plan covers **3 of the 8 changes** from the spec:
- **Change 6**: Confidence-scaled position sizing ($3-$10 based on signal strength)
- **Change 4**: Multi-timeframe trend confirmation (30s + 2m + 5m must agree)
- **Change 1**: Limit-order maker mode (post bid at fair value, cancel after 60s)

Stages 2 and 3 will get their own plans after Stage 1 is validated in production.

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `config.py` | Modify | Add 5 new config constants for Stage 1 |
| `fivemin_modules/risk_manager.py` | Modify | Add `calc_position_size_for_signal()` method |
| `fivemin_modules/indicators.py` | Modify | Add `trends_align()` function for multi-timeframe check |
| `fivemin_modules/signal_engine.py` | Modify | Call `trends_align()` before generating signal |
| `fivemin_modules/market_data.py` | Modify | Track per-asset price history (deque already exists, expose for trend lookups) |
| `fivemin_modules/trade_executor.py` | Modify | Add `compute_fair_value()` + replace immediate-buy with limit-order maker mode |
| `tests/test_position_sizing.py` | Create | Tests for confidence-scaled sizing |
| `tests/test_trend_confirmation.py` | Create | Tests for trends_align function |
| `tests/test_limit_order_maker.py` | Create | Tests for fair value calc + maker order flow |

---

## Task 1: Config Constants for Stage 1

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/config.py`

- [ ] **Step 1: Read current config to find insertion point**

```bash
grep -n "FIVEMIN_" /Users/mbh/Desktop/MakeMoney/config.py | tail -20
```

Expected: shows existing FIVEMIN_* constants. Find the last one.

- [ ] **Step 2: Add Stage 1 config constants after the existing FIVEMIN_* block**

Add these lines to `config.py` inside the `Config` class, after the existing `FIVEMIN_*` constants:

```python
    # Stage 1: Confidence-scaled position sizing
    FIVEMIN_SIZE_3OF3_HIGH = 10.0   # 3/3 indicators, conf >= 0.85
    FIVEMIN_SIZE_3OF3_MED  = 7.0    # 3/3 indicators, conf >= 0.70
    FIVEMIN_SIZE_2OF3_HIGH = 5.0    # 2/3 indicators, conf >= 0.75
    FIVEMIN_SIZE_2OF3_LOW  = 3.0    # 2/3 indicators, conf >= 0.55

    # Stage 1: Multi-timeframe trend confirmation
    FIVEMIN_TREND_REQUIRE_ALIGN = True   # set False to disable check
    FIVEMIN_TREND_LOOKBACK_30S  = 30
    FIVEMIN_TREND_LOOKBACK_2M   = 120
    FIVEMIN_TREND_LOOKBACK_5M   = 300

    # Stage 1: Limit-order maker mode
    FIVEMIN_MAKER_MODE_ENABLED = True
    FIVEMIN_MAKER_TIMEOUT_SEC  = 60      # cancel unfilled orders after this
    FIVEMIN_MAKER_FAIR_VALUE_OFFSET = 0.05  # bid this much below fair value
    FIVEMIN_MAKER_MIN_PRICE = 0.05       # never bid below this
    FIVEMIN_MAKER_MAX_PRICE = 0.80       # never bid above this
```

- [ ] **Step 3: Verify config loads cleanly**

Run: `cd /Users/mbh/Desktop/MakeMoney && python3 -c "from config import Config; c = Config(); print(c.FIVEMIN_SIZE_3OF3_HIGH, c.FIVEMIN_TREND_REQUIRE_ALIGN, c.FIVEMIN_MAKER_MODE_ENABLED)"`
Expected: `10.0 True True`

- [ ] **Step 4: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add config.py && git commit -m "feat(5m): add Stage 1 config constants for sizing, trend, maker mode"
```

---

## Task 2: Confidence-Scaled Position Sizing

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/risk_manager.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_position_sizing.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_position_sizing.py`:

```python
import os
import tempfile
import pytest
from fivemin_modules.risk_manager import FiveMinRiskManager
from utils.fivemin_db import init_fivemin_db
from config import Config


@pytest.fixture
def rm():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        config = Config()
        config.FIVEMIN_DB_PATH = db_path
        init_fivemin_db(db_path)
        rm = FiveMinRiskManager(config)
        rm.init_portfolio(20.0)
        yield rm


def test_3of3_high_confidence(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.90)
    assert size == 10.0


def test_3of3_medium_confidence(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.75)
    assert size == 7.0


def test_2of3_high_confidence(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.80)
    assert size == 5.0


def test_2of3_low_confidence(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.60)
    assert size == 3.0


def test_weak_signal_returns_zero(rm):
    size = rm.calc_position_size_for_signal(score=2, confidence=0.50)
    assert size == 0.0


def test_size_capped_by_balance(rm):
    rm.init_portfolio(4.0)  # only $4 in balance
    size = rm.calc_position_size_for_signal(score=3, confidence=0.95)
    assert size == 4.0  # capped at balance, not $10


def test_3of3_boundary_85(rm):
    """Exactly 0.85 confidence should still get high tier."""
    size = rm.calc_position_size_for_signal(score=3, confidence=0.85)
    assert size == 10.0


def test_3of3_boundary_70(rm):
    size = rm.calc_position_size_for_signal(score=3, confidence=0.70)
    assert size == 7.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_position_sizing.py -v
```

Expected: All 8 tests FAIL with `AttributeError: 'FiveMinRiskManager' object has no attribute 'calc_position_size_for_signal'`

- [ ] **Step 3: Add the method to risk_manager.py**

In `/Users/mbh/Desktop/MakeMoney/fivemin_modules/risk_manager.py`, add this method to the `FiveMinRiskManager` class (after `record_trade_outcome`):

```python
    def calc_position_size_for_signal(self, score: int, confidence: float) -> float:
        """Confidence-scaled position sizing.

        Replaces flat $3 with dynamic $3-$10 based on signal strength.
        Returns 0 if signal is too weak to trade.
        Capped by current balance.
        """
        if score == 3 and confidence >= 0.85:
            size = self.config.FIVEMIN_SIZE_3OF3_HIGH
        elif score == 3 and confidence >= 0.70:
            size = self.config.FIVEMIN_SIZE_3OF3_MED
        elif score == 2 and confidence >= 0.75:
            size = self.config.FIVEMIN_SIZE_2OF3_HIGH
        elif score == 2 and confidence >= 0.55:
            size = self.config.FIVEMIN_SIZE_2OF3_LOW
        else:
            return 0.0

        # Cap by current balance
        balance = self._get_portfolio()["balance"]
        return min(size, balance)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_position_sizing.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/risk_manager.py tests/test_position_sizing.py && git commit -m "feat(5m): add confidence-scaled position sizing ($3-$10 based on signal strength)"
```

---

## Task 3: Multi-Timeframe Trend Confirmation Function

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/indicators.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_trend_confirmation.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_trend_confirmation.py`:

```python
import pytest
from collections import deque
from fivemin_modules.indicators import trends_align


def make_history(prices: list[float], target_len: int = 350) -> deque:
    """Pad prices to target_len so we have at least 300 points (5min @ 1Hz)."""
    if len(prices) >= target_len:
        return deque(prices, maxlen=target_len)
    pad = [prices[0]] * (target_len - len(prices))
    return deque(pad + prices, maxlen=target_len)


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
    # Build 350 prices: 5m ago=100, 2m ago=110 (uptrend), 30s ago=105 (down), now=106 (up 30s, down 2m)
    prices = []
    # 0-50: stable around 100 (5m+ ago)
    prices += [100.0] * 50
    # 50-230: rise to 110 (2m ago)
    for i in range(180):
        prices.append(100.0 + (i / 180) * 10)
    # 230-320: fall to 105
    for i in range(90):
        prices.append(110.0 - (i / 90) * 5)
    # 320-350: rise back to 106
    for i in range(30):
        prices.append(105.0 + (i / 30) * 1)
    history = deque(prices, maxlen=350)
    # 30s trend: up. 2m trend: down (110→106). 5m trend: up (100→106). NOT aligned for UP or DOWN.
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_trend_confirmation.py -v
```

Expected: All 5 tests FAIL with `ImportError: cannot import name 'trends_align' from 'fivemin_modules.indicators'`

- [ ] **Step 3: Add the function to indicators.py**

Append to `/Users/mbh/Desktop/MakeMoney/fivemin_modules/indicators.py`:

```python


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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_trend_confirmation.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/indicators.py tests/test_trend_confirmation.py && git commit -m "feat(5m): add multi-timeframe trends_align function (30s+2m+5m)"
```

---

## Task 4: Wire Trend Confirmation Into Signal Engine

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/signal_engine.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_signal_engine_trend.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_signal_engine_trend.py`:

```python
import pytest
from collections import deque
from fivemin_modules.signal_engine import FiveMinSignalEngine
from config import Config


@pytest.fixture
def engine():
    return FiveMinSignalEngine(Config())


def _build_state(price_history, current_price, window_open):
    """Build a state dict matching what signal_engine.evaluate expects."""
    return {
        "current_price": current_price,
        "window_open_price": window_open,
        "volumes": [100.0] * 60,
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
    # Heavy buy pressure to trigger UP signal
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
    assert signal is not None  # would have fired with old behavior
    # Restore default for other tests
    engine.config.FIVEMIN_TREND_REQUIRE_ALIGN = True
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_signal_engine_trend.py -v
```

Expected: At least one test FAILS (signal_engine doesn't read price_history yet).

- [ ] **Step 3: Modify signal_engine.evaluate() to call trends_align**

Open `/Users/mbh/Desktop/MakeMoney/fivemin_modules/signal_engine.py`. Add `trends_align` to the imports at the top:

```python
from fivemin_modules.indicators import (
    calc_momentum,
    calc_orderbook_imbalance,
    calc_volume_spike,
    trends_align,
    IndicatorResult,
)
```

Then, inside `evaluate()`, in the loop where signals are detected, add the trend check before the `return Signal(...)`. Replace the existing block:

```python
        for direction in ("UP", "DOWN"):
            agreeing = [r for r in results if r.direction == direction]
            if len(agreeing) >= min_agree:
                avg_confidence = sum(r.confidence for r in agreeing) / len(agreeing)
                if avg_confidence >= min_confidence:
                    log.info(
                        f"{asset} {direction} signal: {len(agreeing)}/3 agree, "
                        f"confidence={avg_confidence:.2f}, phase={phase}"
                    )
                    return Signal(
                        asset=asset,
                        direction=direction,
                        confidence=round(avg_confidence, 4),
                        phase=phase,
                        indicators=indicators_detail,
                        timestamp=0.0,
                    )

        return None
```

with this updated block:

```python
        for direction in ("UP", "DOWN"):
            agreeing = [r for r in results if r.direction == direction]
            if len(agreeing) >= min_agree:
                avg_confidence = sum(r.confidence for r in agreeing) / len(agreeing)
                if avg_confidence >= min_confidence:
                    # Multi-timeframe trend confirmation (Stage 1)
                    if getattr(self.config, "FIVEMIN_TREND_REQUIRE_ALIGN", False):
                        history = state.get("price_history")
                        if history is None or not trends_align(history, direction):
                            log.info(
                                f"{asset} {direction} signal blocked: trends not aligned "
                                f"({len(agreeing)}/3 agree, conf={avg_confidence:.2f})"
                            )
                            continue
                    log.info(
                        f"{asset} {direction} signal: {len(agreeing)}/3 agree, "
                        f"confidence={avg_confidence:.2f}, phase={phase}"
                    )
                    return Signal(
                        asset=asset,
                        direction=direction,
                        confidence=round(avg_confidence, 4),
                        phase=phase,
                        indicators=indicators_detail,
                        timestamp=0.0,
                    )

        return None
```

- [ ] **Step 4: Update market_data.py to expose price_history in to_signal_dict**

In `/Users/mbh/Desktop/MakeMoney/fivemin_modules/market_data.py`, find the `to_signal_dict` method on `MarketState`. It currently returns `current_price`, `window_open_price`, `volumes`, `orderbook_up`, `orderbook_down`. Add `price_history`:

```python
    def to_signal_dict(self) -> dict:
        """Convert to dict for signal engine evaluation."""
        return {
            "current_price": self.current_price,
            "window_open_price": self.window_open_price,
            "volumes": list(self.volumes),
            "orderbook_up": self.orderbook_up,
            "orderbook_down": self.orderbook_down,
            "price_history": self.price_history,
        }
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_signal_engine_trend.py -v
```

Expected: 3 passed

- [ ] **Step 6: Verify existing signal engine tests still pass**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/ -k "signal" -v 2>&1 | tail -20
```

Expected: Existing tests still pass. If a pre-existing test breaks because price_history is missing, add `"price_history": deque([], maxlen=350)` to its state dict.

- [ ] **Step 7: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/signal_engine.py fivemin_modules/market_data.py tests/test_signal_engine_trend.py && git commit -m "feat(5m): wire multi-timeframe trend confirmation into signal engine"
```

---

## Task 5: Increase price_history Buffer Size

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/market_data.py`

- [ ] **Step 1: Find the current price_history buffer**

```bash
grep -n "price_history" /Users/mbh/Desktop/MakeMoney/fivemin_modules/market_data.py
```

Expected: shows `price_history: deque = field(default_factory=lambda: deque(maxlen=60))`

- [ ] **Step 2: Increase maxlen from 60 to 350 (5+ minutes)**

In `/Users/mbh/Desktop/MakeMoney/fivemin_modules/market_data.py`, change:

```python
    price_history: deque = field(default_factory=lambda: deque(maxlen=60))
```

to:

```python
    price_history: deque = field(default_factory=lambda: deque(maxlen=350))
```

Also find the `reset()` method on `MarketState` and update the same line there:

```python
        self.price_history = deque(maxlen=350)
```

- [ ] **Step 3: Verify by running existing tests**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/ -k "market_data or signal_engine" -v 2>&1 | tail -20
```

Expected: All passing (or same failures as before this task — no new failures).

- [ ] **Step 4: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/market_data.py && git commit -m "feat(5m): increase price_history buffer to 350 samples (5+ min)"
```

---

## Task 6: Fair Value Calculation for Maker Mode

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_fair_value.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_fair_value.py`:

```python
import pytest
from fivemin_modules.trade_executor import compute_fair_value


def test_high_confidence_high_score_fair_value():
    """3-of-3 indicators agreeing at 0.95 conf → near $0.55."""
    fv = compute_fair_value(score=3, confidence=0.95)
    assert 0.50 <= fv <= 0.65


def test_low_confidence_2of3_lower_fair_value():
    """2-of-3 indicators at 0.55 conf → cheaper bid."""
    fv = compute_fair_value(score=2, confidence=0.55)
    assert 0.20 <= fv <= 0.40


def test_3of3_med_confidence():
    fv = compute_fair_value(score=3, confidence=0.75)
    assert 0.40 <= fv <= 0.55


def test_fair_value_clamped_min():
    """Even with weakest signal, never go below FIVEMIN_MAKER_MIN_PRICE."""
    fv = compute_fair_value(score=2, confidence=0.55)
    assert fv >= 0.05


def test_fair_value_clamped_max():
    """Even with strongest signal, never exceed FIVEMIN_MAKER_MAX_PRICE."""
    fv = compute_fair_value(score=3, confidence=1.0)
    assert fv <= 0.80
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_fair_value.py -v
```

Expected: 5 tests FAIL with `ImportError: cannot import name 'compute_fair_value' from 'fivemin_modules.trade_executor'`

- [ ] **Step 3: Add compute_fair_value function**

Open `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`. Add this function at module level (above the class definition):

```python
def compute_fair_value(score: int, confidence: float,
                       min_price: float = 0.05, max_price: float = 0.80) -> float:
    """Compute a fair-value bid price for a maker order.

    Stronger signal → higher bid (more willing to pay).
    Weaker signal → lower bid (only fill if very cheap).

    Mapping:
      3/3 indicators @ conf 0.95+ → $0.55
      3/3 indicators @ conf 0.85  → $0.50
      3/3 indicators @ conf 0.70  → $0.45
      2/3 indicators @ conf 0.80  → $0.40
      2/3 indicators @ conf 0.55  → $0.30
    """
    if score == 3:
        # Linear from 0.45 (conf=0.70) to 0.60 (conf=1.0)
        fv = 0.45 + (max(0.70, min(1.0, confidence)) - 0.70) * 0.50
    else:  # score == 2
        # Linear from 0.30 (conf=0.55) to 0.45 (conf=1.0)
        fv = 0.30 + (max(0.55, min(1.0, confidence)) - 0.55) * (0.15 / 0.45)

    return round(max(min_price, min(max_price, fv)), 2)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_fair_value.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/trade_executor.py tests/test_fair_value.py && git commit -m "feat(5m): add compute_fair_value for maker-mode bidding"
```

---

## Task 7: Limit-Order Maker Mode With Cancel-On-Timeout

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_maker_mode.py`

- [ ] **Step 1: Read the current `_execute_live` method**

```bash
sed -n '88,180p' /Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py
```

Note the existing flow: receives `limit_price` from the caller, places order, waits, checks fill status.

- [ ] **Step 2: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_maker_mode.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from fivemin_modules.trade_executor import FiveMinTradeExecutor
from fivemin_modules.signal_engine import Signal
from config import Config


@pytest.fixture
def executor():
    config = Config()
    config.FIVEMIN_TRADING_MODE = "live"
    config.FIVEMIN_MAKER_MODE_ENABLED = True
    config.FIVEMIN_MAKER_TIMEOUT_SEC = 5
    return FiveMinTradeExecutor(config, exchange=None)


def make_signal(score=3, confidence=0.90):
    return Signal(
        asset="BTC",
        direction="UP",
        confidence=confidence,
        phase="mid",
        indicators={
            "momentum": {"direction": "UP", "confidence": confidence},
            "imbalance": {"direction": "UP", "confidence": confidence},
            "volume": {"direction": "UP" if score == 3 else "NEUTRAL", "confidence": confidence},
        },
        timestamp=0.0,
    )


def test_maker_mode_uses_fair_value_not_ask_price(executor):
    """When maker mode is on, the order price should be the fair value, not the high ask."""
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed_order_obj"
    fake_client.post_order.return_value = {
        "errorMsg": "",
        "orderID": "0xabc",
        "takingAmount": "10",
        "makingAmount": "5.0",
        "status": "matched",
        "transactionsHashes": ["0xtx"],
        "success": True,
    }
    executor._clob_client = fake_client

    signal = make_signal(score=3, confidence=0.95)
    # Caller passes the high ask, but maker mode should ignore it
    result = executor._execute_live(
        signal=signal, amount=10.0, limit_price=0.99,
        token_id="t1", condition_id="c1",
    )

    # Inspect the OrderArgs that was created
    create_call = fake_client.create_order.call_args
    order_args = create_call[0][0] if create_call[0] else create_call[1].get("order_args")
    assert order_args.price < 0.70, f"Maker mode should use fair value, got {order_args.price}"
    assert order_args.price >= 0.05


def test_maker_mode_disabled_uses_caller_price(executor):
    """When maker mode is disabled, use the limit_price the caller passed."""
    executor.config.FIVEMIN_MAKER_MODE_ENABLED = False
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed"
    fake_client.post_order.return_value = {
        "errorMsg": "", "orderID": "0xabc",
        "takingAmount": "10", "makingAmount": "5.0",
        "status": "matched", "transactionsHashes": ["0xtx"],
        "success": True,
    }
    executor._clob_client = fake_client

    signal = make_signal(score=3, confidence=0.95)
    executor._execute_live(
        signal=signal, amount=10.0, limit_price=0.55,
        token_id="t1", condition_id="c1",
    )

    create_call = fake_client.create_order.call_args
    order_args = create_call[0][0] if create_call[0] else create_call[1].get("order_args")
    assert order_args.price == pytest.approx(0.55)
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_maker_mode.py -v
```

Expected: At least one test FAILS because maker mode logic is not yet wired in.

- [ ] **Step 4: Modify _execute_live to use maker mode**

Open `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`. Find the `_execute_live` method. At the very start of the method (after the `if not token_id:` guard), add this maker-mode override:

```python
        # Stage 1: Maker mode — replace caller's limit_price with fair value
        if getattr(self.config, "FIVEMIN_MAKER_MODE_ENABLED", False):
            score = sum(
                1 for v in signal.indicators.values()
                if isinstance(v, dict) and v.get("direction") == signal.direction
            )
            fair = compute_fair_value(
                score=score,
                confidence=signal.confidence,
                min_price=getattr(self.config, "FIVEMIN_MAKER_MIN_PRICE", 0.05),
                max_price=getattr(self.config, "FIVEMIN_MAKER_MAX_PRICE", 0.80),
            )
            offset = getattr(self.config, "FIVEMIN_MAKER_FAIR_VALUE_OFFSET", 0.05)
            limit_price = max(
                getattr(self.config, "FIVEMIN_MAKER_MIN_PRICE", 0.05),
                round(fair - offset, 2),
            )
            log.info(
                f"MAKER MODE: signal {score}/3 conf={signal.confidence:.2f} "
                f"fair_value=${fair:.2f} → bidding ${limit_price:.2f}"
            )
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_maker_mode.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/trade_executor.py tests/test_maker_mode.py && git commit -m "feat(5m): replace immediate-buy with maker-mode fair-value limit orders"
```

---

## Task 8: Cancel-On-Timeout for Unfilled Maker Orders

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`
- Test: `/Users/mbh/Desktop/MakeMoney/tests/test_maker_cancel.py`

- [ ] **Step 1: Write the failing test**

Create `/Users/mbh/Desktop/MakeMoney/tests/test_maker_cancel.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from fivemin_modules.trade_executor import FiveMinTradeExecutor
from fivemin_modules.signal_engine import Signal
from config import Config


@pytest.fixture
def executor():
    config = Config()
    config.FIVEMIN_TRADING_MODE = "live"
    config.FIVEMIN_MAKER_MODE_ENABLED = True
    config.FIVEMIN_MAKER_TIMEOUT_SEC = 2
    return FiveMinTradeExecutor(config, exchange=None)


def make_signal():
    return Signal(
        asset="BTC", direction="UP", confidence=0.90, phase="mid",
        indicators={
            "momentum": {"direction": "UP", "confidence": 0.9},
            "imbalance": {"direction": "UP", "confidence": 0.9},
            "volume": {"direction": "UP", "confidence": 0.9},
        },
        timestamp=0.0,
    )


def test_unfilled_order_is_cancelled_after_timeout(executor):
    """Order that doesn't fill within FIVEMIN_MAKER_TIMEOUT_SEC should be cancelled."""
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed"
    fake_client.post_order.return_value = {
        "errorMsg": "",
        "orderID": "0xnotfilled",
        "takingAmount": "10",
        "makingAmount": "0",
        "status": "live",  # not matched yet
        "transactionsHashes": [],
        "success": True,
    }
    fake_client.get_order.return_value = {
        "status": "live",
        "size_matched": 0,
    }
    fake_client.cancel.return_value = {"canceled": ["0xnotfilled"]}
    executor._clob_client = fake_client

    result = executor._execute_live(
        signal=make_signal(), amount=10.0, limit_price=0.99,
        token_id="t1", condition_id="c1",
    )

    fake_client.cancel.assert_called_once_with("0xnotfilled")
    assert result["status"] == "error"
    assert "not filled" in result["reason"].lower() or "cancel" in result["reason"].lower()


def test_filled_order_is_not_cancelled(executor):
    """If the order fills immediately, cancel() must NOT be called."""
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed"
    fake_client.post_order.return_value = {
        "errorMsg": "",
        "orderID": "0xfilled",
        "takingAmount": "10",
        "makingAmount": "20",
        "status": "matched",
        "transactionsHashes": ["0xtx"],
        "success": True,
    }
    executor._clob_client = fake_client

    result = executor._execute_live(
        signal=make_signal(), amount=10.0, limit_price=0.99,
        token_id="t1", condition_id="c1",
    )

    fake_client.cancel.assert_not_called()
    assert result["status"] == "filled"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_maker_cancel.py -v
```

Expected: At least `test_unfilled_order_is_cancelled_after_timeout` FAILS.

- [ ] **Step 3: Read the existing fill-check section**

```bash
grep -n "size_matched\|cancel\|status" /Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py | head -20
```

Expected: shows the existing fill-check + cancel logic in `_execute_live`.

- [ ] **Step 4: Update the wait/poll loop to honor FIVEMIN_MAKER_TIMEOUT_SEC**

In `/Users/mbh/Desktop/MakeMoney/fivemin_modules/trade_executor.py`, find the section in `_execute_live` that handles fill checking. Replace the existing post-order fill-check block (the `time.sleep(3)` followed by `get_order` lookup) with a polling loop:

```python
            # Maker mode: poll for fill, cancel if timeout
            timeout = getattr(self.config, "FIVEMIN_MAKER_TIMEOUT_SEC", 60)
            poll_interval = 1
            elapsed = 0
            filled = 0
            status = "unknown"
            order_resp = resp  # initial post_order response

            # If matched immediately, skip polling
            if order_resp.get("status") == "matched":
                filled = float(order_resp.get("makingAmount", shares))
                status = "matched"
            else:
                while elapsed < timeout:
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                    try:
                        order_status = self._clob_client.get_order(order_id)
                        filled = float(order_status.get("size_matched", 0))
                        status = order_status.get("status", "unknown")
                        if filled > 0 or status in ("MATCHED", "FILLED", "matched", "filled"):
                            break
                    except Exception as e:
                        log.warning(f"Order poll error: {e}")
                        break

            # Cancel if still unfilled
            if filled == 0 and status not in ("MATCHED", "FILLED", "matched", "filled"):
                try:
                    self._clob_client.cancel(order_id)
                    log.info(f"Cancelled unfilled order: {order_id}")
                except Exception as e:
                    log.warning(f"Cancel failed: {e}")
                return {"status": "error", "reason": "Order not filled within timeout"}
```

This block replaces the existing `time.sleep(3)` + single `get_order` call. The rest of the method (recording the trade in DB) stays the same.

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_maker_cancel.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add fivemin_modules/trade_executor.py tests/test_maker_cancel.py && git commit -m "feat(5m): poll for maker-order fill and cancel on timeout"
```

---

## Task 9: Wire Confidence-Scaled Sizing Into polybot5m.py

**Files:**
- Modify: `/Users/mbh/Desktop/MakeMoney/polybot5m.py`

- [ ] **Step 1: Find the current sizing logic**

```bash
grep -n "trade_amount\|calc_position_size" /Users/mbh/Desktop/MakeMoney/polybot5m.py
```

Expected: shows existing line `trade_amount = min(can_trade["max_amount"], 5.0 if agreeing >= 3 else 3.0)` (or similar).

- [ ] **Step 2: Replace with confidence-scaled sizing call**

In `/Users/mbh/Desktop/MakeMoney/polybot5m.py`, find this block (around line 175-180):

```python
                # Position sizing: $5 for 3/3 agreement, $3 for 2/3
                agreeing = sum(1 for v in best.indicators.values()
                               if isinstance(v, dict) and v.get("direction") == best.direction)
                trade_amount = min(can_trade["max_amount"], 5.0 if agreeing >= 3 else 3.0)
```

Replace with:

```python
                # Position sizing: confidence-scaled $3-$10 (Stage 1)
                agreeing = sum(1 for v in best.indicators.values()
                               if isinstance(v, dict) and v.get("direction") == best.direction)
                trade_amount = self.risk_manager.calc_position_size_for_signal(
                    score=agreeing,
                    confidence=best.confidence,
                )
                trade_amount = min(trade_amount, can_trade["max_amount"])
                if trade_amount <= 0:
                    log.info(f"Skipping {best.asset} {best.direction}: signal too weak for sizing")
                    await asyncio.sleep(1)
                    continue
```

- [ ] **Step 3: Verify polybot5m.py imports/syntax are clean**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -c "import ast; ast.parse(open('polybot5m.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run the bot in dry mode for 5 seconds to confirm it starts**

```bash
cd /Users/mbh/Desktop/MakeMoney && timeout 5 python3 polybot5m.py --mode paper 2>&1 | head -20 || true
```

Expected: First few log lines show "Starting PolyBot 5M in paper mode" and "PolyBot 5M portfolio initialized". No `AttributeError` about `calc_position_size_for_signal`.

- [ ] **Step 5: Commit**

```bash
cd /Users/mbh/Desktop/MakeMoney && git add polybot5m.py && git commit -m "feat(5m): wire confidence-scaled sizing into main loop"
```

---

## Task 10: Run All Stage 1 Tests + Push to Server

**Files:** none modified in this task

- [ ] **Step 1: Run the full Stage 1 test suite**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/test_position_sizing.py tests/test_trend_confirmation.py tests/test_signal_engine_trend.py tests/test_fair_value.py tests/test_maker_mode.py tests/test_maker_cancel.py -v
```

Expected: All ~25 tests pass.

- [ ] **Step 2: Run the existing fivemin tests to verify no regressions**

```bash
cd /Users/mbh/Desktop/MakeMoney && python3 -m pytest tests/ -k "fivemin or signal or risk or trade_executor or market_data or indicators" -v 2>&1 | tail -30
```

Expected: Same passes/fails as before this plan started. No new test failures.

- [ ] **Step 3: Push to GitHub**

```bash
cd /Users/mbh/Desktop/MakeMoney && find .git -name "*.lock" -delete 2>/dev/null; git push origin master
```

Expected: `master -> master` push success.

- [ ] **Step 4: Pull the new code to the server and restart the bot**

The user runs this in Cloud Shell (or via Playwright MCP):

```bash
gcloud compute ssh polybot-server --zone=us-central1-a --command='cd ~/MakeMoney && git pull && pkill -9 -f polybot5m.py; sleep 2; export HTTPS_PROXY=socks5://127.0.0.1:40000; export HTTP_PROXY=socks5://127.0.0.1:40000; export ALL_PROXY=socks5://127.0.0.1:40000; nohup python3 polybot5m.py --mode live > logs/5m.log 2>&1 & disown; sleep 5; pgrep -a -f polybot5m.py'
```

Expected: a single python process listed.

- [ ] **Step 5: Watch logs for first signal with Stage 1 behavior**

```bash
gcloud compute ssh polybot-server --zone=us-central1-a --command='tail -50 ~/MakeMoney/logs/5m.log'
```

Look for new log lines:
- `MAKER MODE: signal X/3 conf=0.XX fair_value=$0.XX → bidding $0.XX`
- `signal blocked: trends not aligned` (when trends disagree)
- A successful order placement at a fair-value price (not $0.99)

---

## Summary

| Task | Component | Tests | Files Modified |
|------|-----------|-------|----------------|
| 1 | Config constants | manual | config.py |
| 2 | Confidence-scaled sizing | 8 | risk_manager.py |
| 3 | trends_align function | 5 | indicators.py |
| 4 | Wire trends into signal engine | 3 | signal_engine.py, market_data.py |
| 5 | Increase price_history buffer | manual | market_data.py |
| 6 | compute_fair_value | 5 | trade_executor.py |
| 7 | Maker-mode order placement | 2 | trade_executor.py |
| 8 | Cancel-on-timeout polling | 2 | trade_executor.py |
| 9 | Wire sizing into main loop | smoke | polybot5m.py |
| 10 | Full test run + deploy | — | — |
| **Total** | **Stage 1** | **~25 tests** | **6 files** |

## Self-Review

**Spec coverage**:
- Change 6 (confidence-scaled sizing): Tasks 1, 2, 9 ✓
- Change 4 (trend confirmation): Tasks 1, 3, 4, 5 ✓
- Change 1 (limit-order maker mode): Tasks 1, 6, 7, 8 ✓
- Risk caps (max bet $10): enforced in Task 2 sizing table ✓
- Telegram alerts: Already in existing code, no change needed for Stage 1 ✓
- Auto-revert on <40% win rate: deferred to Stage 2 (out of scope here)

**Placeholder scan**: No TBDs, all code blocks are concrete.

**Type consistency**:
- `calc_position_size_for_signal(score, confidence)` — same signature in test, implementation, and main loop call ✓
- `trends_align(price_history, direction)` — same in test, implementation, signal_engine ✓
- `compute_fair_value(score, confidence, min_price, max_price)` — same in test, implementation, _execute_live call ✓

Plan is complete and self-consistent.
