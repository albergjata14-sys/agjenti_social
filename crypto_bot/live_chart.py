"""Grafiku i gjallë (TradingView Lightweight Charts) si komponent Streamlit.

Grafiku jeton në një iframe që nuk rikrijohet kur rifreskohen të dhënat, prandaj zmadhimi dhe pozicioni
që zgjedh përdoruesi ruhen. Libraria është brenda dosjes `chart/` (licenca Apache 2.0, shih NOTICE).
"""
from pathlib import Path

import numpy as np
import pandas as pd

_component = None


def chart_payload(df: pd.DataFrame, symbol: str, timeframe: str, ema_span: int = 0, levels=(), marks=(),
                  change_24h=None, height: int = 440, zones=(), stats=None, live_symbol=None) -> dict:
    """Të dhënat e grafikut në formë JSON.

    marks: [(koha, lloji, teksti)], lloji long / short / exit. zones: [(emri, çmimi1, çmimi2, lloji)], lloji
    entry / stop / target. stats: {emri: vlera} për rreshtin sipër grafikut. live_symbol: kontrata e MEXC
    (p.sh. "BTC_USDT") për çmimin e gjallë çdo sekondë; None = pa lidhje të gjallë.
    """
    t = df.index.as_unit("s").asi8.astype(np.int64)
    rows = np.column_stack([t, df[["open", "high", "low", "close", "volume"]].to_numpy(float)])
    step = int(np.median(np.diff(t))) if len(t) > 1 else 0
    payload = {"symbol": symbol, "timeframe": timeframe, "height": int(height), "step": step,
               "live_symbol": live_symbol, "stats": stats or {},
               "zones": [{"label": n, "top": float(max(a, b)), "bottom": float(min(a, b)), "kind": k}
                         for n, a, b, k in zones if a is not None and b is not None],
               "candles": [[int(r[0]), *map(float, r[1:])] for r in rows],
               "change_24h": None if change_24h is None or np.isnan(change_24h) else float(change_24h)}
    if ema_span:
        e = df["close"].ewm(span=ema_span, adjust=False, min_periods=ema_span).mean()
        payload["ema"] = [[int(a), float(b)] for a, b in zip(t, e.to_numpy()) if not np.isnan(b)]
    payload["levels"] = [{"name": n, "price": float(p), "kind": k} for n, p, k in levels if p is not None and np.isfinite(p)]
    # Çdo shenjë vendoset te qiriri ku ndodhi veprimi (grafiku i njeh vetëm kohët e qirinjve).
    out, seen = [], set()
    for when, kind, text in marks:
        sec = int(pd.Timestamp(when).timestamp())
        i = np.searchsorted(t, sec, side="right") - 1
        if 0 <= i < len(t) and (int(t[i]), kind) not in seen:   # një shenjë për qiri dhe lloj, jo dhjetë njëra mbi tjetrën
            seen.add((int(t[i]), kind))
            out.append({"time": int(t[i]), "kind": kind, "text": text})
    payload["marks"] = out
    return payload


def live_chart(payload: dict, key: str):
    global _component
    if _component is None:
        import streamlit.components.v1 as components

        _component = components.declare_component("crypto_live_chart", path=str(Path(__file__).with_name("chart")))
    return _component(**payload, key=key, default=None)
