import json

import numpy as np
import pandas as pd
import pytest

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
    assert load_config().symbols == ["BTC/USDT"]
    assert load_config() == Config()  # config.json dhe parazgjedhjet në kod përputhen
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
    assert position_cost(Config(), 1000, 8) == pytest.approx(125)
    assert position_cost(Config(), 1000, 2) == pytest.approx(250)
    assert position_cost(Config(risk_per_trade_pct=0, position_size_pct=10), 1000, 8) == pytest.approx(100)
    assert stop_distance_pct(Config(), 100, 3) == 8
    assert stop_distance_pct(Config(stop_loss_atr=1.5), 100, 3) == pytest.approx(4.5)

    cfg = Config(state_file=str(tmp_path / "s.json"), stop_loss_atr=1.5, fee_pct=0)
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
        return self.NS(bid=self.bid, ask=self.ask, last=0.0)

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

    cfg = Config(exchange="mt5", state_file=str(tmp_path / "mt5.json"), fee_pct=0)
    real, data.make_exchange = data.make_exchange, lambda c, with_keys=False: ex
    try:
        assert data.connect(cfg) is ex
    finally:
        data.make_exchange = real
    assert cfg.quote == "USD" and "DEMO" in ex.account_label()   # monedha merret nga llogaria
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
    b = Broker(Config(state_file=str(tmp_path / "s.json"), fee_pct=0))
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
    b = Broker(Config(exchange="mt5", quote="USD", state_file=str(tmp_path / "m.json"), fee_pct=0), ex)
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
