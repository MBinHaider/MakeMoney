from rich.panel import Panel
from rich.text import Text


def render_signal_hitrate(rate: dict) -> Panel:
    content = Text()

    rows = [
        ("Generated", rate["generated"], "bright_blue"),
        ("Skipped (price)", rate["skipped_price"], "yellow"),
        ("Skipped (risk)", rate["skipped_risk"], "yellow"),
        ("Traded", rate["traded"], "bright_blue"),
    ]

    for label, value, color in rows:
        content.append(f"{label:<16}", style="dim")
        content.append(f"{value:>4}\n", style=color)

    # Won line (bold)
    won = rate["won"]
    traded = rate["traded"]
    pct = f"{won/traded:.0%}" if traded > 0 else "—"
    content.append("─" * 20 + "\n", style="dim")
    content.append(f"Won              ", style="dim")
    content.append(f"{won:>4}", style="bold green")
    content.append(f" ({pct})\n", style="green")

    # Funnel bar
    gen = rate["generated"] or 1
    traded_pct = int((rate["traded"] / gen) * 20)
    skipped_pct = 20 - traded_pct
    content.append("\n")
    content.append("█" * traded_pct, style="green")
    content.append("█" * skipped_pct, style="yellow")

    return Panel(content, title="SIGNAL HIT RATE (today)", title_align="left", border_style="dim")
