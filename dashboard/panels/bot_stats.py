from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.table import Table


def _mode_badge(mode: str) -> Text:
    if mode == "live":
        return Text(" LIVE ", style="bold white on green")
    return Text(" PAPER ", style="bold yellow on dark_goldenrod")


def render_fivemin_stats(stats: dict, window_remaining: int) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    pnl_color = "green" if stats["pnl"] >= 0 else "red"
    pnl_sign = "+" if stats["pnl"] >= 0 else ""
    wr_color = "green" if stats["win_rate"] >= 0.5 else "red"
    wins = stats["total_wins"]
    losses = stats["total_trades"] - wins
    mins = window_remaining // 60
    secs = window_remaining % 60

    table.add_row(
        Text("BALANCE\n", style="dim") + Text(f"${stats['balance']:.2f}", style=f"bold {pnl_color}"),
        Text("P&L\n", style="dim") + Text(f"{pnl_sign}${stats['pnl']:.2f}", style=pnl_color),
        Text("RECORD\n", style="dim") + Text(f"{wins}W/{losses}L"),
        Text("WIN%\n", style="dim") + Text(f"{stats['win_rate']:.0%}", style=wr_color),
        Text("WINDOW\n", style="dim") + Text(f"{mins}:{secs:02d}", style="yellow"),
    )

    title = Text()
    title.append("⚡ POLYBOT 5M ", style="bold yellow")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="yellow", expand=True)


def render_binance_stats(stats: dict) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    pnl_color = "green" if stats["pnl"] >= 0 else "red"
    pnl_sign = "+" if stats["pnl"] >= 0 else ""
    wr_color = "green" if stats["win_rate"] >= 0.5 else "red"
    wins = stats["total_wins"]
    losses = stats["total_trades"] - wins

    table.add_row(
        Text("BALANCE\n", style="dim") + Text(f"${stats['balance']:.2f}", style=f"bold {pnl_color}"),
        Text("P&L\n", style="dim") + Text(f"{pnl_sign}${stats['pnl']:.2f}", style=pnl_color),
        Text("RECORD\n", style="dim") + Text(f"{wins}W/{losses}L"),
        Text("WIN%\n", style="dim") + Text(f"{stats['win_rate']:.0%}", style=wr_color),
        Text("OPEN\n", style="dim") + Text(f"{stats['open_positions']}", style="bright_blue"),
    )

    title = Text()
    title.append("📊 BINANCEBOT ", style="bold bright_blue")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="bright_blue", expand=True)


def render_polybot_stats(stats: dict) -> Panel:
    table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")
    table.add_column(ratio=1, justify="center")

    table.add_row(
        Text("MARKETS\n", style="dim") + Text(f"{stats['markets']}"),
        Text("SIGNALS\n", style="dim") + Text(f"{stats['signals']}", style="yellow"),
        Text("WHALES\n", style="dim") + Text(f"{stats['whales']}"),
    )

    title = Text()
    title.append("🔮 POLYBOT ", style="bold medium_purple")
    title.append(" ")
    title.append(_mode_badge(stats["mode"]))

    return Panel(table, title=title, border_style="medium_purple", expand=True)
