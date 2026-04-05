import aiohttp
from utils.logger import get_logger
from config import Config

log = get_logger("fivemin_notifier")

PREFIX = "[5M]"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"


class FiveMinNotifier:
    def __init__(self, config: Config):
        self.config = config
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.token = config.TELEGRAM_BOT_TOKEN

    async def send_message(self, text: str) -> None:
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                resp = await session.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                })
                data = await resp.json()
                if not data.get("ok"):
                    log.error(f"Telegram error: {data.get('description', 'unknown')}")
        except Exception as e:
            log.error(f"Telegram send failed: {e}")

    def format_trade_entry(self, trade: dict, signal_info: dict) -> str:
        asset = trade["asset"]
        direction = trade["direction"]
        price = trade["entry_price"]
        shares = trade["shares"]
        cost = trade["cost"]
        confidence = signal_info["confidence"]
        phase = signal_info["phase"]
        indicators = signal_info.get("indicators", {})
        active = "+".join(k for k, v in indicators.items() if v != "NEUTRAL") if isinstance(indicators, dict) else str(indicators)

        return (
            f"{PREFIX} {DIVIDER}\n"
            f"{PREFIX} <b>BUY {direction} {asset}</b> @ ${price}\n"
            f"{PREFIX} Shares: {shares:.2f} | Cost: ${cost:.2f}\n"
            f"{PREFIX} Confidence: {confidence:.2f} | Phase: {phase}\n"
            f"{PREFIX} Signals: {active}\n"
            f"{PREFIX} {DIVIDER}"
        )

    def format_settlement(self, result: dict, status: dict) -> str:
        asset = result["asset"]
        direction = result["direction"]
        outcome = result["result"].upper()
        pnl = result["pnl"]
        balance = status["balance"]
        losses = status["consecutive_losses"]
        wins = status["total_wins"]
        trades = status["total_trades"]

        pnl_sign = "+" if pnl >= 0 else ""
        streak = f"W{wins}" if pnl >= 0 else f"L{losses}"

        return (
            f"{PREFIX} {DIVIDER}\n"
            f"{PREFIX} <b>{outcome}</b> {asset} {direction} {pnl_sign}${pnl:.2f}\n"
            f"{PREFIX} Balance: ${balance:.2f} | Streak: {streak}\n"
            f"{PREFIX} Record: {wins}/{trades}\n"
            f"{PREFIX} {DIVIDER}"
        )

    def format_cooldown(self, consecutive_losses: int, minutes: int) -> str:
        return (
            f"{PREFIX} {DIVIDER}\n"
            f"{PREFIX} <b>PAUSED</b> — {consecutive_losses} consecutive losses\n"
            f"{PREFIX} Resuming in {minutes} minutes\n"
            f"{PREFIX} {DIVIDER}"
        )

    def format_daily_limit(self, amount_lost: float) -> str:
        return (
            f"{PREFIX} {DIVIDER}\n"
            f"{PREFIX} <b>DAILY LIMIT HIT</b> — lost ${amount_lost:.2f} today\n"
            f"{PREFIX} Stopped until midnight UTC\n"
            f"{PREFIX} {DIVIDER}"
        )

    def format_startup(self, mode: str, balance: float, assets: list[str]) -> str:
        return (
            f"{PREFIX} {DIVIDER}\n"
            f"{PREFIX} <b>PolyBot 5M started</b>\n"
            f"{PREFIX} Mode: {mode} | Balance: ${balance:.2f}\n"
            f"{PREFIX} Assets: {', '.join(assets)}\n"
            f"{PREFIX} Strategy: Hybrid 2-of-3 (momentum + orderbook + volume)\n"
            f"{PREFIX} {DIVIDER}"
        )

    def format_shutdown(self) -> str:
        return f"{PREFIX} PolyBot 5M stopped"
