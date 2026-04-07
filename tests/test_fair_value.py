import pytest
from fivemin_modules.trade_executor import compute_fair_value


def test_high_confidence_high_score_fair_value():
    """3-of-3 indicators agreeing at 0.95 conf → near $0.55."""
    fv = compute_fair_value(score=3, confidence=0.95)
    assert 0.50 <= fv <= 0.65


def test_low_confidence_2of3_lower_fair_value():
    """2-of-3 indicators at 0.55 conf → cheaper bid."""
    fv = compute_fair_value(score=2, confidence=0.55)
    assert 0.20 <= fv <= 0.40


def test_3of3_med_confidence():
    fv = compute_fair_value(score=3, confidence=0.75)
    assert 0.40 <= fv <= 0.55


def test_fair_value_clamped_min():
    """Even with weakest signal, never go below FIVEMIN_MAKER_MIN_PRICE."""
    fv = compute_fair_value(score=2, confidence=0.55)
    assert fv >= 0.05


def test_fair_value_clamped_max():
    """Even with strongest signal, never exceed FIVEMIN_MAKER_MAX_PRICE."""
    fv = compute_fair_value(score=3, confidence=1.0)
    assert fv <= 0.80
