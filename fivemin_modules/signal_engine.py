from dataclasses import dataclass
from fivemin_modules.indicators import (
    calc_momentum,
    calc_orderbook_imbalance,
    calc_volume_spike,
    IndicatorResult,
)
from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_signal_engine")


@dataclass
class Signal:
    asset: str
    direction: str
    confidence: float
    phase: str
    indicators: dict
    timestamp: float


class FiveMinSignalEngine:
    def __init__(self, config: Config):
        self.config = config

    def evaluate(self, asset: str, state: dict, seconds_elapsed: float) -> Signal | None:
        """Evaluate all three indicators and apply adaptive entry thresholds."""
        window_duration = 300
        cutoff = window_duration - self.config.FIVEMIN_ENTRY_CUTOFF_SEC

        if seconds_elapsed >= cutoff:
            return None

        if seconds_elapsed < 120:
            phase = "early"
            min_agree = 3
            min_confidence = self.config.FIVEMIN_CONFIDENCE_EARLY
        elif seconds_elapsed < 240:
            phase = "mid"
            min_agree = 2
            min_confidence = self.config.FIVEMIN_CONFIDENCE_MID
        else:
            phase = "late"
            min_agree = 2
            min_confidence = self.config.FIVEMIN_CONFIDENCE_LATE

        momentum = calc_momentum(state["current_price"], state["window_open_price"])
        imbalance = calc_orderbook_imbalance(state["orderbook_up"], state["orderbook_down"])

        price_delta = 0.0
        if state["window_open_price"] > 0:
            price_delta = (state["current_price"] - state["window_open_price"]) / state["window_open_price"]
        volume = calc_volume_spike(state["volumes"], price_delta)

        results = [momentum, imbalance, volume]
        indicators_detail = {
            "momentum": {"direction": momentum.direction, "confidence": momentum.confidence},
            "imbalance": {"direction": imbalance.direction, "confidence": imbalance.confidence},
            "volume": {"direction": volume.direction, "confidence": volume.confidence},
        }

        for direction in ("UP", "DOWN"):
            agreeing = [r for r in results if r.direction == direction]
            if len(agreeing) >= min_agree:
                avg_confidence = sum(r.confidence for r in agreeing) / len(agreeing)
                if avg_confidence >= min_confidence:
                    log.info(
                        f"{asset} {direction} signal: {len(agreeing)}/3 agree, "
                        f"confidence={avg_confidence:.2f}, phase={phase}"
                    )
                    return Signal(
                        asset=asset,
                        direction=direction,
                        confidence=round(avg_confidence, 4),
                        phase=phase,
                        indicators=indicators_detail,
                        timestamp=0.0,
                    )

        return None

    def select_best(self, signals: list[Signal]) -> Signal | None:
        if not signals:
            return None
        return max(signals, key=lambda s: s.confidence)
