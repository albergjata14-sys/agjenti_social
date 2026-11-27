"""Alert Manager – Vepron vetëm për mesazhet që nisin me "SNIPER SIGNAL" dhe dërgon alarmin në formatin e pastër, pa fjalë shtesë."""
from pathlib import Path

from bots._base import Bot


class AlertManager(Bot):
    name = "Alert Manager"
    role = "Vepron vetëm për mesazhet që nisin me "SNIPER SIGNAL" dhe dërgon alarmin në formatin e pastër, pa fjalë shtesë."

    def __init__(self):
        super().__init__(Path(__file__).parent)
