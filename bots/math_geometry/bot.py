"""Math Geometry – Llogaritjet matematikore dhe gjeometrike mbi grafikun (nivele, vija, kënde, modele)."""
from pathlib import Path

from bots._base import Bot


class MathGeometry(Bot):
    name = "Math Geometry"
    role = "Llogaritjet matematikore dhe gjeometrike mbi grafikun (nivele, vija, kënde, modele)."

    def __init__(self):
        super().__init__(Path(__file__).parent)
