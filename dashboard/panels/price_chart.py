import aiohttp
import asyncio
from rich.panel import Panel
from rich.text import Text


def render_price_chart(candles: list[dict]) -> Panel:
    if not candles or len(candles) < 2:
        return Panel("Waiting for price data...", title="BTC/USD", title_align="left", border_style="dim")

    # Find price range
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price_max = max(highs)
    price_min = min(lows)
    price_range = price_max - price_min or 1

    chart_height = 8
    lines = [[] for _ in range(chart_height)]

    for c in candles[-24:]:
        o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
        is_green = cl >= o

        body_top = max(o, cl)
        body_bot = min(o, cl)

        for row in range(chart_height):
            price_at_row = price_max - (row / (chart_height - 1)) * price_range
            in_wick = l <= price_at_row <= h
            in_body = body_bot <= price_at_row <= body_top

            if in_body:
                lines[row].append("█" if is_green else "█")
            elif in_wick:
                lines[row].append("│")
            else:
                lines[row].append(" ")

    chart_text = Text()
    for i, line in enumerate(lines):
        price_label = price_max - (i / (chart_height - 1)) * price_range
        chart_text.append(f"${price_label:,.0f} ", style="dim")
        for j, ch in enumerate(line):
            candle = candles[-24:][j] if j < len(candles[-24:]) else None
            if candle and ch == "█":
                color = "green" if candle["close"] >= candle["open"] else "red"
                chart_text.append(ch + " ", style=color)
            elif ch == "│":
                chart_text.append(ch + " ", style="dim")
            else:
                chart_text.append(ch + " ")
        chart_text.append("\n")

    # Current price
    if candles:
        last = candles[-1]["close"]
        chart_text.append(f"Current: ${last:,.2f}", style="yellow")

    return Panel(chart_text, title="BTC/USD (1h candles)", title_align="left", border_style="dim")


async def fetch_btc_candles() -> list[dict]:
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": "1h", "limit": 24}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                raw = await resp.json()
                return [
                    {"open": float(k[1]), "high": float(k[2]),
                     "low": float(k[3]), "close": float(k[4])}
                    for k in raw
                ]
    except Exception:
        return []
