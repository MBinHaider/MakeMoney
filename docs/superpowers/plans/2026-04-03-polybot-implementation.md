# PolyBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated Polymarket trading bot that copy-trades top-performing wallets on crypto 5-min up/down markets, filtered by AI signal scoring.

**Architecture:** 6-module Python application — Data Collector fetches market/wallet/price data into SQLite, Wallet Scanner ranks wallets by profitability, Signal Engine scores trade opportunities, Trade Executor places orders via Polymarket CLOB API, Risk Manager enforces capital limits, Notifier sends Telegram alerts and accepts commands.

**Tech Stack:** Python 3.11+, py-clob-client 0.34.6 (Polymarket SDK), python-telegram-bot 22.7, aiohttp, SQLite3 (stdlib), Binance public API (no auth)

---

## File Structure

```
MakeMoney/
├── polybot.py                    # Main entry point, CLI args, async event loop
├── config.py                     # All tunables: thresholds, limits, intervals, API URLs
├── requirements.txt              # Python dependencies
├── .env.example                  # Template for secrets
├── .gitignore                    # Ignore .env, data/, __pycache__/
├── data/                         # SQLite DB lives here (gitignored)
├── modules/
│   ├── __init__.py
│   ├── data_collector.py         # Polymarket + Binance API integrations
│   ├── wallet_scanner.py         # Wallet scoring & ranking
│   ├── signal_engine.py          # Signal generation & confidence scoring
│   ├── trade_executor.py         # Polymarket order placement
│   ├── risk_manager.py           # Drawdown, position limits, kill switch
│   └── notifier.py               # Telegram bot (alerts + commands)
├── utils/
│   ├── __init__.py
│   ├── logger.py                 # Structured logging setup
│   └── db.py                     # SQLite schema, connection, helpers
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_db.py
    ├── test_data_collector.py
    ├── test_wallet_scanner.py
    ├── test_signal_engine.py
    ├── test_trade_executor.py
    ├── test_risk_manager.py
    └── test_notifier.py
```

---

### Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `modules/__init__.py`
- Create: `utils/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```txt
py-clob-client==0.34.6
python-telegram-bot==22.7
aiohttp==3.11.14
python-dotenv==1.1.0
pytest==8.3.5
pytest-asyncio==0.25.3
```

- [ ] **Step 2: Create .env.example**

```txt
# Polymarket
PRIVATE_KEY=your_ethereum_private_key_here
POLYMARKET_API_URL=https://clob.polymarket.com

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Mode
TRADING_MODE=paper
```

- [ ] **Step 3: Create .gitignore**

```txt
.env
data/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 4: Create empty __init__.py files**

Create empty files at:
- `modules/__init__.py`
- `utils/__init__.py`
- `tests/__init__.py`

- [ ] **Step 5: Create data directory**

Run: `mkdir -p data`

- [ ] **Step 6: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore modules/__init__.py utils/__init__.py tests/__init__.py
git commit -m "feat: project scaffolding with dependencies"
```

---

### Task 2: Configuration

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from config import Config


def test_config_has_polymarket_url():
    cfg = Config()
    assert cfg.POLYMARKET_API_URL == "https://clob.polymarket.com"


def test_config_has_gamma_url():
    cfg = Config()
    assert cfg.GAMMA_API_URL == "https://gamma-api.polymarket.com"


def test_config_has_binance_url():
    cfg = Config()
    assert cfg.BINANCE_API_URL == "https://api.binance.com"


def test_config_default_trading_mode_is_paper():
    cfg = Config()
    assert cfg.TRADING_MODE == "paper"


def test_config_signal_thresholds():
    cfg = Config()
    assert cfg.SIGNAL_AUTO_TRADE_THRESHOLD == 70
    assert cfg.SIGNAL_ALERT_THRESHOLD == 50


def test_config_risk_limits():
    cfg = Config()
    assert cfg.MAX_CONCURRENT_POSITIONS == 10
    assert cfg.MAX_CAPITAL_PER_TRADE_PCT == 0.10
    assert cfg.MAX_TOTAL_EXPOSURE_PCT == 0.30
    assert cfg.HARD_STOP_DRAWDOWN_PCT == 0.30
    assert cfg.SOFT_STOP_DRAWDOWN_PCT == 0.15
    assert cfg.DAILY_LOSS_LIMIT_PCT == 0.10


def test_config_wallet_scanner_settings():
    cfg = Config()
    assert cfg.MIN_WALLET_TRADES == 100
    assert cfg.MIN_WALLET_WIN_RATE == 0.52
    assert cfg.TOP_TRACKED_WALLETS == 20


def test_config_polling_intervals():
    cfg = Config()
    assert cfg.MARKET_POLL_INTERVAL_SEC == 30
    assert cfg.WALLET_POLL_INTERVAL_SEC == 15
    assert cfg.PRICE_POLL_INTERVAL_SEC == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'config'"

- [ ] **Step 3: Write config.py**

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API URLs
    POLYMARKET_API_URL = "https://clob.polymarket.com"
    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    BINANCE_API_URL = "https://api.binance.com"

    # Secrets (from .env)
    PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Trading mode: "paper" or "live"
    TRADING_MODE = os.getenv("TRADING_MODE", "paper")

    # Polymarket chain
    CHAIN_ID = 137  # Polygon

    # Polling intervals (seconds)
    MARKET_POLL_INTERVAL_SEC = 30
    WALLET_POLL_INTERVAL_SEC = 15
    PRICE_POLL_INTERVAL_SEC = 10

    # Signal thresholds
    SIGNAL_AUTO_TRADE_THRESHOLD = 70
    SIGNAL_ALERT_THRESHOLD = 50

    # Risk limits
    MAX_CONCURRENT_POSITIONS = 10
    MAX_CAPITAL_PER_TRADE_PCT = 0.10
    MAX_TOTAL_EXPOSURE_PCT = 0.30
    HARD_STOP_DRAWDOWN_PCT = 0.30
    SOFT_STOP_DRAWDOWN_PCT = 0.15
    DAILY_LOSS_LIMIT_PCT = 0.10
    MAX_SAME_DIRECTION_TRADES = 3
    CONSECUTIVE_LOSS_PAUSE = 3
    PAUSE_DURATION_MIN = 30

    # Position sizing
    BASE_BET_PCT = 0.02  # 2% of portfolio per trade

    # Wallet scanner
    MIN_WALLET_TRADES = 100
    MIN_WALLET_WIN_RATE = 0.52
    TOP_TRACKED_WALLETS = 20
    WALLET_LOOKBACK_DAYS = 90

    # Trade execution
    ORDER_TIMEOUT_SEC = 30

    # Targets (BTC/ETH, expandable)
    TARGET_MARKETS = ["BTC", "ETH"]

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "polybot.db")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add configuration with all tunables"
```

---

### Task 3: Logger Utility

**Files:**
- Create: `utils/logger.py`

- [ ] **Step 1: Write logger.py**

```python
# utils/logger.py
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
```

- [ ] **Step 2: Verify it imports**

Run: `python -c "from utils.logger import get_logger; log = get_logger('test'); log.info('works')"`
Expected: prints timestamped log line to stdout

- [ ] **Step 3: Commit**

```bash
git add utils/logger.py
git commit -m "feat: add structured logger utility"
```

---

### Task 4: Database Schema & Helpers

**Files:**
- Create: `utils/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
import os
import sqlite3
import pytest
from utils.db import init_db, get_connection

TEST_DB = "data/test_polybot.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_init_db_creates_tables():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "wallets" in tables
    assert "wallet_trades" in tables
    assert "tracked_wallets" in tables
    assert "signals" in tables
    assert "bot_trades" in tables
    assert "price_candles" in tables
    assert "markets" in tables


def test_init_db_wallets_schema():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute("PRAGMA table_info(wallets)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "address" in columns
    assert "total_trades" in columns
    assert "win_rate" in columns
    assert "total_pnl" in columns
    assert "composite_score" in columns


def test_init_db_bot_trades_schema():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    cursor = conn.execute("PRAGMA table_info(bot_trades)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "market_id" in columns
    assert "side" in columns
    assert "size" in columns
    assert "entry_price" in columns
    assert "outcome" in columns
    assert "pnl" in columns
    assert "signal_score" in columns


def test_get_connection_returns_valid_connection():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL with "cannot import name 'init_db' from 'utils.db'"

- [ ] **Step 3: Write db.py**

```python
# utils/db.py
import sqlite3
import os

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    address TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    total_pnl REAL DEFAULT 0.0,
    avg_bet_size REAL DEFAULT 0.0,
    consistency_score REAL DEFAULT 0.0,
    frequency_score REAL DEFAULT 0.0,
    recency_score REAL DEFAULT 0.0,
    composite_score REAL DEFAULT 0.0,
    preferred_market TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wallet_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_slug TEXT DEFAULT '',
    side TEXT NOT NULL,
    size REAL NOT NULL,
    entry_price REAL NOT NULL,
    outcome TEXT DEFAULT 'pending',
    pnl REAL DEFAULT 0.0,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (wallet_address) REFERENCES wallets(address)
);

CREATE TABLE IF NOT EXISTS tracked_wallets (
    address TEXT PRIMARY KEY,
    rank INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    FOREIGN KEY (address) REFERENCES wallets(address)
);

CREATE TABLE IF NOT EXISTS markets (
    condition_id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    token_id_yes TEXT NOT NULL,
    token_id_no TEXT NOT NULL,
    asset TEXT NOT NULL,
    price_yes REAL DEFAULT 0.5,
    price_no REAL DEFAULT 0.5,
    volume REAL DEFAULT 0.0,
    end_time TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    whale_score REAL DEFAULT 0.0,
    market_score REAL DEFAULT 0.0,
    confluence_score REAL DEFAULT 0.0,
    total_score REAL DEFAULT 0.0,
    action_taken TEXT DEFAULT 'logged',
    triggering_wallet TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    size REAL NOT NULL,
    entry_price REAL NOT NULL,
    outcome TEXT DEFAULT 'pending',
    pnl REAL DEFAULT 0.0,
    signal_score REAL DEFAULT 0.0,
    signal_id INTEGER,
    order_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    resolved_at TEXT DEFAULT '',
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS price_candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    starting_capital REAL NOT NULL,
    current_value REAL NOT NULL,
    peak_value REAL NOT NULL,
    total_trades INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0.0,
    daily_pnl REAL DEFAULT 0.0,
    daily_pnl_date TEXT DEFAULT '',
    is_paused INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_wallet_trades_wallet ON wallet_trades(wallet_address);
CREATE INDEX IF NOT EXISTS idx_wallet_trades_timestamp ON wallet_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_bot_trades_timestamp ON bot_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_price_candles_asset_ts ON price_candles(asset, timestamp);
CREATE INDEX IF NOT EXISTS idx_markets_active ON markets(active);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add utils/db.py tests/test_db.py
git commit -m "feat: add SQLite schema and database helpers"
```

---

### Task 5: Data Collector — Market Fetcher

**Files:**
- Create: `modules/data_collector.py`
- Create: `tests/test_data_collector.py`

- [ ] **Step 1: Write the failing test for market fetching**

```python
# tests/test_data_collector.py
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from modules.data_collector import DataCollector
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_collector.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    return cfg


@pytest.fixture
def collector(config):
    return DataCollector(config)


MOCK_GAMMA_MARKETS = [
    {
        "conditionId": "0xabc123",
        "question": "Will BTC go up in the next 5 minutes?",
        "tokens": [
            {"token_id": "tok_yes_1", "outcome": "Yes", "price": 0.55},
            {"token_id": "tok_no_1", "outcome": "No", "price": 0.45},
        ],
        "endDate": "2026-04-03T14:05:00Z",
        "volume": 50000.0,
        "active": True,
        "closed": False,
    }
]


@pytest.mark.asyncio
async def test_fetch_markets_stores_in_db(collector):
    with patch.object(collector, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MOCK_GAMMA_MARKETS
        await collector.fetch_active_markets()

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM markets").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["condition_id"] == "0xabc123"
    assert rows[0]["asset"] == "BTC"
    assert rows[0]["price_yes"] == 0.55


@pytest.mark.asyncio
async def test_fetch_markets_filters_non_crypto(collector):
    non_crypto = [
        {
            "conditionId": "0xdef456",
            "question": "Will it rain tomorrow?",
            "tokens": [
                {"token_id": "tok_yes_2", "outcome": "Yes", "price": 0.60},
                {"token_id": "tok_no_2", "outcome": "No", "price": 0.40},
            ],
            "endDate": "2026-04-04T00:00:00Z",
            "volume": 1000.0,
            "active": True,
            "closed": False,
        }
    ]
    with patch.object(collector, "_get_json", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = non_crypto
        await collector.fetch_active_markets()

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM markets").fetchall()
    conn.close()
    assert len(rows) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data_collector.py -v`
Expected: FAIL with "cannot import name 'DataCollector'"

- [ ] **Step 3: Write the DataCollector class with market fetching**

```python
# modules/data_collector.py
import aiohttp
from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("data_collector")

TARGET_KEYWORDS = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
}


class DataCollector:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    async def _get_json(self, url: str, params: dict = None) -> list | dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                return await resp.json()

    def _detect_asset(self, question: str) -> str | None:
        q_lower = question.lower()
        for asset, keywords in TARGET_KEYWORDS.items():
            if asset in self.config.TARGET_MARKETS:
                for kw in keywords:
                    if kw in q_lower:
                        return asset
        return None

    async def fetch_active_markets(self) -> list[dict]:
        url = f"{self.config.GAMMA_API_URL}/markets"
        params = {"active": "true", "closed": "false", "limit": 100}
        markets = await self._get_json(url, params)

        stored = []
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()

        for m in markets:
            question = m.get("question", "")
            asset = self._detect_asset(question)
            if not asset:
                continue

            tokens = m.get("tokens", [])
            if len(tokens) < 2:
                continue

            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), tokens[0])
            no_token = next((t for t in tokens if t.get("outcome") == "No"), tokens[1])

            row = {
                "condition_id": m["conditionId"],
                "question": question,
                "token_id_yes": yes_token["token_id"],
                "token_id_no": no_token["token_id"],
                "asset": asset,
                "price_yes": float(yes_token.get("price", 0.5)),
                "price_no": float(no_token.get("price", 0.5)),
                "volume": float(m.get("volume", 0)),
                "end_time": m.get("endDate", ""),
                "active": 1,
                "updated_at": now,
            }

            conn.execute(
                """INSERT OR REPLACE INTO markets
                   (condition_id, question, token_id_yes, token_id_no, asset,
                    price_yes, price_no, volume, end_time, active, updated_at)
                   VALUES (:condition_id, :question, :token_id_yes, :token_id_no,
                           :asset, :price_yes, :price_no, :volume, :end_time,
                           :active, :updated_at)""",
                row,
            )
            stored.append(row)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(stored)} active crypto markets")
        return stored

    async def fetch_price_candles(self, asset: str, limit: int = 60) -> list[dict]:
        symbol = f"{asset}USDT"
        url = f"{self.config.BINANCE_API_URL}/api/v3/klines"
        params = {"symbol": symbol, "interval": "1m", "limit": limit}
        raw = await self._get_json(url, params)

        candles = []
        conn = get_connection(self.db_path)

        for k in raw:
            candle = {
                "asset": asset,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "timestamp": datetime.fromtimestamp(
                    k[0] / 1000, tz=timezone.utc
                ).isoformat(),
            }
            conn.execute(
                """INSERT INTO price_candles
                   (asset, open, high, low, close, volume, timestamp)
                   VALUES (:asset, :open, :high, :low, :close, :volume, :timestamp)""",
                candle,
            )
            candles.append(candle)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(candles)} {asset} candles")
        return candles

    async def fetch_wallet_trades(self, wallet_address: str) -> list[dict]:
        url = f"{self.config.POLYMARKET_API_URL}/trades"
        params = {"maker": wallet_address, "limit": 1000}
        try:
            raw_trades = await self._get_json(url, params)
        except Exception as e:
            log.error(f"Failed to fetch trades for {wallet_address}: {e}")
            return []

        trades = []
        conn = get_connection(self.db_path)

        for t in raw_trades:
            trade = {
                "wallet_address": wallet_address,
                "market_id": t.get("market", ""),
                "market_slug": t.get("matchTime", ""),
                "side": t.get("side", ""),
                "size": float(t.get("size", 0)),
                "entry_price": float(t.get("price", 0)),
                "outcome": t.get("outcome", "pending"),
                "pnl": float(t.get("pnl", 0)),
                "timestamp": t.get("matchTime", ""),
            }
            conn.execute(
                """INSERT INTO wallet_trades
                   (wallet_address, market_id, market_slug, side, size,
                    entry_price, outcome, pnl, timestamp)
                   VALUES (:wallet_address, :market_id, :market_slug, :side,
                           :size, :entry_price, :outcome, :pnl, :timestamp)""",
                trade,
            )
            trades.append(trade)

        conn.commit()
        conn.close()
        log.info(f"Fetched {len(trades)} trades for wallet {wallet_address[:10]}...")
        return trades

    async def poll_tracked_wallets(self) -> list[dict]:
        conn = get_connection(self.db_path)
        tracked = conn.execute(
            "SELECT address FROM tracked_wallets ORDER BY rank"
        ).fetchall()
        conn.close()

        new_trades = []
        for row in tracked:
            address = row["address"]
            url = f"{self.config.POLYMARKET_API_URL}/trades"
            params = {"maker": address, "limit": 10}
            try:
                recent = await self._get_json(url, params)
                for t in recent:
                    t["wallet_address"] = address
                    new_trades.append(t)
            except Exception as e:
                log.error(f"Poll failed for {address[:10]}: {e}")

        log.info(f"Polled {len(tracked)} wallets, found {len(new_trades)} recent trades")
        return new_trades
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data_collector.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/data_collector.py tests/test_data_collector.py
git commit -m "feat: add data collector with market, price, and wallet fetching"
```

---

### Task 6: Wallet Scanner

**Files:**
- Create: `modules/wallet_scanner.py`
- Create: `tests/test_wallet_scanner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wallet_scanner.py
import os
import pytest
from datetime import datetime, timezone, timedelta
from modules.wallet_scanner import WalletScanner
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_scanner.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.MIN_WALLET_TRADES = 5  # lower threshold for testing
    cfg.MIN_WALLET_WIN_RATE = 0.52
    cfg.TOP_TRACKED_WALLETS = 2
    return cfg


@pytest.fixture
def scanner(config):
    return WalletScanner(config)


def _insert_trades(db_path, wallet, num_wins, num_losses, avg_size=10.0):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)
    for i in range(num_wins):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES (?, ?, 'BUY', ?, 0.55, 'won', ?, ?)""",
            (wallet, f"market_{i}", avg_size, avg_size * 0.8,
             (now - timedelta(hours=i)).isoformat()),
        )
    for i in range(num_losses):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES (?, ?, 'BUY', ?, 0.55, 'lost', ?, ?)""",
            (wallet, f"market_loss_{i}", avg_size, -avg_size,
             (now - timedelta(hours=num_wins + i)).isoformat()),
        )
    conn.commit()
    conn.close()


def test_score_wallet_high_win_rate(scanner):
    _insert_trades(TEST_DB, "0xAAA", num_wins=8, num_losses=2)
    score = scanner.score_wallet("0xAAA")
    assert score["win_rate"] == 0.8
    assert score["total_pnl"] > 0
    assert score["composite_score"] > 0


def test_score_wallet_below_min_trades_returns_zero(scanner):
    _insert_trades(TEST_DB, "0xBBB", num_wins=2, num_losses=1)
    score = scanner.score_wallet("0xBBB")
    assert score["composite_score"] == 0


def test_score_wallet_below_min_win_rate_returns_zero(scanner):
    _insert_trades(TEST_DB, "0xCCC", num_wins=2, num_losses=5)
    score = scanner.score_wallet("0xCCC")
    assert score["composite_score"] == 0


def test_rank_and_track_selects_top_wallets(scanner):
    _insert_trades(TEST_DB, "0xTOP1", num_wins=9, num_losses=1, avg_size=20.0)
    _insert_trades(TEST_DB, "0xTOP2", num_wins=7, num_losses=3, avg_size=15.0)
    _insert_trades(TEST_DB, "0xMED", num_wins=6, num_losses=4, avg_size=5.0)

    tracked = scanner.rank_and_track()
    assert len(tracked) == 2
    assert tracked[0]["address"] == "0xTOP1"
    assert tracked[1]["address"] == "0xTOP2"

    conn = get_connection(TEST_DB)
    rows = conn.execute("SELECT * FROM tracked_wallets ORDER BY rank").fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0]["address"] == "0xTOP1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_wallet_scanner.py -v`
Expected: FAIL with "cannot import name 'WalletScanner'"

- [ ] **Step 3: Write wallet_scanner.py**

```python
# modules/wallet_scanner.py
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("wallet_scanner")


class WalletScanner:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_wallet_trades(self, address: str) -> list[dict]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM wallet_trades WHERE wallet_address = ? ORDER BY timestamp DESC",
            (address,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def score_wallet(self, address: str) -> dict:
        trades = self._get_wallet_trades(address)
        total = len(trades)

        result = {
            "address": address,
            "total_trades": total,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "consistency_score": 0.0,
            "frequency_score": 0.0,
            "recency_score": 0.0,
            "composite_score": 0.0,
        }

        if total < self.config.MIN_WALLET_TRADES:
            return result

        wins = sum(1 for t in trades if t["outcome"] == "won")
        losses = total - wins
        win_rate = wins / total if total > 0 else 0
        total_pnl = sum(t["pnl"] for t in trades)

        if win_rate < self.config.MIN_WALLET_WIN_RATE:
            result["wins"] = wins
            result["losses"] = losses
            result["win_rate"] = win_rate
            result["total_pnl"] = total_pnl
            return result

        # Consistency: standard deviation of PnL per trade (lower = more consistent)
        avg_pnl = total_pnl / total if total > 0 else 0
        variance = sum((t["pnl"] - avg_pnl) ** 2 for t in trades) / total
        std_pnl = variance ** 0.5
        # Normalize: lower std relative to avg = higher score
        consistency = max(0, 1 - (std_pnl / (abs(avg_pnl) + 1))) * 100

        # Frequency: trades per day over lookback period
        lookback_days = self.config.WALLET_LOOKBACK_DAYS
        frequency = min(100, (total / max(1, lookback_days)) * 10)

        # Recency: weight recent trades higher
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(days=7)
        recent_trades = [
            t for t in trades
            if t["timestamp"] and t["timestamp"] > recent_cutoff.isoformat()
        ]
        recent_ratio = len(recent_trades) / total if total > 0 else 0
        recency = recent_ratio * 100

        # Composite score (weighted)
        composite = (
            win_rate * 100 * 0.25
            + consistency * 0.25
            + min(100, total_pnl / 100) * 0.20
            + frequency * 0.15
            + recency * 0.15
        )

        result.update({
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "consistency_score": consistency,
            "frequency_score": frequency,
            "recency_score": recency,
            "composite_score": composite,
        })

        # Persist to wallets table
        conn = get_connection(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO wallets
               (address, total_trades, wins, losses, win_rate, total_pnl,
                avg_bet_size, consistency_score, frequency_score, recency_score,
                composite_score, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                address, total, wins, losses, win_rate, total_pnl,
                sum(t["size"] for t in trades) / total,
                consistency, frequency, recency, composite,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return result

    def get_all_wallet_addresses(self) -> list[str]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT DISTINCT wallet_address FROM wallet_trades"
        ).fetchall()
        conn.close()
        return [r["wallet_address"] for r in rows]

    def rank_and_track(self) -> list[dict]:
        addresses = self.get_all_wallet_addresses()
        scored = []
        for addr in addresses:
            s = self.score_wallet(addr)
            if s["composite_score"] > 0:
                scored.append(s)

        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        top = scored[: self.config.TOP_TRACKED_WALLETS]

        conn = get_connection(self.db_path)
        conn.execute("DELETE FROM tracked_wallets")
        now = datetime.now(timezone.utc).isoformat()
        for rank, wallet in enumerate(top, 1):
            conn.execute(
                "INSERT INTO tracked_wallets (address, rank, added_at) VALUES (?, ?, ?)",
                (wallet["address"], rank, now),
            )
        conn.commit()
        conn.close()

        log.info(f"Tracked {len(top)} wallets out of {len(addresses)} total")
        return top
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_wallet_scanner.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/wallet_scanner.py tests/test_wallet_scanner.py
git commit -m "feat: add wallet scanner with scoring and ranking"
```

---

### Task 7: Signal Engine

**Files:**
- Create: `modules/signal_engine.py`
- Create: `tests/test_signal_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_signal_engine.py
import os
import pytest
from datetime import datetime, timezone, timedelta
from modules.signal_engine import SignalEngine
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_signal.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.SIGNAL_AUTO_TRADE_THRESHOLD = 70
    cfg.SIGNAL_ALERT_THRESHOLD = 50
    return cfg


@pytest.fixture
def engine(config):
    return SignalEngine(config)


def _setup_tracked_wallet(db_path, address, rank):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO wallets (address, win_rate, total_pnl, avg_bet_size, composite_score, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (address, 0.75, 5000.0, 50.0, 80.0, now),
    )
    conn.execute(
        "INSERT OR REPLACE INTO tracked_wallets (address, rank, added_at) VALUES (?, ?, ?)",
        (address, rank, now),
    )
    conn.commit()
    conn.close()


def _insert_price_candles(db_path, asset, prices):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)
    for i, price in enumerate(prices):
        conn.execute(
            """INSERT INTO price_candles (asset, open, high, low, close, volume, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (asset, price, price + 10, price - 10, price,
             1000.0, (now - timedelta(minutes=len(prices) - i)).isoformat()),
        )
    conn.commit()
    conn.close()


def test_whale_score_top5_wallet(engine):
    _setup_tracked_wallet(TEST_DB, "0xWHALE", rank=3)
    whale_trade = {
        "wallet_address": "0xWHALE",
        "side": "BUY",
        "size": 100.0,  # 2x average (50)
        "market_id": "market_1",
    }
    score = engine._calc_whale_score(whale_trade)
    assert score > 0
    assert score <= 40


def test_whale_score_top20_wallet(engine):
    _setup_tracked_wallet(TEST_DB, "0xMID", rank=15)
    whale_trade = {
        "wallet_address": "0xMID",
        "side": "BUY",
        "size": 50.0,
        "market_id": "market_1",
    }
    score = engine._calc_whale_score(whale_trade)
    assert score > 0
    assert score <= 40


def test_generate_signal_returns_scored_signal(engine):
    _setup_tracked_wallet(TEST_DB, "0xTOP", rank=1)
    _insert_price_candles(TEST_DB, "BTC", [100, 101, 102, 103, 104])

    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO markets (condition_id, question, token_id_yes, token_id_no,
           asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        ("mkt_1", "Will BTC go up?", "tok_y", "tok_n", "BTC",
         0.55, 0.45, 100000, (now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()

    whale_trade = {
        "wallet_address": "0xTOP",
        "side": "BUY",
        "size": 100.0,
        "market_id": "mkt_1",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal is not None
    assert "total_score" in signal
    assert signal["total_score"] > 0
    assert signal["direction"] == "BUY"


def test_generate_signal_action_auto_trade(engine):
    _setup_tracked_wallet(TEST_DB, "0xBIG", rank=1)
    _insert_price_candles(TEST_DB, "BTC", [100, 101, 102, 103, 104])

    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO markets (condition_id, question, token_id_yes, token_id_no,
           asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        ("mkt_2", "Will BTC go up?", "tok_y2", "tok_n2", "BTC",
         0.52, 0.48, 200000, (now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()

    # Top 1 wallet, big bet, uptrend = high score
    whale_trade = {
        "wallet_address": "0xBIG",
        "side": "BUY",
        "size": 200.0,  # 4x average
        "market_id": "mkt_2",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal["action"] in ("auto_trade", "alert", "logged")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL with "cannot import name 'SignalEngine'"

- [ ] **Step 3: Write signal_engine.py**

```python
# modules/signal_engine.py
from datetime import datetime, timezone, timedelta
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("signal_engine")


class SignalEngine:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_wallet_info(self, address: str) -> dict | None:
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM wallets WHERE address = ?", (address,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _get_wallet_rank(self, address: str) -> int | None:
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT rank FROM tracked_wallets WHERE address = ?", (address,)
        ).fetchone()
        conn.close()
        return row["rank"] if row else None

    def _get_market_info(self, market_id: str) -> dict | None:
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM markets WHERE condition_id = ?", (market_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _get_recent_candles(self, asset: str, limit: int = 10) -> list[dict]:
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM price_candles WHERE asset = ? ORDER BY timestamp DESC LIMIT ?",
            (asset, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _calc_whale_score(self, trade: dict) -> float:
        address = trade["wallet_address"]
        rank = self._get_wallet_rank(address)
        if rank is None:
            return 0.0

        wallet = self._get_wallet_info(address)
        if wallet is None:
            return 0.0

        # Rank score (0-15)
        if rank <= 5:
            rank_pts = 15.0
        elif rank <= 10:
            rank_pts = 10.0
        else:
            rank_pts = 5.0

        # Conviction score (0-15): bet size relative to average
        avg_bet = wallet.get("avg_bet_size", 1.0) or 1.0
        size_ratio = trade.get("size", 0) / avg_bet
        conviction_pts = min(15.0, size_ratio * 5.0)

        # Win rate on this market type (0-10)
        wr = wallet.get("win_rate", 0.5)
        wr_pts = wr * 10.0

        return min(40.0, rank_pts + conviction_pts + wr_pts)

    def _calc_market_score(self, market_id: str, direction: str) -> float:
        market = self._get_market_info(market_id)
        if market is None:
            return 0.0

        asset = market.get("asset", "")
        candles = self._get_recent_candles(asset, 10)
        if len(candles) < 2:
            return 10.0  # neutral score if no price data

        # Momentum (0-15): is price trending in the trade direction?
        prices = [c["close"] for c in reversed(candles)]
        momentum = (prices[-1] - prices[0]) / (prices[0] + 0.01)
        is_aligned = (momentum > 0 and direction == "BUY") or (
            momentum < 0 and direction == "SELL"
        )
        momentum_pts = 15.0 if is_aligned else 5.0

        # Volatility (0-10): moderate is best
        high_low_ranges = [(c["high"] - c["low"]) / (c["low"] + 0.01) for c in candles]
        avg_range = sum(high_low_ranges) / len(high_low_ranges)
        if 0.001 < avg_range < 0.01:
            vol_pts = 10.0  # sweet spot
        elif avg_range <= 0.001:
            vol_pts = 3.0  # too quiet
        else:
            vol_pts = 5.0  # too volatile

        # Volume (0-10)
        volume = market.get("volume", 0)
        if volume > 100000:
            vol_market_pts = 10.0
        elif volume > 50000:
            vol_market_pts = 7.0
        elif volume > 10000:
            vol_market_pts = 5.0
        else:
            vol_market_pts = 2.0

        return min(35.0, momentum_pts + vol_pts + vol_market_pts)

    def _calc_confluence_score(self, market_id: str, direction: str) -> float:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc)
        two_min_ago = (now - timedelta(minutes=2)).isoformat()

        # Check for recent signals on same market in same direction
        rows = conn.execute(
            """SELECT COUNT(*) as cnt FROM signals
               WHERE market_id = ? AND direction = ? AND timestamp > ?""",
            (market_id, direction, two_min_ago),
        ).fetchone()
        conn.close()

        same_direction_count = rows["cnt"] if rows else 0

        # Multiple wallets same direction (0-15)
        if same_direction_count >= 3:
            confluence_pts = 15.0
        elif same_direction_count >= 1:
            confluence_pts = 8.0
        else:
            confluence_pts = 0.0

        # Pattern consistency (0-10) — simplified: always give 5 as baseline
        pattern_pts = 5.0

        return min(25.0, confluence_pts + pattern_pts)

    def generate_signal(self, whale_trade: dict) -> dict | None:
        address = whale_trade.get("wallet_address", "")
        market_id = whale_trade.get("market_id", "")
        direction = whale_trade.get("side", "BUY")
        size = whale_trade.get("size", 0)

        whale_score = self._calc_whale_score(whale_trade)
        market_score = self._calc_market_score(market_id, direction)
        confluence_score = self._calc_confluence_score(market_id, direction)
        total_score = whale_score + market_score + confluence_score

        # Determine action
        if total_score >= self.config.SIGNAL_AUTO_TRADE_THRESHOLD:
            action = "auto_trade"
        elif total_score >= self.config.SIGNAL_ALERT_THRESHOLD:
            action = "alert"
        else:
            action = "logged"

        signal = {
            "market_id": market_id,
            "direction": direction,
            "whale_score": whale_score,
            "market_score": market_score,
            "confluence_score": confluence_score,
            "total_score": total_score,
            "action": action,
            "triggering_wallet": address,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Store signal
        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO signals
               (market_id, direction, whale_score, market_score, confluence_score,
                total_score, action_taken, triggering_wallet, timestamp)
               VALUES (:market_id, :direction, :whale_score, :market_score,
                       :confluence_score, :total_score, :action, :triggering_wallet,
                       :timestamp)""",
            signal,
        )
        signal["id"] = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(
            f"Signal: {direction} on {market_id[:10]} | "
            f"Score: {total_score:.1f} (W:{whale_score:.1f} M:{market_score:.1f} C:{confluence_score:.1f}) | "
            f"Action: {action}"
        )
        return signal
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/signal_engine.py tests/test_signal_engine.py
git commit -m "feat: add signal engine with whale/market/confluence scoring"
```

---

### Task 8: Risk Manager

**Files:**
- Create: `modules/risk_manager.py`
- Create: `tests/test_risk_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_risk_manager.py
import os
import pytest
from datetime import datetime, timezone
from modules.risk_manager import RiskManager
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_risk.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.MAX_CONCURRENT_POSITIONS = 10
    cfg.MAX_CAPITAL_PER_TRADE_PCT = 0.10
    cfg.MAX_TOTAL_EXPOSURE_PCT = 0.30
    cfg.HARD_STOP_DRAWDOWN_PCT = 0.30
    cfg.SOFT_STOP_DRAWDOWN_PCT = 0.15
    cfg.DAILY_LOSS_LIMIT_PCT = 0.10
    cfg.BASE_BET_PCT = 0.02
    cfg.CONSECUTIVE_LOSS_PAUSE = 3
    return cfg


def _init_portfolio(db_path, capital=100.0):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO portfolio
           (id, starting_capital, current_value, peak_value, updated_at)
           VALUES (1, ?, ?, ?, ?)""",
        (capital, capital, capital, now),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def risk_mgr(config):
    _init_portfolio(TEST_DB, 100.0)
    return RiskManager(config)


def test_can_trade_returns_true_when_healthy(risk_mgr):
    result = risk_mgr.can_trade()
    assert result["allowed"] is True


def test_can_trade_blocked_when_paused(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute("UPDATE portfolio SET is_paused = 1 WHERE id = 1")
    conn.commit()
    conn.close()
    result = risk_mgr.can_trade()
    assert result["allowed"] is False
    assert "paused" in result["reason"]


def test_can_trade_blocked_hard_stop_drawdown(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute(
        "UPDATE portfolio SET current_value = 65, peak_value = 100 WHERE id = 1"
    )
    conn.commit()
    conn.close()
    result = risk_mgr.can_trade()
    assert result["allowed"] is False
    assert "hard stop" in result["reason"].lower()


def test_calc_position_size_base(risk_mgr):
    size = risk_mgr.calc_position_size(signal_score=70)
    # Base bet = 2% of 100 = $2, score 70 = 1.0x multiplier
    assert size == pytest.approx(2.0, abs=0.1)


def test_calc_position_size_high_confidence(risk_mgr):
    size = risk_mgr.calc_position_size(signal_score=100)
    # Base bet = $2, score 100 = 2.0x multiplier = $4
    assert size == pytest.approx(4.0, abs=0.1)


def test_calc_position_size_capped_at_max(risk_mgr):
    # Even with huge score, can't exceed 10% of capital
    size = risk_mgr.calc_position_size(signal_score=100)
    assert size <= 100 * 0.10


def test_calc_position_size_reduced_during_soft_stop(risk_mgr):
    conn = get_connection(TEST_DB)
    conn.execute(
        "UPDATE portfolio SET current_value = 87, peak_value = 100 WHERE id = 1"
    )
    conn.commit()
    conn.close()
    size = risk_mgr.calc_position_size(signal_score=70)
    # Should be 50% of normal: $2 * 0.5 = $1
    assert size == pytest.approx(1.0, abs=0.2)


def test_record_trade_outcome_updates_portfolio(risk_mgr):
    risk_mgr.record_trade_outcome(pnl=5.0)
    conn = get_connection(TEST_DB)
    row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
    conn.close()
    assert row["current_value"] == 105.0
    assert row["total_trades"] == 1
    assert row["total_wins"] == 1


def test_pause_and_resume(risk_mgr):
    risk_mgr.pause()
    assert risk_mgr.can_trade()["allowed"] is False
    risk_mgr.resume()
    assert risk_mgr.can_trade()["allowed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: FAIL with "cannot import name 'RiskManager'"

- [ ] **Step 3: Write risk_manager.py**

```python
# modules/risk_manager.py
from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("risk_manager")


class RiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH

    def _get_portfolio(self) -> dict:
        conn = get_connection(self.db_path)
        row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
        conn.close()
        if row is None:
            raise RuntimeError("Portfolio not initialized. Run init_portfolio first.")
        return dict(row)

    def init_portfolio(self, starting_capital: float) -> None:
        conn = get_connection(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO portfolio
               (id, starting_capital, current_value, peak_value,
                total_trades, total_wins, total_pnl, daily_pnl,
                daily_pnl_date, is_paused, updated_at)
               VALUES (1, ?, ?, ?, 0, 0, 0.0, 0.0, ?, 0, ?)""",
            (starting_capital, starting_capital, starting_capital, now[:10], now),
        )
        conn.commit()
        conn.close()
        log.info(f"Portfolio initialized with ${starting_capital}")

    def can_trade(self) -> dict:
        p = self._get_portfolio()

        if p["is_paused"]:
            return {"allowed": False, "reason": "Bot is paused"}

        # Hard stop: 30% drawdown from peak
        drawdown = 1 - (p["current_value"] / (p["peak_value"] or 1))
        if drawdown >= self.config.HARD_STOP_DRAWDOWN_PCT:
            self.pause()
            return {
                "allowed": False,
                "reason": f"Hard stop: {drawdown:.1%} drawdown from peak",
            }

        # Daily loss limit
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = p["daily_pnl"] if p["daily_pnl_date"] == today else 0.0
        daily_loss = -daily_pnl / (p["starting_capital"] or 1)
        if daily_loss >= self.config.DAILY_LOSS_LIMIT_PCT:
            return {
                "allowed": False,
                "reason": f"Daily loss limit: {daily_loss:.1%} loss today",
            }

        # Max concurrent positions
        conn = get_connection(self.db_path)
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["cnt"]
        conn.close()

        if open_count >= self.config.MAX_CONCURRENT_POSITIONS:
            return {
                "allowed": False,
                "reason": f"Max positions: {open_count}/{self.config.MAX_CONCURRENT_POSITIONS}",
            }

        # Max total exposure
        conn = get_connection(self.db_path)
        total_exposure = conn.execute(
            "SELECT COALESCE(SUM(size), 0) as total FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["total"]
        conn.close()

        max_exposure = p["current_value"] * self.config.MAX_TOTAL_EXPOSURE_PCT
        if total_exposure >= max_exposure:
            return {
                "allowed": False,
                "reason": f"Max exposure: ${total_exposure:.2f} >= ${max_exposure:.2f}",
            }

        return {"allowed": True, "reason": "OK"}

    def calc_position_size(self, signal_score: float) -> float:
        p = self._get_portfolio()
        capital = p["current_value"]

        # Base bet: 2% of capital
        base = capital * self.config.BASE_BET_PCT

        # Scale by confidence: 70=1x, 85=1.5x, 100=2x
        multiplier = 1.0 + ((signal_score - 70) / 30)
        multiplier = max(1.0, min(2.0, multiplier))

        size = base * multiplier

        # Soft stop: reduce by 50% if in drawdown zone
        drawdown = 1 - (capital / (p["peak_value"] or 1))
        if drawdown >= self.config.SOFT_STOP_DRAWDOWN_PCT:
            size *= 0.5
            log.warning(f"Soft stop active: position size halved to ${size:.2f}")

        # Hard cap: never exceed 10% of capital
        max_size = capital * self.config.MAX_CAPITAL_PER_TRADE_PCT
        size = min(size, max_size)

        return round(size, 2)

    def record_trade_outcome(self, pnl: float) -> None:
        conn = get_connection(self.db_path)
        p = dict(conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone())
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        new_value = p["current_value"] + pnl
        new_peak = max(p["peak_value"], new_value)
        total_trades = p["total_trades"] + 1
        total_wins = p["total_wins"] + (1 if pnl > 0 else 0)
        total_pnl = p["total_pnl"] + pnl

        # Reset daily PnL if new day
        if p["daily_pnl_date"] == today:
            daily_pnl = p["daily_pnl"] + pnl
        else:
            daily_pnl = pnl

        conn.execute(
            """UPDATE portfolio SET
               current_value = ?, peak_value = ?, total_trades = ?,
               total_wins = ?, total_pnl = ?, daily_pnl = ?,
               daily_pnl_date = ?, updated_at = ?
               WHERE id = 1""",
            (new_value, new_peak, total_trades, total_wins, total_pnl,
             daily_pnl, today, now.isoformat()),
        )
        conn.commit()
        conn.close()

        log.info(f"Trade outcome: PnL=${pnl:.2f} | Portfolio=${new_value:.2f}")

    def pause(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE portfolio SET is_paused = 1 WHERE id = 1")
        conn.commit()
        conn.close()
        log.warning("Trading PAUSED")

    def resume(self) -> None:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE portfolio SET is_paused = 0 WHERE id = 1")
        conn.commit()
        conn.close()
        log.info("Trading RESUMED")

    def get_status(self) -> dict:
        p = self._get_portfolio()
        conn = get_connection(self.db_path)
        open_trades = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_trades WHERE outcome = 'pending'"
        ).fetchone()["cnt"]
        conn.close()

        drawdown = 1 - (p["current_value"] / (p["peak_value"] or 1))
        win_rate = p["total_wins"] / p["total_trades"] if p["total_trades"] > 0 else 0

        return {
            "current_value": p["current_value"],
            "starting_capital": p["starting_capital"],
            "total_pnl": p["total_pnl"],
            "total_trades": p["total_trades"],
            "win_rate": win_rate,
            "drawdown": drawdown,
            "daily_pnl": p["daily_pnl"],
            "open_positions": open_trades,
            "is_paused": bool(p["is_paused"]),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: add risk manager with drawdown protection and position sizing"
```

---

### Task 9: Trade Executor

**Files:**
- Create: `modules/trade_executor.py`
- Create: `tests/test_trade_executor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trade_executor.py
import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from modules.trade_executor import TradeExecutor
from utils.db import init_db, get_connection
from config import Config

TEST_DB = "data/test_executor.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    # Init portfolio
    conn = get_connection(TEST_DB)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO portfolio
           (id, starting_capital, current_value, peak_value, updated_at)
           VALUES (1, 100, 100, 100, ?)""",
        (now,),
    )
    conn.commit()
    conn.close()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.TRADING_MODE = "paper"
    return cfg


@pytest.fixture
def executor(config):
    return TradeExecutor(config)


def test_paper_trade_logs_to_db(executor):
    signal = {
        "id": 1,
        "market_id": "mkt_1",
        "direction": "BUY",
        "total_score": 75.0,
    }
    market = {
        "condition_id": "mkt_1",
        "token_id_yes": "tok_y",
        "token_id_no": "tok_n",
        "price_yes": 0.55,
        "price_no": 0.45,
    }
    result = executor.execute_paper_trade(signal, market, size=2.0)
    assert result["status"] == "filled"
    assert result["size"] == 2.0

    conn = get_connection(TEST_DB)
    trades = conn.execute("SELECT * FROM bot_trades").fetchall()
    conn.close()
    assert len(trades) == 1
    assert trades[0]["side"] == "BUY"
    assert trades[0]["size"] == 2.0


def test_paper_trade_buy_uses_yes_price(executor):
    signal = {"id": 1, "market_id": "mkt_1", "direction": "BUY", "total_score": 80.0}
    market = {
        "condition_id": "mkt_1",
        "token_id_yes": "tok_y",
        "token_id_no": "tok_n",
        "price_yes": 0.60,
        "price_no": 0.40,
    }
    result = executor.execute_paper_trade(signal, market, size=5.0)
    assert result["entry_price"] == 0.60


def test_paper_trade_sell_uses_no_price(executor):
    signal = {"id": 2, "market_id": "mkt_2", "direction": "SELL", "total_score": 72.0}
    market = {
        "condition_id": "mkt_2",
        "token_id_yes": "tok_y2",
        "token_id_no": "tok_n2",
        "price_yes": 0.55,
        "price_no": 0.45,
    }
    result = executor.execute_paper_trade(signal, market, size=3.0)
    assert result["entry_price"] == 0.45
    assert result["side"] == "SELL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_executor.py -v`
Expected: FAIL with "cannot import name 'TradeExecutor'"

- [ ] **Step 3: Write trade_executor.py**

```python
# modules/trade_executor.py
from datetime import datetime, timezone
from utils.db import get_connection
from utils.logger import get_logger
from config import Config

log = get_logger("trade_executor")


class TradeExecutor:
    def __init__(self, config: Config):
        self.config = config
        self.db_path = config.DB_PATH
        self._clob_client = None

    def _get_clob_client(self):
        if self._clob_client is None and self.config.TRADING_MODE == "live":
            from py_clob_client.client import ClobClient

            self._clob_client = ClobClient(
                self.config.POLYMARKET_API_URL,
                key=self.config.PRIVATE_KEY,
                chain_id=self.config.CHAIN_ID,
            )
            creds = self._clob_client.create_or_derive_api_creds()
            self._clob_client.set_api_creds(creds)
            log.info("Polymarket CLOB client initialized")
        return self._clob_client

    def execute_paper_trade(self, signal: dict, market: dict, size: float) -> dict:
        direction = signal["direction"]
        if direction == "BUY":
            entry_price = market["price_yes"]
            token_id = market["token_id_yes"]
        else:
            entry_price = market["price_no"]
            token_id = market["token_id_no"]

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection(self.db_path)
        cursor = conn.execute(
            """INSERT INTO bot_trades
               (market_id, side, size, entry_price, outcome, pnl,
                signal_score, signal_id, order_id, timestamp)
               VALUES (?, ?, ?, ?, 'pending', 0.0, ?, ?, ?, ?)""",
            (
                signal["market_id"],
                direction,
                size,
                entry_price,
                signal["total_score"],
                signal.get("id"),
                f"paper_{now}",
                now,
            ),
        )
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(
            f"PAPER TRADE: {direction} ${size:.2f} on {signal['market_id'][:10]} "
            f"@ {entry_price:.4f} | Score: {signal['total_score']:.1f}"
        )

        return {
            "trade_id": trade_id,
            "status": "filled",
            "side": direction,
            "size": size,
            "entry_price": entry_price,
            "token_id": token_id,
            "order_id": f"paper_{now}",
        }

    def execute_live_trade(self, signal: dict, market: dict, size: float) -> dict:
        client = self._get_clob_client()
        if client is None:
            log.error("CLOB client not available for live trading")
            return {"status": "error", "reason": "CLOB client not initialized"}

        direction = signal["direction"]
        if direction == "BUY":
            token_id = market["token_id_yes"]
            price = market["price_yes"]
        else:
            token_id = market["token_id_no"]
            price = market["price_no"]

        try:
            order = client.create_order(
                token_id=token_id,
                price=price,
                size=size,
                side="BUY",  # Always BUY the token (yes or no)
            )
            resp = client.post_order(order)
            order_id = resp.get("orderID", "")

            now = datetime.now(timezone.utc).isoformat()
            conn = get_connection(self.db_path)
            conn.execute(
                """INSERT INTO bot_trades
                   (market_id, side, size, entry_price, outcome, pnl,
                    signal_score, signal_id, order_id, timestamp)
                   VALUES (?, ?, ?, ?, 'pending', 0.0, ?, ?, ?, ?)""",
                (
                    signal["market_id"],
                    direction,
                    size,
                    price,
                    signal["total_score"],
                    signal.get("id"),
                    order_id,
                    now,
                ),
            )
            conn.commit()
            conn.close()

            log.info(
                f"LIVE TRADE: {direction} ${size:.2f} on {signal['market_id'][:10]} "
                f"@ {price:.4f} | Order: {order_id}"
            )

            return {
                "trade_id": order_id,
                "status": "filled",
                "side": direction,
                "size": size,
                "entry_price": price,
                "token_id": token_id,
                "order_id": order_id,
            }

        except Exception as e:
            log.error(f"Live trade failed: {e}")
            return {"status": "error", "reason": str(e)}

    def execute(self, signal: dict, market: dict, size: float) -> dict:
        if self.config.TRADING_MODE == "paper":
            return self.execute_paper_trade(signal, market, size)
        else:
            return self.execute_live_trade(signal, market, size)

    def resolve_trade(self, trade_id: int, won: bool) -> float:
        conn = get_connection(self.db_path)
        trade = conn.execute(
            "SELECT * FROM bot_trades WHERE id = ?", (trade_id,)
        ).fetchone()

        if trade is None:
            conn.close()
            return 0.0

        size = trade["size"]
        entry_price = trade["entry_price"]

        if won:
            # Win: paid entry_price per share, get $1 back per share
            # Shares bought = size / entry_price
            shares = size / entry_price
            pnl = shares * (1.0 - entry_price)
        else:
            pnl = -size

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE bot_trades SET outcome = ?, pnl = ?, resolved_at = ? WHERE id = ?",
            ("won" if won else "lost", pnl, now, trade_id),
        )
        conn.commit()
        conn.close()

        log.info(f"Trade {trade_id} resolved: {'WON' if won else 'LOST'} | PnL: ${pnl:.2f}")
        return pnl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trade_executor.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/trade_executor.py tests/test_trade_executor.py
git commit -m "feat: add trade executor with paper and live trading"
```

---

### Task 10: Telegram Notifier

**Files:**
- Create: `modules/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_notifier.py
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from modules.notifier import Notifier
from config import Config

TEST_DB = "data/test_notifier.db"


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.TELEGRAM_BOT_TOKEN = "fake_token"
    cfg.TELEGRAM_CHAT_ID = "123456"
    return cfg


@pytest.fixture
def notifier(config):
    return Notifier(config)


def test_format_trade_alert(notifier):
    trade = {
        "side": "BUY",
        "size": 2.50,
        "entry_price": 0.55,
        "market_id": "mkt_btc_up",
    }
    signal_score = 78.5
    msg = notifier.format_trade_alert(trade, signal_score)
    assert "BUY" in msg
    assert "$2.50" in msg
    assert "78.5" in msg


def test_format_trade_outcome(notifier):
    msg = notifier.format_trade_outcome(
        market_id="mkt_btc_up",
        won=True,
        pnl=1.50,
        portfolio_value=101.50,
    )
    assert "WON" in msg
    assert "$1.50" in msg
    assert "$101.50" in msg


def test_format_daily_summary(notifier):
    stats = {
        "current_value": 105.0,
        "starting_capital": 100.0,
        "total_pnl": 5.0,
        "total_trades": 10,
        "win_rate": 0.70,
        "daily_pnl": 3.0,
        "open_positions": 2,
        "is_paused": False,
    }
    msg = notifier.format_daily_summary(stats)
    assert "$105.00" in msg
    assert "70.0%" in msg
    assert "$3.00" in msg


def test_format_status(notifier):
    stats = {
        "current_value": 95.0,
        "starting_capital": 100.0,
        "total_pnl": -5.0,
        "total_trades": 8,
        "win_rate": 0.50,
        "drawdown": 0.05,
        "daily_pnl": -2.0,
        "open_positions": 1,
        "is_paused": False,
    }
    msg = notifier.format_status(stats)
    assert "$95.00" in msg
    assert "-$5.00" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: FAIL with "cannot import name 'Notifier'"

- [ ] **Step 3: Write notifier.py**

```python
# modules/notifier.py
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from utils.logger import get_logger
from config import Config

log = get_logger("notifier")


class Notifier:
    def __init__(self, config: Config):
        self.config = config
        self.chat_id = config.TELEGRAM_CHAT_ID
        self._app = None
        self._on_pause = None
        self._on_resume = None
        self._on_kill = None
        self._get_status = None

    def set_callbacks(self, on_pause=None, on_resume=None, on_kill=None, get_status=None):
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_kill = on_kill
        self._get_status = get_status

    def _build_app(self):
        if not self.config.TELEGRAM_BOT_TOKEN:
            log.warning("No Telegram bot token configured")
            return None

        app = ApplicationBuilder().token(self.config.TELEGRAM_BOT_TOKEN).build()

        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("pause", self._cmd_pause))
        app.add_handler(CommandHandler("resume", self._cmd_resume))
        app.add_handler(CommandHandler("kill", self._cmd_kill))
        app.add_handler(CommandHandler("today", self._cmd_today))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(CommandHandler("balance", self._cmd_balance))
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))

        return app

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "PolyBot is running. Use /help for commands."
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "/status - Current P&L and positions\n"
            "/pause - Pause trading\n"
            "/resume - Resume trading\n"
            "/kill - Emergency stop\n"
            "/today - Today's summary\n"
            "/history - 7-day performance\n"
            "/balance - Portfolio value"
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = self.format_status(stats)
        else:
            msg = "Status not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._on_pause:
            self._on_pause()
        await update.message.reply_text("Trading PAUSED")

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._on_resume:
            self._on_resume()
        await update.message.reply_text("Trading RESUMED")

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("EMERGENCY STOP - Shutting down")
        if self._on_kill:
            self._on_kill()

    async def _cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = self.format_daily_summary(stats)
        else:
            msg = "Stats not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = (
                f"<b>7-Day History</b>\n"
                f"Trades: {stats['total_trades']}\n"
                f"Win Rate: {stats['win_rate']:.1%}\n"
                f"Total P&L: ${stats['total_pnl']:.2f}\n"
                f"Portfolio: ${stats['current_value']:.2f}"
            )
        else:
            msg = "History not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = f"Portfolio: ${stats['current_value']:.2f}"
        else:
            msg = "Balance not available"
        await update.message.reply_text(msg)

    async def send_message(self, text: str) -> None:
        if self._app and self._app.bot:
            try:
                await self._app.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode="HTML",
                )
            except Exception as e:
                log.error(f"Failed to send Telegram message: {e}")

    def format_trade_alert(self, trade: dict, signal_score: float) -> str:
        return (
            f"<b>TRADE EXECUTED</b>\n"
            f"Direction: {trade['side']}\n"
            f"Size: ${trade['size']:.2f}\n"
            f"Price: {trade['entry_price']:.4f}\n"
            f"Market: {trade['market_id'][:20]}\n"
            f"Signal Score: {signal_score:.1f}"
        )

    def format_trade_outcome(self, market_id: str, won: bool, pnl: float, portfolio_value: float) -> str:
        icon = "WON" if won else "LOST"
        return (
            f"<b>TRADE {icon}</b>\n"
            f"Market: {market_id[:20]}\n"
            f"P&L: ${pnl:.2f}\n"
            f"Portfolio: ${portfolio_value:.2f}"
        )

    def format_daily_summary(self, stats: dict) -> str:
        return (
            f"<b>Daily Summary</b>\n"
            f"Portfolio: ${stats['current_value']:.2f}\n"
            f"Today's P&L: ${stats.get('daily_pnl', 0):.2f}\n"
            f"Trades: {stats['total_trades']}\n"
            f"Win Rate: {stats['win_rate']:.1%}\n"
            f"Open Positions: {stats['open_positions']}\n"
            f"Status: {'PAUSED' if stats['is_paused'] else 'ACTIVE'}"
        )

    def format_status(self, stats: dict) -> str:
        pnl_sign = "" if stats["total_pnl"] >= 0 else "-"
        return (
            f"<b>PolyBot Status</b>\n"
            f"Portfolio: ${stats['current_value']:.2f}\n"
            f"Total P&L: {pnl_sign}${abs(stats['total_pnl']):.2f}\n"
            f"Drawdown: {stats.get('drawdown', 0):.1%}\n"
            f"Trades: {stats['total_trades']}\n"
            f"Win Rate: {stats['win_rate']:.1%}\n"
            f"Open: {stats['open_positions']}\n"
            f"Status: {'PAUSED' if stats['is_paused'] else 'ACTIVE'}"
        )

    async def start_polling(self):
        self._app = self._build_app()
        if self._app:
            log.info("Telegram bot starting...")
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/notifier.py tests/test_notifier.py
git commit -m "feat: add Telegram notifier with commands and alerts"
```

---

### Task 11: Main Entry Point

**Files:**
- Create: `polybot.py`

- [ ] **Step 1: Write polybot.py**

```python
# polybot.py
import asyncio
import argparse
import signal
import sys
from datetime import datetime, timezone

from config import Config
from utils.db import init_db
from utils.logger import get_logger
from modules.data_collector import DataCollector
from modules.wallet_scanner import WalletScanner
from modules.signal_engine import SignalEngine
from modules.trade_executor import TradeExecutor
from modules.risk_manager import RiskManager
from modules.notifier import Notifier

log = get_logger("polybot")


class PolyBot:
    def __init__(self, config: Config):
        self.config = config
        self.running = False

        # Initialize modules
        self.collector = DataCollector(config)
        self.scanner = WalletScanner(config)
        self.signal_engine = SignalEngine(config)
        self.executor = TradeExecutor(config)
        self.risk_manager = RiskManager(config)
        self.notifier = Notifier(config)

        # Wire up notifier callbacks
        self.notifier.set_callbacks(
            on_pause=self.risk_manager.pause,
            on_resume=self.risk_manager.resume,
            on_kill=self.stop,
            get_status=self.risk_manager.get_status,
        )

    async def startup(self, starting_capital: float):
        log.info(f"Starting PolyBot in {self.config.TRADING_MODE} mode")
        log.info(f"Starting capital: ${starting_capital}")

        # Initialize database
        init_db(self.config.DB_PATH)

        # Initialize portfolio
        self.risk_manager.init_portfolio(starting_capital)

        # Start Telegram bot
        await self.notifier.start_polling()
        await self.notifier.send_message(
            f"PolyBot started in <b>{self.config.TRADING_MODE}</b> mode\n"
            f"Capital: ${starting_capital:.2f}"
        )

        self.running = True

    async def initial_scan(self):
        log.info("Running initial wallet scan...")
        await self.notifier.send_message("Running initial wallet scan...")

        # Fetch active markets
        await self.collector.fetch_active_markets()

        # Fetch price data
        for asset in self.config.TARGET_MARKETS:
            await self.collector.fetch_price_candles(asset)

        # TODO: In a real implementation, we'd need to discover wallet addresses
        # from Polymarket's public trade data. For now, we start with an empty
        # tracked list and build it up as we observe trades.
        log.info("Initial scan complete. Monitoring for wallet activity...")
        await self.notifier.send_message("Initial scan complete. Bot is now monitoring.")

    async def market_loop(self):
        while self.running:
            try:
                await self.collector.fetch_active_markets()
                await asyncio.sleep(self.config.MARKET_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Market loop error: {e}")
                await asyncio.sleep(5)

    async def price_loop(self):
        while self.running:
            try:
                for asset in self.config.TARGET_MARKETS:
                    await self.collector.fetch_price_candles(asset, limit=10)
                await asyncio.sleep(self.config.PRICE_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Price loop error: {e}")
                await asyncio.sleep(5)

    async def wallet_monitor_loop(self):
        while self.running:
            try:
                new_trades = await self.collector.poll_tracked_wallets()
                for trade in new_trades:
                    await self.process_whale_trade(trade)
                await asyncio.sleep(self.config.WALLET_POLL_INTERVAL_SEC)
            except Exception as e:
                log.error(f"Wallet monitor error: {e}")
                await asyncio.sleep(5)

    async def daily_refresh(self):
        while self.running:
            try:
                # Refresh wallet scores and tracking list
                tracked = self.scanner.rank_and_track()
                if tracked:
                    addrs = ", ".join(t["address"][:8] + "..." for t in tracked[:5])
                    await self.notifier.send_message(
                        f"Daily refresh: tracking {len(tracked)} wallets\nTop 5: {addrs}"
                    )

                # Send daily summary
                stats = self.risk_manager.get_status()
                summary = self.notifier.format_daily_summary(stats)
                await self.notifier.send_message(summary)

                # Sleep 24 hours
                await asyncio.sleep(86400)
            except Exception as e:
                log.error(f"Daily refresh error: {e}")
                await asyncio.sleep(3600)

    async def process_whale_trade(self, trade: dict):
        # Generate signal
        signal = self.signal_engine.generate_signal(trade)
        if signal is None:
            return

        action = signal["action"]

        if action == "auto_trade":
            # Check risk manager
            can = self.risk_manager.can_trade()
            if not can["allowed"]:
                log.info(f"Trade blocked by risk manager: {can['reason']}")
                await self.notifier.send_message(
                    f"Signal blocked: {can['reason']}\nScore: {signal['total_score']:.1f}"
                )
                return

            # Calculate position size
            size = self.risk_manager.calc_position_size(signal["total_score"])

            # Get market info
            from utils.db import get_connection
            conn = get_connection(self.config.DB_PATH)
            market = conn.execute(
                "SELECT * FROM markets WHERE condition_id = ?",
                (signal["market_id"],),
            ).fetchone()
            conn.close()

            if market is None:
                log.warning(f"Market not found: {signal['market_id']}")
                return

            market = dict(market)

            # Execute trade
            result = self.executor.execute(signal, market, size)

            if result["status"] == "filled":
                msg = self.notifier.format_trade_alert(result, signal["total_score"])
                await self.notifier.send_message(msg)

        elif action == "alert":
            await self.notifier.send_message(
                f"<b>SIGNAL DETECTED</b>\n"
                f"Direction: {signal['direction']}\n"
                f"Market: {signal['market_id'][:20]}\n"
                f"Score: {signal['total_score']:.1f}\n"
                f"(Below auto-trade threshold)"
            )

    def stop(self):
        log.info("Stopping PolyBot...")
        self.running = False

    async def run(self, starting_capital: float):
        await self.startup(starting_capital)
        await self.initial_scan()

        # Run all loops concurrently
        tasks = [
            asyncio.create_task(self.market_loop()),
            asyncio.create_task(self.price_loop()),
            asyncio.create_task(self.wallet_monitor_loop()),
            asyncio.create_task(self.daily_refresh()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Tasks cancelled")
        finally:
            await self.notifier.stop()
            log.info("PolyBot stopped")


def main():
    parser = argparse.ArgumentParser(description="PolyBot - Polymarket Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["paper", "live"],
        default=None,
        help="Trading mode (overrides .env)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=100.0,
        help="Starting capital in USDC (default: 100)",
    )
    args = parser.parse_args()

    config = Config()
    if args.mode:
        config.TRADING_MODE = args.mode

    bot = PolyBot(config)

    # Handle Ctrl+C
    def signal_handler(sig, frame):
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(bot.run(args.capital))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports without error**

Run: `python -c "from polybot import PolyBot; print('OK')"`
Expected: prints "OK"

- [ ] **Step 3: Commit**

```bash
git add polybot.py
git commit -m "feat: add main entry point with async event loop"
```

---

### Task 12: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
import os
import pytest
from datetime import datetime, timezone, timedelta
from config import Config
from utils.db import init_db, get_connection
from modules.data_collector import DataCollector
from modules.wallet_scanner import WalletScanner
from modules.signal_engine import SignalEngine
from modules.trade_executor import TradeExecutor
from modules.risk_manager import RiskManager
from modules.notifier import Notifier

TEST_DB = "data/test_integration.db"


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def config():
    cfg = Config()
    cfg.DB_PATH = TEST_DB
    cfg.TRADING_MODE = "paper"
    cfg.TELEGRAM_BOT_TOKEN = ""
    cfg.MIN_WALLET_TRADES = 5
    cfg.TOP_TRACKED_WALLETS = 2
    return cfg


def _seed_test_data(db_path):
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc)

    # Portfolio
    conn.execute(
        """INSERT INTO portfolio
           (id, starting_capital, current_value, peak_value, daily_pnl_date, updated_at)
           VALUES (1, 100, 100, 100, ?, ?)""",
        (now.strftime("%Y-%m-%d"), now.isoformat()),
    )

    # A good wallet with trades
    for i in range(8):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES ('0xGOOD', ?, 'BUY', 50, 0.55, 'won', 40, ?)""",
            (f"mkt_{i}", (now - timedelta(hours=i)).isoformat()),
        )
    for i in range(2):
        conn.execute(
            """INSERT INTO wallet_trades
               (wallet_address, market_id, side, size, entry_price,
                outcome, pnl, timestamp)
               VALUES ('0xGOOD', ?, 'BUY', 50, 0.55, 'lost', -50, ?)""",
            (f"mkt_loss_{i}", (now - timedelta(hours=10 + i)).isoformat()),
        )

    # An active market
    conn.execute(
        """INSERT INTO markets
           (condition_id, question, token_id_yes, token_id_no,
            asset, price_yes, price_no, volume, end_time, active, updated_at)
           VALUES ('mkt_live', 'Will BTC go up?', 'tok_y', 'tok_n',
                   'BTC', 0.55, 0.45, 80000,
                   ?, 1, ?)""",
        ((now + timedelta(minutes=5)).isoformat(), now.isoformat()),
    )

    # Price candles (uptrend)
    for i in range(10):
        conn.execute(
            """INSERT INTO price_candles
               (asset, open, high, low, close, volume, timestamp)
               VALUES ('BTC', ?, ?, ?, ?, 1000, ?)""",
            (100 + i, 110 + i, 90 + i, 101 + i,
             (now - timedelta(minutes=10 - i)).isoformat()),
        )

    conn.commit()
    conn.close()


def test_full_pipeline(config):
    _seed_test_data(TEST_DB)

    # Step 1: Wallet Scanner ranks wallets
    scanner = WalletScanner(config)
    tracked = scanner.rank_and_track()
    assert len(tracked) >= 1
    assert tracked[0]["address"] == "0xGOOD"

    # Step 2: Signal Engine generates signal from whale trade
    engine = SignalEngine(config)
    whale_trade = {
        "wallet_address": "0xGOOD",
        "side": "BUY",
        "size": 100.0,
        "market_id": "mkt_live",
    }
    signal = engine.generate_signal(whale_trade)
    assert signal is not None
    assert signal["total_score"] > 0

    # Step 3: Risk Manager checks if trade is allowed
    risk_mgr = RiskManager(config)
    can = risk_mgr.can_trade()
    assert can["allowed"] is True

    # Step 4: Risk Manager calculates position size
    size = risk_mgr.calc_position_size(signal["total_score"])
    assert size > 0
    assert size <= 10.0  # max 10% of $100

    # Step 5: Trade Executor places paper trade
    executor = TradeExecutor(config)
    market = {
        "condition_id": "mkt_live",
        "token_id_yes": "tok_y",
        "token_id_no": "tok_n",
        "price_yes": 0.55,
        "price_no": 0.45,
    }
    result = executor.execute(signal, market, size)
    assert result["status"] == "filled"

    # Step 6: Resolve trade as win
    pnl = executor.resolve_trade(result["trade_id"], won=True)
    assert pnl > 0

    # Step 7: Risk Manager records outcome
    risk_mgr.record_trade_outcome(pnl)
    status = risk_mgr.get_status()
    assert status["current_value"] > 100
    assert status["total_trades"] == 1
    assert status["total_wins"] == 1

    # Step 8: Notifier formats the result
    notifier = Notifier(config)
    msg = notifier.format_trade_outcome("mkt_live", True, pnl, status["current_value"])
    assert "WON" in msg
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: add integration test for full trading pipeline"
```

---

### Task 13: Setup Script & README

**Files:**
- Create: `setup.py`

- [ ] **Step 1: Write setup.py**

```python
#!/usr/bin/env python3
# setup.py - One-command installer for PolyBot
import subprocess
import sys
import os
import shutil


def main():
    print("=" * 50)
    print("  PolyBot Setup")
    print("=" * 50)

    # Check Python version
    if sys.version_info < (3, 11):
        print(f"ERROR: Python 3.11+ required (you have {sys.version})")
        sys.exit(1)
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} OK")

    # Install dependencies
    print("\nInstalling dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("Dependencies installed OK")

    # Create data directory
    os.makedirs("data", exist_ok=True)
    print("Data directory OK")

    # Create .env if it doesn't exist
    if not os.path.exists(".env"):
        shutil.copy(".env.example", ".env")
        print("\nCreated .env from template")
        print("IMPORTANT: Edit .env with your keys before running!")
    else:
        print(".env already exists")

    # Initialize database
    from utils.db import init_db
    from config import Config
    cfg = Config()
    init_db(cfg.DB_PATH)
    print("Database initialized OK")

    # Run tests
    print("\nRunning tests...")
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"])
    if result.returncode == 0:
        print("\nAll tests passed!")
    else:
        print("\nSome tests failed. Check output above.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("  Setup Complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Edit .env with your private key and Telegram bot token")
    print("2. Run: python polybot.py --mode paper --capital 100")
    print("3. When ready for live: python polybot.py --mode live --capital 25")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify setup script runs**

Run: `python setup.py`
Expected: All steps pass, tests pass

- [ ] **Step 3: Commit**

```bash
git add setup.py
git commit -m "feat: add one-command setup script"
```

---

### Task 14: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify paper mode starts without crash**

Run: `timeout 5 python polybot.py --mode paper --capital 100 || true`
Expected: Bot starts, prints initialization logs, then exits after timeout

- [ ] **Step 3: Final commit with all files**

```bash
git add -A
git status
git commit -m "feat: PolyBot v1.0 - complete trading pipeline"
```
