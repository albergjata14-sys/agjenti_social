"""Marrja e të dhënave të tregut nga platforma (përmes ccxt)."""
import os

import pandas as pd

STABLES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "EUR", "GBP", "USD", "PYUSD", "USDE", "USD1"}
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S")


def make_exchange(cfg, with_keys: bool = False):
    """Krijon lidhjen me platformën. Çelësat lexohen vetëm nga variablat e mjedisit."""
    import ccxt

    if not hasattr(ccxt, cfg.exchange):
        raise ValueError(f"Platforma '{cfg.exchange}' nuk mbështetet nga ccxt")
    params = {"enableRateLimit": True}
    if with_keys:
        key, secret = os.environ.get("CRYPTO_API_KEY"), os.environ.get("CRYPTO_API_SECRET")
        if not key or not secret:
            raise RuntimeError("Vendos CRYPTO_API_KEY dhe CRYPTO_API_SECRET si variabla mjedisi")
        params.update(apiKey=key, secret=secret)
        if os.environ.get("CRYPTO_API_PASSWORD"):
            params["password"] = os.environ["CRYPTO_API_PASSWORD"]
    exchange = getattr(ccxt, cfg.exchange)(params)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:  # ccxt nuk e lexon vetë proxy-n e sistemit
        exchange.https_proxy = proxy
    return exchange


def to_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time").astype(float)


def fetch_candles(exchange, symbol: str, timeframe: str, limit: int, closed_only: bool = True) -> pd.DataFrame:
    """Qirinjtë OHLCV. Qiriri i fundit (ende i hapur) hiqet që sinjalet të mos ndryshojnë."""
    step = exchange.parse_timeframe(timeframe) * 1000
    now = exchange.milliseconds()
    since = now - step * (limit + 1)
    rows = {}
    while since < now:  # faqo përpara në kohë; platformat kufizojnë qirinjtë për kërkesë
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.update((r[0], r) for r in batch)
        nxt = batch[-1][0] + step
        if nxt <= since:
            break
        since = nxt
    ordered = [rows[k] for k in sorted(rows)]
    if closed_only and ordered and ordered[-1][0] + step > now:
        ordered = ordered[:-1]
    return to_frame(ordered[-limit:])


def top_symbols(exchange, quote: str, n: int) -> list:
    """Monedhat më të tregtuara (sipas volumit 24h) kundrejt `quote`, pa stablecoin-e."""
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    ranked = []
    for sym, t in tickers.items():
        m = markets.get(sym)
        if not m or not m.get("spot") or not m.get("active", True) or m.get("quote") != quote:
            continue
        base = m["base"]
        if base in STABLES or any(base.endswith(x) and len(base) > len(x) + 1 for x in LEVERAGED):
            continue
        vol = t.get("quoteVolume") or (t.get("baseVolume") or 0) * (t.get("last") or 0)
        if vol:
            ranked.append((vol, sym))
    return [s for _, s in sorted(ranked, reverse=True)[:n]]
