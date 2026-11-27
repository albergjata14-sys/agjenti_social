"""Chart Feeder – Merr grafikun dhe e etiketon (Pair, Timeframe) pa analizuar; ia kalon Math Geometry."""
from pathlib import Path

from bots._base import Bot


class ChartFeeder(Bot):
    name = "Chart Feeder"
    role = "Merr grafikun dhe e etiketon (Pair, Timeframe) pa analizuar; ia kalon Math Geometry."

    def __init__(self):
        super().__init__(Path(__file__).parent)
