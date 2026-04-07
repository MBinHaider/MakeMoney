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
    indicators = {
        "momentum": {"direction": "UP", "confidence": confidence},
        "imbalance": {"direction": "UP", "confidence": confidence},
    }
    if score == 3:
        indicators["volume"] = {"direction": "UP", "confidence": confidence}
    else:
        indicators["volume"] = {"direction": "NEUTRAL", "confidence": confidence}
    return Signal(
        asset="BTC",
        direction="UP",
        confidence=confidence,
        phase="mid",
        indicators=indicators,
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
