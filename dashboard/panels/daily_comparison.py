from rich.panel import Panel
from rich.table import Table


def render_daily_comparison(daily: dict) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("", style="dim", width=10)
    table.add_column("P&L", justify="right")
    table.add_column("TRADES", justify="center")
    table.add_column("WIN%", justify="center")
    table.add_column("BEST", justify="right")
    table.add_column("WORST", justify="right")

    for label, key, style in [
        ("TODAY", "today", "bold bright_blue"),
        ("Yesterday", "yesterday", "dim"),
        ("Best day", "best", "dim"),
        ("Worst day", "worst", "dim"),
    ]:
        d = daily[key]
        pnl_color = "green" if d["pnl"] >= 0 else "red"
        pnl_sign = "+" if d["pnl"] >= 0 else ""
        wr_color = "green" if d["win_rate"] >= 0.5 else "red"
        best_str = f"+${d['best']:.2f}" if d["best"] > 0 else "—"
        worst_str = f"${d['worst']:.2f}" if d["worst"] < 0 else "—"

        table.add_row(
            f"[{style}]{label}[/]",
            f"[{pnl_color}]{pnl_sign}${d['pnl']:.2f}[/]",
            str(d["trades"]),
            f"[{wr_color}]{d['win_rate']:.0%}[/]",
            f"[green]{best_str}[/]",
            f"[red]{worst_str}[/]",
        )

    return Panel(table, title="DAILY P&L COMPARISON", title_align="left", border_style="dim")
