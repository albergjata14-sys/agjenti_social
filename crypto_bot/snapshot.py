"""Grafik i vogël (PNG) për njoftimet: qirinjtë e fundit me hyrjen, stop-loss dhe objektivin."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

UP, DOWN, INK, MUTED, BG = "#2a78d6", "#eb6834", "#31333f", "#6b6d76", "#ffffff"


def render(df, title: str, entry: float = None, stop: float = None, take: float = None, side: int = 1,
           bars: int = 80) -> bytes:
    """Kthen PNG: qirinjtë (blu rritje, portokalli rënie), zonat e stop-it dhe objektivit dhe vijat me çmimet."""
    d = df.tail(bars)
    fig, ax = plt.subplots(figsize=(9, 5), dpi=110)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    xs = range(len(d))
    for x, (o, h, l, c) in zip(xs, d[["open", "high", "low", "close"]].to_numpy()):
        col = UP if c >= o else DOWN
        ax.vlines(x, l, h, color=col, linewidth=1)
        ax.add_patch(Rectangle((x - 0.35, min(o, c)), 0.7, max(abs(c - o), (h - l) * 0.02 or 1e-9), color=col))
    right = len(d) + 14
    if entry is not None:
        if stop is not None:   # zona e humbjes nga hyrja te stop-i
            ax.add_patch(Rectangle((len(d) - 0.5, min(entry, stop)), right - len(d), abs(entry - stop), color=DOWN, alpha=0.15))
        if take is not None:   # zona e fitimit nga hyrja te objektivi
            ax.add_patch(Rectangle((len(d) - 0.5, min(entry, take)), right - len(d), abs(take - entry), color=UP, alpha=0.15))
        for price, name, col, style in ((entry, "Hyrja", INK, "-"), (stop, "Stop-loss", DOWN, "--"),
                                        (take, "Objektivi (TP)", UP, "--")):
            if price is None:
                continue
            ax.axhline(price, color=col, linestyle=style, linewidth=1.3)
            # Etiketa rri jashtë zonës: sipër vijës kur është mbi hyrjen, poshtë kur është nën të.
            va = "center" if price == entry else ("bottom" if price > entry else "top")
            ax.text(right - 0.3, price, f" {name} {price:,.6g} ", va=va, ha="right", fontsize=9, color=col,
                    bbox={"facecolor": BG, "edgecolor": "none", "pad": 1.0, "alpha": 0.85})
    lo = min([d["low"].min()] + [p for p in (stop, take, entry) if p is not None])
    hi = max([d["high"].max()] + [p for p in (stop, take, entry) if p is not None])
    pad = (hi - lo) * 0.06 or hi * 0.01
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-1, right)
    ticks = list(range(0, len(d), max(1, len(d) // 5)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([d.index[i].strftime("%d %b %H:%M") for i in ticks], fontsize=8, color=MUTED)
    ax.tick_params(axis="y", labelsize=8, colors=MUTED)
    ax.yaxis.tick_right()
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(axis="y", alpha=0.15)
    ax.set_title(title, loc="left", fontsize=12, color=INK, fontweight="bold")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
