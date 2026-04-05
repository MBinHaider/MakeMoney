import aiohttp
from rich.panel import Panel
from rich.text import Text


def render_price_chart(candles: list[dict]) -> Panel:
    if not candles or len(candles) < 2:
        return Panel("Waiting for price data...", title="BTC/USD (1h)", title_align="left", border_style="dim")

    display_candles = candles[-20:]
    highs = [c["high"] for c in display_candles]
    lows = [c["low"] for c in display_candles]
    price_max = max(highs)
    price_min = min(lows)
    price_range = price_max - price_min
    if price_range == 0:
        price_range = 1

    chart_height = 10

    def price_to_row(price):
        return int((price_max - price) / price_range * (chart_height - 1))

    chart_text = Text()

    for row in range(chart_height):
        price_at_row = price_max - (row / (chart_height - 1)) * price_range
        chart_text.append(f"${price_at_row:>8,.0f} ", style="dim")

        for c in display_candles:
            o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
            is_green = cl >= o
            color = "green" if is_green else "red"

            body_top_row = price_to_row(max(o, cl))
            body_bot_row = price_to_row(min(o, cl))
            wick_top_row = price_to_row(h)
            wick_bot_row = price_to_row(l)

            if body_top_row <= row <= body_bot_row:
                chart_text.append("█", style=color)
            elif wick_top_row <= row <= wick_bot_row:
                chart_text.append("│", style=color)
            else:
                chart_text.append(" ")

        chart_text.append("\n")

    # Current price line
    last = display_candles[-1]["close"]
    chart_text.append(f"  Current: ", style="dim")
    chart_text.append(f"${last:,.2f}", style="yellow bold")

    return Panel(chart_text, title="BTC/USD (1h)", title_align="left", border_style="dim")


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
