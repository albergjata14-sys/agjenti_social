"""Signal Cleaner – Filtri i cilësisë: Geometry Strong/Very Strong, Backtester i kaluar, TF më i lartë në një drejtim, R:R ≥ 1:2.8, invalidim i ngushtë; ia kalon Sniper."""
from pathlib import Path

from bots._base import Bot


class SignalCleaner(Bot):
    name = "Signal Cleaner"
    role = "Filtri i cilësisë: Geometry Strong/Very Strong, Backtester i kaluar, TF më i lartë në një drejtim, R:R ≥ 1:2.8, invalidim i ngushtë; ia kalon Sniper."

    def __init__(self):
        super().__init__(Path(__file__).parent)
