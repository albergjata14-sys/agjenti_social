"""Ruajtja e qirinjve në disk: herën e parë shkarkohet historia, pastaj merren vetëm qirinjtë e rinj.

Kështu analisti mund të rifreskojë 30 monedha në tre intervale disa herë në orë pa e ngarkuar platformën.
"""
import os
import time
from pathlib import Path

import pandas as pd

from .data import fetch_candles

DIR = os.environ.get("CRYPTO_BOT_CACHE", "crypto_bot_cache")


def _path(symbol: str, timeframe: str, source: str = "") -> Path:
    name = f"{symbol.replace('/', '_').replace(':', '_')}_{timeframe}"
    return Path(DIR) / (f"{source}_{name}.pkl" if source else f"{name}.pkl")


def _source(exchange, symbol: str) -> str:
    """Çdo burim (MEXC, MT5...) ka skedarët e vet, që historitë të mos përzihen."""
    if hasattr(exchange, "source"):
        return exchange.source(symbol)
    return str(getattr(exchange, "id", "") or "")


def candles(exchange, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Qirinjtë e mbyllur të fundit `limit`, nga disku kur ka dhe nga platforma vetëm për pjesën që mungon."""
    p = _path(symbol, timeframe, _source(exchange, symbol))
    old = None
    if p.exists():
        try:
            old = pd.read_pickle(p)
        except Exception:
            old = None
    step = exchange.parse_timeframe(timeframe) * 1000
    if old is not None and len(old) >= min(limit, 50):
        last_ms = int(old.index[-1].timestamp() * 1000)
        missing = int((exchange.milliseconds() - last_ms) // step) + 2
        if missing <= 0:
            return old.tail(limit)
        # Tregjet e reja (p.sh. ari në MEXC) kanë më pak histori se sa kërkohet: ato rifreskohen plotësisht
        # vetëm një herë në ditë, jo në çdo rreth.
        short_ok = time.time() - old.attrs.get("short_history_at", 0) < 86400
        if missing < limit and (len(old) >= limit * 0.98 or short_ok):
            new = fetch_candles(exchange, symbol, timeframe, missing)
            df = pd.concat([old, new])
            attrs = dict(old.attrs)
            df = df[~df.index.duplicated(keep="last")].sort_index().tail(max(limit, len(old)))
            df.attrs.update(attrs)
            p.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(p)
            return df.tail(limit)
    df = fetch_candles(exchange, symbol, timeframe, limit)
    if len(df) < limit * 0.98:
        df.attrs["short_history_at"] = time.time()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(p)
    return df
