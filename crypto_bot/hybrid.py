"""Të dhënat nga dy burime: MetaTrader 5 (kur është i hapur në kompjuter) dhe kontratat e MEXC.

MEXC e ka arin vetëm nga 2026 dhe EURUSD/GBPUSD vetëm nga 2025, ndaj për analizat 2–3 vjeçare historia e
XAUUSD, EURUSD, GBPUSD dhe BTCUSD merret nga MT5. BTCUSDT mbetet në MEXC (atje ka histori që nga 2020).
Kohët e MT5 (ora e serverit të brokerit) kthehen në UTC që të përputhen me MEXC. Nëse MT5 nuk është i hapur ose
nuk e ka simbolin, përdoret MEXC pa ndërprerje.
"""
import pandas as pd

from .config import MT5_SYMBOLS
from .data import fetch_candles

MT5_SOURCE = {k: v for k, v in MT5_SYMBOLS.items() if k != "BTC/USDT"}   # BTCUSDT: MEXC ka më shumë histori


def to_utc(rows: list, tz: str) -> list:
    """Kohët e serverit (të shkruara si të ishin UTC) → UTC i vërtetë. Ora e dyfishtë e ndërrimit të orës hiqet."""
    if not rows or tz == "UTC":
        return rows
    t = pd.to_datetime([r[0] for r in rows], unit="ms")
    t = t.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").tz_convert("UTC")
    out, seen = [], set()
    for r, ts in zip(rows, t):
        if pd.isna(ts):
            continue
        ms = int(ts.value // 1_000_000)
        if ms not in seen:
            seen.add(ms)
            out.append([ms] + list(r[1:]))
    return out


class HybridExchange:
    def __init__(self, mexc, mt5=None, tz: str = "auto", symbols: dict = None):
        self.mexc, self.mt5, self.tz = mexc, mt5, tz
        self.symbols = MT5_SOURCE if symbols is None else symbols
        self.id = "mt5+" + getattr(mexc, "id", "mexc")
        self._tz, self.errors = {}, {}

    def __getattr__(self, name):           # çmimet e drejtpërdrejta, tregjet etj. vijnë nga MEXC
        return getattr(self.mexc, name)

    def source(self, symbol: str) -> str:
        """Burimi i historisë së simbolit (përdoret edhe për emrin e skedarit në disk)."""
        return "mt5" if self.mt5 is not None and symbol in self.symbols else getattr(self.mexc, "id", "mexc")

    def _server_tz(self, name: str) -> str:
        if self.tz not in ("auto", "", None):
            return self.tz
        if name not in self._tz:
            try:
                self._tz[name] = self.mt5.server_tz(name)
            except Exception:
                self._tz[name] = "Europe/Athens"
        return self._tz[name]

    def fetch_closed_candles(self, symbol: str, timeframe: str, limit: int, closed_only: bool = True) -> list:
        if self.source(symbol) == "mt5":
            name = self.symbols[symbol]
            try:
                rows = to_utc(self.mt5.fetch_closed_candles(name, timeframe, limit, closed_only), self._server_tz(name))
                if len(rows) >= limit * 0.9:
                    self.errors.pop(symbol, None)
                    return rows
                other = self._mexc_rows(symbol, timeframe, limit, closed_only)
                return rows if len(rows) >= len(other) else other     # cila ka histori më të gjatë
            except Exception as e:                                     # MT5 i mbyllur, simbol që mungon...
                self.errors[symbol] = str(e)
        return self._mexc_rows(symbol, timeframe, limit, closed_only)

    def _mexc_rows(self, symbol, timeframe, limit, closed_only) -> list:
        df = fetch_candles(self.mexc, symbol, timeframe, limit, closed_only)
        ms = (df.index.asi8 // 1_000_000).tolist() if len(df) else []
        return [[t, *row] for t, row in zip(ms, df[["open", "high", "low", "close", "volume"]].values.tolist())]


def with_mt5(mexc, cfg, log=None):
    """MEXC + MT5 kur terminali MT5 është i hapur; përndryshe vetëm MEXC."""
    if not getattr(cfg, "use_mt5_data", True):
        return mexc
    try:
        from .mt5 import MT5Exchange

        mt5 = MT5Exchange()
    except Exception:
        return mexc         # p.sh. në internet (Streamlit) ose MT5 i mbyllur
    if log:
        log("Historia e XAUUSD, EURUSD, GBPUSD dhe BTCUSD merret nga MetaTrader 5.")
    return HybridExchange(mexc, mt5, tz=getattr(cfg, "data_tz", "auto"))
