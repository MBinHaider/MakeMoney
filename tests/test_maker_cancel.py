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
    config.FIVEMIN_MAKER_TIMEOUT_SEC = 2
    return FiveMinTradeExecutor(config, exchange=None)


def make_signal():
    return Signal(
        asset="BTC", direction="UP", confidence=0.90, phase="mid",
        indicators={
            "momentum": {"direction": "UP", "confidence": 0.9},
            "imbalance": {"direction": "UP", "confidence": 0.9},
            "volume": {"direction": "UP", "confidence": 0.9},
        },
        timestamp=0.0,
    )


def test_unfilled_order_is_cancelled_after_timeout(executor):
    """Order that doesn't fill within FIVEMIN_MAKER_TIMEOUT_SEC should be cancelled."""
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed"
    fake_client.post_order.return_value = {
        "errorMsg": "",
        "orderID": "0xnotfilled",
        "takingAmount": "10",
        "makingAmount": "0",
        "status": "live",  # not matched yet
        "transactionsHashes": [],
        "success": True,
    }
    fake_client.get_order.return_value = {
        "status": "live",
        "size_matched": 0,
    }
    fake_client.cancel.return_value = {"canceled": ["0xnotfilled"]}
    executor._clob_client = fake_client

    result = executor._execute_live(
        signal=make_signal(), amount=10.0, limit_price=0.99,
        token_id="t1", condition_id="c1",
    )

    fake_client.cancel.assert_called_once_with("0xnotfilled")
    assert result["status"] == "error"
    assert "not filled" in result["reason"].lower() or "cancel" in result["reason"].lower()


def test_filled_order_is_not_cancelled(executor):
    """If the order fills immediately, cancel() must NOT be called."""
    fake_client = MagicMock()
    fake_client.create_order.return_value = "signed"
    fake_client.post_order.return_value = {
        "errorMsg": "",
        "orderID": "0xfilled",
        "takingAmount": "10",
        "makingAmount": "20",
        "status": "matched",
        "transactionsHashes": ["0xtx"],
        "success": True,
    }
    executor._clob_client = fake_client

    result = executor._execute_live(
        signal=make_signal(), amount=10.0, limit_price=0.99,
        token_id="t1", condition_id="c1",
    )

    fake_client.cancel.assert_not_called()
    assert result["status"] == "filled"
