"""Paneli i robotit të kriptove (Streamlit). Hapet më vete me crypto_app.py ose brenda app.py."""
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from . import analyst, futures, journal, memory, notify, radar, research, sentiment
from .backtest import backtest
from .bot import is_running, stop_file
from .broker import Broker
from .config import ACTIVE, FOCUS_SYMBOLS, display, load_config
from .data import fetch_candles, fetch_daily, make_exchange, top_symbols
from .live_chart import chart_payload, live_chart
from .outlook import _frame_states, overview
from .strategy import analyze

PLATFORMS = ["mexc_futures", "mexc", "binance", "bybit", "mt5"]
PLATFORM_NAMES = {"mexc_futures": "MEXC Futures (5 tregjet)", "mexc": "MEXC Spot", "binance": "Binance", "bybit": "Bybit",
                  "mt5": "MetaTrader 5"}
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
CHART_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
MARKETS = ["Futures", "Spot"]
STRATEGIES = ["breakout", "momentum", "score", "engulf"]
FAVORITES = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT"]
UI_CONFIG = "crypto_bot_ui_config.json"
REFRESH = 5    # sekonda mes rifreskimeve të grafikut të gjallë
# Dy mënyra pune. Aktive: hyn lart kur tregu (BTC) është në ngritje dhe poshtë kur është në rënie, te
# monedhat me lëvizjen më të fortë, dhe këmben pozicionet e dobëta. E kujdesshme: vetëm blerje në thyerje maje.
MODES = {"Aktive (lart dhe poshtë)": ACTIVE, "E kujdesshme": {}}
CSS = """
<style>
.cb-strip { display: flex; gap: 8px; overflow-x: auto; padding: 2px 0 10px; scrollbar-width: thin; }
.cb-tile { flex: 0 0 auto; min-width: 112px; border: 1px solid rgba(128, 128, 128, 0.28); border-radius: 12px;
           padding: 7px 12px; line-height: 1.25; }
.cb-tile .n { font-size: 12px; opacity: 0.7; }
.cb-tile .p { font-weight: 700; font-size: 16px; font-variant-numeric: tabular-nums; }
.cb-tile .c { font-size: 12px; font-variant-numeric: tabular-nums; }
.cb-tile.sel { border-color: currentColor; }
.cb-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px; }
.cb-chip { border: 1px solid rgba(128, 128, 128, 0.3); border-radius: 8px; padding: 3px 9px; font-size: 13px; }
.cb-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin: 4px 0 2px; gap: 2px; }
.cb-row { display: flex; justify-content: space-between; font-size: 13px; font-variant-numeric: tabular-nums; }
</style>
"""


# --- të dhënat (me memorie të shkurtër, që platforma të mos ngarkohet) -------------------------------
@st.cache_resource(show_spinner=False)
def _exchange(name: str):
    return make_exchange(load_config(exchange=name))


@st.cache_data(ttl=REFRESH, show_spinner=False)
def _candles(name: str, symbol: str, timeframe: str, candles: int):
    """Qirinjtë, përfshirë atë që është ende i hapur (për grafikun e gjallë)."""
    return fetch_candles(_exchange(name), symbol, timeframe, candles, closed_only=False)


@st.cache_data(ttl=15, show_spinner=False)
def _tickers(name: str) -> dict:
    try:
        return _exchange(name).fetch_tickers()
    except Exception:
        return {}


@st.cache_data(ttl=REFRESH, show_spinner=False)
def _fut_candles(symbol: str, timeframe: str, candles: int):
    return futures.candles(symbol, timeframe, candles)


@st.cache_data(ttl=REFRESH, show_spinner=False)
def _fut_ticker(symbol: str):
    return futures.ticker(symbol)


@st.cache_data(ttl=60, show_spinner=False)
def _fut_funding(symbol: str):
    return futures.funding(symbol)


@st.cache_data(ttl=10, show_spinner=False)
def _fut_depth(symbol: str):
    return futures.depth(symbol, 50)


@st.cache_data(ttl=120, show_spinner=False)
def _fut_all():
    try:
        return futures.all_tickers()
    except Exception:
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _fear_greed():
    try:
        return sentiment.fear_greed()
    except Exception:
        return None


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _daily(name: str, symbol: str, cfg_json: str, first, last):
    cfg = load_config(**json.loads(cfg_json))
    frame = pd.DataFrame(index=pd.DatetimeIndex([first, last]))
    return fetch_daily(_exchange(name), symbol, cfg, frame)


@st.cache_data(ttl=300, show_spinner=False)
def _overview(name: str, cfg_json: str, symbols: tuple):
    cfg = load_config(**json.loads(cfg_json))
    return overview(_exchange(name), cfg, list(symbols), _tickers(name))


@st.cache_data(ttl=3600, show_spinner=False)
def _top(name: str, quote: str, n: int):
    return top_symbols(_exchange(name), quote, n)


def _cfg_json(cfg) -> str:
    return json.dumps(asdict(cfg), sort_keys=True)


def _shift(cfg) -> pd.Timedelta:
    """Sa orë para UTC është ora e të dhënave (zero në bursa; ora e serverit në MT5)."""
    return pd.Timedelta(0) if cfg.data_tz in ("UTC", "auto") else pd.Timestamp.now(tz=cfg.data_tz).utcoffset()


def _closed(live: pd.DataFrame, cfg) -> pd.DataFrame:
    """Vetëm qirinjtë e mbyllur: sinjalet nuk llogariten kurrë mbi qiririn që është ende duke lëvizur."""
    step = live.index.to_series().diff().median()
    return live[live.index + step <= pd.Timestamp.now(tz="UTC") + _shift(cfg)]


def _read_state(cfg):
    p = Path(cfg.state_file)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (OSError, ValueError):
        return None     # roboti po e shkruan skedarin pikërisht tani; provohet në rifreskimin tjetër


def _manual_cfg(cfg):
    return replace(cfg, state_file="crypto_bot_manual.json", log_file="")


def _fmt(x) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.6g}"


def _change(tickers: dict, symbol: str):
    p = tickers.get(symbol, {}).get("percentage")
    return None if p is None else float(p)


# --- pjesët e ndërfaqes ----------------------------------------------------------------------------
def ticker_strip(tickers: dict, symbols: list, selected: str, fg=None):
    tiles = []
    if fg:
        diff = "" if fg["yesterday"] is None else f" · dje {fg['yesterday']}"
        tiles.append(f'<div class="cb-tile"><div class="n">Frika &amp; lakmia</div><div class="p">{fg["value"]} / 100</div>'
                     f'<div class="c">{fg["label"]}{diff}</div></div>')
    for sym in symbols:
        t = tickers.get(sym) or {}
        pct = t.get("percentage")
        arrow = "" if pct is None else ("▲ " if pct >= 0 else "▼ ")
        tiles.append(f'<div class="cb-tile{" sel" if sym == selected else ""}"><div class="n">{display(sym).split("/")[0]}</div>'
                     f'<div class="p">{_fmt(t.get("last"))}</div>'
                     f'<div class="c">{arrow}{"" if pct is None else f"{pct:+.2f}%"}</div></div>')
    st.markdown(CSS + f'<div class="cb-strip">{"".join(tiles)}</div>', unsafe_allow_html=True)
    if fg:
        st.caption("Indeksi i frikës dhe lakmisë: [alternative.me](https://alternative.me/crypto/fear-and-greed-index/)")


def _status(a, cfg, symbol, price, pos, who):
    """Një fjali e thjeshtë: çfarë po ndodh dhe çfarë pritet."""
    if pos:
        side = pos.get("side", 1)
        pnl = (price / pos["entry"] - 1) * 100 * side
        text = (f"**{'Ti ke' if who == 'Ti' else who + ' ka'} një pozicion "
                f"{'blerjeje (long)' if side > 0 else 'shitjeje (short)'} te {display(symbol)}** nga {_fmt(pos['entry'])}. "
                f"Tani është **{pnl:+.2f}%**. Mbyllet me humbje te {_fmt(pos['sl'])}"
                + (f" dhe me fitim te {_fmt(pos['tp'])}." if pos["tp"] else "; fitimi lihet i hapur derisa trendi të kthehet."))
        return (st.success if pnl >= 0 else st.warning)(text)
    if a["signal"] == "BLI":
        return st.success(f"**Sinjal blerjeje te {symbol}:** {a['signal_reason']}.")
    if a["signal"] == "SHORT":
        return st.success(f"**Sinjal shitjeje short te {symbol}:** {a['signal_reason']}.")
    if cfg.strategy != "breakout":
        return st.info(f"**Roboti pret.** {a['signal_reason']}.")
    gap = (a["buy_above"] / price - 1) * 100
    text = f"**Roboti pret.** Blen kur një qiri të mbyllet mbi **{_fmt(a['buy_above'])}** ({gap:+.1f}% nga çmimi tani)"
    if cfg.daily_trend_ema and not a["daily_up"]:
        text += " dhe trendi ditor të kthehet rritës"
    return st.info(text + ".")


def _marks(state, symbol: str, who: str, shift=pd.Timedelta(0)) -> list:
    """Shenjat e hyrjeve dhe daljeve të një portofoli për grafikun: [(koha, lloji, teksti)]."""
    out = []
    if not state:
        return out
    ts = lambda sec: pd.Timestamp(sec, unit="s", tz="UTC") + shift
    for t in state["trades"]:
        if t.get("symbol") != symbol:
            continue
        side = t.get("side", "long")
        if t.get("opened"):
            out.append((ts(t["opened"]), side, f"{who}: hyrje {side}"))
        out.append((ts(t["closed"]), "exit", f"{who}: dalje {t['pnl_pct']:+.1f}%"))
    p = state["positions"].get(symbol)
    if p:
        side = "long" if p.get("side", 1) > 0 else "short"
        out.append((ts(p["opened"]), side, f"{who}: hyrje {side}"))
    return out


def _toast_new(cfg):
    """Shfaq si njoftim të shkurtër çdo njoftim të ri që nga hera e fundit."""
    seen = st.session_state.get("seen_notify", time.time() - 60)
    fresh = [e for e in notify.recent(cfg, 20) if e.get("ts", 0) > seen]
    for e in fresh[:3][::-1]:
        st.toast(e["text"])
    if fresh:
        st.session_state["seen_notify"] = max(e["ts"] for e in fresh)
    elif "seen_notify" not in st.session_state:
        st.session_state["seen_notify"] = seen


def _countdown(ms: int) -> str:
    left = max(0, int(ms / 1000 - time.time()))
    return f"{left // 3600:02d}:{left % 3600 // 60:02d}:{left % 60:02d}"


def _plan(a, cfg, price, atr):
    """Plani i tregtimit nga sinjali i robotit: zona e hyrjes, stop-loss dhe objektivi.

    Stop-i është ai i strategjisë. Kur strategjia nuk ka objektiv fitimi (e lë fitimin të hapur), objektivi
    shfaqet si 2 herë rreziku (2R), vetëm si orientim. Kthen None kur nuk ka sinjal hyrjeje.
    """
    if a["signal"] not in ("BLI", "SHORT"):
        return None
    side = 1 if a["signal"] == "BLI" else -1
    stop = a["plan"]["stop_loss"]
    risk = abs(price - stop)
    take, orient = a["plan"]["take_profit"], False
    if not take:
        take, orient = price + side * 2 * risk, True
    half = 0.25 * (atr if atr and np.isfinite(atr) else risk * 0.1)
    return {"side": side, "entry_low": price - half, "entry_high": price + half, "stop": stop, "take": take,
            "orient": orient, "risk_pct": risk / price * 100, "reward_pct": abs(take - price) / price * 100,
            "rr": abs(take - price) / risk if risk else 0.0, "size_pct": a["plan"]["position_pct"]}


def _chips(items):
    st.markdown('<div class="cb-chips">' + "".join(f'<span class="cb-chip">{t}</span>' for t in items) + "</div>",
                unsafe_allow_html=True)


def _book_bar(buy_pct: float):
    st.markdown(f'<div class="cb-row"><span>▲ Blerës {buy_pct:.0f}%</span><span>Shitës {100 - buy_pct:.0f}% ▼</span></div>'
                f'<div class="cb-bar"><div style="width:{buy_pct:.1f}%;background:#2a78d6"></div>'
                f'<div style="flex:1;background:#eb6834"></div></div>', unsafe_allow_html=True)


@st.fragment(run_every=REFRESH)
def tab_chart(cfg, exchange, symbol):
    c = st.columns([1, 2])
    if cfg.exchange == "mexc_futures":      # mënyra Fokus: gjithmonë kontratat e MEXC
        market = "Futures"
        c[0].markdown(f"**{display(symbol)}**  \nKontrata MEXC")
    else:
        market = c[0].segmented_control("Tregu", MARKETS, key="chart_market", default="Futures") or "Futures"
    tf = c[1].segmented_control("Intervali", CHART_TIMEFRAMES, key="chart_tf",
                                default=cfg.timeframe if cfg.timeframe in CHART_TIMEFRAMES else "4h") or cfg.timeframe
    fut = market == "Futures" and cfg.exchange in ("mexc", "mexc_futures")
    live, tick, stats = None, None, {}
    if fut:
        try:
            live = _fut_candles(symbol, tf, 500)
            tick = _fut_ticker(symbol)
        except Exception as e:
            st.caption(f"Kontratat (Futures) nuk u lexuan ({e}); po tregohet tregu Spot.")
            fut = False
    if live is None:
        live = _candles(cfg.exchange, symbol, tf, 500)
    strat = _candles(cfg.exchange, symbol, cfg.timeframe, max(cfg.candles, 600))
    closed = _closed(strat, cfg)
    daily = _daily(cfg.exchange, symbol, _cfg_json(cfg), closed.index[0], closed.index[-1])
    a = analyze(closed, cfg, symbol, daily=daily)
    tickers = _tickers(cfg.exchange)
    price = float(live["close"].iloc[-1])
    state, mb = _read_state(cfg), Broker(_manual_cfg(cfg))
    # Stop-loss / fitimi i provave me dorë dhe alarmet e çmimit kontrollohen në çdo rifreskim.
    if symbol in mb.positions:
        reason = mb.check_exit(symbol, price)
        if reason:
            t = mb.sell(symbol, price, reason)
            notify.emit(cfg, "tregti", symbol, notify.trade_message("SHIT", symbol, t, cfg.quote).replace("Roboti", "Prova jote"))
    prices = {k: v.get("last") for k, v in tickers.items() if v.get("last")} | {symbol: price}
    notify.check_price_alerts(cfg, prices)
    _toast_new(cfg)

    robot_pos = (state or {}).get("positions", {}).get(symbol)
    my_pos = mb.positions.get(symbol)
    pos, who = (robot_pos, "Roboti") if robot_pos else (my_pos, "Ti") if my_pos else (None, "")
    _status(a, cfg, symbol, price, pos, who)

    t24 = tickers.get(symbol, {})
    change = tick["change_pct"] if tick else _change(tickers, symbol)
    fund = _safe(_fut_funding, symbol) if fut else None
    if tick:
        stats = {"Maja 24h": tick["high"], "Fundi 24h": tick["low"], "Volumi 24h": f"{tick['volume_quote'] / 1e6:,.0f} M",
                 "Financimi": f"{tick['funding_pct']:+.4f}%" + (f" · {_countdown(fund['next_ms'])}" if fund else ""),
                 "Kontrata të hapura": (f"{tick['open_interest_quote'] / 1e6:,.0f} M" if tick["open_interest_quote"] else None)}
    elif t24:
        stats = {"Maja 24h": t24.get("high"), "Fundi 24h": t24.get("low"),
                 "Volumi 24h": f"{(t24.get('quoteVolume') or 0) / 1e6:,.0f} M"}

    plan = None if pos else _plan(a, cfg, price, float(closed["close"].diff().abs().tail(14).mean()))
    zones = []
    if pos:
        levels = [("Hyrja", pos["entry"], "entry"), ("Stop-loss", pos["sl"], "stop")]
        if pos["tp"]:
            levels.append(("Fitimi (TP)", pos["tp"], "target"))
    elif plan:
        levels = []
        near_stop = plan["entry_low"] if plan["side"] > 0 else plan["entry_high"]
        near_take = plan["entry_high"] if plan["side"] > 0 else plan["entry_low"]
        zones = [(f"Stop-loss {_fmt(plan['stop'])}", plan["stop"], near_stop, "stop"),
                 ("", plan["entry_low"], plan["entry_high"], "entry"),
                 (f"Objektivi {_fmt(plan['take'])}", near_take, plan["take"], "target")]
    elif a["engulf"]:
        e = a["engulf"]
        levels = [("Maja e sesionit", e["session_high"], "level"), ("50% e sesionit", e["session_mid"], "level"),
                  ("Fundi i sesionit", e["session_low"], "level")]
    elif cfg.strategy == "breakout":
        levels = [("Blerje mbi", a["buy_above"], "level")] + (
            [("Short nën", a["short_below"], "level")] if cfg.allow_short else [])
    else:
        levels = []
    shift = _shift(cfg)
    marks = _marks(state, symbol, "Roboti", shift) + _marks(mb.state, symbol, "Ti", shift)
    ema_n = cfg.momentum_ema if cfg.strategy == "momentum" else cfg.trend_ema
    title = f"{display(symbol).replace('/', '')} {'Perpetual' if fut else 'Spot'}"
    live_chart(chart_payload(live, title, tf, ema_n, levels, marks, change, height=430, zones=zones, stats=stats,
                             live_symbol=futures.contract(symbol) if fut else None), key="live_chart")
    st.caption(f"Vija vjollcë: mesatarja EMA{ema_n}; butoni MA shfaq MA5/10/30/60. ▲ hyrje në blerje, ▼ hyrje në "
               f"short, ● dalje. Kutitë djathtas: e kuqërremta = deri te stop-loss, blu = deri te objektivi. Sinjalet "
               f"llogariten mbi qirinjtë e mbyllur {cfg.timeframe}.")

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            if plan:
                name = "Plani i blerjes (long)" if plan["side"] > 0 else "Plani i shitjes (short)"
                st.markdown(f"**{name}** · sipas robotit")
                st.markdown(
                    f"Zona e hyrjes **{_fmt(plan['entry_low'])} – {_fmt(plan['entry_high'])}**  \n"
                    f"Fitimi (TP) **{_fmt(plan['take'])}** ({plan['reward_pct']:+.2f}%)"
                    f"{' · orientues, 2× rreziku' if plan['orient'] else ''}  \n"
                    f"Stop-loss **{_fmt(plan['stop'])}** (−{plan['risk_pct']:.2f}%) · raporti fitim/rrezik {plan['rr']:.1f}  \n"
                    f"Madhësia sipas rrezikut: {plan['size_pct']:.3g}% e kapitalit")
                st.caption(f"Arsyeja: {a['signal_reason']}.")
                if st.button("Hap në demo me këtë plan", key="plan_demo", disabled=symbol in mb.positions, width="stretch"):
                    p = mb.buy(symbol, price, mb.equity({symbol: price}), side=plan["side"], stop_price=plan["stop"],
                               take_price=plan["take"])
                    if p:
                        notify.emit(cfg, "tregti", symbol, notify.trade_message("BLI" if plan["side"] > 0 else "SHORT", symbol,
                                                                                p, cfg.quote).replace("Roboti", "Prova jote"))
                    st.rerun(scope="fragment")
            elif pos:
                st.markdown(f"**Pozicioni i hapur** ({who})")
                st.markdown(f"Hyrja {_fmt(pos['entry'])} · Stop-loss {_fmt(pos['sl'])}"
                            + (f" · Fitimi {_fmt(pos['tp'])}" if pos["tp"] else ""))
            else:
                st.markdown("**Ende pa plan tregtimi**")
                st.caption(f"{a['signal_reason']}.")
    with right:
        with st.container(border=True):
            st.markdown("**Gjendja e tregut**")
            items = []
            mom, above, _, states, _ = _frame_states(strat if cfg.timeframe == "4h" else _candles(cfg.exchange, symbol, "4h", 600))
            m14 = a["momentum"] if a.get("momentum") is not None else float(mom.iloc[-1])
            items.append(f"{'▲' if m14 > 0 else '▼'} 14 ditë {m14:+.1f}%")
            items.append(f"{'▲ mbi' if above.iloc[-1] else '▼ nën'} mesataren 100")
            if fund:
                items.append(f"Financimi {fund['rate_pct']:+.4f}% ({'long-ët paguajnë' if fund['rate_pct'] > 0 else 'short-et paguajnë'})")
            fg = _fear_greed()
            if fg:
                items.append(f"Frika &amp; lakmia {fg['value']} · {fg['label']}")
            _chips(items)
            book = _safe(_fut_depth, symbol) if fut else None
            if book:
                _book_bar(book["buy_pct"])
                st.caption("Libri i urdhrave: sasia e urdhrave pranë çmimit. Ndryshon çdo sekondë dhe nuk tregon drejtimin.")

    st.markdown("**Provo vetë me para demo**")
    b = st.columns(3)
    for col, label, side in ((b[0], "🟢 Bli", 1), (b[1], "🔻 Shit short", -1)):
        if col.button(label, width="stretch", disabled=symbol in mb.positions, key=f"open{side}"):
            # Stop-i i provave me dorë është ai i strategjisë (sipas ATR në Fokus), jo një përqindje fikse.
            p = mb.buy(symbol, price, mb.equity({symbol: price}), a["plan"]["stop_pct"], side)
            if p:
                notify.emit(cfg, "tregti", symbol, notify.trade_message("BLI" if side > 0 else "SHORT", symbol, p,
                                                                        cfg.quote).replace("Roboti", "Prova jote"))
            st.rerun(scope="fragment")
    if b[2].button("Mbyll", width="stretch", disabled=symbol not in mb.positions, key="close"):
        t = mb.sell(symbol, price, "me dorë")
        notify.emit(cfg, "tregti", symbol, notify.trade_message("SHIT", symbol, t, cfg.quote).replace("Roboti", "Prova jote"))
        st.rerun(scope="fragment")
    done = mb.state["trades"]
    st.caption(f"Para demo të tuat: {mb.cash():,.2f} {cfg.quote} të lira · {len(done)} tregti të mbyllura, gjithsej "
               f"{sum(t['pnl'] for t in done):+.2f} {cfg.quote}. Stop-loss {a['plan']['stop_pct']:.2f}% larg"
               + (f" ({cfg.stop_loss_atr:g}×ATR)" if cfg.stop_loss_atr else "")
               + (f", objektivi {cfg.take_profit_r:g}R." if cfg.take_profit_r else
                  f", fitimi {cfg.take_profit_pct:g}% larg." if cfg.take_profit_pct else ", fitimi lihet i hapur.")
               + (f" Rreziku për tregti {cfg.risk_per_trade_pct:g}%, gjithsej deri në {cfg.max_total_risk_pct:g}%."
                  if cfg.max_total_risk_pct < 100 else ""))


def tab_market(cfg, exchange):
    st.caption("Ecuria e monedhave më të tregtuara: ndryshimet, lëvizja 14-ditore, gjendja e trendit dhe sinjali i robotit.")
    n = st.select_slider("Sa monedha", [10, 20, 30], 20)
    if st.button("Rifresko pamjen e tregut", type="primary") or st.session_state.get("market_n") == n:
        st.session_state["market_n"] = n
        with st.spinner("Duke parë tregun (deri në një minutë herën e parë)..."):
            symbols = tuple(cfg.symbols) if (cfg.focus or cfg.exchange == "mt5") else tuple(_top(cfg.exchange, cfg.quote, n))
            df = _overview(cfg.exchange, _cfg_json(replace(cfg, timeframe="4h") if cfg.timeframe != "4h" else cfg), symbols)
            fund = _fut_all()
            if fund and not df.empty:
                df = df.copy()
                df.insert(5, "Financimi %", [fund.get(s, {}).get("funding_pct") for s in df["Monedha"]])
    else:
        return st.info("Shtyp butonin për të parë pamjen e tregut.")
    if df.empty:
        return st.warning("Nuk u morën të dhëna.")
    m = st.columns(3)
    m[0].metric("Në ngritje 24 orë", f"{int((df['24 orë %'] > 0).sum())} nga {len(df)}")
    m[1].metric("Në trend rritës 14 ditë", int((df["Lëvizja 14 ditë %"] > 5).sum()))
    m[2].metric("Me sinjal robotit", int(df["Sinjali i robotit"].isin(["BLI", "SHORT"]).sum()))
    st.dataframe(
        df.drop(columns=["Arsyeja"]), width="stretch", hide_index=True,
        column_config={
            "Çmimi": st.column_config.NumberColumn(format="%.6g"),
            "24 orë %": st.column_config.NumberColumn(format="%+.2f"),
            "7 ditë %": st.column_config.NumberColumn(format="%+.1f"),
            "Lëvizja 14 ditë %": st.column_config.NumberColumn(format="%+.1f"),
            "Financimi %": st.column_config.NumberColumn(format="%+.4f", help="Norma e financimit të kontratës: pozitive = "
                                                         "long-ët paguajnë short-et (shumica janë long)."),
            "Gjasat lart 24h %": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f%%",
                help="Sa herë, në gjendje të ngjashme në të kaluarën, çmimi ishte më lart pas 24 orësh."),
            "Raste": st.column_config.NumberColumn(help="Sa raste historike qëndrojnë pas përqindjes"),
        })
    st.caption("“Gjasat lart 24h” nuk janë parashikim: janë sa herë në të kaluarën, në gjendje të ngjashme, çmimi "
               "ishte më lart pas 24 orësh. Në një provë jashtë mostrës (40 monedha, 2024–2026) kjo e qëlloi drejtimin "
               "51% të herëve, sa hedhja e një monedhe. Njëjtë si “AI Analysis” i MEXC, merre si informacion, jo si sinjal.")


def tab_alerts(cfg, symbol, price):
    raw = notify._raw_settings()
    st.markdown("**Njoftime në telefon (Telegram)**")
    if raw:
        token, chat = raw
        c = st.columns([2, 1])
        c[0].info("Tokeni dhe TELEGRAM_CHAT_ID janë vendosur." + ("" if notify.is_numeric_chat(chat) else
                  f" Kujdes: “{chat}” nuk është numër; Telegram-i kërkon chat_id numerik."))
        if c[1].button("Dërgo një mesazh provë", width="stretch"):
            ok, why = notify.telegram_check()
            (st.success if ok else st.error)("Mesazhi u dërgua. Shiko Telegram-in." if ok else why)
        if st.button("🔎 Gjej chat_id automatikisht"):
            try:
                found = notify.telegram_find_chat(token, None if notify.is_numeric_chat(chat) else chat) \
                    or notify.telegram_find_chat(token)
            except Exception as e:
                found, err = None, str(e)
            else:
                err = ""
            if found:
                st.success(f"chat_id yt është **{found}**. Te Streamlit Cloud → Settings → Secrets vendos:")
                st.code(f'TELEGRAM_CHAT_ID = "{found}"', language="toml")
                st.caption("Ruaje, prit pak që aplikacioni të riniset, pastaj provo prapë mesazhin.")
            else:
                st.warning("Nuk u gjet asnjë mesazh. Hap robotin tënd në Telegram, shtyp Start ose shkruaji "
                           "“përshëndetje”, pastaj shtyp prapë këtë buton." + (f" ({err})" if err else ""))
    else:
        st.info("Telegram-i nuk është lidhur ende. Njoftimet shfaqen vetëm këtu në panel.")
    with st.expander("Si ta lidhësh Telegram-in"):
        st.markdown(
            "1. Në Telegram hap **@BotFather**, shkruaj `/newbot` dhe ndiq hapat; merr një **token**.\n"
            "2. Hap robotin tënd të ri dhe shtyp **Start**.\n"
            "3. **Në kompjuter:** `python -m crypto_bot njoftime lidh` (të kërkon tokenin dhe gjen vetë bisedën).\n"
            "4. **Në Streamlit Cloud:** te aplikacioni → Settings → Secrets shto\n"
            "   `TELEGRAM_BOT_TOKEN = \"...\"` dhe `TELEGRAM_CHAT_ID = \"123456789\"` (numri, jo emri i llogarisë; "
            "e gjen me butonin “Gjej chat_id”).\n\n"
            "Mos e ngjit tokenin në biseda apo në kod: kushdo që e ka mund të dërgojë mesazhe në emër të robotit.")
    st.markdown("**Çfarë njoftohet**")
    st.markdown(f"- çdo hyrje dhe dalje e robotit\n- kur një monedhë e ndjekur merr sinjal të ri\n"
                f"- kur një monedhë lëviz {cfg.alert_move_pct:g}% nga njoftimi i fundit\n- alarmet e çmimit më poshtë")
    st.caption("Njoftimet automatike vijnë kur punon roboti (`nis`) ose `python -m crypto_bot njoftime` në kompjuter. "
               "Alarmet e çmimit kontrollohen edhe sa kohë është e hapur kjo faqe.")

    st.markdown("**Alarm çmimi**")
    with st.form("alarm", clear_on_submit=False):
        c = st.columns([2, 1, 2])
        sym = c[0].text_input("Monedha", symbol).strip().upper()
        way = c[1].selectbox("Kur", ["mbi", "nen"], format_func=lambda x: "ngjitet mbi" if x == "mbi" else "bie nën")
        lvl = c[2].number_input("Niveli", min_value=0.0, value=float(f"{price:.6g}"), format="%.6g")
        if st.form_submit_button("Shto alarmin"):
            notify.add_alert(cfg, sym, way, lvl)
            st.toast(f"Alarmi u shtua: {sym} {'mbi' if way == 'mbi' else 'nën'} {_fmt(lvl)}")
    alerts = notify.load_alerts(cfg)
    for i, al in enumerate(alerts):
        c = st.columns([4, 1])
        c[0].write(f"{al['symbol']} {'ngjitet mbi' if al['direction'] == 'mbi' else 'bie nën'} {_fmt(al['price'])}")
        if c[1].button("Fshi", key=f"del_alert_{i}"):
            notify.save_alerts(cfg, alerts[:i] + alerts[i + 1:])
            st.rerun()

    st.markdown("**Njoftimet e fundit**")
    feed = notify.recent(cfg, 40)
    if not feed:
        return st.caption("Ende asnjë njoftim.")
    d = pd.DataFrame(feed)
    d["Koha"] = pd.to_datetime(d["ts"], unit="s", utc=True).dt.tz_convert("Europe/Tirane").dt.strftime("%d %b %H:%M")
    d["Telegram"] = d["telegram"].map({True: "u dërgua", False: "–"})
    st.dataframe(d[["Koha", "text", "Telegram"]].rename(columns={"text": "Njoftimi"}), width="stretch", hide_index=True)


def _positions_table(positions: dict, tickers: dict) -> pd.DataFrame:
    rows = []
    for key, p in positions.items():
        sym = key.split("#")[0]
        price = float((tickers.get(sym) or {}).get("last") or p["entry"])   # një kërkesë për të gjitha çmimet
        side = p.get("side", 1)
        rows.append({**({"Strategjia": p["strategy"]} if p.get("strategy") else {}),
                     "Monedha": sym, "Drejtimi": "long" if side > 0 else "short", "Hyrja": p["entry"],
                     "Çmimi tani": price, "Fitim/humbje %": round((price / p["entry"] - 1) * 100 * side, 2),
                     "Vlera": round(Broker.value(p, price), 2), "Stop-loss": p["sl"],
                     "Fitimi (TP)": p["tp"] if p["tp"] else "i hapur"})
    return pd.DataFrame(rows)


@st.fragment(run_every=20)
def tab_robot(cfg, exchange):
    state = _read_state(cfg)
    running = is_running(cfg, state or {})
    team_mode = st.radio("Si punon roboti", ["Ekipi: analisti + tregtari", "Një strategji (rregullimet e mia)"],
                         horizontal=True, disabled=running, key="robot_mode",
                         help="Ekipi: analisti miraton strategjitë që fitojnë, tregtari i luan njëkohësisht me kapitalin "
                              "e ndarë, dhe turneu i provon të gjitha me para demo.") .startswith("Ekipi")
    whole = True if team_mode else st.toggle("Skano gjithë tregun (jo vetëm monedhën e zgjedhur)", True, disabled=running)
    c1, c2 = st.columns(2)
    if c1.button("▶ Nis robotin", disabled=running, width="stretch", type="primary"):
        # Roboti niset me pikërisht rregullimet që shihen në panel.
        Path(UI_CONFIG).write_text(json.dumps(asdict(replace(cfg, scan_market=whole)), indent=2))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open("crypto_bot_output.log", "a", encoding="utf-8") as out:
            subprocess.Popen([sys.executable, "-m", "crypto_bot", "nis", "--config", UI_CONFIG] + (["--ekip"] if team_mode else []),
                             stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
        st.toast("Roboti po niset; gjendja shfaqet pas ciklit të parë.")
    if c2.button("■ Ndalo robotin", disabled=not running, width="stretch"):
        stop_file(cfg).write_text("stop")
        st.toast("U kërkua ndalimi; roboti ndalet brenda pak sekondash.")
    if state is None:
        return st.info("Roboti nuk është nisur ende. Tregton vetë me para demo (virtuale) mbi çmime reale.")
    ago = time.time() - state.get("heartbeat", 0)
    table = _positions_table(state["positions"], _tickers(cfg.exchange))
    trades = state["trades"]
    equity = state["cash"] + (float(table["Vlera"].sum()) if len(table) else 0.0)
    (st.success if running else st.info)(
        f"**Roboti {'po punon' if running else 'është i ndalur'}.**"
        + (f" Kontrolli i fundit para {ago:.0f} sekondash." if running else "")
        + f" Ka {len(state['positions'])} pozicione të hapura dhe {len(trades)} tregti të mbyllura.")
    m = st.columns(3)
    m[0].metric("Kapitali demo", f"{equity:,.2f} {cfg.quote}", f"{(equity / cfg.paper_balance - 1) * 100:+.2f}% nga fillimi")
    m[1].metric("Fitimi i mbyllur", f"{sum(t['pnl'] for t in trades):+.2f} {cfg.quote}")
    m[2].metric("Tregti fituese", f"{sum(t['pnl'] > 0 for t in trades)} nga {len(trades)}" if trades else "–")
    if state.get("team"):
        st.markdown("**Ekipi i strategjive**")
        st.dataframe(pd.DataFrame([{
            "Strategjia": m["name"], "Miratuar nga analisti": "po" if m["approved"] else "jo",
            "Kapitali": m["capital"], "Tani": round(m["equity"], 2),
            "%": round((m["equity"] / m["capital"] - 1) * 100, 2), "Të hapura": m["open"], "Tregti": m["trades"]}
            for m in state["members"]]), width="stretch", hide_index=True,
            column_config={"%": st.column_config.NumberColumn(format="%+.2f"),
                           "Kapitali": st.column_config.NumberColumn(format="%.2f")})
    if len(table):
        st.markdown("**Pozicionet e hapura**")
        st.dataframe(table, width="stretch", hide_index=True,
                     column_config={"Fitim/humbje %": st.column_config.NumberColumn(format="%+.2f")})
    if trades:
        st.markdown("**Tregtitë e mbyllura**")
        t = pd.DataFrame(trades).iloc[::-1]
        t["closed"] = pd.to_datetime(t["closed"], unit="s").dt.strftime("%d %b %H:%M")
        cols = {"closed": "Mbyllur", "strategy": "Strategjia", "symbol": "Monedha", "side": "Drejtimi", "entry": "Hyrja", "exit": "Dalja",
                "reason": "Arsyeja", "pnl": "Fitim/humbje", "pnl_pct": "%"}
        st.dataframe(t[[c for c in cols if c in t]].rename(columns=cols), width="stretch", hide_index=True)
    log = Path(cfg.log_file)
    if cfg.log_file and log.exists():
        with st.expander("Pse vendosi kështu roboti (vendimet e fundit)"):
            d = pd.DataFrame([json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()[-200:]]).iloc[::-1]
            d["time"] = d["time"].str.slice(5, 16).str.replace("T", " ")
            if st.checkbox("Vetëm hyrjet dhe daljet", False):
                d = d[d["action"].isin(["BLI", "SHORT", "SHIT"])]
            cols = {"time": "Koha (UTC)", "symbol": "Monedha", "action": "Vendimi", "reason": "Arsyeja", "price": "Çmimi"}
            st.dataframe(d[[c for c in cols if c in d]].rename(columns=cols).head(60), width="stretch", hide_index=True)


def _ago(ts) -> str:
    if not ts:
        return "ende jo"
    m = int((time.time() - ts) // 60)
    return "tani" if m < 1 else f"para {m} min" if m < 120 else f"para {m // 60} orësh"


def _research_panel(cfg):
    """Gjendja e analistit të vazhdueshëm dhe radari i monedhave në trend."""
    rs = research.status(cfg)
    alive = bool(rs) and research.is_alive(cfg, rs)
    with st.container(border=True):
        st.markdown(f"**Analisti i vazhdueshëm** · {'🟢 po punon' if alive else '⚪ nuk po punon'}"
                    + (f" · {rs.get('status', '')}" if alive else ""))
        if rs:
            m = st.columns(3)
            m[0].metric("Strategji të provuara", rs.get("tested_total", 0))
            m[1].metric("Fituan në të dyja periudhat", rs.get("passed_total", 0))
            m[2].metric("Në turne tani", len(memory.strategies(cfg, ["turne"])) if Path(cfg.memory_file).exists() else 0)
            st.caption(f"Grupi i fundit i strategjive: {_ago(rs.get('last_lab'))} · rivlerësimi i ekipit: "
                       f"{_ago(rs.get('last_rec'))} · radari: {_ago(rs.get('last_radar'))}")
        if not alive:
            st.caption("Niset vetë bashkë me ekipin (skeda Roboti → Ekipi), ose me "
                       "`python -m crypto_bot analist --vazhdimisht`.")
            if st.button("Nis analistin e vazhdueshëm", key="start_research"):
                conf = cfg.state_file.replace(".json", "_analist_config.json")
                Path(conf).write_text(json.dumps(asdict(cfg), indent=2))
                with open("crypto_bot_analist.log", "a", encoding="utf-8") as out:
                    subprocess.Popen([sys.executable, "-m", "crypto_bot", "analist", "--vazhdimisht", "--config", conf],
                                     stdout=out, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                st.toast("Analisti po niset; radari i parë del brenda pak minutash.")
    rd = radar.load(cfg)
    if not rd:
        return
    st.markdown(f"**Radari: monedhat në trend tani** · {rd['scanned']} monedha të para {_ago(rd['ts'])}")
    c = st.columns(2)
    for col, side, title in ((c[0], "up", "📈 Në trend rritës"), (c[1], "down", "📉 Në trend rënës")):
        rows = rd[side][:8]
        col.markdown(title)
        if not rows:
            col.caption("Asnjë monedhë me trend të qartë.")
            continue
        col.dataframe(pd.DataFrame([{"Monedha": r["symbol"].split("/")[0], "14 ditë %": r["m14"], "7 ditë %": r["m7"],
                                     "24h %": r["change24"], "Volumi ×": r["volume_x"]} for r in rows]),
                      hide_index=True, width="stretch", column_config={
                          "14 ditë %": st.column_config.NumberColumn(format="%+.1f"),
                          "7 ditë %": st.column_config.NumberColumn(format="%+.1f"),
                          "24h %": st.column_config.NumberColumn(format="%+.2f"),
                          "Volumi ×": st.column_config.NumberColumn(help="Volumi i 24 orëve kundrejt mesatares ditore të javës")})
    if rd.get("extreme"):
        st.caption("Lëvizje ekstreme (mbi 80% në 14 ditë, shpesh monedha që po shemben), jashtë radarit: "
                   + ", ".join(x.split("/")[0] for x in rd["extreme"]))
    st.caption("Radari informon; tregtari tregton monedhat më të tregtuara (10, 20 ose 30, sipas strategjisë). "
               "Në 27 muaj të dhëna, kalimi nga 20 në 40 monedha i rriti rëniet e të tri strategjive kryesore.")


def tab_analyst(cfg, exchange):
    st.caption("Analisti provon disa strategji mbi monedhat më të tregtuara: si do të kishin dalë në një periudhë më "
               "të vjetër (mësimi) dhe në ditët e fundit (kontrolli). Miraton ato që fituan në të dyja; tregtari i "
               "luan njëkohësisht. Kur asnjë nuk fiton, rekomandon pushim.")
    _research_panel(cfg)
    rec = analyst.load_recommendation(cfg)
    c = st.columns([1, 1])
    n = c[0].select_slider("Sa monedha", [10, 20, 30], 20, key="analyst_n")
    if c[1].button("🧠 Analizo tani", type="primary", width="stretch"):
        with st.spinner("Analisti po shkarkon historinë dhe po provon strategjitë (1–3 minuta)..."):
            rec = analyst.analyze_market(exchange, cfg, n_symbols=n, log=lambda *_: None)
        notify.emit(cfg, "analist", "", "🧠 Analisti: " + ("pushim, asnjë strategji e miratuar" if rec["action"] == "pause"
                                                          else "miratoi " + ", ".join(rec["approved"])))
    if not rec:
        return st.info("Analisti nuk është nisur ende. Shtyp “Analizo tani”, ose nise robotin si ekip: analisti "
                       f"rifreskohet vetë çdo {cfg.analyst_hours:g} orë.")
    when = pd.Timestamp(rec["ts"], unit="s", tz="UTC").tz_convert("Europe/Tirane")
    (st.warning if rec["action"] == "pause" else st.success)(
        f"**{'Pushim' if rec['action'] == 'pause' else 'Strategji të miratuara: ' + str(len(rec['approved']))}** · "
        f"{rec['reason']}  \nAnalizuar më {when:%d %b %H:%M}, {rec['symbols']} monedha, kontrolli = {rec['test_days']} ditët e fundit.")
    fwd = rec.get("forward") or analyst.forward_results(cfg)
    fwd_now = analyst.forward_results(cfg)
    rows = []
    for r in rec["results"]:
        if "error" in r:
            continue
        f = fwd_now.get(r["id"]) or fwd.get(r["id"]) or {}
        rows.append({"Strategjia": r["name"], "Miratuar": "✅" if r["id"] in rec.get("approved", []) else "–",
                     "Mësimi %": r["train"]["return_pct"], "Kontrolli %": r["test"]["return_pct"],
                     "Rënia maks. %": r["test"]["drawdown_pct"], "Tregti": r["test"]["trades"],
                     "Turne live %": f.get("return_pct"), "Tregti live": f.get("trades")})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
        "Mësimi %": st.column_config.NumberColumn(format="%+.1f"),
        "Kontrolli %": st.column_config.NumberColumn(format="%+.1f"),
        "Turne live %": st.column_config.NumberColumn(format="%+.2f", help="Prova në kohë reale me para demo që nga nisja e turneut")})
    st.caption("“Turne live” mbushet kur roboti punon si ekip: çdo strategji provohet pa ndalur me 1000 USDT demo. "
               "Një strategji që humbet qartë në turne (nën −5% pas 15 tregtive) nuk miratohet më.")
    with st.expander("Pse miraton disa strategji dhe nuk zgjedh vetëm “më të mirën”?"):
        st.markdown("Në një provë jashtë mostrës (20 monedha, 14 muaj, vendim çdo 60 ditë):\n\n"
                    "| Mënyra | Fitimi |\n|---|---|\n"
                    "| Kalimi te strategjia që fitoi më shumë së fundmi | +2.6% |\n"
                    "| Të gjitha strategjitë e miratuara njëherësh | +12.7% |\n"
                    "| Të gjitha strategjitë pa filtër | +6.6% |\n\n"
                    "Strategjia që doli më mirë së fundmi shpesh nuk vazhdoi të dalë mirë. Heqja e atyre që humbasin "
                    "dhe ndarja e kapitalit mes të tjerave ndihmoi më shumë. As kjo nuk garanton fitim.")


SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def tab_memory(cfg):
    st.caption("Kujtesa e robotit: çdo vendim, tregti dhe kapitali i çdo strategjie ruhen ditë pas dite; çdo ditë "
               "shkruhet një raport dhe laboratori krijon strategji të reja.")
    if not cfg.memory_file or not Path(cfg.memory_file).exists():
        return st.info("Kujtesa është bosh. Mbushet kur punon roboti si ekip (`nis --ekip` ose `start_ekipi.bat`).")
    days = st.select_slider("Periudha", [1, 3, 7, 14, 30, 90], 7, format_func=lambda d: f"{d} ditë", key="mem_days")
    since = time.time() - days * 86400
    eq = memory.query(cfg, "SELECT ts, strategy, equity FROM equity WHERE ts>=? AND strategy NOT LIKE 'Turne%'", (since,))
    if len(eq):
        eq["koha"] = pd.to_datetime(eq["ts"], unit="s", utc=True).dt.tz_convert("Europe/Tirane")
        start = eq.sort_values("ts").groupby("strategy")["equity"].transform("first")
        eq["%"] = (eq["equity"] / start - 1) * 100
        order = ["Ekipi"] + sorted(s for s in eq["strategy"].unique() if s != "Ekipi")
        st.markdown("**Si ka ecur çdo strategji e ekipit (%)**")
        if eq["ts"].nunique() < 3:
            st.caption("Grafiku mbushet pas disa cikleve të robotit.")
        st.altair_chart(alt.Chart(eq).mark_line(strokeWidth=2).encode(
            x=alt.X("koha:T", title=None, axis=alt.Axis(grid=False, format="%d %b %H:%M")),
            y=alt.Y("%:Q", title="Ndryshimi nga fillimi i periudhës (%)", axis=alt.Axis(gridOpacity=0.25, format="+.1f")),
            color=alt.Color("strategy:N", title=None, sort=order, scale=alt.Scale(domain=order, range=SERIES[:len(order)]),
                            legend=alt.Legend(orient="bottom", columns=2, labelLimit=320)),
            tooltip=[alt.Tooltip("strategy:N", title="Strategjia"), alt.Tooltip("koha:T", title="Koha", format="%d %b %H:%M"),
                     alt.Tooltip("%:Q", format="+.2f"), alt.Tooltip("equity:Q", title="Kapitali", format=",.2f")],
        ).properties(height=300), width="stretch")
    reports = memory.query(cfg, "SELECT day, text FROM reports ORDER BY day DESC LIMIT 30")
    st.markdown("**Raportet ditore**")
    if not len(reports):
        st.caption("Raporti i parë shkruhet kur mbaron dita e parë e plotë (mesnata UTC).")
    for _, r in reports.iterrows():
        with st.expander(f"📔 {r['day']}"):
            st.text(r["text"])
    tr = memory.query(cfg, "SELECT ts_close, strategy, symbol, side, entry, exit, pnl, pnl_pct, reason FROM trades "
                           "WHERE ts_close>=? ORDER BY ts_close DESC", (since,))
    m = st.columns(3)
    team_tr = tr[~tr["strategy"].str.startswith("Turne")]
    m[0].metric("Tregti të ekipit", len(team_tr))
    m[1].metric("Fituese", f"{int((team_tr['pnl'] > 0).sum())}" if len(team_tr) else "–")
    m[2].metric("Fitimi i mbyllur", f"{team_tr['pnl'].sum():+.2f} {cfg.quote}" if len(team_tr) else "–")
    if len(tr):
        with st.expander(f"Të gjitha tregtitë e periudhës ({len(tr)}, përfshirë turneun)"):
            tr["ts_close"] = pd.to_datetime(tr["ts_close"], unit="s", utc=True).dt.tz_convert("Europe/Tirane").dt.strftime("%d %b %H:%M")
            st.dataframe(tr.rename(columns={"ts_close": "Mbyllur", "strategy": "Strategjia", "symbol": "Monedha",
                                            "side": "Drejtimi", "entry": "Hyrja", "exit": "Dalja", "pnl": "Fitim/humbje",
                                            "pnl_pct": "%", "reason": "Arsyeja"}), width="stretch", hide_index=True)
    st.markdown("**Laboratori: strategjitë e reja**")
    labs = memory.strategies(cfg)
    if not labs:
        return st.caption(f"Laboratori nis vetë çdo {cfg.lab_hours:g} orë kur punon ekipi, ose me "
                          "`python -m crypto_bot laboratori`.")
    fwd = analyst.forward_results(cfg)
    names = {"provuar": "provuar", "turne": "🏁 në turne", "ekip": "✅ në ekip", "hedhur": "✖ hedhur"}
    st.dataframe(pd.DataFrame([{
        "Gjendja": names.get(s["status"], s["status"]), "Strategjia": s["name"], "Mësimi %": s["train"],
        "Kontrolli %": s["test"], "Turne %": (fwd.get(s["id"]) or {}).get("return_pct"),
        "Tregti turne": (fwd.get(s["id"]) or {}).get("trades"), "Shënim": s["note"] or ""}
        for s in sorted(labs, key=lambda s: (["ekip", "turne", "provuar", "hedhur"].index(s["status"])
                                             if s["status"] in names else 9, -(s["test"] or -999)))]),
        width="stretch", hide_index=True, column_config={
            "Mësimi %": st.column_config.NumberColumn(format="%+.1f"),
            "Kontrolli %": st.column_config.NumberColumn(format="%+.1f"),
            "Turne %": st.column_config.NumberColumn(format="%+.2f")})
    st.caption(f"Rruga e një strategjie të re: provë në të kaluarën → turne me para demo → ekip pas {cfg.promote_days:g} "
               "ditësh fitimi në turne (të paktën 15 tregti). Laboratori provon shumë variante, ndaj disa duken mirë "
               "rastësisht; turneu në kohë reale është prova që vendos.")


def _backtest_section(cfg, exchange, symbol):
    n = st.select_slider("Sa qirinj historikë", [1000, 2000, 3000, 5000], 3000)
    if not st.button("Provo strategjinë në të kaluarën"):
        return
    with st.spinner("Duke shkarkuar historinë..."):
        df = fetch_candles(exchange, symbol, cfg.timeframe, n)
        r = backtest(df, cfg, fetch_daily(exchange, symbol, cfg, df))
    m = st.columns(4)
    m[0].metric("Roboti", f"{r['return_pct']:+.2f}%")
    m[1].metric("Mbajtja pa tregtuar", f"{r['buy_hold_pct']:+.2f}%")
    m[2].metric("Tregti fituese", f"{r['wins']} nga {r['trades']}")
    m[3].metric("Rënia maksimale", f"{r['max_drawdown_pct']:.1f}%")
    st.caption(f"Periudha: {df.index[0]:%d %b %Y} – {df.index[-1]:%d %b %Y}. Rezultati i së kaluarës nuk garanton të ardhmen.")
    eq = pd.DataFrame({"koha": df.index[-len(r["equity"]):], "kapitali": r["equity"]})
    st.altair_chart(alt.Chart(eq).mark_line(strokeWidth=2, color="#2a78d6").encode(
        x=alt.X("koha:T", title=None, axis=alt.Axis(grid=False)),
        y=alt.Y("kapitali:Q", title=f"Kapitali ({cfg.quote})", scale=alt.Scale(zero=False), axis=alt.Axis(gridOpacity=0.25)),
        tooltip=[alt.Tooltip("koha:T", title="Koha"), alt.Tooltip("kapitali:Q", title="Kapitali", format=",.2f")],
    ).properties(height=260), width="stretch")
    if r["trade_list"]:
        t = pd.DataFrame(r["trade_list"]).iloc[::-1]
        for col in ("entry_time", "exit_time"):
            t[col] = t[col].str.slice(0, 16)
        cols = {"entry_time": "Hyrja (koha)", "exit_time": "Dalja (koha)", "side": "Drejtimi", "entry": "Çmimi i hyrjes",
                "exit": "Çmimi i daljes", "reason": "Arsyeja", "pnl": "Fitim/humbje", "pnl_pct": "%"}
        st.dataframe(t[list(cols)].rename(columns=cols), width="stretch", hide_index=True)


def _journal_section(cfg, exchange, symbol):
    st.caption("Fut parashikimet e një burimi (p.sh. AI Analysis i MEXC). Pasi kalon afati, paneli kontrollon çmimin "
               "dhe llogarit sa shpesh ka pasur të drejtë.")
    with st.form("parashikim"):
        c = st.columns(2)
        source = c[0].text_input("Burimi", "mexc-ai")
        direction = c[1].selectbox("Drejtimi", ["rënie", "rritje"])
        hours = c[0].number_input("Afati (orë)", 1.0, 720.0, 24.0, 1.0)
        target = c[1].number_input("Objektivi (0 = pa)", 0.0, value=0.0)
        if st.form_submit_button(f"Shto parashikim për {symbol}"):
            price = float(exchange.fetch_ticker(symbol)["last"])
            journal.add(cfg.predictions_file, source, symbol, direction, hours, price, None, target or None)
            st.success(f"U shtua (çmimi tani {_fmt(price)}).")
    journal.check(cfg.predictions_file, exchange)
    entries = journal.load(cfg.predictions_file)
    if not entries:
        return st.info("Ditari është bosh.")
    stats = []
    for src in sorted({e["source"] for e in entries}):
        mine = [e for e in entries if e["source"] == src]
        closed = [e for e in mine if e["correct"] is not None]
        ok = sum(e["correct"] for e in closed)
        stats.append({"Burimi": src, "Gjithsej": len(mine), "Të mbyllura": len(closed), "Të sakta": ok,
                      "Saktësia": f"{ok / len(closed) * 100:.0f}%" if closed else "–"})
    st.dataframe(pd.DataFrame(stats), width="stretch", hide_index=True)
    if max(s["Të mbyllura"] for s in stats) < 30:
        st.caption("Me më pak se 30 parashikime të mbyllura, përqindja nuk tregon ende asgjë.")


def tab_tests(cfg, exchange, symbol):
    with st.expander("Prova në të kaluarën", expanded=True):
        _backtest_section(cfg, exchange, symbol)
    with st.expander("Ditari i parashikimeve"):
        _journal_section(cfg, exchange, symbol)


def _settings(tickers):
    """Zgjedhja e monedhës, mënyra dhe “Rregullime”. Kthen (cfg, exchange, simboli) ose None."""
    base = load_config()
    favorites = list(base.symbols) if base.focus else FAVORITES
    pick = st.pills("Tregu", favorites + ["Tjetër"], key="coin", default=favorites[0],
                    format_func=lambda s: display(s) if s in FOCUS_SYMBOLS else (s.split("/")[0] if "/" in s else s))
    symbol = pick or base.symbols[0]
    if pick == "Tjetër":
        symbol = st.text_input("Shkruaj monedhën (p.sh. PEPE/USDT ose XAUUSD në MT5)", "PEPE/USDT").strip().upper()
    mode = st.session_state.get("mode", list(MODES)[0])
    # Në telefon grafiku duhet të duket shpejt: mënyra dhe rregullimet rrinë të mbledhura në një vend.
    with st.expander(f"⚙️ Mënyra: {mode.split(' (')[0]} · rregullimet"):
        mode = st.radio("Mënyra e robotit", list(MODES), horizontal=True, key="mode",
                        help="Aktive: hyn lart kur tregu është në ngritje dhe poshtë kur është në rënie, në të gjitha "
                             "monedhat, dhe këmben pozicionet e dobëta me monedha më të forta. E kujdesshme: pak tregti, "
                             "vetëm blerje kur tregu është në ngritje.")
        preset = replace(base, **MODES[mode])
        if MODES[mode]:
            st.caption("Mënyra aktive tregton shpesh, në të dy drejtimet. Në prova (20 monedha, 26 muaj) dha +72% me "
                       "rënie deri në 30%; fitimi erdhi nga blerjet, ndërsa shitjet short vetë dolën me humbje.")
        r = st.columns(2)
        name = r[0].selectbox("Platforma", PLATFORMS, key=f"ex_{mode}", format_func=PLATFORM_NAMES.get,
                              index=PLATFORMS.index(base.exchange) if base.exchange in PLATFORMS else 0)
        timeframe = r[1].selectbox("Intervali i strategjisë", TIMEFRAMES, key=f"tf_{mode}",
                                   index=TIMEFRAMES.index(preset.timeframe) if preset.timeframe in TIMEFRAMES else 2)
        stop = r[0].number_input("Stop-loss % (humbja ku mbyllet)", 0.2, 50.0, float(preset.stop_loss_pct), 0.5,
                                 key=f"sl_{mode}")
        take = r[1].number_input("Fitimi % ku mbyllet (0 = i hapur)", 0.0, 500.0, float(preset.take_profit_pct), 0.5,
                                 key=f"tp_{mode}", help="Me 0 fitimi lihet të rritet derisa trendi të kthehet.")
        strategy = r[0].selectbox("Strategjia", STRATEGIES, key=f"st_{mode}", index=STRATEGIES.index(preset.strategy))
        short = r[1].toggle("Lejo edhe shitje short", preset.allow_short, key=f"sh_{mode}",
                            help="Roboti hap pozicione edhe kur pret rënie. Në prova kjo e ka dobësuar rezultatin.")
    try:
        cfg = replace(preset, exchange=name, symbols=[symbol], timeframe=timeframe, stop_loss_pct=stop,
                      take_profit_pct=take, allow_short=short, strategy=strategy).validate()
        if strategy == "engulf" and not cfg.max_trades_per_day:
            cfg.max_trades_per_day = 2
        exchange = _exchange(name)
        cfg.data_tz = "UTC"
        if hasattr(exchange, "account_currency"):   # MT5: monedha bazë është ajo e llogarisë, ora ajo e serverit
            cfg.quote = exchange.account_currency()
            cfg.data_tz = exchange.server_tz(symbol)
            if cfg.market_filter_symbol == "BTC/USDT":
                cfg.market_filter_symbol = ""
    except Exception as e:
        st.error(f"Gabim: {e}")
        return None
    return cfg, exchange, symbol


@st.fragment(run_every=15)
def _strip(name, selected, symbols):
    ticker_strip(_tickers(name), symbols, selected, _fear_greed())


def render():
    st.subheader("📈 Roboti i tregtimit")
    base_cfg = load_config()
    st.caption(("Fokus: XAUUSD, BTCUSDT, BTCUSD, EURUSD, GBPUSD · rreziku i hapur gjithsej deri në "
                f"{base_cfg.max_total_risk_pct:g}% · " if base_cfg.focus else "") + "Çmime reale, para demo. Nuk është këshillë financiare.")
    base = load_config()
    _strip(base.exchange if base.exchange != "mt5" else "mexc", st.session_state.get("coin") or base.symbols[0],
           list(base.symbols) if base.focus else FAVORITES)
    got = _settings(_tickers(base.exchange))
    if got is None:
        return
    cfg, exchange, symbol = got
    tabs = st.tabs(["📈 Grafiku", "🌐 Tregu", "🧠 Analisti", "🤖 Roboti", "📔 Kujtesa", "🔔 Njoftime", "🧪 Prova"])
    calls = [(tab_chart, (cfg, exchange, symbol)), (tab_market, (cfg, exchange)), (tab_analyst, (cfg, exchange)),
             (tab_robot, (cfg, exchange)), (tab_memory, (cfg,)),
             (tab_alerts, (cfg, symbol, None)), (tab_tests, (cfg, exchange, symbol))]
    for tab, (fn, args) in zip(tabs, calls):
        with tab:
            try:
                if fn is tab_alerts:
                    t = _tickers(cfg.exchange).get(symbol, {})
                    args = (cfg, symbol, float(t.get("last") or 0.0))
                fn(*args)
            except Exception as e:
                st.error(f"Gabim: {e}")
