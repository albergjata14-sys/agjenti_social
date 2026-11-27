"""Signal Cleaner – Filtron sinjalet: heq zhurmën, dublikatat dhe sinjalet e dobëta."""
from pathlib import Path

from bots._base import Bot


class SignalCleaner(Bot):
    name = "Signal Cleaner"
    role = "Filtron sinjalet: heq zhurmën, dublikatat dhe sinjalet e dobëta."

    def __init__(self):
        super().__init__(Path(__file__).parent)
