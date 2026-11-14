import json

import numpy as np
import pandas as pd
import pytest

SIZE = dict(risk_per_trade_pct=1.0, position_size_pct=25.0)   # madhësia e supozuar në testet e llogaritjeve

from crypto_bot.backtest import backtest
from crypto_bot.bot import losses_in_row, run_cycle
from crypto_bot.broker import Broker
from crypto_bot.config import Config, load_config
from crypto_bot.data import fetch_candles, make_exchange, top_symbols
from crypto_bot.indicators import rsi
from crypto_bot.strategy import analyze, daily_trend, position_cost, score_frame, signal_frame, stop_distance_pct


def candles(closes, vol=100.0):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) * 1.001,
                         "low": np.minimum(opens, closes) * 0.999, "close": closes, "volume": vol}, index=idx)


def trend(n, start, rate, noise=0.004, seed=7):
    """Trend me zhurmë realiste (një trend krejt i lëmuar jep RSI 100 = i mbiblerë)."""
    steps = np.random.default_rng(seed).normal(rate, noise, n) if noise else np.full(n, rate)
    return start * np.exp(np.cumsum(steps))


def test_rsi_extremes():
    assert rsi(pd.Series(trend(60, 100, 0.01, 0))).iloc[-1] == 100
    assert rsi(pd.Series(trend(60, 100, -0.01, 0))).iloc[-1] < 1


def test_signals_follow_trend():
    cfg = Config(strategy="score", take_profit_pct=4, stop_loss_pct=2)
    up, down = candles(trend(600, 100, 0.002)), candles(trend(600, 100, -0.002))
    su, sd = score_frame(up)["score"].dropna(), score_frame(down)["score"].dropna()
    assert (su >= cfg.buy_threshold).mean() > 3 * (su <= cfg.sell_threshold).mean()
    assert (sd <= cfg.sell_threshold).mean() > 3 * (sd >= cfg.buy_threshold).mean()

    i = up.index.get_loc(su.idxmax())
    a = analyze(up.iloc[: i + 1], cfg, "X/USDT")
    assert a["signal"] == "BLI" and a["direction"] == "RRITJE" and a["score"] == round(su.max(), 1)
    assert a["plan"]["take_profit"] == pytest.approx(a["price"] * 1.04)
    assert a["plan"]["stop_loss"] == pytest.approx(a["price"] * 0.98)
    assert a["forecast"]["low"] < a["price"] < a["forecast"]["high"]
    j = down.index.get_loc(sd.idxmin())
    assert analyze(down.iloc[: j + 1], cfg)["signal"] == "SHIT"


def test_no_lookahead():
    df = candles(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 400)))
    full = score_frame(df)["score"]
    part = score_frame(df.iloc[:300])["score"]
    assert np.allclose(full.iloc[:300].dropna(), part.dropna())


def test_backtest_take_profit_and_stop_loss():
    always_in = dict(strategy="score", buy_threshold=-1000, sell_threshold=-2000, fee_pct=0)
    r = backtest(candles(trend(600, 100, 0.002)), Config(take_profit_pct=5, stop_loss_pct=50, **always_in))
    assert r["trades"] > 3
    assert all(t["reason"] == "take-profit" and t["pnl_pct"] == pytest.approx(5) for t in r["trade_list"][:-1])
    assert r["end"] > r["start"]

    r = backtest(candles(trend(600, 100, -0.002)), Config(take_profit_pct=50, stop_loss_pct=2, **always_in))
    assert r["trades"] > 3
    assert all(t["reason"] == "stop-loss" and t["pnl_pct"] == pytest.approx(-2) for t in r["trade_list"][:-1])
    assert r["end"] < r["start"] and r["max_drawdown_pct"] > 0

    # Pa sinjale nuk ka tregti.
    assert backtest(candles(trend(600, 100, 0.002)), Config(strategy="score", buy_threshold=1000))["trades"] == 0


def test_config_validation(tmp_path):
    with pytest.raises(ValueError):
        Config(stop_loss_pct=0).validate()
    p = tmp_path / "c.json"
    p.write_text('{"take_profit_pct": 7, "bogus": 1}')
    with pytest.raises(ValueError):
        load_config(p)
    p.write_text('{"take_profit_pct": 7}')
    assert load_config(p, stop_loss_pct=3).take_profit_pct == 7
    from dataclasses import replace

    from crypto_bot.config import FOCUS
    # config.json = parazgjedhjet në kod + mënyra Fokus (pesë tregjet).
    assert load_config() == replace(Config(), **FOCUS)
    assert load_config().symbols == ["BTC/USDT"]
    with pytest.raises(ValueError):
        Config(risk_per_trade_pct=3, max_total_risk_pct=2).validate()
    with pytest.raises(ValueError):
        Config(strategy="x").validate()


class FakeExchange:
    """Platformë e rreme: kthen qirinj të përgatitur, me kufi 100 për kërkesë."""

    def __init__(self, data, now_ms):
        self.data, self.now, self.last, self.spread = data, now_ms, {}, {}

    def parse_timeframe(self, tf):
        return 3600

    def milliseconds(self):
        return self.now

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        df = self.data[symbol]
        rows = [[int(t.timestamp() * 1000), *v] for t, v in zip(df.index, df.to_numpy().tolist())]
        return [r for r in rows if r[0] >= since][:100]

    def fetch_ticker(self, symbol):
        last = self.last.get(symbol, float(self.data[symbol]["close"].iloc[-2]))
        half = last * self.spread.get(symbol, 0.01) / 200
        return {"last": last, "bid": last - half, "ask": last + half}

    def load_markets(self):
        return {s: {"spot": True, "active": True, "quote": s.split("/")[1], "base": s.split("/")[0]} for s in self.t}

    def fetch_tickers(self):
        return self.t


def make_fake(closes_by_symbol):
    data = {s: candles(c) for s, c in closes_by_symbol.items()}
    last_open = next(iter(data.values())).index[-1]
    # "Tani" është në mes të qiririt të fundit → ai qiri është ende i hapur.
    return FakeExchange(data, int(last_open.timestamp() * 1000) + 1_800_000)


def test_fetch_candles_paginates_and_drops_open_candle():
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.001)})
    df = fetch_candles(ex, "BTC/USDT", "1h", 300)
    assert len(df) == 300
    assert df.index[-1] == ex.data["BTC/USDT"].index[-2]
    assert df.index.is_monotonic_increasing and df.index.is_unique


def test_top_symbols_filters_and_ranks():
    ex = make_fake({"BTC/USDT": [1, 2]})
    ex.t = {"BTC/USDT": {"quoteVolume": 5}, "ETH/USDT": {"quoteVolume": 9}, "USDC/USDT": {"quoteVolume": 99},
            "BTCUP/USDT": {"quoteVolume": 50}, "ETH/BTC": {"quoteVolume": 70}, "DOGE/USDT": {"quoteVolume": 1}}
    assert top_symbols(ex, "USDT", 2) == ["ETH/USDT", "BTC/USDT"]


def read_log(cfg):
    return [json.loads(line) for line in open(cfg.log_file, encoding="utf-8")]


def test_paper_bot_buys_then_exits(tmp_path):
    cfg = Config(symbols=["BTC/USDT", "ETH/USDT"], candles=300, state_file=str(tmp_path / "s.json"),
                 log_file=str(tmp_path / "d.jsonl"), strategy="score", max_daily_loss_pct=0,
                 risk_per_trade_pct=0, position_size_pct=10, take_profit_pct=4, stop_loss_pct=2, max_open_positions=1, fee_pct=0.1)
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.002), "ETH/USDT": trend(400, 100, -0.002)})
    broker = Broker(cfg)
    actions = run_cycle(ex, broker, cfg)
    assert [(a[0], a[1]) for a in actions] == [("BLI", "BTC/USDT")]
    pos = broker.positions["BTC/USDT"]
    assert broker.cash() == pytest.approx(900)
    assert pos["tp"] == pytest.approx(pos["entry"] * 1.04) and pos["sl"] == pytest.approx(pos["entry"] * 0.98)
    # Çdo vendim regjistrohet me arsyen: blerja e BTC dhe mosblerja e ETH.
    logged = {e["symbol"]: e["action"] for e in read_log(cfg)}
    assert logged["BTC/USDT"] == "BLI" and logged["ETH/USDT"] in ("PRIT", "SHIT") and len(logged) == 2
    assert all(e["reason"] for e in read_log(cfg))

    # Gjendja mbijeton rinisjen; çmimi prek take-profit → shitje me fitim.
    broker = Broker(cfg)
    ex.last["BTC/USDT"] = pos["entry"] * 1.05
    actions = run_cycle(ex, broker, cfg)
    assert len(actions) == 1 and actions[0][2]["reason"] == "take-profit" and actions[0][2]["pnl"] > 0
    # Pa ri-hyrje në të njëjtin qiri: sinjali i vjetër nuk përdoret dy herë.
    assert not broker.positions
    assert run_cycle(ex, broker, cfg) == [] and not broker.positions
    assert len(read_log(cfg)) == 3  # vendimet e të njëjtit qiri nuk përsëriten në regjistër


def test_stop_loss_and_daily_loss_halt(tmp_path):
    cfg = Config(symbols=["BTC/USDT", "ETH/USDT"], candles=300, state_file=str(tmp_path / "s.json"),
                 log_file=str(tmp_path / "d.jsonl"), strategy="score", position_size_pct=100, risk_per_trade_pct=0,
                 stop_loss_pct=6, max_daily_loss_pct=5, max_open_positions=1)
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.002), "ETH/USDT": trend(400, 100, 0.002)})
    broker = Broker(cfg)
    bought = run_cycle(ex, broker, cfg)[0][1]
    skipped = [e for e in read_log(cfg) if e["action"] == "ANASHKALO"]
    assert len(skipped) == 1 and "maksimal" in skipped[0]["reason"]
    ex.last[bought] = broker.positions[bought]["entry"] * 0.93
    actions = run_cycle(ex, broker, cfg)
    # Stop-loss shet me humbje; humbja ditore (−7%) kalon kufirin 5% → asnjë blerje e re sot.
    assert [(a[0], a[2]["reason"]) for a in actions] == [("SHIT", "stop-loss")]
    assert actions[0][2]["pnl_pct"] < -6 and not broker.positions
    other = next(s for s in cfg.symbols if s != bought)
    assert run_cycle(ex, broker, cfg) == []
    # Ditën tjetër kufiri rifillon nga kapitali i ri.
    broker.state["day"] = "2000-01-01"
    assert [(a[0], a[1]) for a in run_cycle(ex, broker, cfg)] == [("BLI", other)]


def breakout_series():
    """Rritje e ngadaltë, pastaj plato, thyerje lart dhe në fund rënie e fortë."""
    rng = np.random.default_rng(5)
    base = np.r_[trend(260, 100, 0.001, 0.002), np.full(60, np.nan)]
    plateau = base[259] * (1 + rng.normal(0, 0.001, 60))
    base[260:] = plateau
    up = plateau[-1] * np.cumprod(np.full(30, 1.01))
    down = up[-1] * np.cumprod(np.full(40, 0.985))
    return np.r_[base, up, down]


def test_breakout_strategy():
    cfg = Config(fee_pct=0, daily_trend_ema=0)  # breakout 55/20, pa take-profit, stop 8%
    assert cfg.strategy == "breakout"
    closes = breakout_series()
    df = candles(closes)
    s = signal_frame(df, cfg)
    assert not s["buy"].iloc[270:320].any()          # në plato nuk ka thyerje
    assert s["buy"].iloc[320:325].any()              # thyerja e majës jep sinjal blerjeje
    assert s["sell"].iloc[350:].any()                # rënia nën fundin e 20 qirinjve jep shitje
    a = analyze(df.iloc[:322], cfg, "X/USDT")
    assert a["signal"] == "BLI" and "theu majën" in a["signal_reason"]
    assert a["plan"]["take_profit"] is None and a["plan"]["stop_loss"] == pytest.approx(a["price"] * 0.92)
    assert "pa thyerje" in analyze(df.iloc[:300], cfg)["signal_reason"]

    r = backtest(df, cfg)
    assert r["trades"] == 1 and r["trade_list"][0]["pnl_pct"] > 10
    assert r["trade_list"][0]["reason"] in ("sinjal", "stop-loss")
    # Në trend rënës (nën EMA200) nuk blihet asnjëherë.
    assert backtest(candles(trend(600, 100, -0.002)), cfg)["trades"] == 0


def test_trailing_stop_moves_up(tmp_path):
    cfg = Config(state_file=str(tmp_path / "s.json"), trailing_stop_pct=3, take_profit_pct=50, stop_loss_pct=5,
                 risk_per_trade_pct=0)
    b = Broker(cfg)
    b.buy("BTC/USDT", 100, 1000)
    assert b.check_exit("BTC/USDT", 120) is None
    assert b.positions["BTC/USDT"]["sl"] == pytest.approx(116.4)
    assert b.check_exit("BTC/USDT", 116) == "stop-loss"


class FakeLive:
    """Platformë reale e rreme: regjistron urdhrat dhe kthen ekzekutimin."""

    def __init__(self):
        self.orders, self.free = [], 500.0

    def fetch_balance(self):
        return {"free": {"USDT": self.free}}

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.4f}"

    def market(self, symbol):
        return {"limits": {"cost": {"min": 10}, "amount": {"min": 0.0001}}}

    def create_order(self, symbol, type_, side, qty, price=None, params=None):
        self.orders.append((symbol, type_, side, qty))
        price = 101.0 if side == "buy" else 110.0
        self.free += -qty * price if side == "buy" else qty * price
        return {"id": "1", "filled": qty, "average": price, "cost": qty * price}


def test_live_broker_sends_orders_and_uses_fill_price(tmp_path):
    cfg = Config(state_file=str(tmp_path / "live.json"), position_size_pct=10, risk_per_trade_pct=0, fee_pct=0.1, take_profit_pct=4)
    ex = FakeLive()
    b = Broker(cfg, ex)
    pos = b.buy("BTC/USDT", 100.0, 500.0)
    assert ex.orders == [("BTC/USDT", "market", "buy", pytest.approx(0.4995))]
    assert pos["entry"] == 101.0 and pos["tp"] == pytest.approx(101 * 1.04)
    t = b.sell("BTC/USDT", 109.0, "take-profit")
    assert ex.orders[-1][2] == "sell" and t["exit"] == 110.0 and t["pnl"] > 0
    # Nën minimumin e platformës nuk dërgohet urdhër.
    assert b.buy("ETH/USDT", 100.0, 50.0) is None and len(ex.orders) == 2
    # Skedari i gjendjes reale nuk mund të hapet në simulim.
    with pytest.raises(RuntimeError):
        Broker(cfg)


def test_daily_trend_uses_only_closed_days():
    cfg = Config(daily_trend_ema=3)
    idx = pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC")
    #            d0   d1   d2   d3   d4   d5   d6   d7   d8   d9
    daily = pd.DataFrame({"close": [100, 100, 100, 100, 120, 121, 122, 90, 89, 88]}, index=idx)
    h4 = pd.date_range("2025-01-01", periods=60, freq="4h", tz="UTC")
    df = pd.DataFrame({"close": 1.0}, index=h4)
    up = daily_trend(df, cfg, daily)
    # Dita 4 (rritja) mbyllet në mesnatën e ditës 5: qiriri 20:00–24:00 i ditës 4 e sheh i pari.
    assert not up[pd.Timestamp("2025-01-05 16:00", tz="UTC")]
    assert up[pd.Timestamp("2025-01-05 20:00", tz="UTC")]
    # Rënia e ditës 7 njihet vetëm kur ajo ditë mbyllet.
    assert up[pd.Timestamp("2025-01-08 16:00", tz="UTC")]
    assert not up[pd.Timestamp("2025-01-08 20:00", tz="UTC")]
    # Pa qirinj ditorë të dhënë, ditët nxirren nga vetë qirinjtë; i fikur → gjithmonë True.
    assert daily_trend(candles(trend(600, 100, 0.002)), cfg).iloc[-1]
    assert not daily_trend(candles(trend(600, 100, -0.002)), cfg).iloc[-1]
    assert daily_trend(df, Config(daily_trend_ema=0)).all()
    # Filtri ndalon blerjet e breakout-it kur trendi ditor nuk njihet si rritës.
    b = candles(breakout_series())
    assert signal_frame(b, Config(daily_trend_ema=0))["buy"].any()
    assert not signal_frame(b, Config(daily_trend_ema=50))["buy"].any()
    assert "trendi ditor" in analyze(b.iloc[:322], Config(daily_trend_ema=50))["signal_reason"]


def test_risk_based_sizing_and_atr_stop(tmp_path):
    # Rrezik 1% me stop 8% → 12.5% e kapitalit; me stop 2% do të ishte 50%, por kufiri është 25%.
    assert position_cost(Config(**SIZE), 1000, 8) == pytest.approx(125)
    assert position_cost(Config(**SIZE), 1000, 2) == pytest.approx(250)
    assert position_cost(Config(risk_per_trade_pct=0, position_size_pct=10), 1000, 8) == pytest.approx(100)
    assert stop_distance_pct(Config(), 100, 3) == 8
    assert stop_distance_pct(Config(stop_loss_atr=1.5), 100, 3) == pytest.approx(4.5)

    cfg = Config(state_file=str(tmp_path / "s.json"), stop_loss_atr=1.5, fee_pct=0, **SIZE)
    b = Broker(cfg)
    pos = b.buy("BTC/USDT", 100, 1000, stop_pct=4.5)
    assert pos["sl"] == pytest.approx(95.5) and pos["cost"] == pytest.approx(1000 * 1 / 4.5)
    # Nëse preket stop-i, humbja është 1% e kapitalit.
    assert b.sell("BTC/USDT", 95.5, "stop-loss")["pnl"] == pytest.approx(-10)

    a = analyze(candles(breakout_series()).iloc[:322], Config(stop_loss_atr=2, daily_trend_ema=0))
    assert a["plan"]["stop_pct"] == pytest.approx(2 * a["indicators"]["atr"] / a["price"] * 100)


def test_spread_filter_and_losing_streak(tmp_path):
    cfg = Config(symbols=["BTC/USDT"], candles=300, state_file=str(tmp_path / "s.json"),
                 log_file=str(tmp_path / "d.jsonl"), strategy="score", max_spread_pct=0.5)
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.002)})
    ex.spread["BTC/USDT"] = 2.0
    broker = Broker(cfg)
    assert run_cycle(ex, broker, cfg) == []
    assert "diferenca" in read_log(cfg)[-1]["reason"]
    ex.spread["BTC/USDT"] = 0.1
    assert [a[0] for a in run_cycle(ex, broker, cfg)] == ["BLI"]

    now = pd.Timestamp.now(tz="UTC")
    today, ts = now.strftime("%Y-%m-%d"), now.timestamp()
    lose, win = {"closed": ts, "pnl": -1.0}, {"closed": ts, "pnl": 2.0}
    assert losses_in_row([win, lose, lose, lose], today) == 3
    assert losses_in_row([lose, lose, win, lose], today) == 1
    assert losses_in_row([{"closed": ts - 2 * 86400, "pnl": -1.0}] * 3, today) == 0
    # Tre humbje radhazi sot → asnjë blerje e re.
    cfg2 = Config(**{**cfg.__dict__, "state_file": str(tmp_path / "s2.json")})
    b2 = Broker(cfg2)
    b2.state["trades"] = [lose, lose, lose]
    assert run_cycle(ex, b2, cfg2) == [] and "humbje radhazi" in read_log(cfg2)[-1]["reason"]


def test_make_exchange_platforms():
    for name in ("mexc", "binance", "bybit"):
        ex = make_exchange(Config(exchange=name))
        assert ex.id == name and ex.options["defaultType"] == "spot"
    # Rrjeti i testimit: Binance dhe Bybit e kanë, MEXC jo.
    assert "testnet" in make_exchange(Config(exchange="binance", testnet=True)).urls["api"]["public"]
    assert "testnet" in str(make_exchange(Config(exchange="bybit", testnet=True)).urls["api"])
    with pytest.raises(ValueError):
        make_exchange(Config(exchange="mexc", testnet=True))
    with pytest.raises(ValueError):
        make_exchange(Config(exchange="nuk-ekziston"))


class FakeMT5:
    """Modul i rremë MetaTrader5 me një simbol BTCUSD (1 lot = 1 BTC, hapi 0.01)."""
    TIMEFRAME_H4, TIMEFRAME_D1 = "H4", "D1"
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL = 1, 0, 1
    ORDER_TIME_GTC, ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 0, 1, 2
    TRADE_RETCODE_DONE = 10009

    def __init__(self, df):
        from types import SimpleNamespace as NS
        self.NS, self.df, self.requests, self.open = NS, df, [], []
        self.info = NS(name="BTCUSD", visible=True, trade_contract_size=1.0, volume_step=0.01, volume_min=0.01,
                       digits=2, filling_mode=2, currency_base="BTC", currency_profit="USD")
        self.bid, self.ask = 99.95, 100.05

    def initialize(self, **kw):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return self.info if symbol == "BTCUSD" else None

    def symbol_select(self, symbol, on):
        return True

    def symbols_get(self):
        return [self.info]

    def symbol_info_tick(self, symbol):
        import time as _t
        return self.NS(bid=self.bid, ask=self.ask, last=0.0, time=_t.time() + 2 * 3600)   # serveri në UTC+2

    def copy_rates_from_pos(self, symbol, tf, start, count):
        d = self.df.iloc[: len(self.df) - start].tail(count)
        return [{"time": int(t.timestamp()), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
                 "tick_volume": r.volume} for t, r in zip(d.index, d.itertuples())]

    def account_info(self):
        return self.NS(currency="USD", margin_free=1000.0, equity=1000.0, balance=1000.0, login=1, server="Demo",
                       trade_mode=0)

    def positions_get(self, symbol=None):
        return list(self.open)

    def order_send(self, req):
        self.requests.append(req)
        if "position" in req:   # mbyllje e një pozicioni ekzistues
            self.open = [p for p in self.open if p.ticket != req["position"]]
        else:
            self.open.append(self.NS(ticket=7, volume=req["volume"], magic=req["magic"], type=req["type"]))
        return self.NS(retcode=self.TRADE_RETCODE_DONE, price=req["price"], volume=req["volume"], order=1, comment="")


def test_mt5_adapter(tmp_path):
    from crypto_bot.mt5 import MAGIC, MT5Exchange

    df = candles(trend(400, 100, 0.002))
    fake = FakeMT5(df)
    ex = MT5Exchange(fake)
    got = fetch_candles(ex, "BTCUSD", "4h", 300)
    assert len(got) == 300 and got.index[-1] == df.index[-2]      # qiriri i hapur anashkalohet
    assert got["close"].iloc[-1] == pytest.approx(df["close"].iloc[-2])
    assert top_symbols(ex, "USD", 5) == ["BTCUSD"]
    with pytest.raises(ValueError):
        ex.fetch_ticker("NUKKA")

    import crypto_bot.data as data

    cfg = Config(exchange="mt5", state_file=str(tmp_path / "mt5.json"), fee_pct=0, **SIZE)
    real, data.make_exchange = data.make_exchange, lambda c, with_keys=False: ex
    try:
        assert data.connect(cfg) is ex
    finally:
        data.make_exchange = real
    assert cfg.quote == "USD" and "DEMO" in ex.account_label()   # monedha merret nga llogaria
    assert cfg.data_tz == "Europe/Athens"                        # ora e serverit njihet vetë
    b = Broker(cfg, ex)
    pos = b.buy("BTCUSD", 100.0, 1000.0)                          # 1% rrezik / 8% stop = 125 USD → 1.25 lote
    buy = fake.requests[0]
    assert buy["volume"] == pytest.approx(1.25) and buy["price"] == 100.05 and buy["magic"] == MAGIC
    assert buy["sl"] == pytest.approx(92.0)                       # stop-i vendoset edhe në server
    assert pos["qty"] == pytest.approx(1.25) and pos["entry"] == 100.05
    fake.bid = 110.0
    t = b.sell("BTCUSD", 110.0, "sinjal")
    assert fake.requests[1]["position"] == 7 and fake.requests[1]["volume"] == pytest.approx(1.25)
    assert t["pnl"] == pytest.approx(1.25 * (110.0 - 100.05)) and not fake.open
    # Nëse stop-i në server e ka mbyllur tashmë pozicionin, roboti nuk dërgon urdhër të dytë.
    b.buy("BTCUSD", 100.0, 1000.0)
    fake.open.clear()
    b.sell("BTCUSD", 92.0, "stop-loss")
    assert len(fake.requests) == 3
    # Sasi nën minimumin e brokerit nuk blihet.
    assert Broker(Config(**{**cfg.__dict__, "state_file": str(tmp_path / "m2.json"), "position_size_pct": 0.01}),
                  ex).buy("BTCUSD", 100.0, 1000.0) is None


def test_prediction_journal(tmp_path):
    from datetime import timedelta

    from crypto_bot import journal

    path = tmp_path / "p.jsonl"
    closes = np.r_[np.full(300, 100.0), np.linspace(100, 90, 100)]   # e sheshtë, pastaj rënie në 90
    ex = make_fake({"BTC/USDT": closes})
    df = ex.data["BTC/USDT"]
    t0 = df.index[310].to_pydatetime()                              # çasti i parashikimit
    now = df.index[-1].to_pydatetime()
    price = float(df["open"].iloc[310])
    journal.add(path, "mexc-ai", "BTC/USDT", "rënie", 24, price, 74, target=97.0, now=t0)
    journal.add(path, "roboti", "BTC/USDT", "rritje", 24, price, now=t0)
    journal.add(path, "mexc-ai", "BTC/USDT", "renie", 24, 90.0, now=now)   # afati ende s'ka ardhur
    with pytest.raises(ValueError):
        journal.add(path, "x", "BTC/USDT", "anash", 24, 1.0)

    assert journal.check(path, ex, now=now + timedelta(minutes=30)) == 2
    a, b, c = journal.load(path)
    assert a["correct"] is True and a["target_hit"] is True
    assert a["result_price"] == pytest.approx(float(df["open"].iloc[334]))
    assert b["correct"] is False and b["target_hit"] is None
    assert c["correct"] is None
    assert journal.check(path, ex, now=now + timedelta(minutes=30)) == 0   # nuk rillogaritet
    text = journal.report(path)
    assert "mexc-ai" in text and "100%" in text and "0%" in text and "në pritje" in text
    assert "bosh" in journal.report(tmp_path / "nuk-ka.jsonl")


def test_cli_commands(tmp_path, monkeypatch, capsys):
    """Komandat e rreshtit të komandës, nga fillimi në fund, mbi një platformë të rreme."""
    import crypto_bot.__main__ as cli

    ex = make_fake({"BTC/USDT": trend(700, 100, 0.002), "ETH/USDT": trend(700, 100, -0.002)})
    ex.t = {"BTC/USDT": {"quoteVolume": 5}, "ETH/USDT": {"quoteVolume": 3}}
    monkeypatch.setattr(cli, "connect", lambda cfg, with_keys=False: ex)
    monkeypatch.chdir(tmp_path)
    cfgfile = tmp_path / "c.json"
    cfgfile.write_text(json.dumps({"candles": 400, "daily_trend_ema": 0}))
    base = ["--config", str(cfgfile)]

    cli.main(["analizo", "--symbol", "BTC/USDT,ETH/USDT", *base])
    out = capsys.readouterr().out
    assert "=== BTC/USDT" in out and "=== ETH/USDT" in out and "Plani:" in out
    cli.main(["skano", *base])
    out = capsys.readouterr().out
    assert "2 monedha" in out and "Blerje mbi" in out
    cli.main(["backtest", "--candles", "600", *base])
    assert "Backtest BTC/USDT" in capsys.readouterr().out
    cli.main(["ditar", "shto", "--drejtimi", "rënie", "--ore", "24", *base])
    assert "U shtua: mexc-ai parashikon rënie" in capsys.readouterr().out
    with pytest.raises(ValueError):
        cli.main(["ditar", "shto", *base])


def test_short_selling(tmp_path):
    down = candles(breakout_series()[::-1] * 1.0)     # pasqyra: rënie → plato → thyerje poshtë → ngritje
    off, on = Config(daily_trend_ema=0, fee_pct=0), Config(daily_trend_ema=0, fee_pct=0, allow_short=True)
    # I fikur si parazgjedhje: asnjë sinjal short.
    assert not signal_frame(down, off)["short"].any()
    s = signal_frame(down, on)
    assert s["short"].any() and s["cover"].any() and not s["buy"].any()
    i = 210 + int(np.argmax(s["short"].to_numpy()[210:]))   # sinjali i parë pas periudhës së ngrohjes
    assert s["short"].iloc[i]
    a = analyze(down.iloc[: i + 1], on, "X")
    assert a["signal"] == "SHORT" and a["side"] == -1 and "theu fundin" in a["signal_reason"]
    assert a["plan"]["stop_loss"] == pytest.approx(a["price"] * 1.08)      # stop-i i short-it është sipër

    r = backtest(down, on)
    shorts = [t for t in r["trade_list"] if t["side"] == "short"]
    assert shorts and shorts[0]["exit"] < shorts[0]["entry"] and shorts[0]["pnl"] > 0
    assert backtest(down, off)["trades"] == 0

    # Llogaritja në simulim: short 125 USDT në 100 → çmimi 90 jep +10%, çmimi 108 prek stop-in.
    b = Broker(Config(state_file=str(tmp_path / "s.json"), fee_pct=0, **SIZE))
    pos = b.buy("X/USDT", 100.0, 1000.0, side=-1)
    assert pos["side"] == -1 and pos["sl"] == pytest.approx(108) and b.cash() == pytest.approx(875)
    assert b.equity({"X/USDT": 90.0}) == pytest.approx(1012.5)
    assert b.check_exit("X/USDT", 95.0) is None and b.check_exit("X/USDT", 108.5) == "stop-loss"
    t = b.sell("X/USDT", 90.0, "sinjal")
    assert t["side"] == "short" and t["pnl"] == pytest.approx(12.5) and b.cash() == pytest.approx(1012.5)
    b.buy("X/USDT", 100.0, 1000.0, side=-1)
    assert b.sell("X/USDT", 108.0, "stop-loss")["pnl"] == pytest.approx(-10)   # humbja = 1% e kapitalit
    # Trailing për short: stop-i zbret pas çmimit.
    b2 = Broker(Config(state_file=str(tmp_path / "t.json"), trailing_stop_pct=3, stop_loss_pct=5, risk_per_trade_pct=0))
    b2.buy("X/USDT", 100.0, 1000.0, side=-1)
    assert b2.check_exit("X/USDT", 80.0) is None and b2.positions["X/USDT"]["sl"] == pytest.approx(82.4)
    assert b2.check_exit("X/USDT", 83.0) == "stop-loss"

    # Në platformë spot reale short-i refuzohet.
    with pytest.raises(RuntimeError):
        Broker(Config(state_file=str(tmp_path / "live.json")), FakeLive()).buy("BTC/USDT", 100.0, 500.0, side=-1)


def test_bot_opens_and_closes_short(tmp_path):
    closes = breakout_series()[::-1]
    cfg = Config(symbols=["BTC/USDT"], candles=300, state_file=str(tmp_path / "s.json"), allow_short=True,
                 log_file=str(tmp_path / "d.jsonl"), daily_trend_ema=0, max_daily_loss_pct=0)
    s = signal_frame(candles(closes), cfg)
    i = 210 + int(np.argmax(s["short"].to_numpy()[210:]))
    j = i + int(np.argmax(s["cover"].to_numpy()[i:]))
    assert s["short"].iloc[i] and s["cover"].iloc[j] and j > i
    ex = make_fake({"BTC/USDT": closes[: i + 2]})       # qiriri i fundit i mbyllur është ai i sinjalit short
    broker = Broker(cfg)
    assert [(a[0], a[1]) for a in run_cycle(ex, broker, cfg)] == [("SHORT", "BTC/USDT")]
    assert broker.positions["BTC/USDT"]["side"] == -1
    ex2 = make_fake({"BTC/USDT": closes[: j + 2]})      # më vonë: çmimi kthehet lart → mbyllje me sinjal
    ex2.last["BTC/USDT"] = float(closes[j])
    acts = run_cycle(ex2, broker, cfg)
    assert [a[0] for a in acts] == ["SHIT"] and acts[0][2]["side"] == "short" and not broker.positions
    assert [e["action"] for e in read_log(cfg) if e["action"] in ("SHORT", "SHIT")] == ["SHORT", "SHIT"]


def test_mt5_short(tmp_path):
    from crypto_bot.mt5 import MT5Exchange

    fake = FakeMT5(candles(trend(400, 100, 0.002)))
    ex = MT5Exchange(fake)
    b = Broker(Config(exchange="mt5", quote="USD", state_file=str(tmp_path / "m.json"), fee_pct=0, **SIZE), ex)
    pos = b.buy("BTCUSD", 100.0, 1000.0, side=-1)
    opened = fake.requests[0]
    assert opened["type"] == fake.ORDER_TYPE_SELL and opened["price"] == 99.95       # short hapet në bid
    assert opened["sl"] == pytest.approx(108.0) and "position" not in opened         # stop-i sipër, në server
    assert pos["side"] == -1 and pos["entry"] == 99.95
    fake.ask = 90.0
    t = b.sell("BTCUSD", 90.0, "sinjal")
    closed = fake.requests[1]
    assert closed["type"] == fake.ORDER_TYPE_BUY and closed["position"] == 7 and closed["price"] == 90.0
    assert t["pnl"] == pytest.approx(1.25 * (99.95 - 90.0)) and not fake.open


def random_walk_15m(days=60, seed=11):
    rng = np.random.default_rng(seed)
    n = days * 96
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.0015, n)))
    idx = pd.date_range("2026-01-05", periods=n, freq="15min", tz="UTC")
    opens = np.r_[closes[0], closes[:-1]]
    wick = np.abs(rng.normal(0, 0.0008, n))
    return pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) * (1 + wick),
                         "low": np.minimum(opens, closes) * (1 - wick), "close": closes, "volume": 100.0}, index=idx)


def test_find_engulfs_and_uk_clock():
    from crypto_bot.engulf import find_engulfs, uk_clock

    #            0      1      2      3      4
    o = np.array([10.0, 10.0, 9.0, 9.6, 10.6])
    c = np.array([10.0, 9.0, 9.6, 10.6, 9.4])    # 1 rënës; 2 rritës (nuk mbyllet mbi majën e 1); 3 e konfirmon
    h = np.array([10.1, 10.2, 9.7, 10.7, 10.8])
    l = np.array([9.9, 8.8, 8.9, 9.5, 9.3])
    bull, bull_low, bear, bear_high = find_engulfs(o, h, l, c, max_bars=3)
    assert bull.tolist() == [False, False, False, True, False] and bull_low[3] == pytest.approx(8.8)
    # Qiriri 4 mbyllet nën fundin e qiririt 3 (rritësi i fundit) → engulf bearish; zona shkon deri te maja 10.8.
    assert bear.tolist() == [False, False, False, False, True] and bear_high[4] == pytest.approx(10.8)
    # Konfirmimi shumë i vonë nuk vlen.
    assert not find_engulfs(o, h, l, c, max_bars=1)[0].any()

    # Ora UK: në verë (BST) 00:00 UTC është 01:00 në UK; në dimër 01:00 UTC është 01:00.
    idx = pd.DatetimeIndex(["2026-07-01 00:00", "2026-01-15 01:00"], tz="UTC")
    assert uk_clock(idx, Config())[1].tolist() == [1.0, 1.0]
    # Serveri MT5 (ora e Evropës Lindore) është gjithmonë 2 orë para UK: 03:00 e serverit = 01:00 UK.
    srv = pd.DatetimeIndex(["2026-07-01 03:00", "2026-01-15 03:00"], tz="UTC")
    assert uk_clock(srv, Config(data_tz="Europe/Athens"))[1].tolist() == [1.0, 1.0]


def test_engulf_strategy_rules():
    df = random_walk_15m()
    cfg = Config(strategy="engulf", timeframe="15m", allow_short=True, daily_trend_ema=0)
    s = signal_frame(df, cfg)
    assert s["buy"].sum() > 3 and s["short"].sum() > 3
    hour = (s.index.hour + s.index.minute / 60).to_numpy()      # janar–mars: UK = UTC
    for side, col, swept in ((1, "buy", "swept_low"), (-1, "short", "swept_high")):
        e = s[s[col]]
        assert (e["bias"] == side).all() and e[swept].all()                      # me bias-in dhe pas marrjes së nivelit
        assert ((e["close"] - e["stop_price"]) * side > 0).all()                 # stop-i në anën e duhur
        assert ((e["target_price"] - e["close"]) * side > 0).all()               # objektivi në drejtim të bias-it
        rr = (e["target_price"] - e["close"]).abs() / (e["close"] - e["stop_price"]).abs()
        assert (rr >= cfg.engulf_min_rr - 1e-9).all()
        assert ((hour[s[col].to_numpy()] >= 5) & (hour[s[col].to_numpy()] < 20)).all()   # vetëm pas sesionit
    assert not (s["sell"] | s["cover"]).any()
    # Pa short të lejuar nuk ka sinjale shitjeje; bias neutral nuk tregton (parazgjedhja).
    assert not signal_frame(df, Config(strategy="engulf", daily_trend_ema=0))["short"].any()
    assert not (s["buy"] | s["short"])[s["bias"] == 0].any()
    more = signal_frame(df, Config(strategy="engulf", allow_short=True, daily_trend_ema=0, engulf_neutral_mode=True))
    assert (more["buy"] | more["short"]).sum() > (s["buy"] | s["short"]).sum()
    strong = signal_frame(df, Config(strategy="engulf", allow_short=True, daily_trend_ema=0, engulf_require_strong=True))
    assert 0 < (strong["buy"] | strong["short"]).sum() < (s["buy"] | s["short"]).sum()

    # Pa të dhëna nga e ardhmja: sinjalet e së kaluarës nuk ndryshojnë kur shtohen qirinj të rinj.
    part = signal_frame(df.iloc[:4000], cfg)
    for col in ("buy", "short", "bias"):
        assert (part[col].to_numpy() == s[col].to_numpy()[:4000]).all()
    assert np.allclose(part["stop_price"].to_numpy(), s["stop_price"].to_numpy()[:4000], equal_nan=True)

    a = analyze(df.iloc[: s.index.get_loc(s[s["buy"]].index[-1]) + 1], cfg, "X")
    assert a["signal"] == "BLI" and "hyrje" in a["signal_reason"] and a["engulf"]["bias"] == 1
    assert a["plan"]["stop_loss"] < a["price"] < a["plan"]["take_profit"]


def test_engulf_backtest_and_daily_limit(tmp_path):
    df = random_walk_15m()
    kw = dict(strategy="engulf", timeframe="15m", allow_short=True, daily_trend_ema=0, fee_pct=0)
    r = backtest(df, Config(**kw))
    assert r["trades"] > 5
    for t in r["trade_list"][:-1]:
        assert t["reason"] in ("stop-loss", "take-profit")       # dalje vetëm me stop ose objektiv
    stops = [t for t in r["trade_list"] if t["reason"] == "stop-loss"]
    assert stops and all(t["r"] == pytest.approx(-1, abs=0.35) for t in stops)   # një stop kushton rreth 1R
    assert r["total_r"] == pytest.approx(sum(t["r"] for t in r["trade_list"]))
    # Kufiri i hyrjeve në ditë respektohet.
    one = backtest(df, Config(**kw, max_trades_per_day=1))
    per_day = pd.Series([t["entry_time"][:10] for t in one["trade_list"]]).value_counts()
    assert per_day.max() == 1 and one["trades"] <= r["trades"]

    # Brokeri përdor stop-in dhe objektivin e saktë të sinjalit; madhësia del nga largësia e stop-it.
    b = Broker(Config(state_file=str(tmp_path / "s.json"), fee_pct=0, position_size_pct=100))
    pos = b.buy("EUR/USDT", 1.1000, 1000.0, side=-1, stop_price=1.1055, take_price=1.0900)
    assert pos["sl"] == 1.1055 and pos["tp"] == 1.0900 and pos["cost"] == pytest.approx(1000.0)   # 1% / 0.5% > kufiri
    assert b.check_exit("EUR/USDT", 1.0890) == "take-profit"


def test_market_filter_and_portfolio(tmp_path):
    from crypto_bot.backtest import format_portfolio, portfolio_backtest
    from crypto_bot.bot import market_trend_up

    # Filtri i tregut: BTC në rënie ditore → roboti nuk blen, edhe kur monedha ka sinjal blerjeje.
    up, down = trend(400, 100, 0.002), trend(400, 100, -0.002)
    cfg = Config(symbols=["ETH/USDT"], candles=300, strategy="score", state_file=str(tmp_path / "s.json"),
                 log_file=str(tmp_path / "d.jsonl"), daily_trend_ema=3, market_filter_symbol="BTC/USDT")

    class DailyFake(FakeExchange):          # platforma e rreme jep ditorë të nxjerrë nga qirinjtë orarë
        def parse_timeframe(self, tf):
            return 86400 if tf == "1d" else 3600

        def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
            if timeframe != "1d":
                return super().fetch_ohlcv(symbol, timeframe, since, limit)
            d = self.data[symbol].resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                                      "close": "last", "volume": "sum"}).dropna()
            return [[int(t.timestamp() * 1000), *v] for t, v in zip(d.index, d.to_numpy().tolist())]

    def exchange(btc):
        base = make_fake({"ETH/USDT": up, "BTC/USDT": btc})
        ex = DailyFake(base.data, base.now)
        return ex

    assert market_trend_up(exchange(up), cfg) is True and market_trend_up(exchange(down), cfg) is False
    assert market_trend_up(exchange(up), Config(market_filter_symbol="")) is None
    assert run_cycle(exchange(down), Broker(cfg), cfg) == []
    assert "tregu i përgjithshëm" in read_log(cfg)[-1]["reason"]
    assert [a[0] for a in run_cycle(exchange(up), Broker(cfg), cfg)] == ["BLI"]

    # Prova e portofolit: kapital i përbashkët, kufi pozicionesh, filtër tregu.
    frames = {f"C{i}/USDT": (candles(trend(700, 100, 0.0, 0.01, seed=i)), None) for i in range(5)}   # pa drejtim, me luhatje
    pc = Config(strategy="score", daily_trend_ema=0, max_open_positions=2, fee_pct=0.1, market_filter_symbol="",
                stop_loss_pct=1.5)      # stop i ngushtë që të ketë shumë tregti të mbyllura
    r = portfolio_backtest(frames, pc)
    assert r["symbols"] == 5 and r["trades"] > 5 and r["end"] > 0
    assert r["months_up"] + r["months_flat"] + r["months_down"] == len(r["monthly"])
    t = pd.DataFrame(r["trade_list"])
    opened = pd.to_datetime(t["entry_time"]).to_numpy()[:, None]
    closed = pd.to_datetime(t["exit_time"]).to_numpy()[:, None]
    grid = pd.to_datetime(t["entry_time"]).to_numpy()[None, :]
    assert ((opened <= grid) & (closed > grid)).sum(axis=0).max() <= 2      # kurrë më shumë se 2 pozicione njëherësh
    assert "Portofoli" in format_portfolio(r, pc)
    # Me tregun në rënie filtri ndalon çdo blerje.
    pm = Config(strategy="score", daily_trend_ema=3, max_open_positions=2)
    blocked = portfolio_backtest({k: (v[0], None) for k, v in frames.items()}, pm, market=(candles(down), None))
    assert blocked["trades"] == 0


def test_momentum_strategy_and_rotation(tmp_path):
    from crypto_bot.backtest import portfolio_backtest
    from crypto_bot.bot import _rotate
    from crypto_bot.config import ACTIVE

    cfg = Config(strategy="momentum", allow_short=True, momentum_days=2, momentum_min_pct=5, momentum_ema=20,
                 daily_trend_ema=0, market_filter_symbol="", fee_pct=0)
    up, down, flat = candles(trend(400, 100, 0.003)), candles(trend(400, 100, -0.003)), candles(np.full(400, 100.0))
    a_up, a_dn, a_flat = (analyze(d, cfg, "X") for d in (up, down, flat))
    # Lëvizja 2-ditore (48 qirinj orarë) vendos drejtimin: lart, poshtë ose asgjë.
    assert a_up["signal"] == "BLI" and a_up["momentum"] > 5 and a_up["side"] == 1
    assert a_dn["signal"] == "SHORT" and a_dn["momentum"] < -5 and a_dn["side"] == -1
    assert a_flat["signal"] == "PRIT" and abs(a_flat["momentum"]) < 1e-9
    assert a_up["strength"] == pytest.approx(a_up["momentum"]) and a_dn["strength"] == pytest.approx(-a_dn["momentum"])
    assert "lëvizja 2-ditore" in a_up["signal_reason"]
    s = signal_frame(up, cfg)
    assert s["momentum"].iloc[-1] == pytest.approx((up["close"].iloc[-1] / up["close"].iloc[-49] - 1) * 100)
    assert not signal_frame(down, Config(strategy="momentum", momentum_days=2, daily_trend_ema=0))["short"].any()

    # Këmbimi: me vendet plot, pozicioni më i dobët i lë vendin një monedhe dukshëm më të fortë.
    bc = Config(**{**cfg.__dict__, "state_file": str(tmp_path / "s.json"), "log_file": "", "max_open_positions": 2})
    b = Broker(bc)
    b.buy("A/USDT", 100.0, 1000.0)
    b.buy("B/USDT", 100.0, 1000.0, side=-1)
    held = {"A/USDT": {"momentum": 6.0, "price": 101.0}, "B/USDT": {"momentum": -30.0, "price": 99.0}}
    acts = []
    assert not _rotate(b, bc, {"symbol": "C/USDT", "strength": 12.0}, held, {}, acts)        # jo mjaft më e fortë
    assert _rotate(b, bc, {"symbol": "C/USDT", "strength": 25.0}, held, {}, acts)            # 25 > 6 + 10
    assert list(b.positions) == ["B/USDT"] and "këmbim me C/USDT" in acts[0][2]["reason"]
    assert not _rotate(b, Config(**{**bc.__dict__, "rotate": False}), {"symbol": "D", "strength": 99.0}, held, {}, acts)

    # Drejtimi sipas tregut: me tregun në ngritje nuk hapen short-e, me tregun në rënie nuk hapen blerje.
    frames = {"UP/USDT": (up, None), "DN/USDT": (down, None)}
    pc = Config(**{**cfg.__dict__, "daily_trend_ema": 3, "market_filter_symbol": "BTC/USDT"})
    rising = portfolio_backtest(frames, pc, market=(up, None))
    falling = portfolio_backtest(frames, pc, market=(down, None))
    assert {t["side"] for t in rising["trade_list"]} <= {"long"} and rising["short_pnl"] == 0
    assert {t["side"] for t in falling["trade_list"]} <= {"short"} and falling["long_pnl"] == 0
    assert rising["end"] > rising["start"] and falling["end"] > falling["start"]
    both = portfolio_backtest(frames, Config(**{**cfg.__dict__}))
    assert both["end"] > max(rising["end"], falling["end"])            # pa filtër fiton në të dy anët
    assert ACTIVE["strategy"] == "momentum" and ACTIVE["allow_short"]


def test_bot_active_mode_follows_market(tmp_path):
    """Me BTC në rënie, roboti aktiv hap short te monedha që bie dhe nuk blen atë që ngjitet."""
    up, down = trend(400, 100, 0.003), trend(400, 100, -0.003)
    cfg = Config(strategy="momentum", allow_short=True, momentum_days=2, momentum_ema=20, candles=300,
                 symbols=["UP/USDT", "DN/USDT"], daily_trend_ema=3, market_filter_symbol="BTC/USDT",
                 state_file=str(tmp_path / "s.json"), log_file=str(tmp_path / "d.jsonl"))

    class DailyFake(FakeExchange):
        def parse_timeframe(self, tf):
            return 86400 if tf == "1d" else 3600

        def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
            if timeframe != "1d":
                return super().fetch_ohlcv(symbol, timeframe, since, limit)
            d = self.data[symbol].resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                                      "close": "last", "volume": "sum"}).dropna()
            return [[int(t.timestamp() * 1000), *v] for t, v in zip(d.index, d.to_numpy().tolist())]

    def exchange(btc):
        base = make_fake({"UP/USDT": up, "DN/USDT": down, "BTC/USDT": btc})
        return DailyFake(base.data, base.now)

    acts = run_cycle(exchange(down), Broker(cfg), cfg)
    assert [(a[0], a[1]) for a in acts] == [("SHORT", "DN/USDT")]
    assert any("pa" not in e["reason"] and e["action"] == "ANASHKALO" and "trend ditor rritës" in e["reason"]
               for e in read_log(cfg))
    cfg2 = Config(**{**cfg.__dict__, "state_file": str(tmp_path / "s2.json"), "log_file": str(tmp_path / "d2.jsonl")})
    acts = run_cycle(exchange(up), Broker(cfg2), cfg2)
    assert [(a[0], a[1]) for a in acts] == [("BLI", "UP/USDT")]
    assert any("pa shitje short" in e["reason"] for e in read_log(cfg2))


def test_live_chart_payload():
    from crypto_bot.live_chart import chart_payload

    df = candles(trend(300, 100, 0.002))
    opened = df.index[250] + pd.Timedelta(minutes=20)        # brenda qiririt 250
    p = chart_payload(df, "BTC/USDT", "1h", 20, levels=[("Hyrja", 101.0, "entry"), ("Pa çmim", None, "level")],
                      marks=[(opened, "long", "Ti: hyrje long"), (df.index[0] - pd.Timedelta(days=3), "exit", "jashtë")],
                      change_24h=-3.5)
    assert len(p["candles"]) == 300 and p["candles"][0][0] == int(df.index[0].timestamp())
    assert p["candles"][-1][4] == pytest.approx(df["close"].iloc[-1])
    assert len(p["ema"]) == 300 - 19                                   # mesatarja vetëm pasi ka histori
    assert p["levels"] == [{"name": "Hyrja", "price": 101.0, "kind": "entry"}]
    assert p["marks"] == [{"time": int(df.index[250].timestamp()), "kind": "long", "text": "Ti: hyrje long"}]
    assert p["change_24h"] == -3.5 and p["symbol"] == "BTC/USDT"
    json.dumps(p)                                                       # duhet të jetë JSON i pastër


def test_notifications(tmp_path, monkeypatch):
    from crypto_bot import notify

    sent = []

    class Resp:
        ok = True

        def json(self):
            return {"ok": True}

    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: sent.append((url, json)) or Resp())
    cfg = Config(alert_move_pct=5)
    # Pa Telegram: njoftimi ruhet vetëm në regjistër.
    e = notify.emit(cfg, "test", "BTC/USDT", "përshëndetje")
    assert e["telegram"] is False and not sent and notify.recent(cfg)[0]["text"] == "përshëndetje"
    # Me Telegram (skedari lokal): dërgohet edhe atje, te biseda e duhur.
    notify.telegram_save("123:ABC", "999")
    assert notify.telegram_settings() == ("123:ABC", "999")
    assert notify.emit(cfg, "test", "BTC/USDT", "tani")["telegram"] is True
    assert sent[-1][0].endswith("/bot123:ABC/sendMessage") and sent[-1][1]["chat_id"] == "999"

    # Alarmet e çmimit: kontrollohen, dërgohen një herë dhe hiqen.
    notify.add_alert(cfg, "BTC/USDT", "mbi", 80000)
    notify.add_alert(cfg, "ETH/USDT", "nen", 2000)
    with pytest.raises(ValueError):
        notify.add_alert(cfg, "ETH/USDT", "anash", 1)
    assert notify.check_price_alerts(cfg, {"BTC/USDT": 79000, "ETH/USDT": 2100}) == []
    fired = notify.check_price_alerts(cfg, {"BTC/USDT": 80500, "ETH/USDT": 2100})
    assert len(fired) == 1 and "BTC/USDT u ngjit mbi 80,000" in fired[0]["text"]
    assert [a["symbol"] for a in notify.load_alerts(cfg)] == ["ETH/USDT"]

    # Sinjalet e reja dhe lëvizjet e mëdha njoftohen një herë.
    state = {}
    a = lambda sig, price, t="t1": {"symbol": "SOL/USDT", "signal": sig, "price": price, "time": t, "signal_reason": "arsye"}
    assert len(notify.check_market(cfg, state, [a("PRIT", 100)])) == 0
    out = notify.check_market(cfg, state, [a("BLI", 101, "t2")])
    assert len(out) == 1 and "sinjal blerjeje te SOL/USDT" in out[0]["text"]
    assert notify.check_market(cfg, state, [a("BLI", 102, "t3")]) == []            # i njëjti sinjal nuk përsëritet
    move = notify.check_market(cfg, state, [a("BLI", 106, "t4")])
    assert len(move) == 1 and "+6.0%" in move[0]["text"]
    assert notify.check_market(cfg, state, [a("BLI", 107, "t5")]) == []            # baza u rivendos te 106
    assert "Roboti BLEU" in notify.trade_message("BLI", "X", {"entry": 1, "sl": 0.9, "tp": None}, "USDT")
    assert "Roboti mbylli short" in notify.trade_message(
        "SHIT", "X", {"side": "short", "exit": 1, "pnl": 2, "pnl_pct": 3, "reason": "sinjal"}, "USDT")


def test_bot_sends_trade_notifications(tmp_path):
    from crypto_bot import notify

    cfg = Config(symbols=["BTC/USDT"], candles=300, strategy="score", max_daily_loss_pct=0, market_filter_symbol="",
                 daily_trend_ema=0, state_file=str(tmp_path / "s.json"), log_file="")
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.002)})
    run_cycle(ex, Broker(cfg), cfg)
    texts = [e["text"] for e in notify.recent(cfg)]
    assert any("Roboti BLEU BTCUSDT" in t for t in texts) and any("sinjal blerjeje" in t for t in texts)


def test_market_overview():
    from crypto_bot.outlook import overview

    ex = make_fake({"UP/USDT": trend(700, 100, 0.004), "DN/USDT": trend(700, 100, -0.004)})
    ex.parse_timeframe = lambda tf: 14400        # qirinjtë e rremë trajtohen si 4-orësh
    df = overview(ex, Config(), ["UP/USDT", "DN/USDT", "NUK/USDT"], tickers={"UP/USDT": {"last": 5.0, "percentage": 1.5}})
    assert list(df["Monedha"]) == ["UP/USDT", "DN/USDT"]                # e renditur sipas lëvizjes 14-ditore
    up, dn = df.iloc[0], df.iloc[1]
    assert up["Çmimi"] == 5.0 and up["24 orë %"] == 1.5                 # nga ticker-i kur ka
    assert up["Gjendja"].startswith("rritje") and dn["Gjendja"].startswith("rënie")
    assert 0 <= up["Gjasat lart 24h %"] <= 100 and up["Raste"] > 0


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_futures_and_fear_greed(monkeypatch):
    from crypto_bot import futures, sentiment

    calls = []
    bodies = {
        "kline/BTC_USDT": {"time": [1700000000, 1700003600], "open": [1, 2], "high": [3, 4], "low": [0.5, 1.5],
                           "close": [2, 3], "amount": [10, 20]},
        "detail": {"contractSize": 0.0001},
        "ticker": {"lastPrice": 70000, "high24Price": 72000, "lower24Price": 69000, "riseFallRate": -0.0123,
                   "amount24": 2.9e9, "fundingRate": 0.0001, "fairPrice": 70001, "indexPrice": 70002, "holdVol": 600000000},
        "funding_rate/BTC_USDT": {"fundingRate": -0.0002, "nextSettleTime": 1794528000000, "collectCycle": 8},
        "depth/BTC_USDT": {"bids": [[69999, 300, 1], [69998, 100, 1]], "asks": [[70001, 100, 1]]},
    }

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "alternative.me" in url:
            return FakeResponse({"data": [{"value": "28", "value_classification": "Fear"},
                                          {"value": "35", "value_classification": "Fear"}]})
        return FakeResponse({"success": True, "data": bodies[url.rsplit("/contract/", 1)[1]]})

    monkeypatch.setattr(futures.requests, "get", fake_get)
    df = futures.candles("BTC/USDT", "1h", 10)
    assert list(df["close"]) == [2.0, 3.0] and str(df.index.tz) == "UTC" and calls[0][1]["interval"] == "Min60"
    t = futures.ticker("BTC/USDT")
    assert t["change_pct"] == pytest.approx(-1.23) and t["funding_pct"] == pytest.approx(0.01)
    assert t["open_interest_coins"] == pytest.approx(60000) and t["open_interest_quote"] == pytest.approx(4.2e9)
    assert futures.funding("BTC/USDT")["rate_pct"] == pytest.approx(-0.02)
    assert futures.depth("BTC/USDT")["buy_pct"] == pytest.approx(80)
    assert futures.contract("ETH/USDT:USDT") == "ETH_USDT"
    with pytest.raises(ValueError):
        futures.candles("BTC/USDT", "3h")
    fg = sentiment.fear_greed()
    assert fg == {"value": 28, "label": "Frikë", "yesterday": 35}


def test_trade_plan_from_signal():
    from crypto_bot.ui import _plan

    cfg = Config()
    short = {"signal": "SHORT", "signal_reason": "x", "plan": {"stop_loss": 108.0, "take_profit": None, "position_pct": 6.25}}
    p = _plan(short, cfg, 100.0, 2.0)
    assert p["side"] == -1 and p["stop"] == 108.0 and p["take"] == pytest.approx(84.0) and p["orient"]   # 2× rreziku
    assert p["entry_low"] == pytest.approx(99.5) and p["entry_high"] == pytest.approx(100.5) and p["rr"] == pytest.approx(2)
    long = {"signal": "BLI", "signal_reason": "x", "plan": {"stop_loss": 95.0, "take_profit": 110.0, "position_pct": 10}}
    p = _plan(long, cfg, 100.0, 1.0)
    assert p["take"] == 110.0 and not p["orient"] and p["rr"] == pytest.approx(2) and p["reward_pct"] == pytest.approx(10)
    assert _plan({"signal": "PRIT"}, cfg, 100.0, 1.0) is None


def test_chart_payload_zones_and_live():
    from crypto_bot.live_chart import chart_payload

    df = candles(trend(50, 100, 0.0))
    p = chart_payload(df, "BTCUSDT Perpetual", "1h", zones=[("Stop", 110.0, 100.0, "stop"), ("Pa", None, 1.0, "entry")],
                      stats={"Maja 24h": 5.0}, live_symbol="BTC_USDT")
    assert p["zones"] == [{"label": "Stop", "top": 110.0, "bottom": 100.0, "kind": "stop"}]
    assert p["step"] == 3600 and p["live_symbol"] == "BTC_USDT" and p["stats"] == {"Maja 24h": 5.0}


def test_analyst_approves_and_team_trades(tmp_path):
    from crypto_bot import analyst
    from crypto_bot.bot import CycleCache, run_team_cycle

    rows = [
        {"id": "a", "name": "A", "overrides": {"strategy": "momentum"}, "eligible": True,
         "train": {"return_pct": 10}, "test": {"return_pct": 3, "drawdown_pct": 5, "trades": 20}, "test_from": "x", "test_to": "y"},
        {"id": "b", "name": "B", "overrides": {"strategy": "breakout"}, "eligible": True,
         "train": {"return_pct": 5}, "test": {"return_pct": 8, "drawdown_pct": 5, "trades": 20}, "test_from": "x", "test_to": "y"},
        {"id": "c", "name": "C", "overrides": {}, "eligible": False,
         "train": {"return_pct": -5}, "test": {"return_pct": 9, "drawdown_pct": 5, "trades": 20}},
    ]
    rec = analyst.choose(rows)
    assert rec["action"] == "trade" and rec["approved"] == ["b", "a"] and rec["id"] == "b"
    # Një strategji që po humbet qartë në turne nuk miratohet.
    assert analyst.choose(rows, {"b": {"return_pct": -8, "trades": 20}})["approved"] == ["a"]
    pause = analyst.choose([rows[2]])
    assert pause["action"] == "pause" and pause["approved"] == []
    base = Config()
    assert analyst.apply_recommendation(base, pause).pause_entries
    assert analyst.apply_recommendation(base, rec).strategy == "breakout"
    assert analyst.apply_recommendation(base, None) is base

    # Vlerësimi me të dhëna sintetike: një trend i qartë rritës duhet të miratohet nga blerjet.
    frames = {f"C{i}/USDT": (candles(trend(1500, 100, 0.002, 0.01, seed=i)), None) for i in range(3)}
    frames["BTC/USDT"] = (candles(trend(1500, 100, 0.002, 0.01, seed=9)), None)
    res = analyst.evaluate({"1h": frames, "4h": frames}, Config(daily_trend_ema=0), test_days=20)
    by = {r["id"]: r for r in res}
    assert set(by) == {c["id"] for c in analyst.CANDIDATES}
    assert all("train" in r and "test" in r for r in res)
    assert by["momentum_blerje"]["train"]["return_pct"] > 0

    # Ekipi: çdo strategji ka pjesën e vet të kapitalit; vetëm të miratuarat hapin pozicione.
    cfg = Config(symbols=["UP/USDT"], candles=300, strategy="momentum", momentum_days=2, momentum_ema=20,
                 daily_trend_ema=0, market_filter_symbol="", state_file=str(tmp_path / "s.json"),
                 log_file=str(tmp_path / "d.jsonl"), scan_top_n=2, max_active=2)
    ex = make_fake({"UP/USDT": trend(400, 100, 0.003), "DN/USDT": trend(400, 100, -0.003)})
    ex.t = {"UP/USDT": {"quoteVolume": 9}, "DN/USDT": {"quoteVolume": 5}}
    real = analyst.CANDIDATES
    analyst.CANDIDATES = [{"id": "m", "name": "M", "overrides": {"strategy": "momentum", "timeframe": "4h",
                                                                   "allow_short": False, "momentum_days": 2.0}},
                          {"id": "n", "name": "N", "overrides": {"strategy": "momentum", "timeframe": "4h",
                                                                   "allow_short": False, "momentum_days": 2.0}}]
    try:
        team = run_team_cycle(ex, cfg, {"approved": ["m"], "name": "M"}, tournament=True)
        members = {m["id"]: m for m in team["members"]}
        assert set(members) == {"m"} and members["m"]["approved"]               # vetëm strategjitë aktive tregtojnë
        assert members["m"]["open"] == 1 and members["m"]["capital"] == pytest.approx(500)   # 1000 / max_active 2
        assert team["pool"] == pytest.approx(500)                                # pjesa tjetër pret në rezervë
        assert team["last_equity"] == pytest.approx(1000, rel=0.01)
        # "n" bëhet provizore: merr kapital nga rezerva dhe tregton me gjysmën e rrezikut.
        team2 = run_team_cycle(ex, cfg, {"approved": ["m"], "provisional": ["n"], "name": "M"}, tournament=False)
        m2 = {m["id"]: m for m in team2["members"]}
        assert m2["n"]["provisional"] and m2["n"]["capital"] == pytest.approx(500, rel=0.01) and team2["pool"] == pytest.approx(0, abs=1)
        # Kur "n" del nga lista dhe s'ka pozicione, kapitali i saj kthehet te rezerva.
        nfile = tmp_path / "s_ekip_n.json"
        st = json.loads(nfile.read_text())
        st["positions"] = {}
        nfile.write_text(json.dumps(st))
        team3 = run_team_cycle(ex, cfg, {"approved": ["m"], "name": "M"}, tournament=False)
        assert {m["id"] for m in team3["members"]} == {"m"} and not nfile.exists() and team3["pool"] > 0
    finally:
        analyst.CANDIDATES = real
    assert team["team"] and "UP/USDT" in team["positions"] and team["positions"]["UP/USDT"]["strategy"] == "M"
    assert json.loads((tmp_path / "s.json").read_text())["team"]
    with pytest.raises(RuntimeError):
        Broker(cfg)                                                           # përmbledhja nuk përdoret si portofol
    # Turneu provon edhe strategjinë e pamiratuar, me gjithë kapitalin.
    shadow = json.loads((tmp_path / "s_turne_n.json").read_text())
    assert len(shadow["positions"]) == 1
    assert any("[M]" in e["text"] for e in notify_recent(cfg))

    # Memoria e ciklit: kërkesat e njëjta shkojnë në platformë vetëm një herë.
    calls = []
    ex.fetch_ohlcv_orig = ex.fetch_ohlcv
    ex.fetch_ohlcv = lambda *a, **k: calls.append(a) or ex.fetch_ohlcv_orig(*a, **k)
    cc = CycleCache(ex)
    fetch_candles(cc, "UP/USDT", "1h", 100)
    n = len(calls)
    fetch_candles(cc, "UP/USDT", "1h", 100)
    assert len(calls) == n


def notify_recent(cfg):
    from crypto_bot import notify
    return notify.recent(cfg, 100)


def test_memory_records_and_daily_report(tmp_path):
    import time as _time

    from crypto_bot import memory

    cfg = Config(label="M")
    day = memory._day(_time.time())
    memory.log_equity(cfg, [("Ekipi", 1000.0, 0), ("M", 500.0, 0)])
    memory.log_equity(cfg, [("Ekipi", 1010.0, 1), ("M", 506.0, 1)])
    memory.log_trade(cfg, "BTC/USDT", {"opened": 1.0, "closed": _time.time(), "side": "long", "entry": 100, "exit": 110,
                                       "pnl": 10, "pnl_pct": 10, "reason": "sinjal"})
    memory.log_market(cfg, [("BTC/USDT", 100.0, 1.0), ("ETH/USDT", 10.0, 2.0)])
    memory.log_market(cfg, [("BTC/USDT", 102.0, 1.0), ("ETH/USDT", 9.0, 2.0)])
    memory.log_event(cfg, "vendim", "BTC/USDT", "BLI", 100.0, {"reason": "x"})
    r = memory.daily_report(cfg, day)
    team = next(x for x in r["strategies"] if x["name"] == "Ekipi")
    assert team["pct"] == pytest.approx(1.0) and r["trades"] == 1 and r["wins"] == 1 and r["entries"] == 1
    assert r["btc"] == pytest.approx(2.0) and r["best"][0]["symbol"] == "BTC/USDT" and r["worst"][0]["symbol"] == "ETH/USDT"
    text = memory.save_report(cfg, r)
    assert "Ekipi: 1000.00 → 1010.00 (+1.00%)" in text and "BTC gjatë ditës: +2.00%" in text
    assert memory.query(cfg, "SELECT COUNT(*) AS n FROM reports")["n"].iloc[0] == 1

    # Roboti shkruan vetë në kujtesë çdo vendim dhe çdo tregti të mbyllur.
    bc = Config(symbols=["BTC/USDT"], candles=300, strategy="score", daily_trend_ema=0, market_filter_symbol="",
                state_file=str(tmp_path / "s.json"), log_file=str(tmp_path / "d.jsonl"), take_profit_pct=4)
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.002)})
    b = Broker(bc)
    run_cycle(ex, b, bc)
    ex.last["BTC/USDT"] = b.positions["BTC/USDT"]["entry"] * 1.05
    run_cycle(ex, b, bc)
    ev = memory.query(bc, "SELECT action FROM events WHERE kind='vendim'")
    assert "BLI" in set(ev["action"])
    assert memory.query(bc, "SELECT reason FROM trades")["reason"].iloc[-1] == "take-profit"


def test_lab_creates_tests_and_promotes(tmp_path):
    import random
    import time as _time

    from crypto_bot import analyst, lab, memory

    rng = random.Random(1)
    for _ in range(50):
        o = lab.random_overrides(rng)
        cfg = analyst.candidate_config(Config(), {"overrides": o})       # çdo strategji e krijuar është e vlefshme
        assert cfg.strategy in lab.SPACE and set(o) <= lab.FIELDS and set(o) - {"strategy"} <= analyst.STRATEGY_FIELDS
        child = lab.mutate(o, rng)
        assert child["strategy"] == o["strategy"] and sum(child[k] != o[k] for k in o) <= 2
    assert lab.strategy_id({"a": 1, "b": 2}) == lab.strategy_id({"b": 2, "a": 1})
    assert "momentum 7d" in lab.describe(lab.complete({"strategy": "momentum", "momentum_days": 7.0}, rng))

    frames = {f"C{i}/USDT": (candles(trend(1500, 100, 0.002, 0.01, seed=i)), None) for i in range(3)}
    base = Config(daily_trend_ema=0, market_filter_symbol="", max_evolved=2)
    rows = lab.run_lab({"1h": frames, "4h": frames}, base, n=6, seed=3, test_days=20, log=lambda *_: None)
    saved = memory.strategies(base)
    assert len(rows) == 6 and len(saved) == 6
    turne = [s for s in saved if s["status"] == "turne"]
    assert 0 < len(turne) <= 2 and all(s["test"] > 0 and s["train"] > 0 for s in turne)
    # Të njëjtat strategji nuk provohen dy herë.
    assert not {r["id"] for r in lab.run_lab({"1h": frames, "4h": frames}, base, n=3, seed=3, test_days=20,
                                             log=lambda *_: None)} & {s["id"] for s in saved}
    # Kandidatët: turneu përfshin strategjitë e laboratorit, ekipi vetëm ato të ngritura.
    assert len(analyst.tournament_candidates(base)) == len(analyst.CANDIDATES) + len(turne)
    assert len(analyst.team_candidates(base)) == len(analyst.CANDIDATES)
    a, b2 = turne[0], (turne[1] if len(turne) > 1 else None)
    now = _time.time()
    fwd = {a["id"]: {"return_pct": 3.0, "trades": 20, "since": now - 20 * 86400}}
    if b2:
        fwd[b2["id"]] = {"return_pct": -8.0, "trades": 16, "since": now - 3 * 86400}
    changes = dict(lab.review_tournament(base, fwd, now))
    assert changes[a["name"]] == "ekip" and (not b2 or changes[b2["name"]] == "hedhur")
    assert {c["id"] for c in analyst.team_candidates(base)} >= {a["id"]}
    assert "evo_" in analyst.shadow_state_file(base, a)


def test_cache_fetches_only_missing_candles(tmp_path, monkeypatch):
    from crypto_bot import cache

    monkeypatch.setattr(cache, "DIR", str(tmp_path / "c"))
    ex = make_fake({"BTC/USDT": trend(400, 100, 0.001)})
    calls = []
    real = ex.fetch_ohlcv
    ex.fetch_ohlcv = lambda *a, **k: calls.append(a) or real(*a, **k)
    first = cache.candles(ex, "BTC/USDT", "1h", 300)
    n = len(calls)
    ex.now += 2 * 3600 * 1000                                  # kalojnë dy orë
    second = cache.candles(ex, "BTC/USDT", "1h", 300)
    assert len(first) == len(second) == 300 and second.index.is_unique
    assert len(calls) - n <= 2                                  # vetëm kërkesa të vogla për qirinjtë e rinj
    assert len(second) == 300


def test_radar_and_research_round(tmp_path, monkeypatch):
    from crypto_bot import analyst, cache, memory, radar, research

    monkeypatch.setattr(cache, "DIR", str(tmp_path / "c"))
    ex = make_fake({"UP/USDT": trend(400, 100, 0.003), "DN/USDT": trend(400, 100, -0.003),
                    "FLAT/USDT": trend(400, 100, 0.0, 0.0005), "BTC/USDT": trend(400, 100, 0.001)})
    ex.t = {s: {"quoteVolume": v, "last": 1.0, "percentage": 0.5}
            for s, v in [("UP/USDT", 9), ("DN/USDT", 8), ("FLAT/USDT", 7), ("BTC/USDT", 10)]}
    cfg = Config(lab_batch=4, max_evolved=2, daily_trend_ema=0, market_filter_symbol="")
    rd, entered = radar.update(ex, cfg)
    assert [r["symbol"] for r in rd["up"]][:1] == ["UP/USDT"] and [r["symbol"] for r in rd["down"]] == ["DN/USDT"]
    assert {r["symbol"] for r in entered["up"]} >= {"UP/USDT"}
    assert radar.update(ex, cfg)[1] == {"up": [], "down": []}            # pa ndryshime, pa njoftime të reja

    # 250 ditë qirinj orarë: mjaftojnë për periudhën e mësimit dhe 120 ditët e kontrollit.
    frames = {f"C{i}/USDT": (candles(trend(6000, 100, 0.0005, 0.006, seed=i)), None) for i in range(3)}
    monkeypatch.setattr(research, "_frames", lambda ex, cfg, syms: {"4h": frames, "1h": frames})
    st = research.research_once(ex, cfg, {}, log=lambda *_: None)
    assert st["tested_total"] == 4 and st["last_lab"] and st["last_rec"] and st["last_radar"]
    rec = analyst.load_recommendation(cfg)
    assert rec and "approved" in rec and rec["lab_tested"] == 4
    assert len(memory.strategies(cfg)) == 4 and len(memory.strategies(cfg, ["turne"])) <= 2
    # Rrethi tjetër menjëherë: asgjë nuk i ka ardhur radha, asgjë nuk provohet.
    st2 = research.research_once(ex, cfg, dict(st), log=lambda *_: None)
    assert st2["tested_total"] == 4
    later = research.research_once(ex, cfg, dict(st), log=lambda *_: None, now=st["last_lab"] + 11 * 60)
    assert later["tested_total"] == 8
    research._save(cfg, later)
    assert research.is_alive(cfg) and research.status(cfg)["tested_total"] == 8


def test_trailing_stop_in_portfolio_backtest():
    from crypto_bot.backtest import portfolio_backtest

    closes = np.r_[np.full(260, 100.0), np.linspace(100, 130, 30), np.linspace(130, 110, 30)]
    frames = {"X/USDT": (candles(closes), None)}
    base = dict(strategy="score", buy_threshold=-1000, sell_threshold=-2000, daily_trend_ema=0, market_filter_symbol="",
                risk_per_trade_pct=0, position_size_pct=100, fee_pct=0, stop_loss_pct=50, max_open_positions=1)
    plain = portfolio_backtest(frames, Config(**base))
    trail = portfolio_backtest(frames, Config(**base, trailing_stop_pct=5))
    t = trail["trade_list"][0]
    assert t["reason"] == "stop-loss" and t["exit"] == pytest.approx(130 * 0.95, rel=0.01)   # mbyllet 5% nën majën
    assert trail["end"] > plain["end"]


def test_telegram_username_and_errors(monkeypatch):
    from crypto_bot import notify

    sent = []

    class R:
        def __init__(self, body):
            self.body, self.ok = body, body.get("ok", False)

        def json(self):
            return self.body

    updates = {"ok": True, "result": [
        {"message": {"chat": {"id": 111, "username": "dikush"}, "from": {"username": "dikush"}}},
        {"message": {"chat": {"id": 777, "username": "Alber_Alb"}, "from": {"username": "Alber_Alb"}}}]}
    monkeypatch.setattr(notify.requests, "get", lambda url, timeout: R(updates))

    def post(url, json, timeout):
        sent.append(json)
        if json["chat_id"] == "403":
            return R({"ok": False, "error_code": 403, "description": "Forbidden: bot was blocked by the user"})
        return R({"ok": True})
    monkeypatch.setattr(notify.requests, "post", post)
    notify._resolved.clear()

    # Emri i llogarisë kthehet vetë në chat_id numerik nga mesazhet që i janë dërguar robotit.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:AA")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@alber_alb")
    assert notify.telegram_settings() == ("1:AA", "777")
    assert notify.telegram_check() == (True, "") and sent[-1]["chat_id"] == "777"
    assert notify.telegram_find_chat("1:AA") == "777" and notify.telegram_find_chat("1:AA", "dikush") == "111"
    # Emër që nuk gjendet: shpjegim i qartë në vend të dështimit pa arsye.
    notify._resolved.clear()
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "askush")
    ok, why = notify.telegram_check()
    assert not ok and "duhet të jetë numër" in why
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "403")
    ok, why = notify.telegram_check()
    assert not ok and "Start" in why and "blocked" in why


def test_focus_mode_risk_and_targets(tmp_path):
    from dataclasses import replace

    from crypto_bot import lab
    from crypto_bot.analyst import FOCUS_CANDIDATES, base_candidates, candidate_config
    from crypto_bot.config import FOCUS, MT5_SYMBOLS, display
    from crypto_bot.strategy import exit_prices, size_position

    cfg = replace(Config(), **FOCUS)
    assert base_candidates(cfg) is FOCUS_CANDIDATES and display("XAU/USDT") == "XAUUSD"
    assert cfg.symbols == ["BTC/USDT"] and MT5_SYMBOLS["BTC/USDT"] == "BTCUSD" and cfg.strategy == "mtf"
    # Objektivi si shumëfish i rrezikut: stop 0.5%, 2R → objektiv 1%.
    sl, tp = exit_prices(replace(cfg, take_profit_r=2.0), 100.0, 0.5, side=1)
    assert sl == pytest.approx(99.5) and tp == pytest.approx(101.0)
    # Me levë 10: stop 0.4% (si EURUSD) dhe rrezik 0.5% → pozicion 1.25× kapitali, marzh 12.5%.
    cost, qty, margin = size_position(replace(cfg, fee_pct=0), 1000, 1000, 1.10, 0.4)
    assert qty * 1.10 == pytest.approx(1250) and cost == pytest.approx(125)
    # Rreziku i përbashkët: kur pozicionet e hapura rrezikojnë tashmë 1.8%, i riu merr vetëm 0.2%.
    cost, qty, _ = size_position(replace(cfg, fee_pct=0), 1000, 1000, 1.10, 0.4, open_risk=18)
    assert qty * 1.10 * 0.004 == pytest.approx(2.0)
    assert size_position(cfg, 1000, 1000, 1.10, 0.4, open_risk=20) is None

    # Brokeri me levë: fitimi dhe humbja llogariten mbi gjithë pozicionin, kufiri 2% respektohet.
    b = Broker(replace(cfg, fee_pct=0, state_file=str(tmp_path / "f.json"), risk_per_trade_pct=1.0))
    p = b.buy("EUR/USDT", 1.10, 1000, stop_pct=0.4)
    assert p["cost"] == pytest.approx(250) and b.open_risk() == pytest.approx(10)
    assert b.equity({"EUR/USDT": 1.10 * 1.004}) == pytest.approx(1010)          # +0.4% × 2500 = +10
    b.buy("GBP/USDT", 1.30, 1000, stop_pct=0.4)
    assert b.open_risk() == pytest.approx(20)                                   # 2% e kapitalit
    assert b.buy("XAU/USDT", 3800, 1000, stop_pct=1.0) is None                  # s'ka më vend për rrezik
    t = b.sell("EUR/USDT", 1.10 * 0.996, "stop-loss")
    assert t["pnl"] == pytest.approx(-10)                                       # humbja = 1% e kapitalit

    # Laboratori në Fokus: stop me ATR dhe objektiv me R, pa përqindje fikse.
    import random
    rng = random.Random(2)
    for _ in range(20):
        o = lab.random_overrides(rng, cfg)
        assert o["stop_loss_atr"] > 0 and "take_profit_r" in o and "stop_loss_pct" not in o
        candidate_config(cfg, {"overrides": o})
    a = {"strategy": "momentum", "momentum_daily_filter": False, "daily_trend_ema": 20, "momentum_days": 7.0}
    assert lab.strategy_id(a) == lab.strategy_id({**a, "daily_trend_ema": 50})
    assert "2×ATR" in lab.describe(lab.complete({"strategy": "breakout"}, rng, cfg))


def test_trade_chart_image():
    from crypto_bot.snapshot import render

    png = render(candles(trend(120, 100, 0.001)), "EURUSD 1h · BLERJE (long)", 100.0, 99.0, 102.0, 1)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000


def test_provisional_approval():
    from crypto_bot import analyst

    def row(i, tr, te, re, n=20):
        return {"id": i, "name": i, "overrides": {}, "train": {"return_pct": tr}, "test": {"return_pct": te, "drawdown_pct": 5,
                "trades": n}, "recent": {"return_pct": re}, "eligible": tr > 0 and te > 0 and n >= 8,
                "provisional": not (tr > 0 and te > 0) and te > 0 and re >= 0 and n >= 8, "test_from": "a", "test_to": "b"}
    rows = [row("a", 5, 4, 1), row("b", -10, 9, 2), row("c", -10, 6, -1), row("d", -5, -2, 3), row("e", -3, 3, 0, n=4)]
    rec = analyst.choose(rows, max_active=3)
    assert rec["approved"] == ["a"] and rec["provisional"] == ["b"] and rec["action"] == "trade"
    only_prov = analyst.choose([rows[1]])
    assert only_prov["action"] == "trade" and only_prov["provisional"] == ["b"] and "Provizore" in only_prov["reason"]
    assert analyst.choose([rows[2], rows[3]])["action"] == "pause"
    cfg = Config(risk_per_trade_pct=0.5, provisional_risk=0.5)
    c = analyst.team_config(cfg, {"id": "b", "name": "B", "overrides": {}}, set(), provisional={"b"})
    assert c.risk_per_trade_pct == pytest.approx(0.25) and not c.pause_entries


def test_lab_learns_from_past_tests():
    import random

    from crypto_bot import lab, memory

    cfg = Config(focus=True)
    good = {"strategy": "momentum", "timeframe": "4h", "stop_loss_atr": 2.0}
    bad = {"strategy": "momentum", "timeframe": "15m", "stop_loss_atr": 1.0}
    for i in range(6):
        memory.upsert_strategy(cfg, f"g{i}", "g", {**good, "momentum_days": float(i)}, "laboratori", "provuar", 5, 20.0, 5, 30)
        memory.upsert_strategy(cfg, f"b{i}", "b", {**bad, "momentum_days": float(i)}, "laboratori", "provuar", -5, -25.0, 5, 30)
    stats = lab.learned(cfg)
    assert stats[("momentum", "timeframe", '"4h"')] == (pytest.approx(20.0), 6)
    rng = random.Random(0)
    picks = [lab._pick(rng, "momentum", "timeframe", ["15m", "1h", "4h", "1d"], stats) for _ in range(2000)]
    assert picks.count("4h") > 3 * picks.count("15m")               # mëson, por nuk e heq krejt alternativën
    assert picks.count("15m") > 0 and picks.count("1h") > 0
    ls = {(x["family"], x["param"]): x for x in lab.lessons(cfg)}
    assert ls[("momentum", "timeframe")]["best"] == "4h" and ls[("momentum", "timeframe")]["worst"] == "15m"


def test_signals_grouped_with_levels(monkeypatch):
    from crypto_bot import analyst, notify, research

    ex = make_fake({"UP/USDT": trend(700, 100, 0.003)})
    ex.parse_timeframe = lambda tf: 14400
    cfg = Config(focus=True, symbols=["UP/USDT"], daily_trend_ema=0, market_filter_symbol="")
    cands = [{"id": "a", "name": "A", "overrides": {"strategy": "momentum", "momentum_days": 2.0, "timeframe": "4h",
                                                     "stop_loss_atr": 2.0, "take_profit_r": 2.0}},
             {"id": "b", "name": "B", "overrides": {"strategy": "momentum", "momentum_days": 3.0, "timeframe": "4h",
                                                     "stop_loss_atr": 2.0}}]
    monkeypatch.setattr(research, "tournament_candidates", lambda c: cands)
    monkeypatch.setattr(research, "load_recommendation", lambda c: {"action": "trade", "approved": ["a"], "provisional": ["b"]})
    st = {}
    sent = research.send_signals(ex, cfg, st, log=lambda *_: None)
    assert len(sent) == 1                                                  # dy strategji, një mesazh
    text = sent[0]["text"]
    assert "BLERJE (long) UP/USDT" in text and "Stop-loss" in text and "Objektivi" in text
    assert "Strategjia: A (✅ e miratuar)" in text and "Pajtohen edhe: B" in text and "Rreziku 0.5%" in text
    assert research.send_signals(ex, cfg, st, log=lambda *_: None) == []   # i njëjti qiri nuk dërgohet dy herë


def _rates(start, n, step=3600, price=100.0):
    return [[(start + k * step) * 1000, price, price + 1, price - 1, price + 0.5, 10.0] for k in range(n)]


class _FakeMT5:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail, self.calls = rows, fail, []

    def fetch_closed_candles(self, name, tf, limit, closed_only=True):
        self.calls.append(name)
        if self.fail:
            raise RuntimeError("MT5 i mbyllur")
        return self.rows[-limit:]

    def server_tz(self, name):
        return "Europe/Athens"


class _FakeMexc:
    id = "mexc_futures"

    def __init__(self, rows):
        self.rows = rows

    def parse_timeframe(self, tf):
        return 3600

    def milliseconds(self):
        return self.rows[-1][0] + 2 * 3600 * 1000

    def fetch_ohlcv(self, symbol, tf, since=None, limit=1000):
        return [r for r in self.rows if r[0] >= since][:limit]


def test_hybrid_uses_mt5_history_in_utc_and_falls_back_to_mexc():
    from crypto_bot.data import fetch_candles
    from crypto_bot.hybrid import HybridExchange

    winter = 1736935200          # 2025-01-15 10:00 UTC
    mt5_rows = _rates(winter + 2 * 3600, 50)          # ora e serverit (UTC+2) e shkruar si UTC
    mexc_rows = _rates(winter, 30, price=200.0)
    ex = HybridExchange(_FakeMexc(mexc_rows), _FakeMT5(mt5_rows))
    df = fetch_candles(ex, "XAU/USDT", "1h", 40)
    assert len(df) == 40 and df["open"].iloc[0] == 100.0
    assert df.index[-1] == pd.Timestamp((winter + 49 * 3600) * 1e9, tz="UTC")   # 12:00 server → 10:00 UTC
    assert ex.source("XAU/USDT") == "mt5" and ex.source("BTC/USDT") == "mexc_futures"
    btc = fetch_candles(ex, "BTC/USDT", "1h", 20)                                 # BTCUSDT: gjithmonë MEXC
    assert btc["open"].iloc[-1] == 200.0 and ex.mt5.calls == ["XAUUSD"]
    down = HybridExchange(_FakeMexc(mexc_rows), _FakeMT5(fail=True))
    df = fetch_candles(down, "EUR/USDT", "1h", 20)
    assert len(df) == 20 and df["open"].iloc[-1] == 200.0 and "EUR/USDT" in down.errors


def test_focus_bars_and_yearly_returns():
    from crypto_bot.analyst import focus_bars, yearly

    bars = focus_bars(Config(history_years=3))
    assert bars["4h"] == 6570 and bars["1h"] == 26280 and bars["15m"] == 105120 and bars["30m"] == 52560 and bars["8h"] == 3285 and bars["1d"] >= 1095
    idx = pd.date_range("2023-01-01", periods=1100, freq="D", tz="UTC")
    eq = pd.Series(np.linspace(1000, 1300, 1100), index=idx)
    eq.iloc[-365:] = np.linspace(1300, 1200, 365)
    ys = yearly(eq, 3)
    assert len(ys) == 3 and ys[0]["return_pct"] < 0 and ys[1]["return_pct"] > 0 and ys[2]["return_pct"] > 0
    assert yearly(eq.iloc[-200:], 3) == []


def test_cache_keeps_sources_apart(tmp_path, monkeypatch):
    from crypto_bot import cache
    from crypto_bot.hybrid import HybridExchange

    monkeypatch.setattr(cache, "DIR", str(tmp_path))
    winter = 1736935200
    ex = HybridExchange(_FakeMexc(_rates(winter, 80, price=200.0)), _FakeMT5(_rates(winter, 80)), tz="UTC")
    cache.candles(ex, "XAU/USDT", "1h", 60)
    cache.candles(ex.mexc, "XAU/USDT", "1h", 60)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["mexc_futures_XAU_USDT_1h.pkl", "mt5_XAU_USDT_1h.pkl"]


def _btc15(n=7000, drift=0.0004, seed=3):
    rng = np.random.default_rng(seed)
    close = 60000 * np.exp(np.cumsum(drift + rng.normal(0, 0.002, n)))
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": np.r_[close[0], close[:-1]], "high": close * 1.001, "low": np.r_[close[0], close[:-1]] * 0.999,
                         "close": close, "volume": 100.0}, index=idx)


def test_mtf_trends_follow_the_market_and_never_look_ahead():
    from crypto_bot.mtf import trends, warmup_bars
    from crypto_bot.strategy import warmup

    cfg = Config(strategy="mtf", timeframe="15m", allow_short=True, mtf_ema=20, mtf_min_align=4)
    assert warmup(cfg) == warmup_bars(cfg) == 20 * 96 + 96
    up = _btc15()
    t = trends(up, cfg)
    assert list(t.columns) == ["t_1d", "t_8h", "t_4h", "t_30m"]
    assert (t.iloc[-1] == 1).all() and (t["t_1d"].iloc[:1900] == 0).all()     # ngritje e qartë; pa histori → 0
    down = _btc15(drift=-0.0004)
    assert (trends(down, cfg).iloc[-1] == -1).all()
    s = signal_frame(up, cfg)
    assert s["buy"].sum() > 0 and s["short"].sum() == 0 and not s["buy"].iloc[:warmup(cfg) - 96].any()
    # Sinjalet e së shkuarës nuk ndryshojnë kur vijnë qirinj të rinj (asnjë e dhënë nga e ardhmja).
    part = signal_frame(up.iloc[:5000], cfg)
    assert part["buy"].equals(s["buy"].iloc[:5000]) and part["t_4h"].equals(s["t_4h"].iloc[:5000])
    # Me qirinj 30-minutësh numërohen vetëm intervalet më të mëdha.
    half = up.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    assert list(trends(half, replace_cfg(cfg, timeframe="30m")).columns) == ["t_1d", "t_8h", "t_4h"]


def replace_cfg(cfg, **kw):
    from dataclasses import replace

    return replace(cfg, **kw)


def test_trend_report_every_15_minutes(tmp_path, monkeypatch):
    from crypto_bot import cache, research
    from crypto_bot.config import FOCUS

    cfg = replace_cfg(Config(), **{**FOCUS, "mtf_ema": 20, "candles": 3000, "notify_file": str(tmp_path / "n.jsonl"),
                                   "notify_telegram": False, "recommendation_file": str(tmp_path / "r.json"),
                                   "research_file": str(tmp_path / "res.json"), "memory_file": ""})
    df = _btc15()
    rep = research.trend_report(df, cfg, "BTC/USDT")
    assert rep["mtf"] == {"1d": 1, "8h": 1, "4h": 1, "30m": 1} and rep["side"] == 1
    assert "BTCUSDT" in rep["text"] and "1 ditë ⬆️" in rep["text"] and "Plani long" in rep["text"]
    assert rep["plan"]["stop"] < rep["price"] < rep["plan"]["target"]
    monkeypatch.setattr(cache, "candles", lambda ex, sym, tf, n: df)
    monkeypatch.setattr(research, "send_signals", lambda *a, **k: [])
    st = {"last_radar": 1e12, "last_rec": 1e12, "last_lab": 1e12}
    (tmp_path / "r.json").write_text('{"action": "pause"}')
    now = 1_800_000_000.0
    st = research.research_once(None, cfg, st, log=lambda *_: None, now=now)
    st = research.research_once(None, cfg, st, log=lambda *_: None, now=now + 60)       # i njëjti qiri: pa përsëritje
    lines = (tmp_path / "n.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["kind"] == "trend"
    assert st["trend"]["BTC/USDT"]["side"] == 1
