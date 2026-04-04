import aiohttp
from utils.logger import get_logger
from config import Config

log = get_logger("binance_notifier")

# Visual header to distinguish from PolyBot
HEADER = "⚡⚡⚡ BINANCE BOT ⚡⚡⚡"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"


class BinanceNotifier:
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

    def format_buy_alert(self, trade: dict, indicators: dict, status: dict) -> str:
        symbol = trade["symbol"]
        price = trade["entry_price"]
        size = trade["size"]
        tp = trade["tp"]
        sl = trade["sl"]
        tp_pct = ((tp - price) / price) * 100
        sl_pct = ((price - sl) / price) * 100

        signals = []
        rsi = indicators.get("rsi")
        if rsi is not None and rsi < 30:
            signals.append(f"RSI({rsi:.0f})")
        macd_h = indicators.get("macd_histogram")
        if macd_h is not None and macd_h > 0:
            signals.append("MACD cross")
        signals_str = " + ".join(signals) if signals else "combined"

        return (
            f"{HEADER}\n"
            f"{DIVIDER}\n"
            f"🟢🟢🟢 <b>BUY {symbol}</b> 🟢🟢🟢\n"
            f"{DIVIDER}\n"
            f"💰 Price: <b>${price:,.2f}</b>\n"
            f"📦 Size: ${size:.2f}\n"
            f"📡 Signal: {signals_str}\n"
            f"\n"
            f"🎯 TP: ${tp:,.2f} (+{tp_pct:.1f}%)\n"
            f"🛑 SL: ${sl:,.2f} (-{sl_pct:.1f}%)\n"
            f"\n"
            f"📊 Open: {status['open_positions']}/3\n"
            f"💼 Portfolio: ${status['balance']:.2f}\n"
            f"{DIVIDER}"
        )

    def format_sell_alert(self, closed: dict, status: dict) -> str:
        symbol = closed["symbol"]
        exit_price = closed["exit_price"]
        pnl = closed["pnl"]
        reason = closed["reason"].replace("_", " ").title()
        hold_time = closed.get("hold_time", "")
        pnl_sign = "+" if pnl >= 0 else ""
        pnl_emoji = "💵" if pnl >= 0 else "💸"

        return (
            f"{HEADER}\n"
            f"{DIVIDER}\n"
            f"🔴🔴🔴 <b>SOLD {symbol}</b> 🔴🔴🔴\n"
            f"{DIVIDER}\n"
            f"💰 Exit: <b>${exit_price:,.2f}</b>\n"
            f"{pnl_emoji} P&L: <b>{pnl_sign}${pnl:.2f}</b>\n"
            f"⏱ Hold: {hold_time}\n"
            f"📋 Reason: {reason}\n"
            f"\n"
            f"📊 Open: {status['open_positions']}/3\n"
            f"💼 Portfolio: ${status['balance']:.2f}\n"
            f"{DIVIDER}"
        )

    def format_summary(self, status: dict, open_trades: list[dict]) -> str:
        balance = status["balance"]
        start = status["starting_balance"]
        daily_pnl = status["daily_pnl"]
        total_trades = status["total_trades"]
        wins = status["total_wins"]
        losses = total_trades - wins
        win_rate = status["win_rate"]

        daily_pct = (daily_pnl / start * 100) if start > 0 else 0
        daily_sign = "+" if daily_pnl >= 0 else ""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"

        open_lines = ""
        for t in open_trades:
            open_lines += f"   ▸ {t['side'].upper()} {t['symbol']} @ ${t['price']:,.2f}\n"
        if not open_lines:
            open_lines = "   ▸ No open positions\n"

        return (
            f"{HEADER}\n"
            f"{DIVIDER}\n"
            f"📊 <b>15-MIN STATUS</b>\n"
            f"{DIVIDER}\n"
            f"💼 Portfolio: <b>${balance:.2f}</b> (start: ${start:.2f})\n"
            f"{pnl_emoji} Today: {daily_sign}${daily_pnl:.2f} ({daily_sign}{daily_pct:.1f}%)\n"
            f"🔄 Trades: {total_trades} ({wins}W/{losses}L, {win_rate:.1%})\n"
            f"\n"
            f"📌 <b>Open Positions:</b>\n"
            f"{open_lines}"
            f"{DIVIDER}"
        )

    def format_daily_report(self, status: dict, today_trades: list[dict]) -> str:
        balance = status["balance"]
        start = status["starting_balance"]
        daily_pnl = status.get("daily_pnl", status.get("total_pnl", 0))
        total_trades = status["total_trades"]
        wins = status["total_wins"]
        losses = total_trades - wins
        daily_pct = (daily_pnl / start * 100) if start > 0 else 0
        daily_sign = "+" if daily_pnl >= 0 else ""

        best_pnl = max((t["pnl"] for t in today_trades), default=0)
        worst_pnl = min((t["pnl"] for t in today_trades), default=0)
        best_sym = next((t["symbol"] for t in today_trades if t["pnl"] == best_pnl), "N/A")
        worst_sym = next((t["symbol"] for t in today_trades if t["pnl"] == worst_pnl), "N/A")

        return (
            f"{HEADER}\n"
            f"{DIVIDER}\n"
            f"🌅 <b>DAILY REPORT</b>\n"
            f"{DIVIDER}\n"
            f"💰 Net P&L: <b>{daily_sign}${daily_pnl:.2f}</b> ({daily_sign}{daily_pct:.1f}%)\n"
            f"🔄 Trades: {total_trades} ({wins}W/{losses}L)\n"
            f"🏆 Best: {best_sym} +${best_pnl:.2f}\n"
            f"💀 Worst: {worst_sym} ${worst_pnl:.2f}\n"
            f"\n"
            f"💼 Balance: <b>${balance:.2f}</b> (from ${start:.2f})\n"
            f"{DIVIDER}"
        )
