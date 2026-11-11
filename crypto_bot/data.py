"""Marrja e të dhënave të tregut nga platforma (përmes ccxt)."""
import os

import pandas as pd

STABLES = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDP", "EUR", "GBP", "USD", "PYUSD", "USDE", "USD1"}
LEVERAGED = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S")


def make_exchange(cfg, with_keys: bool = False):
    """Krijon lidhjen me platformën. Çelësat lexohen vetëm nga variablat e mjedisit."""
    if cfg.exchange.lower() in ("mt5", "metatrader5", "metatrader"):
        from .mt5 import MT5Exchange

        return MT5Exchange()  # llogaria (reale ose demo) zgjidhet në vetë terminalin MT5

    import ccxt

    if not hasattr(ccxt, cfg.exchange):
        raise ValueError(f"Platforma '{cfg.exchange}' nuk mbështetet nga ccxt")
    # Vetëm tregu spot: pa levë dhe pa kërkesa drejt serverëve të futures.
    params = {"enableRateLimit": True, "options": {"defaultType": "spot", "fetchMarkets": ["spot"]}}
    if cfg.exchange == "bybit":
        params["options"]["fetchMarkets"] = {"types": ["spot"]}
    if with_keys:
        key, secret = os.environ.get("CRYPTO_API_KEY"), os.environ.get("CRYPTO_API_SECRET")
        if not key or not secret:
            raise RuntimeError("Vendos CRYPTO_API_KEY dhe CRYPTO_API_SECRET si variabla mjedisi")
        params.update(apiKey=key, secret=secret)
        if os.environ.get("CRYPTO_API_PASSWORD"):
            params["password"] = os.environ["CRYPTO_API_PASSWORD"]
    exchange = getattr(ccxt, cfg.exchange)(params)
    if cfg.testnet:
        if not exchange.urls.get("test"):
            raise ValueError(f"'{cfg.exchange}' nuk ka rrjet testimi; përdor simulimin e robotit (pa --live)")
        exchange.set_sandbox_mode(True)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:  # ccxt nuk e lexon vetë proxy-n e sistemit
        exchange.https_proxy = proxy
    return exchange


def adapt_config(cfg, exchange):
    """Përshtat konfigurimin me platformën: në MT5 monedha bazë është ajo e llogarisë (p.sh. USD)."""
    if hasattr(exchange, "account_currency"):
        cfg.quote = exchange.account_currency()
    return cfg


def to_frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    return df.set_index("time").astype(float)


def fetch_candles(exchange, symbol: str, timeframe: str, limit: int, closed_only: bool = True) -> pd.DataFrame:
    """Qirinjtë OHLCV. Qiriri i fundit (ende i hapur) hiqet që sinjalet të mos ndryshojnë."""
    if hasattr(exchange, "fetch_closed_candles"):  # p.sh. MT5, që i jep vetë qirinjtë e mbyllur
        return to_frame(exchange.fetch_closed_candles(symbol, timeframe, limit, closed_only))
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


def fetch_daily(exchange, symbol: str, cfg, df: pd.DataFrame):
    """Qirinjtë ditorë për filtrin e trendit ditor, sa për të mbuluar gjithë `df`. None nëse s'duhen."""
    if not cfg.daily_trend_ema or exchange.parse_timeframe(cfg.timeframe) >= 86400 or df.empty:
        return None
    days = (df.index[-1] - df.index[0]).days + 3 * cfg.daily_trend_ema + 5
    return fetch_candles(exchange, symbol, "1d", days)


def spread_pct(exchange, symbol: str):
    """Diferenca mes çmimit të blerjes dhe shitjes në %, ose None kur platforma s'e jep."""
    t = exchange.fetch_ticker(symbol)
    bid, ask = t.get("bid"), t.get("ask")
    return (ask - bid) / ask * 100 if bid and ask else None


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
