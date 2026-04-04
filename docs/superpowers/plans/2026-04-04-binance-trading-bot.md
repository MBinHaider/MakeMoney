# BinanceBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rapid BTC/ETH trading bot for Binance spot market with technical indicator signals, paper trading, and Telegram notifications.

**Architecture:** Separate bot (`binancebot.py`) in same repo as PolyBot, with its own `binance_modules/` directory. Shares `config.py`, `.env`, `utils/` (db, logger). SQLite database at `data/binancebot.db`. Async main loop polls Binance every 60s, computes RSI/MACD/BB, generates signals, executes paper trades, sends Telegram alerts.

**Tech Stack:** Python 3, aiohttp (existing), python-telegram-bot (existing), SQLite, hand-rolled indicators (no new deps).

**Spec:** `docs/superpowers/specs/2026-04-04-binance-trading-bot-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config.py` | **Modify** — Add Binance-specific config fields |
| `utils/binance_db.py` | **Create** — Schema + init for `data/binancebot.db` |
| `binance_modules/__init__.py` | **Create** — Package init |
| `binance_modules/market_data.py` | **Create** — Fetch candles + prices from Binance REST API |
| `binance_modules/indicators.py` | **Create** — RSI(14), MACD(12,26,9), Bollinger Bands(20,2) |
| `binance_modules/signal_engine.py` | **Create** — Combine indicators into buy/sell/hold with timeframe confirmation |
| `binance_modules/risk_manager.py` | **Create** — Position sizing, stop-loss, daily limits, cooldowns |
| `binance_modules/trade_executor.py` | **Create** — Paper + live order execution, trailing stops |
| `binance_modules/notifier.py` | **Create** — Telegram trade alerts, summaries, daily reports |
| `binancebot.py` | **Create** — Entry point, main loop, async task orchestration |
| `tests/test_indicators.py` | **Create** — Unit tests for indicator math |
| `tests/test_signal_engine.py` | **Create** — Unit tests for signal scoring |
| `tests/test_risk_manager.py` | **Create** — Unit tests for risk rules |
| `tests/test_trade_executor.py` | **Create** — Unit tests for paper trade execution |
| `tests/test_notifier_binance.py` | **Create** — Unit tests for message formatting |

---

### Task 1: Config + Database Schema

**Files:**
- Modify: `config.py`
- Create: `utils/binance_db.py`
- Test: `tests/test_binance_db.py`

- [ ] **Step 1: Write the failing test for database initialization**

```python
# tests/test_binance_db.py
import os
import tempfile
import pytest
from utils.binance_db import BINANCE_SCHEMA, init_binance_db
from utils.db import get_connection


def test_init_binance_db_creates_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_binance.db")
        init_binance_db(db_path)
        conn = get_connection(db_path)
        tables = [
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        conn.close()
        assert "candles" in tables
        assert "bn_signals" in tables
        assert "bn_trades" in tables
        assert "bn_portfolio" in tables


def test_init_binance_db_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_binance.db")
        init_binance_db(db_path)
        init_binance_db(db_path)  # should not raise
        conn = get_connection(db_path)
        tables = [
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        conn.close()
        assert "candles" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_binance_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'utils.binance_db'`

- [ ] **Step 3: Add Binance config to config.py**

Add after the existing `DB_PATH` line in `config.py`:

```python
    # Binance API
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    # BinanceBot trading
    BINANCE_TRADING_MODE = os.getenv("BINANCE_TRADING_MODE", "paper")
    BINANCE_PAIRS = ["BTCUSDT", "ETHUSDT"]
    BINANCE_CANDLE_INTERVAL_1M = "1m"
    BINANCE_CANDLE_INTERVAL_5M = "5m"
    BINANCE_POLL_INTERVAL_SEC = 60
    BINANCE_SUMMARY_INTERVAL_SEC = 900  # 15 minutes
    BINANCE_DAILY_REPORT_INTERVAL_SEC = 86400

    # BinanceBot risk
    BINANCE_MAX_PER_TRADE_PCT = 0.30
    BINANCE_STRONG_SIGNAL_PCT = 0.30  # 3-of-3 indicator agreement
    BINANCE_NORMAL_SIGNAL_PCT = 0.20  # 2-of-3 indicator agreement
    BINANCE_MAX_POSITIONS = 3
    BINANCE_STOP_LOSS_PCT = 0.01
    BINANCE_TAKE_PROFIT_PCT = 0.015
    BINANCE_TRAILING_STOP_STEP_PCT = 0.005
    BINANCE_DAILY_LOSS_LIMIT_PCT = 0.05
    BINANCE_CONSECUTIVE_LOSS_PAUSE = 3
    BINANCE_PAUSE_DURATION_MIN = 15
    BINANCE_MIN_TRADE_INTERVAL_SEC = 120
    BINANCE_FEE_PCT = 0.001
    BINANCE_SLIPPAGE_PCT = 0.001

    # BinanceBot portfolio
    BINANCE_STARTING_BALANCE = 45.00

    # BinanceBot database
    BINANCE_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "binancebot.db")
```

- [ ] **Step 4: Create utils/binance_db.py**

```python
# utils/binance_db.py
import os
import sqlite3
from utils.db import get_connection

BINANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    UNIQUE(symbol, interval, open_time)
);

CREATE TABLE IF NOT EXISTS bn_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    rsi REAL,
    macd REAL,
    macd_signal REAL,
    bb_upper REAL,
    bb_lower REAL,
    bb_mid REAL,
    score INTEGER DEFAULT 0,
    action TEXT DEFAULT 'hold'
);

CREATE TABLE IF NOT EXISTS bn_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    tp REAL NOT NULL,
    sl REAL NOT NULL,
    trailing_sl REAL,
    status TEXT DEFAULT 'open',
    exit_price REAL,
    exit_time TEXT,
    pnl REAL DEFAULT 0.0,
    fees REAL DEFAULT 0.0,
    reason TEXT DEFAULT '',
    signal_id INTEGER,
    FOREIGN KEY (signal_id) REFERENCES bn_signals(id)
);

CREATE TABLE IF NOT EXISTS bn_portfolio (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    balance REAL NOT NULL,
    starting_balance REAL NOT NULL,
    peak_balance REAL NOT NULL,
    daily_pnl REAL DEFAULT 0.0,
    daily_pnl_date TEXT DEFAULT '',
    total_trades INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0.0,
    consecutive_losses INTEGER DEFAULT 0,
    last_trade_time TEXT DEFAULT '',
    is_paused INTEGER DEFAULT 0,
    pause_until TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval ON candles(symbol, interval, open_time);
CREATE INDEX IF NOT EXISTS idx_bn_signals_timestamp ON bn_signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_bn_trades_status ON bn_trades(status);
CREATE INDEX IF NOT EXISTS idx_bn_trades_timestamp ON bn_trades(timestamp);
"""


def init_binance_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(BINANCE_SCHEMA)
    conn.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_binance_db.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add config.py utils/binance_db.py tests/test_binance_db.py
git commit -m "feat(binance): add config and database schema for BinanceBot"
```

---

### Task 2: Market Data Module

**Files:**
- Create: `binance_modules/__init__.py`
- Create: `binance_modules/market_data.py`
- Test: `tests/test_market_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_data.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from binance_modules.market_data import MarketData
from config import Config


@pytest.fixture
def config():
    return Config()


@pytest.fixture
def sample_klines_response():
    """Binance klines response: [open_time, open, high, low, close, volume, ...]"""
    return [
        [1700000000000, "42000.00", "42100.00", "41900.00", "42050.00", "100.5",
         1700000059999, "4200000.00", 500, "50.0", "2100000.00", "0"],
        [1700000060000, "42050.00", "42200.00", "42000.00", "42150.00", "120.3",
         1700000119999, "5060000.00", 600, "60.0", "2530000.00", "0"],
    ]


def test_parse_klines(config, sample_klines_response):
    md = MarketData(config)
    candles = md.parse_klines(sample_klines_response)
    assert len(candles) == 2
    assert candles[0]["open"] == 42000.00
    assert candles[0]["high"] == 42100.00
    assert candles[0]["low"] == 41900.00
    assert candles[0]["close"] == 42050.00
    assert candles[0]["volume"] == 100.5
    assert candles[0]["open_time"] == 1700000000000


@pytest.mark.asyncio
async def test_fetch_klines_calls_api(config, sample_klines_response):
    md = MarketData(config)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=sample_klines_response)

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        candles = await md.fetch_klines("BTCUSDT", "1m", limit=2)

    assert len(candles) == 2
    assert candles[1]["close"] == 42150.00
    mock_session.get.assert_called_once()
    call_url = mock_session.get.call_args[0][0]
    assert "/api/v3/klines" in call_url


@pytest.mark.asyncio
async def test_fetch_price(config):
    md = MarketData(config)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"symbol": "BTCUSDT", "price": "42050.00"})

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        price = await md.fetch_price("BTCUSDT")

    assert price == 42050.00
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_market_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'binance_modules'`

- [ ] **Step 3: Create binance_modules package and market_data.py**

```python
# binance_modules/__init__.py
```

```python
# binance_modules/market_data.py
import aiohttp
from utils.logger import get_logger
from config import Config

log = get_logger("binance_market_data")


class MarketData:
    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.BINANCE_API_URL

    def parse_klines(self, raw: list) -> list[dict]:
        candles = []
        for k in raw:
            candles.append({
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        return candles

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 100) -> list[dict]:
        url = f"{self.base_url}/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with aiohttp.ClientSession() as session:
            resp = await session.get(url, params=params)
            if resp.status != 200:
                log.error(f"Binance klines error: {resp.status}")
                return []
            raw = await resp.json()
            return self.parse_klines(raw)

    async def fetch_price(self, symbol: str) -> float:
        url = f"{self.base_url}/api/v3/ticker/price"
        params = {"symbol": symbol}
        async with aiohttp.ClientSession() as session:
            resp = await session.get(url, params=params)
            if resp.status != 200:
                log.error(f"Binance price error: {resp.status}")
                return 0.0
            data = await resp.json()
            return float(data["price"])

    async def fetch_all_candles(self) -> dict[str, dict[str, list[dict]]]:
        """Fetch 1m and 5m candles for all configured pairs.
        Returns: {symbol: {"1m": [candles], "5m": [candles]}}
        """
        result = {}
        for symbol in self.config.BINANCE_PAIRS:
            candles_1m = await self.fetch_klines(
                symbol, self.config.BINANCE_CANDLE_INTERVAL_1M, limit=100
            )
            candles_5m = await self.fetch_klines(
                symbol, self.config.BINANCE_CANDLE_INTERVAL_5M, limit=100
            )
            result[symbol] = {"1m": candles_1m, "5m": candles_5m}
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_market_data.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/__init__.py binance_modules/market_data.py tests/test_market_data.py
git commit -m "feat(binance): add market data module for Binance API candles and prices"
```

---

### Task 3: Technical Indicators

**Files:**
- Create: `binance_modules/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_indicators.py
import pytest
from binance_modules.indicators import compute_rsi, compute_macd, compute_bollinger_bands, compute_all


def _make_closes(values: list[float]) -> list[dict]:
    return [{"close": v} for v in values]


class TestRSI:
    def test_rsi_with_all_gains(self):
        # 15 increasing prices -> RSI should be near 100
        closes = _make_closes([float(i) for i in range(1, 16)])
        rsi = compute_rsi(closes, period=14)
        assert rsi > 95

    def test_rsi_with_all_losses(self):
        # 15 decreasing prices -> RSI should be near 0
        closes = _make_closes([float(i) for i in range(15, 0, -1)])
        rsi = compute_rsi(closes, period=14)
        assert rsi < 5

    def test_rsi_with_mixed_data(self):
        # alternating up/down should give RSI near 50
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
        # Strong uptrend -> MACD line should be above signal
        closes = _make_closes([float(100 + i * 2) for i in range(35)])
        macd_line, signal_line, histogram = compute_macd(closes)
        assert macd_line is not None
        assert histogram > 0  # bullish

    def test_macd_bearish_trend(self):
        # Strong downtrend -> histogram should be negative
        closes = _make_closes([float(200 - i * 2) for i in range(35)])
        macd_line, signal_line, histogram = compute_macd(closes)
        assert histogram < 0  # bearish

    def test_macd_insufficient_data(self):
        closes = _make_closes([100, 101, 102])
        result = compute_macd(closes)
        assert result == (None, None, None)


class TestBollingerBands:
    def test_bb_basic(self):
        # Stable prices -> bands should be tight around price
        closes = _make_closes([100.0] * 25)
        upper, mid, lower = compute_bollinger_bands(closes, period=20, num_std=2)
        assert mid == pytest.approx(100.0)
        assert upper == pytest.approx(100.0)  # no std dev when all same
        assert lower == pytest.approx(100.0)

    def test_bb_with_volatility(self):
        # Volatile prices -> bands should be wide
        closes = _make_closes([100, 110, 90, 110, 90, 100, 110, 90, 110, 90,
                               100, 110, 90, 110, 90, 100, 110, 90, 110, 90,
                               100, 110, 90, 110, 100])
        upper, mid, lower = compute_bollinger_bands(closes, period=20, num_std=2)
        assert upper > mid > lower
        assert upper - lower > 10  # significant spread

    def test_bb_insufficient_data(self):
        closes = _make_closes([100, 101])
        result = compute_bollinger_bands(closes, period=20, num_std=2)
        assert result == (None, None, None)


class TestComputeAll:
    def test_compute_all_returns_all_indicators(self):
        # 40 candles to have enough data for all indicators
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_indicators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'binance_modules.indicators'`

- [ ] **Step 3: Implement indicators.py**

```python
# binance_modules/indicators.py
"""Hand-rolled technical indicators. No external dependencies."""

import math


def compute_rsi(candles: list[dict], period: int = 14) -> float | None:
    """Compute RSI from a list of candle dicts with 'close' key.
    Returns RSI value 0-100, or None if insufficient data.
    """
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

    # Smoothed RSI using Wilder's method
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    """Compute Exponential Moving Average."""
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
    """Compute MACD line, signal line, and histogram.
    Returns (macd_line, signal_line, histogram) or (None, None, None).
    """
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
    """Compute Bollinger Bands (upper, middle, lower).
    Returns (upper, mid, lower) or (None, None, None).
    """
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
    """Compute all indicators on a list of candles.
    Returns dict with rsi, macd, macd_signal, macd_histogram, bb_upper, bb_mid, bb_lower.
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_indicators.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/indicators.py tests/test_indicators.py
git commit -m "feat(binance): add hand-rolled RSI, MACD, Bollinger Bands indicators"
```

---

### Task 4: Signal Engine

**Files:**
- Create: `binance_modules/signal_engine.py`
- Test: `tests/test_signal_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_signal_engine.py
import pytest
from binance_modules.signal_engine import SignalEngine
from config import Config


@pytest.fixture
def engine():
    return SignalEngine(Config())


class TestSignalGeneration:
    def test_strong_buy_all_three_agree(self, engine):
        indicators_1m = {
            "rsi": 25,  # < 30 -> buy
            "macd_histogram": 0.5,  # positive -> buy (crossed above)
            "bb_lower": 100, "bb_mid": 105, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 35,  # not bearish (< 70)
            "macd_histogram": 0.3,  # positive -> bullish trend
            "bb_lower": 99, "bb_mid": 104, "bb_upper": 109,
            "macd": 0.8, "macd_signal": 0.5,
        }
        current_price = 99.5  # below BB lower band -> buy
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "buy"
        assert signal["strength"] == "strong"
        assert signal["score"] == 3

    def test_normal_buy_two_of_three(self, engine):
        indicators_1m = {
            "rsi": 25,  # < 30 -> buy
            "macd_histogram": 0.5,  # positive -> buy
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 40,
            "macd_histogram": 0.2,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": 0.5, "macd_signal": 0.3,
        }
        current_price = 95.0  # not at BB lower band
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "buy"
        assert signal["strength"] == "normal"
        assert signal["score"] == 2

    def test_hold_when_only_one_indicator(self, engine):
        indicators_1m = {
            "rsi": 25,  # < 30 -> buy
            "macd_histogram": -0.5,  # negative -> not buy
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": -1.0, "macd_signal": -0.5,
        }
        indicators_5m = {
            "rsi": 50,
            "macd_histogram": -0.2,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -0.5, "macd_signal": -0.3,
        }
        current_price = 100.0
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "hold"

    def test_hold_when_5m_trend_bearish(self, engine):
        """Even if 1m says buy, reject when 5m is strongly bearish."""
        indicators_1m = {
            "rsi": 25,
            "macd_histogram": 0.5,
            "bb_lower": 100, "bb_mid": 105, "bb_upper": 110,
            "macd": 1.0, "macd_signal": 0.5,
        }
        indicators_5m = {
            "rsi": 75,  # > 70 -> bearish (overbought on higher timeframe)
            "macd_histogram": -2.0,  # strong bearish
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -1.0, "macd_signal": 1.0,
        }
        current_price = 99.5
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "hold"

    def test_sell_signal_overbought(self, engine):
        indicators_1m = {
            "rsi": 75,  # > 70 -> sell
            "macd_histogram": -0.5,  # negative -> sell
            "bb_lower": 90, "bb_mid": 100, "bb_upper": 110,
            "macd": -1.0, "macd_signal": -0.5,
        }
        indicators_5m = {
            "rsi": 65,
            "macd_histogram": -0.3,
            "bb_lower": 89, "bb_mid": 99, "bb_upper": 109,
            "macd": -0.5, "macd_signal": -0.3,
        }
        current_price = 111.0  # above BB upper
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, current_price)
        assert signal["action"] == "sell"

    def test_returns_none_indicators(self, engine):
        """When indicators have None values (insufficient data), return hold."""
        indicators_1m = {
            "rsi": None, "macd_histogram": None,
            "bb_lower": None, "bb_mid": None, "bb_upper": None,
            "macd": None, "macd_signal": None,
        }
        indicators_5m = {
            "rsi": None, "macd_histogram": None,
            "bb_lower": None, "bb_mid": None, "bb_upper": None,
            "macd": None, "macd_signal": None,
        }
        signal = engine.evaluate("BTCUSDT", indicators_1m, indicators_5m, 100.0)
        assert signal["action"] == "hold"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement signal_engine.py**

```python
# binance_modules/signal_engine.py
from utils.logger import get_logger
from config import Config

log = get_logger("binance_signal_engine")


class SignalEngine:
    def __init__(self, config: Config):
        self.config = config

    def _count_buy_signals(self, indicators: dict, current_price: float) -> int:
        """Count how many of the 3 indicators say 'buy'."""
        count = 0
        rsi = indicators.get("rsi")
        if rsi is not None and rsi < 30:
            count += 1

        histogram = indicators.get("macd_histogram")
        if histogram is not None and histogram > 0:
            count += 1

        bb_lower = indicators.get("bb_lower")
        if bb_lower is not None and current_price <= bb_lower:
            count += 1

        return count

    def _count_sell_signals(self, indicators: dict, current_price: float) -> int:
        """Count how many of the 3 indicators say 'sell'."""
        count = 0
        rsi = indicators.get("rsi")
        if rsi is not None and rsi > 70:
            count += 1

        histogram = indicators.get("macd_histogram")
        if histogram is not None and histogram < 0:
            count += 1

        bb_upper = indicators.get("bb_upper")
        if bb_upper is not None and current_price >= bb_upper:
            count += 1

        return count

    def _is_5m_bearish(self, indicators_5m: dict) -> bool:
        """Check if the 5m timeframe is strongly bearish."""
        rsi = indicators_5m.get("rsi")
        histogram = indicators_5m.get("macd_histogram")
        # Bearish if RSI overbought AND MACD histogram negative
        if rsi is not None and rsi > 70 and histogram is not None and histogram < 0:
            return True
        return False

    def _is_5m_bullish_or_neutral(self, indicators_5m: dict) -> bool:
        """Check if 5m trend is not bearish (allows buy entries)."""
        return not self._is_5m_bearish(indicators_5m)

    def evaluate(
        self,
        symbol: str,
        indicators_1m: dict,
        indicators_5m: dict,
        current_price: float,
    ) -> dict:
        """Evaluate signals from both timeframes.
        Returns: {action: buy|sell|hold, strength: strong|normal, score: 0-3, symbol, ...}
        """
        buy_count_1m = self._count_buy_signals(indicators_1m, current_price)
        sell_count_1m = self._count_sell_signals(indicators_1m, current_price)

        # Check buy signals
        if buy_count_1m >= 2 and self._is_5m_bullish_or_neutral(indicators_5m):
            strength = "strong" if buy_count_1m == 3 else "normal"
            log.info(f"{symbol} BUY signal: {buy_count_1m}/3 indicators, strength={strength}")
            return {
                "action": "buy",
                "strength": strength,
                "score": buy_count_1m,
                "symbol": symbol,
                "price": current_price,
                "indicators_1m": indicators_1m,
                "indicators_5m": indicators_5m,
            }

        # Check sell signals
        if sell_count_1m >= 2:
            strength = "strong" if sell_count_1m == 3 else "normal"
            log.info(f"{symbol} SELL signal: {sell_count_1m}/3 indicators, strength={strength}")
            return {
                "action": "sell",
                "strength": strength,
                "score": sell_count_1m,
                "symbol": symbol,
                "price": current_price,
                "indicators_1m": indicators_1m,
                "indicators_5m": indicators_5m,
            }

        return {
            "action": "hold",
            "strength": "none",
            "score": 0,
            "symbol": symbol,
            "price": current_price,
            "indicators_1m": indicators_1m,
            "indicators_5m": indicators_5m,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_signal_engine.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/signal_engine.py tests/test_signal_engine.py
git commit -m "feat(binance): add signal engine with 2-of-3 indicator agreement and 5m confirmation"
```

---

### Task 5: Risk Manager

**Files:**
- Create: `binance_modules/risk_manager.py`
- Test: `tests/test_risk_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_risk_manager.py
import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from binance_modules.risk_manager import BinanceRiskManager
from utils.binance_db import init_binance_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = Config()
        config.BINANCE_DB_PATH = db_path
        init_binance_db(db_path)
        rm = BinanceRiskManager(config)
        rm.init_portfolio(45.0)
        yield rm, db_path


class TestInitPortfolio:
    def test_init_creates_portfolio(self, setup_db):
        rm, db_path = setup_db
        status = rm.get_status()
        assert status["balance"] == 45.0
        assert status["starting_balance"] == 45.0
        assert status["total_trades"] == 0
        assert status["is_paused"] is False


class TestCanTrade:
    def test_can_trade_when_clear(self, setup_db):
        rm, _ = setup_db
        result = rm.can_trade()
        assert result["allowed"] is True

    def test_blocked_when_paused(self, setup_db):
        rm, _ = setup_db
        rm.pause()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "paused" in result["reason"].lower()

    def test_blocked_at_max_positions(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            conn.execute(
                "INSERT INTO bn_trades (timestamp, symbol, side, price, size, tp, sl, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, "open"),
            )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "position" in result["reason"].lower()

    def test_blocked_by_daily_loss_limit(self, setup_db):
        rm, _ = setup_db
        # Lose 5% = $2.25 on $45
        rm.record_trade_outcome(-2.25)
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "daily" in result["reason"].lower()

    def test_blocked_by_consecutive_losses(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-0.10)
        rm.record_trade_outcome(-0.10)
        rm.record_trade_outcome(-0.10)
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "consecutive" in result["reason"].lower()

    def test_blocked_by_min_trade_interval(self, setup_db):
        rm, db_path = setup_db
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE bn_portfolio SET last_trade_time = ? WHERE id = 1", (now,)
        )
        conn.commit()
        conn.close()
        result = rm.can_trade()
        assert result["allowed"] is False
        assert "interval" in result["reason"].lower()


class TestPositionSizing:
    def test_normal_signal_size(self, setup_db):
        rm, _ = setup_db
        size = rm.calc_position_size("normal")
        # 20% of $45 = $9
        assert size == pytest.approx(9.0)

    def test_strong_signal_size(self, setup_db):
        rm, _ = setup_db
        size = rm.calc_position_size("strong")
        # 30% of $45 = $13.5
        assert size == pytest.approx(13.5)


class TestRecordOutcome:
    def test_win_updates_portfolio(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(0.50)
        status = rm.get_status()
        assert status["balance"] == 45.50
        assert status["total_trades"] == 1
        assert status["total_wins"] == 1
        assert status["consecutive_losses"] == 0

    def test_loss_updates_portfolio(self, setup_db):
        rm, _ = setup_db
        rm.record_trade_outcome(-0.15)
        status = rm.get_status()
        assert status["balance"] == 44.85
        assert status["total_trades"] == 1
        assert status["total_wins"] == 0
        assert status["consecutive_losses"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_risk_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement risk_manager.py**

```python
# binance_modules/risk_manager.py
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("binance_risk_manager")


class BinanceRiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.BINANCE_DB_PATH

    def _get_portfolio(self) -> dict:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("BinanceBot portfolio not initialized.")
        return dict(row)

    def init_portfolio(self, starting_balance: float) -> None:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO bn_portfolio
               (id, balance, starting_balance, peak_balance,
                daily_pnl, daily_pnl_date, total_trades, total_wins,
                total_pnl, consecutive_losses, last_trade_time,
                is_paused, pause_until, updated_at)
               VALUES (1, ?, ?, ?, 0.0, ?, 0, 0, 0.0, 0, '', 0, '', ?)""",
            (starting_balance, starting_balance, starting_balance, now[:10], now),
        )
        conn.commit()
        conn.close()
        log.info(f"BinanceBot portfolio initialized: ${starting_balance}")

    def can_trade(self) -> dict:
        p = self._get_portfolio()

        if p["is_paused"]:
            # Check if pause has expired
            if p["pause_until"]:
                try:
                    pause_end = datetime.fromisoformat(p["pause_until"])
                    if datetime.now(timezone.utc) >= pause_end:
                        self.resume()
                        p = self._get_portfolio()
                    else:
                        return {"allowed": False, "reason": f"Paused until {p['pause_until']}"}
                except ValueError:
                    pass
            else:
                return {"allowed": False, "reason": "Trading is paused"}

        # Check daily loss limit
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        daily_loss_pct = -daily_pnl / p["starting_balance"] if p["starting_balance"] > 0 else 0
        if daily_loss_pct >= self.config.BINANCE_DAILY_LOSS_LIMIT_PCT:
            return {"allowed": False, "reason": f"Daily loss limit: {daily_loss_pct:.1%}"}

        # Check consecutive losses
        if p["consecutive_losses"] >= self.config.BINANCE_CONSECUTIVE_LOSS_PAUSE:
            pause_until = datetime.now(timezone.utc) + timedelta(minutes=self.config.BINANCE_PAUSE_DURATION_MIN)
            self._set_pause(pause_until)
            return {"allowed": False, "reason": f"Consecutive losses ({p['consecutive_losses']}), pausing {self.config.BINANCE_PAUSE_DURATION_MIN}min"}

        # Check max positions
        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
        ).fetchone()["cnt"]
        conn.close()
        if open_count >= self.config.BINANCE_MAX_POSITIONS:
            return {"allowed": False, "reason": f"Max positions: {open_count}/{self.config.BINANCE_MAX_POSITIONS}"}

        # Check min trade interval
        if p["last_trade_time"]:
            try:
                last_trade = datetime.fromisoformat(p["last_trade_time"])
                elapsed = (datetime.now(timezone.utc) - last_trade).total_seconds()
                if elapsed < self.config.BINANCE_MIN_TRADE_INTERVAL_SEC:
                    remaining = int(self.config.BINANCE_MIN_TRADE_INTERVAL_SEC - elapsed)
                    return {"allowed": False, "reason": f"Min trade interval: {remaining}s remaining"}
            except ValueError:
                pass

        return {"allowed": True, "reason": "OK"}

    def calc_position_size(self, strength: str) -> float:
        p = self._get_portfolio()
        balance = p["balance"]
        if strength == "strong":
            pct = self.config.BINANCE_STRONG_SIGNAL_PCT
        else:
            pct = self.config.BINANCE_NORMAL_SIGNAL_PCT
        size = round(balance * pct, 2)
        return size

    def record_trade_outcome(self, pnl: float) -> None:
        conn = get_connection(self.db_path)
        p = dict(conn.execute("SELECT * FROM bn_portfolio WHERE id = 1").fetchone())
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        new_balance = p["balance"] + pnl
        new_peak = max(p["peak_balance"], new_balance)
        total_trades = p["total_trades"] + 1
        total_wins = p["total_wins"] + (1 if pnl > 0 else 0)
        total_pnl = p["total_pnl"] + pnl
        consecutive_losses = 0 if pnl > 0 else p["consecutive_losses"] + 1

        if p["daily_pnl_date"] == today:
            daily_pnl = p["daily_pnl"] + pnl
        else:
            daily_pnl = pnl

        conn.execute(
            """UPDATE bn_portfolio SET
               balance = ?, peak_balance = ?, daily_pnl = ?, daily_pnl_date = ?,
               total_trades = ?, total_wins = ?, total_pnl = ?,
               consecutive_losses = ?, last_trade_time = ?, updated_at = ?
               WHERE id = 1""",
            (new_balance, new_peak, daily_pnl, today, total_trades, total_wins,
             total_pnl, consecutive_losses, now.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()
        log.info(f"Trade outcome: PnL=${pnl:.2f} | Balance=${new_balance:.2f}")

    def _set_pause(self, until: datetime) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE bn_portfolio SET is_paused = 1, pause_until = ? WHERE id = 1",
            (until.isoformat(),),
        )
        conn.commit()
        conn.close()

    def pause(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE bn_portfolio SET is_paused = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        log.warning("BinanceBot trading PAUSED")

    def resume(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute(
            "UPDATE bn_portfolio SET is_paused = 0, pause_until = '', consecutive_losses = 0 WHERE id = 1"
        )
        conn.commit()
        conn.close()
        log.info("BinanceBot trading RESUMED")

    def get_status(self) -> dict:
        p = self._get_portfolio()
        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bn_trades WHERE status = 'open'"
        ).fetchone()["cnt"]
        conn.close()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        win_rate = p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0

        return {
            "balance": p["balance"],
            "starting_balance": p["starting_balance"],
            "peak_balance": p["peak_balance"],
            "total_pnl": p["total_pnl"],
            "daily_pnl": daily_pnl,
            "total_trades": p["total_trades"],
            "total_wins": p["total_wins"],
            "win_rate": win_rate,
            "open_positions": open_count,
            "consecutive_losses": p["consecutive_losses"],
            "is_paused": bool(p["is_paused"]),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_risk_manager.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/risk_manager.py tests/test_risk_manager.py
git commit -m "feat(binance): add risk manager with position sizing, daily limits, and cooldowns"
```

---

### Task 6: Trade Executor

**Files:**
- Create: `binance_modules/trade_executor.py`
- Test: `tests/test_trade_executor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trade_executor.py
import os
import tempfile
import pytest
from datetime import datetime, timezone
from binance_modules.trade_executor import BinanceTradeExecutor
from utils.binance_db import init_binance_db
from utils.db import get_connection
from config import Config


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        config = Config()
        config.BINANCE_DB_PATH = db_path
        config.BINANCE_TRADING_MODE = "paper"
        init_binance_db(db_path)
        executor = BinanceTradeExecutor(config)
        yield executor, db_path


class TestPaperTrade:
    def test_paper_buy_creates_trade(self, setup):
        executor, db_path = setup
        signal = {
            "action": "buy", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        assert result["status"] == "filled"
        assert result["side"] == "buy"
        assert result["size"] == 10.0
        assert result["tp"] == pytest.approx(42000 * 1.015)
        assert result["sl"] == pytest.approx(42000 * 0.99)

        conn = get_connection(db_path)
        trade = conn.execute("SELECT * FROM bn_trades WHERE id = ?", (result["trade_id"],)).fetchone()
        conn.close()
        assert trade is not None
        assert trade["status"] == "open"
        assert trade["symbol"] == "BTCUSDT"

    def test_paper_buy_applies_slippage(self, setup):
        executor, _ = setup
        signal = {
            "action": "buy", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        # Buy slippage: price goes up by 0.1%
        expected_price = 42000.0 * (1 + 0.001)
        assert result["entry_price"] == pytest.approx(expected_price)

    def test_paper_sell_applies_slippage(self, setup):
        executor, _ = setup
        signal = {
            "action": "sell", "symbol": "BTCUSDT", "price": 42000.0,
            "strength": "normal", "score": 2,
        }
        result = executor.execute_trade(signal, size=10.0)
        # Sell slippage: price goes down by 0.1%
        expected_price = 42000.0 * (1 - 0.001)
        assert result["entry_price"] == pytest.approx(expected_price)


class TestCheckOpenPositions:
    def test_take_profit_hit(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        # Current price above TP
        closed = executor.check_open_positions({"BTCUSDT": 42700.0})
        assert len(closed) == 1
        assert closed[0]["reason"] == "take_profit"
        assert closed[0]["pnl"] > 0

    def test_stop_loss_hit(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        closed = executor.check_open_positions({"BTCUSDT": 41500.0})
        assert len(closed) == 1
        assert closed[0]["reason"] == "stop_loss"
        assert closed[0]["pnl"] < 0

    def test_trailing_stop_updates(self, setup):
        executor, db_path = setup
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, "BTCUSDT", "buy", 42000, 10, 42630, 41580, 41580, "open"),
        )
        conn.commit()
        conn.close()

        # Price went up but not to TP — trailing stop should move
        closed = executor.check_open_positions({"BTCUSDT": 42400.0})
        assert len(closed) == 0  # not closed yet

        conn = get_connection(db_path)
        trade = conn.execute("SELECT trailing_sl FROM bn_trades WHERE id = 1").fetchone()
        conn.close()
        # Trailing stop should have moved up: 42400 * (1 - 0.005) = 42188
        assert trade["trailing_sl"] > 41580
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_trade_executor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement trade_executor.py**

```python
# binance_modules/trade_executor.py
from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("binance_trade_executor")


class BinanceTradeExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.BINANCE_DB_PATH

    def execute_trade(self, signal: dict, size: float) -> dict:
        if self.config.BINANCE_TRADING_MODE == "paper":
            return self._execute_paper(signal, size)
        else:
            return self._execute_live(signal, size)

    def _execute_paper(self, signal: dict, size: float) -> dict:
        price = signal["price"]
        side = signal["action"]  # "buy" or "sell"
        symbol = signal["symbol"]

        # Apply slippage
        if side == "buy":
            entry_price = price * (1 + self.config.BINANCE_SLIPPAGE_PCT)
            tp = entry_price * (1 + self.config.BINANCE_TAKE_PROFIT_PCT)
            sl = entry_price * (1 - self.config.BINANCE_STOP_LOSS_PCT)
        else:
            entry_price = price * (1 - self.config.BINANCE_SLIPPAGE_PCT)
            tp = entry_price * (1 - self.config.BINANCE_TAKE_PROFIT_PCT)
            sl = entry_price * (1 + self.config.BINANCE_STOP_LOSS_PCT)

        fees = size * self.config.BINANCE_FEE_PCT
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO bn_trades
               (timestamp, symbol, side, price, size, tp, sl, trailing_sl, status, fees)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
            (now, symbol, side, entry_price, size, tp, sl, sl, fees),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(f"PAPER {side.upper()} {symbol} ${size:.2f} @ {entry_price:.2f} | TP:{tp:.2f} SL:{sl:.2f}")
        return {
            "trade_id": trade_id,
            "status": "filled",
            "side": side,
            "symbol": symbol,
            "entry_price": entry_price,
            "size": size,
            "tp": tp,
            "sl": sl,
            "fees": fees,
        }

    def _execute_live(self, signal: dict, size: float) -> dict:
        # TODO: Implement when moving to live mode
        # Will use Binance API: POST /api/v3/order with HMAC signature
        log.warning("Live trading not yet implemented")
        return {"status": "error", "reason": "Live trading not implemented"}

    def check_open_positions(self, current_prices: dict[str, float]) -> list[dict]:
        """Check all open trades against current prices.
        Closes trades that hit TP/SL/trailing stop.
        Updates trailing stops for profitable positions.
        Returns list of closed trade dicts.
        """
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open'"
        ).fetchall()

        closed = []
        now = datetime.now(timezone.utc).isoformat()

        for trade in open_trades:
            trade = dict(trade)
            symbol = trade["symbol"]
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue

            side = trade["side"]
            tp = trade["tp"]
            sl = trade["sl"]
            trailing_sl = trade["trailing_sl"] or sl
            entry_price = trade["price"]
            size = trade["size"]

            reason = None
            exit_price = current_price

            if side == "buy":
                # Check take-profit
                if current_price >= tp:
                    reason = "take_profit"
                # Check trailing stop (or original stop-loss)
                elif current_price <= trailing_sl:
                    reason = "stop_loss" if trailing_sl == sl else "trailing_stop"
                else:
                    # Update trailing stop if price moved up
                    new_trailing = current_price * (1 - self.config.BINANCE_TRAILING_STOP_STEP_PCT)
                    if new_trailing > trailing_sl:
                        conn.execute(
                            "UPDATE bn_trades SET trailing_sl = ? WHERE id = ?",
                            (new_trailing, trade["id"]),
                        )
            else:  # sell/short
                if current_price <= tp:
                    reason = "take_profit"
                elif current_price >= trailing_sl:
                    reason = "stop_loss" if trailing_sl == sl else "trailing_stop"
                else:
                    new_trailing = current_price * (1 + self.config.BINANCE_TRAILING_STOP_STEP_PCT)
                    if new_trailing < trailing_sl:
                        conn.execute(
                            "UPDATE bn_trades SET trailing_sl = ? WHERE id = ?",
                            (new_trailing, trade["id"]),
                        )

            if reason:
                # Calculate P&L
                if side == "buy":
                    pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price
                pnl = size * pnl_pct - trade["fees"]

                conn.execute(
                    """UPDATE bn_trades SET
                       status = 'closed', exit_price = ?, exit_time = ?,
                       pnl = ?, reason = ?
                       WHERE id = ?""",
                    (exit_price, now, round(pnl, 4), reason, trade["id"]),
                )

                hold_time = ""
                try:
                    entry_time = datetime.fromisoformat(trade["timestamp"])
                    delta = datetime.fromisoformat(now) - entry_time
                    minutes = int(delta.total_seconds() / 60)
                    hold_time = f"{minutes}m"
                except (ValueError, TypeError):
                    pass

                closed.append({
                    "trade_id": trade["id"],
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "size": size,
                    "pnl": round(pnl, 4),
                    "reason": reason,
                    "hold_time": hold_time,
                })
                log.info(f"CLOSED {symbol} {side}: {reason} | PnL: ${pnl:.4f}")

        conn.commit()
        conn.close()
        return closed

    def close_by_signal(self, symbol: str, current_price: float, reason: str = "opposing_signal") -> list[dict]:
        """Close all open positions for a symbol due to opposing signal."""
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open' AND symbol = ?",
            (symbol,),
        ).fetchall()

        closed = []
        now = datetime.now(timezone.utc).isoformat()

        for trade in open_trades:
            trade = dict(trade)
            entry_price = trade["price"]
            side = trade["side"]
            size = trade["size"]

            if side == "buy":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            pnl = size * pnl_pct - trade["fees"]

            conn.execute(
                """UPDATE bn_trades SET
                   status = 'closed', exit_price = ?, exit_time = ?,
                   pnl = ?, reason = ?
                   WHERE id = ?""",
                (current_price, now, round(pnl, 4), reason, trade["id"]),
            )
            closed.append({
                "trade_id": trade["id"],
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "exit_price": current_price,
                "size": size,
                "pnl": round(pnl, 4),
                "reason": reason,
            })

        conn.commit()
        conn.close()
        return closed

    def get_open_positions(self) -> list[dict]:
        conn = get_connection(self.db_path)
        trades = conn.execute(
            "SELECT * FROM bn_trades WHERE status = 'open' ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()
        return [dict(t) for t in trades]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_trade_executor.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/trade_executor.py tests/test_trade_executor.py
git commit -m "feat(binance): add trade executor with paper mode, trailing stops, and TP/SL"
```

---

### Task 7: Telegram Notifier

**Files:**
- Create: `binance_modules/notifier.py`
- Test: `tests/test_notifier_binance.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notifier_binance.py
import pytest
from binance_modules.notifier import BinanceNotifier
from config import Config


@pytest.fixture
def notifier():
    return BinanceNotifier(Config())


class TestFormatBuyAlert:
    def test_buy_alert_format(self, notifier):
        trade = {
            "side": "buy", "symbol": "BTCUSDT", "entry_price": 68432.50,
            "size": 12.00, "tp": 69458.85, "sl": 67748.18,
        }
        indicators = {"rsi": 28, "macd_histogram": 0.5}
        status = {"open_positions": 2, "balance": 47.32}
        msg = notifier.format_buy_alert(trade, indicators, status)
        assert "BinanceBot" in msg
        assert "BUY" in msg
        assert "BTCUSDT" in msg
        assert "68,432.50" in msg
        assert "12.00" in msg


class TestFormatSellAlert:
    def test_sell_alert_format(self, notifier):
        closed = {
            "symbol": "ETHUSDT", "exit_price": 3521.40,
            "pnl": 0.38, "hold_time": "7m", "reason": "take_profit",
        }
        status = {"open_positions": 1, "balance": 47.70}
        msg = notifier.format_sell_alert(closed, status)
        assert "BinanceBot" in msg
        assert "SELL" in msg or "CLOSED" in msg
        assert "ETHUSDT" in msg
        assert "0.38" in msg


class TestFormatSummary:
    def test_summary_format(self, notifier):
        status = {
            "balance": 47.70, "starting_balance": 45.00,
            "daily_pnl": 2.70, "total_trades": 8, "total_wins": 5,
            "win_rate": 0.625, "open_positions": 1, "is_paused": False,
        }
        open_trades = [
            {"symbol": "BTCUSDT", "side": "buy", "price": 68432, "size": 12},
        ]
        msg = notifier.format_summary(status, open_trades)
        assert "BinanceBot" in msg
        assert "47.70" in msg
        assert "45.00" in msg


class TestFormatDailyReport:
    def test_daily_report_format(self, notifier):
        status = {
            "balance": 47.70, "starting_balance": 45.00,
            "daily_pnl": 2.70, "total_pnl": 2.70,
            "total_trades": 14, "total_wins": 9,
            "win_rate": 0.643, "open_positions": 0,
        }
        today_trades = [
            {"symbol": "ETHUSDT", "pnl": 0.52},
            {"symbol": "BTCUSDT", "pnl": -0.14},
        ]
        msg = notifier.format_daily_report(status, today_trades)
        assert "BinanceBot" in msg
        assert "Daily" in msg
        assert "47.70" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_notifier_binance.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement notifier.py**

```python
# binance_modules/notifier.py
import aiohttp
from utils.logger import get_logger
from config import Config

log = get_logger("binance_notifier")


class BinanceNotifier:
    def __init__(self, config: Config):
        self.config = config
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.token = config.TELEGRAM_BOT_TOKEN

    async def send_message(self, text: str) -> None:
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                resp = await session.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                data = await resp.json()
                if not data.get("ok"):
                    log.error(f"Telegram error: {data.get('description', 'unknown')}")
        except Exception as e:
            log.error(f"Telegram send failed: {e}")

    def format_buy_alert(self, trade: dict, indicators: dict, status: dict) -> str:
        symbol = trade["symbol"]
        price = trade["entry_price"]
        size = trade["size"]
        tp = trade["tp"]
        sl = trade["sl"]
        tp_pct = ((tp - price) / price) * 100
        sl_pct = ((price - sl) / price) * 100

        signals = []
        rsi = indicators.get("rsi")
        if rsi is not None and rsi < 30:
            signals.append(f"RSI({rsi:.0f})")
        macd_h = indicators.get("macd_histogram")
        if macd_h is not None and macd_h > 0:
            signals.append("MACD cross")
        signals_str = " + ".join(signals) if signals else "combined"

        return (
            f"BinanceBot 🟢 <b>BUY {symbol}</b> @ ${price:,.2f}\n"
            f"Size: ${size:.2f} | Signal: {signals_str}\n"
            f"TP: ${tp:,.2f} (+{tp_pct:.1f}%) | SL: ${sl:,.2f} (-{sl_pct:.1f}%)\n"
            f"Open: {status['open_positions']}/3 | Portfolio: ${status['balance']:.2f}"
        )

    def format_sell_alert(self, closed: dict, status: dict) -> str:
        symbol = closed["symbol"]
        exit_price = closed["exit_price"]
        pnl = closed["pnl"]
        reason = closed["reason"].replace("_", " ").title()
        hold_time = closed.get("hold_time", "")
        pnl_sign = "+" if pnl >= 0 else ""

        return (
            f"BinanceBot 🔴 <b>CLOSED {symbol}</b> @ ${exit_price:,.2f}\n"
            f"P&L: <b>{pnl_sign}${pnl:.2f}</b> | Hold: {hold_time}\n"
            f"Reason: {reason}\n"
            f"Open: {status['open_positions']}/3 | Portfolio: ${status['balance']:.2f}"
        )

    def format_summary(self, status: dict, open_trades: list[dict]) -> str:
        balance = status["balance"]
        start = status["starting_balance"]
        daily_pnl = status["daily_pnl"]
        total_trades = status["total_trades"]
        wins = status["total_wins"]
        losses = total_trades - wins
        win_rate = status["win_rate"]

        daily_pct = (daily_pnl / start * 100) if start > 0 else 0
        daily_sign = "+" if daily_pnl >= 0 else ""

        open_lines = ""
        for t in open_trades:
            open_lines += f"  {t['side'].upper()} {t['symbol']} @ ${t['price']:,.2f}\n"
        if not open_lines:
            open_lines = "  None\n"

        return (
            f"BinanceBot 📊 <b>Status</b>\n"
            f"Portfolio: ${balance:.2f} (started: ${start:.2f})\n"
            f"Today P&L: {daily_sign}${daily_pnl:.2f} ({daily_sign}{daily_pct:.1f}%)\n"
            f"Trades today: {total_trades} ({wins}W/{losses}L, {win_rate:.1%})\n"
            f"Open:\n{open_lines}"
        )

    def format_daily_report(self, status: dict, today_trades: list[dict]) -> str:
        balance = status["balance"]
        start = status["starting_balance"]
        daily_pnl = status.get("daily_pnl", status.get("total_pnl", 0))
        total_trades = status["total_trades"]
        wins = status["total_wins"]
        losses = total_trades - wins
        daily_pct = (daily_pnl / start * 100) if start > 0 else 0
        daily_sign = "+" if daily_pnl >= 0 else ""

        best_pnl = max((t["pnl"] for t in today_trades), default=0)
        worst_pnl = min((t["pnl"] for t in today_trades), default=0)
        best_sym = next((t["symbol"] for t in today_trades if t["pnl"] == best_pnl), "N/A")
        worst_sym = next((t["symbol"] for t in today_trades if t["pnl"] == worst_pnl), "N/A")

        return (
            f"BinanceBot 📈 <b>Daily Report</b>\n"
            f"Net P&L: {daily_sign}${daily_pnl:.2f} ({daily_sign}{daily_pct:.1f}%)\n"
            f"Total trades: {total_trades} ({wins}W/{losses}L)\n"
            f"Best: {best_sym} +${best_pnl:.2f} | Worst: {worst_sym} ${worst_pnl:.2f}\n"
            f"Running total: ${balance:.2f} (from ${start:.2f} start)"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_notifier_binance.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add binance_modules/notifier.py tests/test_notifier_binance.py
git commit -m "feat(binance): add Telegram notifier with trade alerts, summaries, and daily reports"
```

---

### Task 8: Main Entry Point (binancebot.py)

**Files:**
- Create: `binancebot.py`

- [ ] **Step 1: Create binancebot.py**

```python
# binancebot.py
import asyncio
import argparse
import signal
import sys
from datetime import datetime, timezone

from config import Config
from utils.binance_db import init_binance_db
from utils.db import get_connection
from utils.logger import get_logger
from binance_modules.market_data import MarketData
from binance_modules.indicators import compute_all
from binance_modules.signal_engine import SignalEngine
from binance_modules.risk_manager import BinanceRiskManager
from binance_modules.trade_executor import BinanceTradeExecutor
from binance_modules.notifier import BinanceNotifier

log = get_logger("binancebot")


class BinanceBot:
    def __init__(self, config: Config):
        self.config = config
        self.running = False
        self.market_data = MarketData(config)
        self.signal_engine = SignalEngine(config)
        self.risk_manager = BinanceRiskManager(config)
        self.executor = BinanceTradeExecutor(config)
        self.notifier = BinanceNotifier(config)

    async def startup(self, starting_balance: float):
        log.info(f"Starting BinanceBot in {self.config.BINANCE_TRADING_MODE} mode")
        init_binance_db(self.config.BINANCE_DB_PATH)
        self.risk_manager.init_portfolio(starting_balance)
        await self.notifier.send_message(
            f"BinanceBot started in <b>{self.config.BINANCE_TRADING_MODE}</b> mode\n"
            f"Capital: ${starting_balance:.2f}\n"
            f"Pairs: {', '.join(self.config.BINANCE_PAIRS)}\n"
            f"Strategy: RSI + MACD + BB (2-of-3 agreement)"
        )
        self.running = True

    async def trading_loop(self):
        """Main loop: fetch candles, compute indicators, generate signals, execute trades."""
        while self.running:
            try:
                # 1. Fetch candles for all pairs
                all_candles = await self.market_data.fetch_all_candles()

                # 2. Get current prices
                current_prices = {}
                for symbol in self.config.BINANCE_PAIRS:
                    if symbol in all_candles and all_candles[symbol]["1m"]:
                        current_prices[symbol] = all_candles[symbol]["1m"][-1]["close"]

                # 3. Check open positions for TP/SL/trailing
                closed_trades = self.executor.check_open_positions(current_prices)
                for closed in closed_trades:
                    self.risk_manager.record_trade_outcome(closed["pnl"])
                    status = self.risk_manager.get_status()
                    msg = self.notifier.format_sell_alert(closed, status)
                    await self.notifier.send_message(msg)

                # 4. Evaluate signals for each pair
                for symbol in self.config.BINANCE_PAIRS:
                    if symbol not in all_candles:
                        continue

                    candles_1m = all_candles[symbol].get("1m", [])
                    candles_5m = all_candles[symbol].get("5m", [])

                    if len(candles_1m) < 35 or len(candles_5m) < 35:
                        continue

                    indicators_1m = compute_all(candles_1m)
                    indicators_5m = compute_all(candles_5m)
                    current_price = current_prices.get(symbol, 0)

                    if current_price == 0:
                        continue

                    signal = self.signal_engine.evaluate(
                        symbol, indicators_1m, indicators_5m, current_price
                    )

                    if signal["action"] == "hold":
                        continue

                    # Sell signal: close opposing positions
                    if signal["action"] == "sell":
                        open_positions = self.executor.get_open_positions()
                        buy_positions = [p for p in open_positions if p["symbol"] == symbol and p["side"] == "buy"]
                        if buy_positions:
                            closed = self.executor.close_by_signal(symbol, current_price, "opposing_signal")
                            for c in closed:
                                self.risk_manager.record_trade_outcome(c["pnl"])
                                status = self.risk_manager.get_status()
                                msg = self.notifier.format_sell_alert(c, status)
                                await self.notifier.send_message(msg)
                        continue

                    # Buy signal: check risk and execute
                    can_trade = self.risk_manager.can_trade()
                    if not can_trade["allowed"]:
                        log.info(f"Trade blocked: {can_trade['reason']}")
                        continue

                    size = self.risk_manager.calc_position_size(signal["strength"])

                    # Check minimum order size ($5 on Binance)
                    if size < 5.0:
                        log.info(f"Position too small: ${size:.2f} < $5 minimum")
                        continue

                    result = self.executor.execute_trade(signal, size)
                    if result["status"] == "filled":
                        # Deduct fee from balance tracking
                        status = self.risk_manager.get_status()
                        msg = self.notifier.format_buy_alert(
                            result, indicators_1m, status
                        )
                        await self.notifier.send_message(msg)

                await asyncio.sleep(self.config.BINANCE_POLL_INTERVAL_SEC)

            except Exception as e:
                log.error(f"Trading loop error: {e}")
                await asyncio.sleep(10)

    async def summary_loop(self):
        """Send periodic summaries every 15 minutes."""
        while self.running:
            try:
                await asyncio.sleep(self.config.BINANCE_SUMMARY_INTERVAL_SEC)
                status = self.risk_manager.get_status()
                open_trades = self.executor.get_open_positions()
                msg = self.notifier.format_summary(status, open_trades)
                await self.notifier.send_message(msg)
            except Exception as e:
                log.error(f"Summary loop error: {e}")
                await asyncio.sleep(60)

    async def daily_report_loop(self):
        """Send daily report."""
        while self.running:
            try:
                await asyncio.sleep(self.config.BINANCE_DAILY_REPORT_INTERVAL_SEC)
                status = self.risk_manager.get_status()
                conn = get_connection(self.config.BINANCE_DB_PATH)
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                today_trades = conn.execute(
                    "SELECT * FROM bn_trades WHERE status = 'closed' AND date(exit_time) = ?",
                    (today,),
                ).fetchall()
                conn.close()
                today_trades = [dict(t) for t in today_trades]
                msg = self.notifier.format_daily_report(status, today_trades)
                await self.notifier.send_message(msg)
            except Exception as e:
                log.error(f"Daily report error: {e}")
                await asyncio.sleep(3600)

    def stop(self):
        log.info("Stopping BinanceBot...")
        self.running = False

    async def run(self, starting_balance: float):
        await self.startup(starting_balance)
        tasks = [
            asyncio.create_task(self.trading_loop()),
            asyncio.create_task(self.summary_loop()),
            asyncio.create_task(self.daily_report_loop()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            log.info("BinanceBot stopped")


def main():
    parser = argparse.ArgumentParser(description="BinanceBot - Rapid BTC/ETH Trading Bot")
    parser.add_argument(
        "--mode", choices=["paper", "live"], default=None,
        help="Trading mode (overrides .env)",
    )
    parser.add_argument(
        "--capital", type=float, default=45.0,
        help="Starting capital in USD (default: 45)",
    )
    args = parser.parse_args()

    config = Config()
    if args.mode:
        config.BINANCE_TRADING_MODE = args.mode

    bot = BinanceBot(config)

    def signal_handler(sig, frame):
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(bot.run(args.capital))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it starts in paper mode (smoke test)**

Run: `cd /Users/mbh/Desktop/MakeMoney && timeout 10 python binancebot.py --mode paper --capital 45 2>&1 || true`
Expected: Should start, print startup logs, and attempt to fetch candles. Will exit after timeout. Verify "Starting BinanceBot in paper mode" appears in output.

- [ ] **Step 3: Commit**

```bash
git add binancebot.py
git commit -m "feat(binance): add main entry point with trading, summary, and daily report loops"
```

---

### Task 9: Run All Tests + Update .env

**Files:**
- Modify: `.env` (add Binance placeholders)

- [ ] **Step 1: Run all tests**

Run: `cd /Users/mbh/Desktop/MakeMoney && python -m pytest tests/test_binance_db.py tests/test_market_data.py tests/test_indicators.py tests/test_signal_engine.py tests/test_risk_manager.py tests/test_trade_executor.py tests/test_notifier_binance.py -v`
Expected: All tests pass (37 total across all test files)

- [ ] **Step 2: Add Binance env vars to .env**

Append to the existing `.env` file:

```
# Binance
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TRADING_MODE=paper
```

- [ ] **Step 3: Verify BinanceBot starts and fetches live candle data**

Run: `cd /Users/mbh/Desktop/MakeMoney && timeout 15 python binancebot.py --mode paper --capital 45 2>&1 || true`
Expected: Should start, fetch real BTC/ETH candles from Binance, compute indicators, and log signal evaluations. Telegram startup message should arrive.

- [ ] **Step 4: Commit**

```bash
git add .env tests/
git commit -m "feat(binance): finalize BinanceBot setup with all tests passing"
```

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Config + DB schema | 2 |
| 2 | Market data (Binance API) | 3 |
| 3 | Indicators (RSI, MACD, BB) | 10 |
| 4 | Signal engine (2-of-3 + 5m confirm) | 6 |
| 5 | Risk manager (sizing, limits) | 9 |
| 6 | Trade executor (paper, TP/SL, trailing) | 6 |
| 7 | Notifier (Telegram alerts) | 4 |
| 8 | Main entry point (binancebot.py) | smoke test |
| 9 | Full test run + .env + integration | all |
| **Total** | **9 tasks** | **~40 tests** |
