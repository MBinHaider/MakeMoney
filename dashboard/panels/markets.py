from rich.panel import Panel
from rich.table import Table


def render_markets(market_data: list[dict]) -> Panel:
    """Render live markets being analyzed."""
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("MARKET", width=30)
    table.add_column("YES", justify="center", width=6)
    table.add_column("NO", justify="center", width=6)
    table.add_column("VOL", justify="right", width=8)
    table.add_column("SIGNAL", justify="center", width=8)

    if not market_data:
        table.add_row("[dim]No markets tracked[/]", "", "", "", "")
    else:
        for m in market_data[:6]:
            question = m.get("question", "—")[:28]
            yes_price = m.get("price_yes", 0.5)
            no_price = m.get("price_no", 0.5)
            volume = m.get("volume", 0)
            signal_score = m.get("signal_score", 0)

            yes_color = "green" if yes_price > 0.6 else "yellow" if yes_price > 0.4 else "red"
            no_color = "red" if no_price > 0.6 else "yellow" if no_price > 0.4 else "green"

            sig_str = "[dim]—[/]"
            if signal_score >= 50:
                sig_str = f"[green]▲ {signal_score}[/]"
            elif signal_score >= 35:
                sig_str = f"[yellow]● {signal_score}[/]"

            vol_str = f"${volume:,.0f}" if volume > 0 else "—"

            table.add_row(
                question,
                f"[{yes_color}]${yes_price:.2f}[/]",
                f"[{no_color}]${no_price:.2f}[/]",
                vol_str,
                sig_str,
            )

    return Panel(table, title="📈 MARKETS ANALYZED (live)", title_align="left", border_style="green")
