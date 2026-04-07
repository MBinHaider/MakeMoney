import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API URLs
    POLYMARKET_API_URL = "https://clob.polymarket.com"
    GAMMA_API_URL = "https://gamma-api.polymarket.com"
    BINANCE_API_URL = os.getenv("BINANCE_API_URL", "https://data-api.binance.vision")

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
    SIGNAL_AUTO_TRADE_THRESHOLD = 50  # Paper testing: lower to generate trades for evaluation
    SIGNAL_ALERT_THRESHOLD = 35

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

    # PolyBot 5M
    FIVEMIN_TRADING_MODE = os.getenv("FIVEMIN_TRADING_MODE", "paper")
    FIVEMIN_ASSETS = ["BTC", "ETH", "SOL"]
    FIVEMIN_STARTING_BALANCE = 25.00
    FIVEMIN_MAX_PER_TRADE = 5.00
    FIVEMIN_CONFIDENCE_EARLY = 0.75
    FIVEMIN_CONFIDENCE_MID = 0.60
    FIVEMIN_CONFIDENCE_LATE = 0.55
    FIVEMIN_ENTRY_CUTOFF_SEC = 10
    FIVEMIN_COOLDOWN_LOSSES = 3
    FIVEMIN_COOLDOWN_MINUTES = 15
    FIVEMIN_DAILY_LOSS_LIMIT_PCT = 0.20
    FIVEMIN_DAILY_TRADE_CAP = 50
    FIVEMIN_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "polybot5m.db")

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

    POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS", "")
