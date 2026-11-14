"""Radari: monedhat që po lëvizin më fort tani, lart dhe poshtë.

Për 50 monedhat më të tregtuara mat lëvizjen 7 dhe 14 ditore, pozicionin ndaj mesatares 100 (4h) dhe
volumin e 24 orëve kundrejt mesatares së javës. Ruhet te `radar_file` dhe njoftohet kur një monedhë hyn
ndër 5 më të fortat. Radari informon; sa monedha tregtohen e vendos laboratori me prova (në 27 muaj të
dhëna, kalimi nga 20 në 40 monedha i rriti rëniet e të tri strategjive kryesore).
"""
import json
import time
from pathlib import Path

import numpy as np

from . import cache
from .data import top_symbols


def scan(exchange, cfg, n: int = 50) -> dict:
    tickers = exchange.fetch_tickers()
    rows = []
    for sym in (list(cfg.symbols) if cfg.focus else top_symbols(exchange, cfg.quote, n)):
        try:
            df = cache.candles(exchange, sym, "4h", 300)
        except Exception:
            continue
        if len(df) < 90:
            continue
        c, v = df["close"], df["volume"]
        price = float(c.iloc[-1])
        ema = float(c.ewm(span=100, adjust=False).mean().iloc[-1])
        m7 = (price / float(c.iloc[-43]) - 1) * 100
        m14 = (price / float(c.iloc[-85]) - 1) * 100
        # Forex-i dhe ari kanë pushim në fundjavë në disa burime: mjafton të ketë qirinj të mjaftueshëm.
        vol_ratio = float(v.iloc[-6:].sum() / (v.iloc[-48:-6].sum() / 7)) if v.iloc[-48:-6].sum() else np.nan
        t = tickers.get(sym, {})
        rows.append({"symbol": sym, "price": float(t.get("last") or price), "change24": t.get("percentage"),
                     "m7": round(m7, 2), "m14": round(m14, 2), "above_ema": price > ema,
                     "volume_x": None if np.isnan(vol_ratio) else round(vol_ratio, 2)})
    # Lëvizjet mbi 80% në 14 ditë janë zakonisht monedha që po shemben ose po hiqen nga bursa: mbahen veçmas.
    extreme = [r for r in rows if abs(r["m14"]) > 80]
    normal = [r for r in rows if abs(r["m14"]) <= 80]
    th = 1.0 if cfg.focus else 5.0            # forex-i lëviz më pak: prag më i ulët në Fokus
    up = sorted((r for r in normal if r["m14"] > th and r["m7"] > 0 and r["above_ema"]), key=lambda r: -r["m14"])
    down = sorted((r for r in normal if r["m14"] < -th and r["m7"] < 0 and not r["above_ema"]), key=lambda r: r["m14"])
    return {"ts": time.time(), "scanned": len(rows), "up": up[:15], "down": down[:15], "all": rows,
            "extreme": [r["symbol"] for r in extreme]}


def load(cfg):
    p = Path(cfg.radar_file)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except ValueError:
        return None


def update(exchange, cfg) -> tuple:
    """Rifreskon radarin dhe kthen (radari, monedhat që hynë rishtas ndër 5 më të fortat lart / poshtë)."""
    old = load(cfg) or {"up": [], "down": []}
    new = scan(exchange, cfg)
    Path(cfg.radar_file).write_text(json.dumps(new, indent=2))
    entered = {side: [r for r in new[side][:5] if r["symbol"] not in {o["symbol"] for o in old[side][:5]}]
               for side in ("up", "down")}
    return new, entered
