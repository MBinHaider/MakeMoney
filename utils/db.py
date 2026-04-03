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
