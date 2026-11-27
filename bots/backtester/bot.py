"""Backtester – Provon setup-et Strong/Very Strong: ≥40 tregti, PF ≥ 1.45, pritshmëri ≥ 0.32R, DD ≤ 20%, kosto ≥ 0.15%; ia kalon Signal Cleaner."""
from pathlib import Path

from bots._base import Bot


class Backtester(Bot):
    name = "Backtester"
    role = "Provon setup-et Strong/Very Strong: ≥40 tregti, PF ≥ 1.45, pritshmëri ≥ 0.32R, DD ≤ 20%, kosto ≥ 0.15%; ia kalon Signal Cleaner."

    def __init__(self):
        super().__init__(Path(__file__).parent)
