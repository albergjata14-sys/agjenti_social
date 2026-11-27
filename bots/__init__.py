"""Botët e veçantë – secili me dosjen, klasën dhe promptin e vet."""
from bots.alert_manager import AlertManager
from bots.backtester import Backtester
from bots.chart_feeder import ChartFeeder
from bots.math_geometry import MathGeometry
from bots.signal_cleaner import SignalCleaner
from bots.sniper import Sniper

ALL_BOTS = (ChartFeeder, MathGeometry, Backtester, SignalCleaner, Sniper, AlertManager)


def get_bot(name):
    """Gjen botin sipas emrit ('Sniper', 'sniper', 'signal_cleaner' ...)."""
    key = name.lower().replace("_", " ").strip()
    for cls in ALL_BOTS:
        if cls.name.lower() == key:
            return cls()
    raise KeyError(f"Nuk ka bot me emrin {name!r}. Botët: {', '.join(c.name for c in ALL_BOTS)}")
