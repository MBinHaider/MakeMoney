import asciichartpy
from rich.panel import Panel
from rich.text import Text


def render_pnl_chart(pnl_history: dict) -> Panel:
    fm = pnl_history.get("fivemin", [0])
    bn = pnl_history.get("binance", [0])
    combined = pnl_history.get("combined", [0])

    # Ensure at least 2 points for charting
    if len(combined) < 2:
        combined = [0, 0]
    if len(fm) < 2:
        fm = [0, 0]
    if len(bn) < 2:
        bn = [0, 0]

    # Trim to last 50 points for readability
    combined = combined[-50:]
    fm = fm[-50:]
    bn = bn[-50:]

    try:
        chart = asciichartpy.plot(
            [combined, fm, bn],
            {"height": 8, "colors": [
                asciichartpy.green,
                asciichartpy.yellow,
                asciichartpy.blue,
            ]},
        )
    except Exception:
        chart = "No data yet"

    legend = Text()
    legend.append("━ Combined  ", style="green")
    legend.append("━ 5M  ", style="yellow")
    legend.append("━ BN", style="bright_blue")

    content = Text(chart + "\n")
    content.append(legend)

    return Panel(content, title="P&L OVER TIME (24h)", title_align="left", border_style="dim")
