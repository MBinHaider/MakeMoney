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
