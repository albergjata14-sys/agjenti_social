"""Sniper – Zgjedh pikën e saktë të hyrjes, stop-loss dhe objektivin për sinjalet e pastra."""
from pathlib import Path

from bots._base import Bot


class Sniper(Bot):
    name = "Sniper"
    role = "Zgjedh pikën e saktë të hyrjes, stop-loss dhe objektivin për sinjalet e pastra."

    def __init__(self):
        super().__init__(Path(__file__).parent)
