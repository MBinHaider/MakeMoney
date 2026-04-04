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
