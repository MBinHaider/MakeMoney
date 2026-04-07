# PolyBot Strategy Upgrade — Design Spec

**Date**: 2026-04-07
**Status**: Approved
**Author**: Claude + Mohammad

## Goal

Maximize total profit from PolyBot 5M by improving 3 dimensions simultaneously: more trade opportunities, better entry quality, and bigger wins per trade.

**Current baseline**: 6 real trades total, 3W/3L (50% win rate), +$9.91 net P&L. Bot was bottlenecked by sparse liquidity (asks at $0.99) and rigid sizing ($3 flat).

**Target**: Increase trade volume 5-10x while maintaining or improving win rate and growing average profit per winning trade.

## Scope

Applies only to **PolyBot 5M** (`polybot5m.py` and `fivemin_modules/`). BinanceBot is out of scope. The original PolyBot is only touched as a fallback data source for long-duration markets.

## The 8 Changes

### Change 1: Limit-Order Maker Mode

**Problem**: Bot waits for someone to sell at $0.99 → almost never trades.

**Fix**: Bot becomes a market maker. When a signal fires, compute fair value from indicators and post a BUY limit order at that price. Wait up to 60s for fill, then cancel.

**Implementation**:
- Add `compute_fair_value(asset, direction, indicators)` function in `signal_engine.py`
- Returns a price between $0.05 and $0.80 based on signal strength
- `trade_executor.py` uses this as the limit price instead of the orderbook ask
- After placing the order, wait 60s polling `client.get_order(order_id)` for status
- If unfilled, call `client.cancel(order_id)` and log

**Files**: `fivemin_modules/signal_engine.py`, `fivemin_modules/trade_executor.py`

### Change 2: Wider Price Filter With Size Adjustment

**Problem**: Hard cap at $0.70 means bot skips many opportunities just above that.

**Fix**: Allow up to $0.85, but scale position size down for riskier prices.

**Implementation**:
```python
def calc_size_for_price(base_size: float, ask: float) -> float:
    if ask <= 0.50: return base_size           # 100%
    if ask <= 0.70: return base_size * 0.6     # 60%
    if ask <= 0.85: return base_size * 0.3     # 30%
    return 0  # skip
```

**Files**: `fivemin_modules/risk_manager.py`

### Change 3: Long-Duration Market Fallback

**Problem**: When 5-min markets are completely dry for 10+ minutes, bot sits idle.

**Fix**: Fall back to trading 1-hour and daily Polymarket crypto markets via the existing PolyBot data collector.

**Implementation**:
- New module `fivemin_modules/long_market_fallback.py`
- Imports `modules/data_collector.py` (existing PolyBot module)
- After 10 minutes of no 5-min trades, query Gamma API for active 1h markets
- Reuses existing signal engine but with longer timeframe checks
- Marks fallback trades with `fallback=true` in DB

**Files**: `fivemin_modules/long_market_fallback.py` (new), `polybot5m.py`

### Change 4: Trend Confirmation (Multi-Timeframe)

**Problem**: Current bot only checks 30-second momentum → noisy signals.

**Fix**: Require 30s, 2m, and 5m trends to all agree before entering.

**Implementation**:
```python
def trend_at(price_history, seconds_back):
    if len(price_history) < seconds_back:
        return None
    return price_history[-1] - price_history[-seconds_back]

def trends_align(price_history, direction):
    t30 = trend_at(price_history, 30)
    t2m = trend_at(price_history, 120)
    t5m = trend_at(price_history, 300)
    if None in (t30, t2m, t5m):
        return False
    if direction == "UP":
        return t30 > 0 and t2m > 0 and t5m > 0
    else:
        return t30 < 0 and t2m < 0 and t5m < 0
```

Called from `signal_engine.evaluate()` before generating a signal.

**Files**: `fivemin_modules/indicators.py` (new function), `fivemin_modules/signal_engine.py`

### Change 5: Self-Learning Blacklist

**Problem**: Bot keeps making the same losing trades.

**Fix**: Track every signal's outcome. If a similar setup loses 2+ times in 24h, blacklist it.

**Implementation**:
- New table `fm_signal_outcomes` in `polybot5m.db`:
  ```sql
  CREATE TABLE fm_signal_outcomes (
    id INTEGER PRIMARY KEY,
    asset TEXT, direction TEXT,
    confidence_bucket TEXT,  -- "low", "med", "high"
    phase TEXT,
    indicators_pattern TEXT,  -- "MOM_OB" or "MOM_VOL" or "OB_VOL" or "ALL3"
    result TEXT,  -- "win" or "loss"
    timestamp TEXT
  );
  ```
- Before placing a trade, query: `SELECT COUNT(*) FROM fm_signal_outcomes WHERE asset=? AND direction=? AND confidence_bucket=? AND phase=? AND indicators_pattern=? AND result='loss' AND timestamp > datetime('now', '-24 hours')`
- If result >= 2, skip the trade and log "blacklisted: similar setup lost N times"

**Files**: `utils/fivemin_db.py` (schema), `fivemin_modules/risk_manager.py`

### Change 6: Confidence-Scaled Position Sizing

**Problem**: Flat $3 per trade doesn't capitalize on strong signals.

**Fix**: Dynamic sizing $3-$10 based on signal strength.

**Implementation**:
```python
def calc_position_size(signal):
    score = signal.score          # 2 or 3 indicators agreeing
    conf = signal.confidence      # 0.0-1.0

    if score == 3 and conf >= 0.85: return 10.0
    if score == 3 and conf >= 0.70: return 7.0
    if score == 2 and conf >= 0.75: return 5.0
    if score == 2 and conf >= 0.55: return 3.0
    return 0  # don't trade
```

**Files**: `fivemin_modules/risk_manager.py`

### Change 7: Patient Entry

**Problem**: Buying immediately at signal time often misses better prices that appear within seconds.

**Fix**: Wait up to 30s for the ask to drop by ~10c before placing the order. Bail early if price runs away.

**Implementation**:
```python
def patient_buy(asset, direction, max_wait=30):
    initial_ask = fetch_ask(asset, direction)
    target = max(0.05, initial_ask - 0.10)
    deadline = time.time() + max_wait
    while time.time() < deadline:
        time.sleep(1)
        ask = fetch_ask(asset, direction)
        if ask <= target:
            return place_order(ask)
        if ask > initial_ask + 0.10:
            return place_order(initial_ask)  # price escaping
    return place_order(initial_ask)  # 30s up
```

**Files**: `fivemin_modules/trade_executor.py`

### Change 8: Smart Pyramiding

**Problem**: When a trade is winning big, bot doesn't capitalize.

**Fix**: Add a second smaller position if the winner is trending well, with strict guardrails.

**Conditions (ALL required)**:
- Existing position has unrealized P&L > $1.00
- Window has > 90 seconds remaining
- New signal is 3/3 indicators agreeing (full confidence)
- Total position after pyramid ≤ $15
- Underlying asset price has moved further in our direction since entry

**Implementation**:
```python
def should_pyramid(open_pos, signal, asset_price_now, window_remaining_sec):
    if window_remaining_sec < 90: return False
    if open_pos.unrealized_pnl < 1.0: return False
    if signal.score < 3: return False
    if open_pos.size + 5.0 > 15.0: return False
    if open_pos.direction == "UP" and asset_price_now <= open_pos.entry_asset_price:
        return False
    if open_pos.direction == "DOWN" and asset_price_now >= open_pos.entry_asset_price:
        return False
    return True
```

If true, place a $3-5 follow-up order. Track in DB as `pyramid_of=<original_trade_id>`.

**Files**: `fivemin_modules/trade_executor.py`, `polybot5m.py`

## Risk Limits

| Rule | Value | Reason |
|------|-------|--------|
| Max bet per trade | $10 | Cap on confidence-scaled sizing |
| Max same-window exposure | $15 | Limit pyramiding total |
| Daily loss limit | 20% (~$3.45 on $17.23) | Unchanged |
| Consecutive losses pause | 3 losses → 15min | Unchanged |
| Auto-revert threshold | < 40% win rate over 10 trades | New safety |
| Min trade interval | None within window, 1 window between | Unchanged |

## Implementation Stages

### Stage 1 — Foundation (Lowest Risk)
- Change 6: Confidence-scaled sizing
- Change 4: Trend confirmation
- Change 1: Limit-order maker mode

**Why first**: Improves quality of every trade without changing volume. Validates that better signals → better outcomes.

**Test for**: 5+ trades over 24h with these changes. Compare win rate to baseline.

### Stage 2 — Volume
- Change 2: Wider price filter
- Change 7: Patient entry
- Change 5: Self-learning blacklist

**Why second**: After Stage 1 proves entry quality, these increase trade volume safely.

**Test for**: Trade count up 2-3x without win rate dropping below 50%.

### Stage 3 — Aggressive (Highest Risk)
- Change 8: Smart pyramiding
- Change 3: Long-duration market fallback

**Why last**: Pyramiding can double exposure. Long-duration fallback is a different market type with its own learning curve.

**Test for**: Pyramiding only triggers in clearly winning positions. Fallback only kicks in during drought periods.

## Safety Nets

1. **Hard daily loss limit**: 20% of starting balance, auto-pause until next UTC day
2. **3-loss cooldown**: 15-minute pause after 3 consecutive losses
3. **Auto-revert**: If win rate drops below 40% over the most recent 10 trades, revert to baseline strategy and Telegram alert
4. **Telegram alerts**: Every trade entry, every fill, every loss
5. **Dashboard emergency stop**: Button on web dashboard sets `is_paused=1` in DB; bot reads this every cycle

## Database Changes

Add to `utils/fivemin_db.py`:

```sql
CREATE TABLE IF NOT EXISTS fm_signal_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence_bucket TEXT NOT NULL,
    phase TEXT NOT NULL,
    indicators_pattern TEXT NOT NULL,
    result TEXT NOT NULL,
    pnl REAL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fm_outcomes_pattern ON fm_signal_outcomes(asset, direction, confidence_bucket, phase, indicators_pattern, timestamp);
```

Modify `fm_trades`:

```sql
ALTER TABLE fm_trades ADD COLUMN pyramid_of INTEGER REFERENCES fm_trades(id);
ALTER TABLE fm_trades ADD COLUMN entry_asset_price REAL;
ALTER TABLE fm_trades ADD COLUMN is_fallback INTEGER DEFAULT 0;
```

## Testing Strategy

Each stage has its own test plan:

**Stage 1 tests** (in `tests/`):
- `test_confidence_scaled_sizing.py` — verify size table for all combos
- `test_trend_confirmation.py` — multi-timeframe alignment logic
- `test_limit_order_maker.py` — fair value calculation, cancel-on-timeout

**Stage 2 tests**:
- `test_wider_price_filter.py` — size scaling at different asks
- `test_patient_entry.py` — 30s wait + early exit on price escape
- `test_blacklist.py` — 2 losses on same pattern → blacklisted

**Stage 3 tests**:
- `test_pyramiding.py` — all 5 conditions must be true
- `test_long_duration_fallback.py` — triggers after 10min drought

## Success Criteria

After 1 week with all 8 changes deployed:
- Trade volume: 10-30 trades (vs current ~3/week)
- Win rate: ≥ 50%
- Net P&L: positive (target: +$5-15)
- Zero days hitting hard loss limit

## Out of Scope

- BinanceBot improvements
- New asset support (DOGE, LINK, etc.)
- Machine learning models
- Multi-account trading
- Web UI changes (existing dashboard handles new fields automatically)
