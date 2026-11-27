"""Zinxhiri automatik: Chart Feeder → Math Geometry → Backtester → Signal Cleaner → Sniper → Alert Manager.

Falas dhe pa asnjë API të inteligjencës artificiale: çdo bot zbaton rregullat e promptit të vet me kod
(bots/<emri>/logic.py). Grafiku merret vetë nga MEXC. Zinxhiri ndalet te boti i parë që refuzon.
"""
from dataclasses import dataclass, field

from bots.alert_manager.logic import send
from bots.backtester.logic import check
from bots.chart_feeder.logic import feed, fetch_candles
from bots.math_geometry.logic import analyze
from bots.signal_cleaner.logic import clean
from bots.sniper.logic import snipe

NAMES = ["Chart Feeder", "Math Geometry", "Backtester", "Signal Cleaner", "Sniper", "Alert Manager"]


@dataclass
class Step:
    bot: str
    status: str            # "passed" | "rejected" | "alert" | "error"
    output: str = ""


@dataclass
class ChainResult:
    pair: str
    timeframe: str
    steps: list = field(default_factory=list)
    setup: object = None
    chart: object = None       # grafiku që solli Chart Feeder (për tregtinë demo)
    new_alert: bool = False

    @property
    def alert(self):
        last = self.steps[-1] if self.steps else None
        return last.output if last and last.status == "alert" else ""

    @property
    def stopped_at(self):
        last = self.steps[-1] if self.steps else None
        return last.bot if last and last.status in ("rejected", "error") else ""

    @property
    def statuses(self):
        done = [s.status for s in self.steps]
        return done + ["idle"] * (len(NAMES) - len(done))


def run_chain(pair, timeframe, candles=3000, fetch=fetch_candles, on_step=None, save_alert=True):
    """Kalon një çift nëpër 6 botët. `on_step(index, Step|None)`: None kur boti nis, Step kur mbaron."""
    res = ChainResult(pair, timeframe)

    def step(i, status, text):
        s = Step(NAMES[i], status, text)
        res.steps.append(s)
        if on_step:
            on_step(i, s)
        return status not in ("rejected", "error")

    def start(i):
        if on_step:
            on_step(i, None)

    start(0)
    try:
        chart, msg = feed(pair, timeframe, candles, fetch)
    except Exception as exc:                       # rrjeti, çift që nuk ekziston, etj.
        step(0, "error", f"{type(exc).__name__}: {exc}")
        return res
    res.pair = chart.pair
    res.chart = chart
    if not step(0, "passed", msg):
        return res

    start(1)
    setup, msg = analyze(chart)
    res.setup = setup
    if not step(1, "passed" if setup else "rejected", msg):
        return res

    start(2)
    stats, msg = check(chart, setup)
    if not step(2, "passed" if stats.passed else "rejected", msg):
        return res

    start(3)
    ok, msg = clean(chart, setup, stats)
    if not step(3, "passed" if ok else "rejected", msg):
        return res

    start(4)
    ok, msg, reasons = snipe(chart, setup, ok)
    if not step(4, "passed" if ok else "rejected", msg or f"(refuzuar në heshtje)\n{reasons}"):
        return res

    start(5)
    if save_alert:
        alert, res.new_alert = send(msg, timeframe)
    else:
        from bots.alert_manager.logic import format_alert
        alert = format_alert(msg)
    step(5, "alert", alert)
    return res


def scan(pairs, timeframe, candles=3000, fetch=fetch_candles, on_result=None):
    """Kalon shumë çifte njëri pas tjetrit."""
    out = []
    for p in pairs:
        r = run_chain(p, timeframe, candles, fetch)
        out.append(r)
        if on_result:
            on_result(r)
    return out
