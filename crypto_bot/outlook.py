"""Pamja e tregut: ecuria e çdo monedhe dhe gjasat historike për 24 orët e ardhshme.

Gjasat NUK janë parashikim. Janë sa herë, në të kaluarën e afërt të këtyre monedhave, çmimi ishte më lart
pas 24 orësh kur tregu ishte në një gjendje të ngjashme (lëvizja 14-ditore dhe pozicioni ndaj mesatares).
Në një provë jashtë mostrës (40 monedha, 2024–2026) kjo e qëlloi drejtimin rreth 51% të herëve.
"""
import numpy as np
import pandas as pd

from .data import fetch_candles
from .strategy import analyze

HORIZON_H = 24


def state_of(momentum: float, above: bool) -> str:
    move = "rritje" if momentum > 5 else "rënie" if momentum < -5 else "anash"
    return f"{move}, {'mbi' if above else 'nën'} mesataren"


def _frame_states(df: pd.DataFrame):
    c = df["close"]
    step = df.index.to_series().diff().median()
    bars14 = max(1, int(round(pd.Timedelta(days=14) / step)))
    ahead = max(1, int(round(pd.Timedelta(hours=HORIZON_H) / step)))
    mom = (c / c.shift(bars14) - 1) * 100
    above = c > c.ewm(span=100, adjust=False, min_periods=100).mean()
    future = c.shift(-ahead) / c - 1
    states = pd.Series([state_of(m, a) if not np.isnan(m) else None for m, a in zip(mom, above)], index=df.index)
    return mom, above, future, states, ahead


def overview(exchange, cfg, symbols, tickers=None, candles: int = 600) -> pd.DataFrame:
    """Një rresht për monedhë: çmimi, ndryshimet, lëvizja 14-ditore, gjendja, sinjali dhe gjasat historike."""
    frames, pool = {}, []
    for sym in symbols:
        try:
            df = fetch_candles(exchange, sym, "4h", candles)
        except Exception:
            continue
        if len(df) < 200:
            continue
        mom, above, future, states, ahead = _frame_states(df)
        frames[sym] = (df, mom, above, states, ahead)
        pool.append(pd.DataFrame({"state": states, "up": future > 0}).dropna().iloc[:-ahead or None])
    hist = pd.concat(pool) if pool else pd.DataFrame(columns=["state", "up"])
    rates = hist.groupby("state")["up"].agg(["mean", "size"])
    rows = []
    for sym, (df, mom, above, states, ahead) in frames.items():
        c = df["close"]
        price = float(c.iloc[-1])
        st_now = states.iloc[-1]
        p_up, n = (float(rates.loc[st_now, "mean"]), int(rates.loc[st_now, "size"])) if st_now in rates.index else (np.nan, 0)
        t = (tickers or {}).get(sym, {})
        signal = reason = None
        if cfg.timeframe == "4h":
            try:
                a = analyze(df, cfg, sym)
                signal, reason = a["signal"], a["signal_reason"]
            except Exception:
                pass
        rows.append({
            "Monedha": sym, "Çmimi": float(t.get("last") or price),
            "24 orë %": float(t["percentage"]) if t.get("percentage") is not None else (price / c.iloc[-1 - ahead] - 1) * 100,
            "7 ditë %": (price / c.iloc[-1 - 7 * ahead] - 1) * 100 if len(c) > 7 * ahead else np.nan,
            "Lëvizja 14 ditë %": float(mom.iloc[-1]), "Gjendja": st_now,
            "Gjasat lart 24h %": p_up * 100, "Raste": n,
            "Sinjali i robotit": signal if signal in ("BLI", "SHORT") else "–", "Arsyeja": reason,
        })
    return pd.DataFrame(rows).sort_values("Lëvizja 14 ditë %", ascending=False, ignore_index=True) if rows else pd.DataFrame()
