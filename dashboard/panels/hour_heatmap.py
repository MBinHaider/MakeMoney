from rich.panel import Panel
from rich.text import Text


def render_hour_heatmap(hourly: list[dict]) -> Panel:
    heatmap = Text()

    for h in hourly:
        hour_label = f"{h['hour']:02d}"
        if h["trades"] == 0:
            heatmap.append(f" {hour_label} ", style="dim on #161b22")
        elif h["rate"] >= 0.7:
            heatmap.append(f" {hour_label} ", style="bold white on #26a641")
        elif h["rate"] >= 0.4:
            heatmap.append(f" {hour_label} ", style="on #0e4429")
        else:
            heatmap.append(f" {hour_label} ", style="white on #da3633")
        heatmap.append(" ")

    heatmap.append("\n\n")
    heatmap.append(" ░ ", style="dim on #161b22")
    heatmap.append(" none ", style="dim")
    heatmap.append(" ░ ", style="white on #da3633")
    heatmap.append(" <40% ", style="dim")
    heatmap.append(" ░ ", style="on #0e4429")
    heatmap.append(" 40-70% ", style="dim")
    heatmap.append(" ░ ", style="bold white on #26a641")
    heatmap.append(" >70%", style="dim")

    return Panel(heatmap, title="WIN RATE BY HOUR (UTC) — 5M", title_align="left", border_style="dim")
