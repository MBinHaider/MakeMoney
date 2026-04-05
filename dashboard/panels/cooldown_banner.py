from rich.panel import Panel
from rich.text import Text
from rich.align import Align


def render_cooldown_banner(cooldown: dict) -> Panel | None:
    if not cooldown["active"]:
        return None

    secs = cooldown["seconds_remaining"]
    mins = secs // 60
    remaining_secs = secs % 60
    losses = cooldown["consecutive_losses"]

    msg = Text()
    msg.append("⏸ POLYBOT 5M PAUSED", style="bold yellow")
    msg.append(f" — {losses} consecutive losses │ Resuming in ", style="dim")
    msg.append(f"{mins}:{remaining_secs:02d}", style="bold yellow")

    return Panel(
        Align.center(msg),
        border_style="yellow",
        style="on #2d1b00",
    )
