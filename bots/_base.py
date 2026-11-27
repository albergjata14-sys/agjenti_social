"""Bazë e vogël e përbashkët: çdo bot ka emrin, rolin dhe promptin e vet në dosjen e vet."""
from pathlib import Path

PLACEHOLDER = "<!-- PROMPTI DO TË SHTOHET -->"


class Bot:
    name = ""
    role = ""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.prompt_file = self.folder / "prompt.md"

    @property
    def prompt(self):
        text = self.prompt_file.read_text(encoding="utf-8").strip() if self.prompt_file.exists() else ""
        return "" if text == PLACEHOLDER else text

    @property
    def ready(self):
        return bool(self.prompt)

    def set_prompt(self, text):
        self.prompt_file.write_text(text.strip() + "\n", encoding="utf-8")

    def __repr__(self):
        return f"<{self.name} ({'gati' if self.ready else 'pa prompt'})>"


# ---------------------------------------------------------------- të dhënat që kalojnë nga një bot te tjetri

from dataclasses import dataclass, field


@dataclass
class Chart:
    """Ajo që Chart Feeder ia jep Math Geometry-së."""
    pair: str
    timeframe: str
    df: object                 # pandas DataFrame: open, high, low, close, volume (qirinj të mbyllur)
    htf_timeframe: str = ""
    htf_df: object = None      # e njëjta gjë në kohën më të gjatë (për Signal Cleaner dhe Sniper)


@dataclass
class Setup:
    """Setup-i gjeometrik që gjen Math Geometry."""
    direction: str             # "Long" | "Short"
    entry_low: float
    entry_high: float
    entry: float
    stop: float
    target1: float
    target2: float
    atr: float
    score: int                 # sa mjete bien dakord te zona (Fibonacci = 1, çdo mjet tjetër +1)
    tools: list = field(default_factory=list)   # rreshtat me nivelet dhe raportet e sakta
    leg: tuple = ()            # (çmimi A, çmimi B) i lëvizjes që matet

    @property
    def side(self):
        return 1 if self.direction == "Long" else -1

    @property
    def risk(self):
        return abs(self.entry - self.stop)

    @property
    def rr(self):
        return abs(self.target1 - self.entry) / self.risk if self.risk else 0.0

    @property
    def confluence(self):
        return "Very Strong" if self.score >= 4 else "Strong" if self.score == 3 else "Moderate" if self.score == 2 else "Weak"


def fmt(price):
    """Çmimi me aq shifra sa duhen (BTC 61660.15, PEPE 0.00001234)."""
    if price == 0:
        return "0"
    digits = max(2, 6 - len(str(int(abs(price)))) if abs(price) >= 1 else 8)
    return f"{price:.{digits}f}".rstrip("0").rstrip(".") if abs(price) < 1 else f"{price:.{min(digits, 4)}f}"
