from rich.panel import Panel
from rich.table import Table


def render_signals(signal_data: list[dict]) -> Panel:
    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("ASSET", width=5)
    table.add_column("MOM", justify="center", width=5)
    table.add_column("OB", justify="center", width=5)
    table.add_column("VOL", justify="center", width=5)
    table.add_column("SIGNAL", justify="center")
    table.add_column("CONF", justify="center", width=5)

    for s in signal_data:
        asset_colors = {"BTC": "#f7931a", "ETH": "#627eea", "SOL": "#00ffa3"}
        asset_style = asset_colors.get(s["asset"], "white")

        def dir_cell(d):
            if d == "UP":
                return "[green]UP↑[/]"
            elif d == "DOWN":
                return "[red]DN↓[/]"
            return "[dim]—[/]"

        signal_str = f"[dim]—[/]"
        conf_str = f"[dim]—[/]"
        if s.get("signal"):
            count = s.get("agree_count", 0)
            sig_color = "green" if s["signal"] == "UP" else "red"
            signal_str = f"[bold {sig_color}]{count}/3 {s['signal']}[/]"
            conf_color = "green" if s.get("confidence", 0) >= 0.7 else "yellow"
            conf_str = f"[{conf_color}]{s.get('confidence', 0):.2f}[/]"

        table.add_row(
            f"[{asset_style}]{s['asset']}[/]",
            dir_cell(s.get("momentum", "")),
            dir_cell(s.get("orderbook", "")),
            dir_cell(s.get("volume", "")),
            signal_str,
            conf_str,
        )

    return Panel(table, title="LIVE SIGNALS (5M)", title_align="left", border_style="dim")
