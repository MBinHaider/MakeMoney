from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_trades(trades: list[dict]) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("TIME", width=6, style="dim")
    table.add_column("BOT", width=4)
    table.add_column("MODE", width=7)
    table.add_column("ASSET", width=8)
    table.add_column("DIR", width=5)
    table.add_column("ENTRY", justify="right", width=9)
    table.add_column("SIZE", justify="right", width=5)
    table.add_column("RESULT", width=6)
    table.add_column("P&L", justify="right", width=8)
    table.add_column("CONF", justify="center", width=5)

    bot_colors = {"5M": "yellow", "BN": "bright_blue", "POLY": "medium_purple"}

    for t in trades[:10]:
        bot_color = bot_colors.get(t["bot"], "white")
        mode_style = "yellow" if t["mode"] == "paper" else "green"

        if t["result"] == "win":
            result_str = "[green]WIN[/]"
        elif t["result"] == "loss":
            result_str = "[red]LOSS[/]"
        elif t["result"] == "open":
            result_str = "[yellow]OPEN[/]"
        else:
            result_str = "[dim]...[/]"

        pnl = t["pnl"]
        pnl_str = f"[green]+${pnl:.2f}[/]" if pnl > 0 else f"[red]${pnl:.2f}[/]" if pnl < 0 else "[dim]—[/]"

        entry = t["entry"]
        if entry > 1000:
            entry_str = f"${entry:,.0f}"
        else:
            entry_str = f"${entry:.2f}"

        conf = t["confidence"]
        conf_str = f"{conf:.2f}" if conf > 0 else "—"

        table.add_row(
            t["time"][11:16] if len(t["time"]) > 11 else t["time"],
            f"[{bot_color}]{t['bot']}[/]",
            f"[{mode_style}]PAPER[/]" if t["mode"] == "paper" else f"[{mode_style}]LIVE[/]",
            t["asset"],
            t["direction"],
            entry_str,
            f"${t['size']:.0f}",
            result_str,
            pnl_str,
            conf_str,
        )

    return Panel(table, title="RECENT TRADES", title_align="left", border_style="dim")
