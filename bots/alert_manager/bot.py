"""Alert Manager – Menaxhon dhe dërgon njoftimet (paneli, Telegram) për sinjalet dhe hyrjet."""
from pathlib import Path

from bots._base import Bot


class AlertManager(Bot):
    name = "Alert Manager"
    role = "Menaxhon dhe dërgon njoftimet (paneli, Telegram) për sinjalet dhe hyrjet."

    def __init__(self):
        super().__init__(Path(__file__).parent)
