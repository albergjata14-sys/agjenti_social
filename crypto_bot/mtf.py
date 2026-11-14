"""Strategjia shumë-intervalëshe (`mtf`): trendi matet nga lart poshtë dhe hyrja bëhet në intervalin e vogël.

Radha: 1 ditë → 8 orë → 4 orë → 30 minuta; "beteja" (hyrja) bëhet në qirinjtë 15-minutësh. Trendi i çdo intervali
llogaritet mbi vetë qirinjtë e vegjël me një mesatare të shtrirë sa ai interval (EMA `mtf_ema` e intervalit të
madh), kështu që nuk përdoret asnjë e dhënë nga e ardhmja dhe trendi rifreskohet në çdo qiri të mbyllur.
"""
import numpy as np
import pandas as pd

FRAMES = {"1d": 1440, "8h": 480, "4h": 240, "30m": 30}      # intervalet e trendit, në minuta
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "8h": 480, "1d": 1440}


def bar_minutes(df: pd.DataFrame) -> float:
    return df.index.to_series().diff().median() / pd.Timedelta(minutes=1)


def used_frames(base: float) -> dict:
    """Intervalet më të mëdha se ai i qirinjve (p.sh. me qirinj 30-minutësh, 30m nuk numërohet më vete)."""
    return {k: m for k, m in FRAMES.items() if m > base}


def trends(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Për çdo interval: +1 (ngritje), −1 (rënie) ose 0 (i paqartë). Kolonat `t_1d`, `t_8h`, `t_4h`, `t_30m`."""
    c, base = df["close"], bar_minutes(df)
    out = pd.DataFrame(index=df.index)
    for name, minutes in used_frames(base).items():
        k = max(1, int(round(minutes / base)))
        span = cfg.mtf_ema * k
        ema = c.ewm(span=span, adjust=False, min_periods=span).mean()
        rising, falling = ema > ema.shift(k), ema < ema.shift(k)
        out[f"t_{name}"] = np.where((c > ema) & rising, 1, np.where((c < ema) & falling, -1, 0))
        out.loc[ema.isna(), f"t_{name}"] = 0
    return out


def mtf_signals(s: pd.DataFrame, cfg) -> dict:
    """Kolonat buy/sell/short/cover: hyrje vetëm kur intervalet e mëdha janë në një drejtim dhe 15m e konfirmon."""
    t = trends(s, cfg)
    cols = list(t.columns)
    up, down = (t[cols] == 1).sum(axis=1), (t[cols] == -1).sum(axis=1)
    need = min(cfg.mtf_min_align, len(cols))
    c, o, h, l = s["close"], s["open"], s["high"], s["low"]
    fast = c.ewm(span=cfg.mtf_trigger_ema, adjust=False, min_periods=cfg.mtf_trigger_ema).mean()
    if cfg.mtf_trigger == "breakout":       # thyerje e majës / fundit të qirinjve të fundit
        hi, lo = h.rolling(cfg.mtf_trigger_ema).max().shift(), l.rolling(cfg.mtf_trigger_ema).min().shift()
        go_up, go_down = c > hi, c < lo
    else:                                   # tërheqje: çmimi u kthye te mesatarja e shpejtë dhe u rikthye në trend
        go_up = (l.shift() <= fast.shift()) & (c > fast) & (c > o)
        go_down = (h.shift() >= fast.shift()) & (c < fast) & (c < o)
    out = {name: t[name] for name in cols}
    out["align"] = up - down
    out["momentum"] = (c / c.shift(max(1, int(round(240 / bar_minutes(s))))) - 1) * 100     # lëvizja 4-orëshe
    out["buy"] = (up >= need) & (down == 0) & go_up
    out["short"] = (down >= need) & (up == 0) & go_down
    exit_col = f"t_{cfg.mtf_exit}" if cfg.mtf_exit and f"t_{cfg.mtf_exit}" in t else None
    out["sell"] = (t[exit_col] == -1) if exit_col else pd.Series(False, index=s.index)
    out["cover"] = (t[exit_col] == 1) if exit_col else pd.Series(False, index=s.index)
    return out


def warmup_bars(cfg) -> int:
    base = MINUTES.get(cfg.timeframe, 15)
    return int(cfg.mtf_ema * max(used_frames(base).values(), default=base) / base) + int(1440 / base)


LABELS = {"1d": "1 ditë", "8h": "8 orë", "4h": "4 orë", "30m": "30 min", "15m": "15 min"}
ARROWS = {1: "⬆️", -1: "⬇️", 0: "➡️"}


def trend_text(mtf: dict) -> str:
    """P.sh. "1 ditë ⬆️ · 8 orë ⬆️ · 4 orë ➡️ · 30 min ⬇️"."""
    return " · ".join(f"{LABELS.get(k, k)} {ARROWS[int(v)]}" for k, v in mtf.items())
