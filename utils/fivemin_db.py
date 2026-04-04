import os
import sqlite3
from utils.db import get_connection

FIVEMIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS fm_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    shares REAL NOT NULL,
    cost REAL NOT NULL,
    result TEXT DEFAULT 'pending',
    pnl REAL DEFAULT 0.0,
    window_ts INTEGER NOT NULL,
    signal_confidence REAL DEFAULT 0.0,
    signal_phase TEXT DEFAULT '',
    signal_details TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    resolved_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fm_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_ts INTEGER NOT NULL,
    asset TEXT NOT NULL,
    direction TEXT DEFAULT 'NEUTRAL',
    confidence REAL DEFAULT 0.0,
    phase TEXT DEFAULT '',
    momentum_dir TEXT DEFAULT 'NEUTRAL',
    momentum_conf REAL DEFAULT 0.0,
    imbalance_dir TEXT DEFAULT 'NEUTRAL',
    imbalance_conf REAL DEFAULT 0.0,
    volume_dir TEXT DEFAULT 'NEUTRAL',
    volume_conf REAL DEFAULT 0.0,
    action_taken TEXT DEFAULT 'none',
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fm_daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    pnl REAL DEFAULT 0.0,
    best_trade REAL DEFAULT 0.0,
    worst_trade REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS fm_cooldowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    reason TEXT DEFAULT '',
    consecutive_losses INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fm_portfolio (
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
    daily_trade_count INTEGER DEFAULT 0,
    is_paused INTEGER DEFAULT 0,
    pause_until TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_fm_trades_window ON fm_trades(window_ts);
CREATE INDEX IF NOT EXISTS idx_fm_trades_timestamp ON fm_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_fm_signals_window ON fm_signals(window_ts);
CREATE INDEX IF NOT EXISTS idx_fm_daily_stats_date ON fm_daily_stats(date);
"""


def init_fivemin_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(FIVEMIN_SCHEMA)
    conn.close()
