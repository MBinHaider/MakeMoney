import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from utils.logger import get_logger
from config import Config

log = get_logger("notifier")


class Notifier:
    def __init__(self, config: Config):
        self.config = config
        self.chat_id = config.TELEGRAM_CHAT_ID
        self._app = None
        self._on_pause = None
        self._on_resume = None
        self._on_kill = None
        self._get_status = None

    def set_callbacks(self, on_pause=None, on_resume=None, on_kill=None, get_status=None):
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_kill = on_kill
        self._get_status = get_status

    def _build_app(self):
        if not self.config.TELEGRAM_BOT_TOKEN:
            log.warning("No Telegram bot token configured")
            return None
        app = ApplicationBuilder().token(self.config.TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("pause", self._cmd_pause))
        app.add_handler(CommandHandler("resume", self._cmd_resume))
        app.add_handler(CommandHandler("kill", self._cmd_kill))
        app.add_handler(CommandHandler("today", self._cmd_today))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(CommandHandler("balance", self._cmd_balance))
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        return app

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("PolyBot is running. Use /help for commands.")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "/status - Current P&L and positions\n"
            "/pause - Pause trading\n"
            "/resume - Resume trading\n"
            "/kill - Emergency stop\n"
            "/today - Today's summary\n"
            "/history - 7-day performance\n"
            "/balance - Portfolio value"
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = self.format_status(stats)
        else:
            msg = "Status not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._on_pause:
            self._on_pause()
        await update.message.reply_text("Trading PAUSED")

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._on_resume:
            self._on_resume()
        await update.message.reply_text("Trading RESUMED")

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("EMERGENCY STOP - Shutting down")
        if self._on_kill:
            self._on_kill()

    async def _cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = self.format_daily_summary(stats)
        else:
            msg = "Stats not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = (f"<b>7-Day History</b>\nTrades: {stats['total_trades']}\n"
                   f"Win Rate: {stats['win_rate']:.1%}\nTotal P&L: ${stats['total_pnl']:.2f}\n"
                   f"Portfolio: ${stats['current_value']:.2f}")
        else:
            msg = "History not available"
        await update.message.reply_text(msg, parse_mode="HTML")

    async def _cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self._get_status:
            stats = self._get_status()
            msg = f"Portfolio: ${stats['current_value']:.2f}"
        else:
            msg = "Balance not available"
        await update.message.reply_text(msg)

    async def send_message(self, text: str) -> None:
        # Try the app bot first, fall back to direct HTTP
        sent = False
        if self._app and self._app.bot:
            try:
                await self._app.bot.send_message(chat_id=self.chat_id, text=text, parse_mode="HTML")
                sent = True
            except Exception as e:
                log.error(f"App send failed, trying HTTP: {e}")

        if not sent and self.config.TELEGRAM_BOT_TOKEN and self.chat_id:
            try:
                import aiohttp
                url = f"https://api.telegram.org/bot{self.config.TELEGRAM_BOT_TOKEN}/sendMessage"
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                    })
            except Exception as e:
                log.error(f"HTTP send also failed: {e}")

    def format_trade_alert(self, trade: dict, signal_score: float) -> str:
        return (f"<b>TRADE EXECUTED</b>\nDirection: {trade['side']}\n"
                f"Size: ${trade['size']:.2f}\nPrice: {trade['entry_price']:.4f}\n"
                f"Market: {trade['market_id'][:20]}\nSignal Score: {signal_score:.1f}")

    def format_trade_outcome(self, market_id: str, won: bool, pnl: float, portfolio_value: float) -> str:
        icon = "WON" if won else "LOST"
        return (f"<b>TRADE {icon}</b>\nMarket: {market_id[:20]}\n"
                f"P&L: ${pnl:.2f}\nPortfolio: ${portfolio_value:.2f}")

    def format_daily_summary(self, stats: dict) -> str:
        return (f"<b>Daily Summary</b>\nPortfolio: ${stats['current_value']:.2f}\n"
                f"Today's P&L: ${stats.get('daily_pnl', 0):.2f}\n"
                f"Trades: {stats['total_trades']}\nWin Rate: {stats['win_rate']:.1%}\n"
                f"Open Positions: {stats['open_positions']}\n"
                f"Status: {'PAUSED' if stats['is_paused'] else 'ACTIVE'}")

    def format_status(self, stats: dict) -> str:
        pnl_sign = "" if stats["total_pnl"] >= 0 else "-"
        return (f"<b>PolyBot Status</b>\nPortfolio: ${stats['current_value']:.2f}\n"
                f"Total P&L: {pnl_sign}${abs(stats['total_pnl']):.2f}\n"
                f"Drawdown: {stats.get('drawdown', 0):.1%}\nTrades: {stats['total_trades']}\n"
                f"Win Rate: {stats['win_rate']:.1%}\nOpen: {stats['open_positions']}\n"
                f"Status: {'PAUSED' if stats['is_paused'] else 'ACTIVE'}")

    async def start_polling(self):
        self._app = self._build_app()
        if self._app:
            log.info("Telegram bot starting...")
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
