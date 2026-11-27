"""Math Geometry – Analizë gjeometrike (Fibonacci, harmonikë, Gann, Pitchfork, strukturë, Volume Profile) vetëm me konfluencë të fortë; ia kalon Backtester."""
from pathlib import Path

from bots._base import Bot


class MathGeometry(Bot):
    name = "Math Geometry"
    role = "Analizë gjeometrike (Fibonacci, harmonikë, Gann, Pitchfork, strukturë, Volume Profile) vetëm me konfluencë të fortë; ia kalon Backtester."

    def __init__(self):
        super().__init__(Path(__file__).parent)
