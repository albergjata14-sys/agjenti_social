"""Signal Cleaner: filtri i cilësisë. Setup-i mbijeton vetëm kur kalon të gjitha kushtet."""
from bots._base import fmt
from bots.math_geometry.logic import Geometry

MIN_RR, MAX_RISK_ATR = 2.8, 1.5


def htf_trend(htf_df):
    """Drejtimi në kohën më të gjatë: +1 lart, -1 poshtë, 0 i paqartë. Duhet ta thonë si EMA50 ashtu edhe struktura."""
    if htf_df is None or len(htf_df) < 60:
        return 0, "not enough higher-timeframe data"
    close = htf_df["close"]
    ema = close.ewm(span=50, adjust=False).mean()
    ema_dir = 1 if close.iloc[-1] > ema.iloc[-1] and ema.iloc[-1] > ema.iloc[-6] else \
        -1 if close.iloc[-1] < ema.iloc[-1] and ema.iloc[-1] < ema.iloc[-6] else 0
    s = Geometry(htf_df).swings(len(htf_df) - 1)
    highs = [p for _, p, k in s if k == "H"][-2:]
    lows = [p for _, p, k in s if k == "L"][-2:]
    struct = 0
    if len(highs) == 2 and len(lows) == 2:
        struct = 1 if highs[1] > highs[0] and lows[1] > lows[0] else -1 if highs[1] < highs[0] and lows[1] < lows[0] else 0
    word = {1: "up", -1: "down", 0: "unclear"}
    trend = ema_dir if ema_dir == struct else 0          # "e qartë" = të dyja bien dakord
    return trend, f"EMA50 {word[ema_dir]}, structure {word[struct]} (EMA50 {fmt(ema.iloc[-1])})"


def clean(chart, setup, backtest_stats):
    """Kthen (kaloi?, mesazhi i botit)."""
    trend, why = htf_trend(chart.htf_df)
    risk_atr = setup.risk / setup.atr
    checks = [
        ("Math Geometry = Strong/Very Strong", setup.score >= 3, setup.confluence),
        ("Backtester passed all criteria", bool(backtest_stats and backtest_stats.passed), "yes" if backtest_stats and backtest_stats.passed else "no"),
        (f"Higher timeframe ({chart.htf_timeframe}) aligned", trend == setup.side, why),
        (f"Risk-Reward ≥ 1:{MIN_RR}", setup.rr >= MIN_RR, f"1:{setup.rr:.2f}"),
        (f"Tight, logical invalidation (≤ {MAX_RISK_ATR} ATR, beyond 0.786)", risk_atr <= MAX_RISK_ATR,
         f"stop {fmt(setup.stop)} = {risk_atr:.2f} ATR"),
    ]
    ok = all(c[1] for c in checks)
    lines = [f"{'✔' if c[1] else '✘'} {c[0]}: {c[2]}" for c in checks]
    lines.append("→ Passing to Sniper" if ok else "REJECTED.")
    return ok, "\n".join(lines)
