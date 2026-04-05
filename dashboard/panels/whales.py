from rich.panel import Panel
from rich.table import Table


def render_whales(whale_data: list[dict]) -> Panel:
    """Render live whale activity table."""
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("WALLET", width=10, style="dim")
    table.add_column("WIN%", justify="center", width=5)
    table.add_column("LAST TRADE", width=20)
    table.add_column("SIDE", justify="center", width=5)
    table.add_column("SIZE", justify="right", width=8)

    if not whale_data:
        table.add_row("[dim]No whale data yet[/]", "", "", "", "")
    else:
        for w in whale_data[:8]:
            addr = w.get("address", "")[:8] + "..."
            win_rate = w.get("win_rate", 0)
            wr_color = "green" if win_rate >= 0.6 else "yellow" if win_rate >= 0.5 else "red"
            market = w.get("market", "—")[:18]
            side = w.get("side", "—")
            side_color = "green" if side.upper() == "YES" else "red" if side.upper() == "NO" else "dim"
            size = w.get("size", 0)

            table.add_row(
                f"[cyan]{addr}[/]",
                f"[{wr_color}]{win_rate:.0%}[/]",
                market,
                f"[{side_color}]{side}[/]",
                f"${size:,.0f}" if size > 0 else "—",
            )

    return Panel(table, title="🐋 WHALE ACTIVITY (live)", title_align="left", border_style="cyan")
