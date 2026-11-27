"""Chart Feeder – Mbledh dhe ushqen të dhënat e grafikut (qirinjtë, volumi) për botët e tjerë."""
from pathlib import Path

from bots._base import Bot


class ChartFeeder(Bot):
    name = "Chart Feeder"
    role = "Mbledh dhe ushqen të dhënat e grafikut (qirinjtë, volumi) për botët e tjerë."

    def __init__(self):
        super().__init__(Path(__file__).parent)
