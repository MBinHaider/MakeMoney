import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API URLs
    POLYMARKET_API_URL = "https://clob.polymarket.com"
    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    BINANCE_API_URL = "https://api.binance.com"

    # SOCKS5 proxy for Polymarket API (Cloudflare WARP proxy mode)
    PROXY_URL = os.getenv("PROXY_URL", "socks5://127.0.0.1:40000")

    # Secrets (from .env)
    PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Trading mode: "paper" or "live"
    TRADING_MODE = os.getenv("TRADING_MODE", "paper")

    # Polymarket chain
    CHAIN_ID = 137  # Polygon

    # Polling intervals (seconds)
    MARKET_POLL_INTERVAL_SEC = 60      # Markets change slowly
    WALLET_POLL_INTERVAL_SEC = 30      # Check for new whale trades every 30s
    PRICE_POLL_INTERVAL_SEC = 30       # Price candles every 30s

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
    MIN_WALLET_TRADES = 10  # Low initially to bootstrap; raise to 100 once data accumulates
    MIN_WALLET_WIN_RATE = 0.52
    TOP_TRACKED_WALLETS = 20
    WALLET_LOOKBACK_DAYS = 90

    # Trade execution
    ORDER_TIMEOUT_SEC = 30

    # Targets (BTC/ETH, expandable)
    TARGET_MARKETS = ["BTC", "ETH"]

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "polybot.db")
