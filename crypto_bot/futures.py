"""Të dhëna publike të kontratave të përhershme (Perpetual / Futures) të MEXC.

Përdoren për grafikun dhe për pamjen e tregut: qirinjtë, çmimi i drejtë, norma e financimit (funding),
kontratat e hapura (open interest) dhe libri i urdhrave. Nuk dërgohet asnjë urdhër: vetëm lexim.
"""
import time

import pandas as pd
import requests

BASE = "https://api.mexc.com/api/v1/contract"
INTERVALS = {"1m": "Min1", "5m": "Min5", "15m": "Min15", "30m": "Min30", "1h": "Min60", "4h": "Hour4",
             "8h": "Hour8", "1d": "Day1", "1w": "Week1"}
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "8h": 28800, "1d": 86400,
           "1w": 604800}
_sizes = {}


def contract(symbol: str) -> str:
    """"BTC/USDT" → "BTC_USDT" (emri i kontratës në MEXC)."""
    return symbol.replace(":USDT", "").replace("/", "_")


def _get(path: str, **params):
    r = requests.get(f"{BASE}/{path}", params=params, timeout=10)
    r.raise_for_status()
    body = r.json()
    if not body.get("success", False):
        raise RuntimeError(f"MEXC nuk ktheu të dhëna për {path}: {body.get('message') or body.get('code')}")
    return body["data"]


def candles(symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Qirinjtë e kontratës, përfshirë atë që është ende i hapur, me kohë UTC."""
    if timeframe not in INTERVALS:
        raise ValueError(f"Intervali '{timeframe}' nuk mbështetet për kontratat")
    start = int(time.time()) - SECONDS[timeframe] * (limit + 1)
    d = _get(f"kline/{contract(symbol)}", interval=INTERVALS[timeframe], start=start)
    df = pd.DataFrame({"time": pd.to_datetime(d["time"], unit="s", utc=True), "open": d["open"], "high": d["high"],
                       "low": d["low"], "close": d["close"], "volume": d["amount"]})
    return df.set_index("time").astype(float).tail(limit)


def contract_size(symbol: str) -> float:
    """Sa monedha përfaqëson një kontratë (p.sh. 0.0001 BTC); ruhet në memorie."""
    c = contract(symbol)
    if c not in _sizes:
        _sizes[c] = float(_get("detail", symbol=c)["contractSize"])
    return _sizes[c]


def ticker(symbol: str) -> dict:
    """Çmimi i fundit, maja/fundi 24 orë, volumi, financimi dhe kontratat e hapura."""
    d = _get("ticker", symbol=contract(symbol))
    price = float(d["lastPrice"])
    try:
        oi_coins = float(d["holdVol"]) * contract_size(symbol)
    except Exception:
        oi_coins = None
    return {"last": price, "high": float(d["high24Price"]), "low": float(d["lower24Price"]),
            "change_pct": float(d["riseFallRate"]) * 100, "volume_quote": float(d["amount24"]),
            "funding_pct": float(d["fundingRate"]) * 100, "fair": float(d["fairPrice"]), "index": float(d["indexPrice"]),
            "open_interest_coins": oi_coins, "open_interest_quote": None if oi_coins is None else oi_coins * price}


def funding(symbol: str) -> dict:
    d = _get(f"funding_rate/{contract(symbol)}")
    return {"rate_pct": float(d["fundingRate"]) * 100, "next_ms": int(d["nextSettleTime"]),
            "cycle_h": int(d.get("collectCycle") or 8)}


def depth(symbol: str, limit: int = 50) -> dict:
    """Libri i urdhrave dhe pjesa e blerësve kundrejt shitësve në nivelet më të afërta."""
    d = _get(f"depth/{contract(symbol)}", limit=limit)
    bids = sum(float(q) for _, q, *_ in d["bids"])
    asks = sum(float(q) for _, q, *_ in d["asks"])
    total = bids + asks
    return {"bids": d["bids"], "asks": d["asks"], "buy_pct": bids / total * 100 if total else 50.0}


def all_tickers() -> dict:
    """Të gjitha kontratat me një kërkesë: {"BTC/USDT": {"funding_pct", "change_pct", "last"}}."""
    out = {}
    for d in _get("ticker"):
        sym = d["symbol"].replace("_", "/")
        out[sym] = {"last": float(d["lastPrice"]), "funding_pct": float(d["fundingRate"]) * 100,
                    "change_pct": float(d["riseFallRate"]) * 100}
    return out


def history(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    """Histori e gjatë: MEXC kthen deri në 2000 qirinj për kërkesë, ndaj faqosim mbrapa në kohë."""
    if timeframe not in INTERVALS:
        raise ValueError(f"Intervali '{timeframe}' nuk mbështetet për kontratat")
    step, end, parts, got = SECONDS[timeframe], int(time.time()), [], 0
    while got < limit:
        d = _get(f"kline/{contract(symbol)}", interval=INTERVALS[timeframe], start=end - step * 2000, end=end)
        if not d["time"]:
            break
        df = pd.DataFrame({"time": pd.to_datetime(d["time"], unit="s", utc=True), "open": d["open"], "high": d["high"],
                           "low": d["low"], "close": d["close"], "volume": d["amount"]}).set_index("time").astype(float)
        parts.append(df)
        got += len(df)
        if len(df) < 1900:          # nuk ka më histori më të vjetër
            break
        end = int(df.index[0].timestamp()) - 1
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = pd.concat(parts).sort_index()
    return out[~out.index.duplicated(keep="last")].tail(limit)


class MexcFuturesExchange:
    """Kontratat e MEXC me të njëjtën ndërfaqe si platformat e ccxt (vetëm lexim; urdhrat bëhen në simulim
    ose në MT5). Simbolet shkruhen si "XAU/USDT", "BTC/USD", "EUR/USDT"."""

    id = "mexc_futures"

    def parse_timeframe(self, timeframe: str) -> int:
        if timeframe not in SECONDS:
            raise ValueError(f"Intervali '{timeframe}' nuk mbështetet për kontratat")
        return SECONDS[timeframe]

    def milliseconds(self) -> int:
        return int(time.time() * 1000)

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        """Si ccxt: me `since` kthen qirinjtë që fillojnë nga ai çast (deri në `limit`, maksimumi 2000)."""
        if timeframe not in INTERVALS:
            raise ValueError(f"Intervali '{timeframe}' nuk mbështetet për kontratat")
        n = min(limit or 500, 2000)
        if since is None:
            df = candles(symbol, timeframe, n)
        else:
            step = SECONDS[timeframe]
            start = int(since // 1000)
            end = min(int(time.time()), start + step * n)
            d = _get(f"kline/{contract(symbol)}", interval=INTERVALS[timeframe], start=start, end=end)
            df = pd.DataFrame({"time": pd.to_datetime(d["time"], unit="s", utc=True), "open": d["open"], "high": d["high"],
                               "low": d["low"], "close": d["close"], "volume": d["amount"]}).set_index("time").astype(float)
            df = df[df.index >= pd.Timestamp(since, unit="ms", tz="UTC")].head(n)
        return [[int(t.timestamp() * 1000), *r] for t, r in zip(df.index, df[["open", "high", "low", "close", "volume"]].to_numpy().tolist())]

    def fetch_ticker(self, symbol):
        t = ticker(symbol)
        return {"symbol": symbol, "last": t["last"], "bid": None, "ask": None, "high": t["high"], "low": t["low"],
                "percentage": t["change_pct"], "quoteVolume": t["volume_quote"]}

    def fetch_tickers(self):
        out = {}
        for d in _get("ticker"):
            sym = d["symbol"].replace("_", "/")
            out[sym] = {"symbol": sym, "last": float(d["lastPrice"]), "percentage": float(d["riseFallRate"]) * 100,
                        "high": float(d["high24Price"]), "low": float(d["lower24Price"]),
                        "quoteVolume": float(d.get("amount24") or 0), "bid": float(d.get("bid1") or 0) or None,
                        "ask": float(d.get("ask1") or 0) or None}
        return out

    def load_markets(self):
        return {s: {"spot": True, "active": True, "base": s.split("/")[0], "quote": s.split("/")[1]}
                for s in self.fetch_tickers()}
