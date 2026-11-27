"""Backtester – Provon strategjitë në të dhënat e së kaluarës dhe mat rezultatet."""
from pathlib import Path

from bots._base import Bot


class Backtester(Bot):
    name = "Backtester"
    role = "Provon strategjitë në të dhënat e së kaluarës dhe mat rezultatet."

    def __init__(self):
        super().__init__(Path(__file__).parent)
