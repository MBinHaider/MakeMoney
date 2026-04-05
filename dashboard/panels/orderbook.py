from rich.panel import Panel
from rich.text import Text


def render_orderbook(book: dict, asset: str) -> Panel:
    bids = book.get("bids", [])
    asks = book.get("asks", [])

    if not bids and not asks:
        return Panel("[dim]No orderbook data[/]", title="ORDERBOOK", title_align="left", border_style="dim")

    max_size = max(
        [s for _, s in bids[:3]] + [s for _, s in asks[:3]] + [1]
    )

    content = Text()
    content.append("BIDS\n", style="green")
    for price, size in bids[:3]:
        bar_len = int((size / max_size) * 8)
        content.append(f"${price:.2f} ", style="dim")
        content.append("█" * bar_len, style="green")
        content.append(f" {size:.0f}\n")

    content.append("\nASKS\n", style="red")
    for price, size in asks[:3]:
        bar_len = int((size / max_size) * 8)
        content.append(f"${price:.2f} ", style="dim")
        content.append("█" * bar_len, style="red")
        content.append(f" {size:.0f}\n")

    # Imbalance
    total_bid = sum(s for _, s in bids[:5])
    total_ask = sum(s for _, s in asks[:5])
    total = total_bid + total_ask
    if total > 0:
        imbalance = (total_bid - total_ask) / total
        imb_color = "green" if imbalance > 0 else "red"
        content.append(f"\nImbalance: ", style="dim")
        content.append(f"{imbalance:+.2f}", style=imb_color)

    return Panel(content, title=f"ORDERBOOK ({asset} UP)", title_align="left", border_style="dim")
