import time
from rich.columns import Columns
from rich.text import Text


def render_footer(prices: dict, caffeinate_pid: int | None, bots_running: dict) -> Text:
    footer = Text()

    # Prices
    for symbol, price in prices.items():
        color = "green" if price.get("change", 0) >= 0 else "red"
        footer.append(f"{symbol} ", style="dim")
        footer.append(f"${price['value']:,.0f}", style=color)
        footer.append(" │ ", style="dim")

    # Next 5M window
    now = int(time.time())
    window_end = now - (now % 300) + 300
    remaining = window_end - now
    mins = remaining // 60
    secs = remaining % 60
    footer.append(f"Next 5M: ", style="dim")
    footer.append(f"{mins}:{secs:02d}", style="yellow")
    footer.append(" │ ", style="dim")

    # Status
    cafe_str = "ON" if caffeinate_pid else "OFF"
    cafe_color = "green" if caffeinate_pid else "red"
    footer.append("caffeinate: ", style="dim")
    footer.append(f"●{cafe_str}", style=cafe_color)
    footer.append(" │ ", style="dim")

    all_running = all(bots_running.values())
    run_color = "green" if all_running else "yellow"
    running_count = sum(1 for v in bots_running.values() if v)
    footer.append(f"Bots: ", style="dim")
    footer.append(f"●{running_count}/{len(bots_running)}", style=run_color)

    return footer
