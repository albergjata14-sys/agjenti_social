"""Chart Feeder: merr vetë grafikun nga MEXC (spot) dhe e etiketon. Nuk analizon asgjë."""
import json
import time
import urllib.parse
import urllib.request

import pandas as pd

from bots._base import Chart

API = "https://api.mexc.com/api/v3"
INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "4h": "4h", "1d": "1d", "1w": "1W"}
MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
      "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}
HIGHER = {"1m": "15m", "5m": "1h", "15m": "1h", "30m": "4h", "1h": "4h", "4h": "1d", "1d": "1w", "1w": "1w"}
STABLES = {"USDC", "USDE", "FDUSD", "TUSD", "DAI", "USDP", "PYUSD", "BUSD", "EUR", "USD1", "XUSD", "RLUSD"}
LEVERAGED = ("3L", "3S", "5L", "5S", "UP", "DOWN", "BULL", "BEAR")


def _get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "bots-chart-feeder"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def symbol(pair):
    """'BTC/USDT' / 'btcusdt' / 'BTC-USDT' → 'BTCUSDT'."""
    return pair.upper().replace("/", "").replace("-", "").replace("_", "").strip()


def pretty(pair):
    s = symbol(pair)
    return f"{s[:-4]}/USDT" if s.endswith("USDT") else s


def fetch_candles(pair, timeframe, limit=1000):
    """Qirinjtë e mbyllur më të fundit (deri në `limit`, me disa kërkesa nëse duhet)."""
    if timeframe not in INTERVAL:
        raise ValueError(f"Timeframe '{timeframe}' nuk mbështetet. Zgjidh: {', '.join(INTERVAL)}")
    step = MS[timeframe]
    rows = _get("klines", symbol=symbol(pair), interval=INTERVAL[timeframe], limit=500)   # MEXC jep max 500
    while rows and len(rows) < limit:
        # MEXC e shpërfill endTime pa startTime, ndaj faqet e vjetra kërkohen me të dyja.
        end = rows[0][0] - 1
        batch = _get("klines", symbol=symbol(pair), interval=INTERVAL[timeframe], limit=500,
                     startTime=end - 500 * step, endTime=end)
        older = [b for b in batch if b[0] < rows[0][0]]
        if not older:
            break                                   # nuk ka histori më të vjetër
        rows = older + rows
    if not rows:
        raise ValueError(f"MEXC nuk ktheu të dhëna për {pretty(pair)}")
    now = int(time.time() * 1000)
    rows = [r for r in rows if int(r[6]) < now]               # vetëm qirinj të mbyllur
    df = pd.DataFrame(rows, columns=["t", "open", "high", "low", "close", "volume", "ct", "qv"][:len(rows[0])])
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df[~df.index.duplicated()].sort_index().tail(limit)


def top_pairs(n=10):
    """Monedhat me volumin më të madh në MEXC (çiftet me USDT)."""
    out = []
    for t in _get("ticker/24hr"):
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in STABLES or base.endswith(LEVERAGED):
            continue
        out.append((float(t.get("quoteVolume") or 0), f"{base}/USDT"))
    return [p for _, p in sorted(out, reverse=True)[:n]]


def feed(pair, timeframe, candles=3000, fetch=fetch_candles):
    """Merr grafikun dhe grafikun e kohës më të gjatë. Kthen (Chart, mesazhi i botit)."""
    df = fetch(pair, timeframe, candles)
    htf = HIGHER[timeframe]
    htf_df = fetch(pair, htf, 500)
    chart = Chart(pretty(pair), timeframe, df, htf, htf_df)
    return chart, f"Chart ready\nPair: {chart.pair}\nTimeframe: {timeframe}\n→ Passing to Math Geometry"
