"""Sniper – Miraton SNIPER SIGNAL vetëm me konfluencë Very Strong, R:R ≥ 1:3.2, stop të ngushtë dhe pa strukturë kundër; ia kalon Alert Manager."""
from pathlib import Path

from bots._base import Bot


class Sniper(Bot):
    name = "Sniper"
    role = "Miraton SNIPER SIGNAL vetëm me konfluencë Very Strong, R:R ≥ 1:3.2, stop të ngushtë dhe pa strukturë kundër; ia kalon Alert Manager."

    def __init__(self):
        super().__init__(Path(__file__).parent)
