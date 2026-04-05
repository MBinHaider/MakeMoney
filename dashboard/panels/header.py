from datetime import datetime, timezone
from rich.text import Text
from rich.align import Align


def render_header(start_time: datetime, caffeinate_pid: int | None) -> Text:
    now = datetime.now(timezone.utc)
    uptime = now - start_time
    hours = int(uptime.total_seconds() // 3600)
    minutes = int((uptime.total_seconds() % 3600) // 60)
    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    sleep_status = "ON" if caffeinate_pid else "N/A"
    time_str = now.strftime("%b %d %Y %H:%M:%S UTC")

    title = Text()
    title.append("━━━ ", style="yellow")
    title.append("MBH Trading Bots Command Center", style="bold bright_blue")
    title.append(" ━━━", style="yellow")
    title.append(f"\n{time_str} │ Uptime: {uptime_str} │ Sleep Lock: {sleep_status} │ Press Q to quit", style="dim")
    title.stylize("bold", 4, 35)
    return Align.center(title)
