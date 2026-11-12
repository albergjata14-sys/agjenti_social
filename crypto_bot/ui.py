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

from . import journal, notify
from .backtest import backtest
from .bot import is_running, stop_file
from .broker import Broker
from .config import ACTIVE, load_config
from .data import fetch_candles, fetch_daily, make_exchange, top_symbols
from .live_chart import chart_payload, live_chart
from .outlook import overview
from .strategy import analyze

PLATFORMS = ["mexc", "binance", "bybit", "mt5"]
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
CHART_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
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
def ticker_strip(tickers: dict, symbols: list, selected: str):
    tiles = []
    for sym in symbols:
        t = tickers.get(sym) or {}
        pct = t.get("percentage")
        arrow = "" if pct is None else ("▲ " if pct >= 0 else "▼ ")
        tiles.append(f'<div class="cb-tile{" sel" if sym == selected else ""}"><div class="n">{sym.split("/")[0]}</div>'
                     f'<div class="p">{_fmt(t.get("last"))}</div>'
                     f'<div class="c">{arrow}{"" if pct is None else f"{pct:+.2f}%"}</div></div>')
    st.markdown(CSS + f'<div class="cb-strip">{"".join(tiles)}</div>', unsafe_allow_html=True)


def _status(a, cfg, symbol, price, pos, who):
    """Një fjali e thjeshtë: çfarë po ndodh dhe çfarë pritet."""
    if pos:
        side = pos.get("side", 1)
        pnl = (price / pos["entry"] - 1) * 100 * side
        text = (f"**{'Ti ke' if who == 'Ti' else who + ' ka'} një pozicion "
                f"{'blerjeje (long)' if side > 0 else 'shitjeje (short)'} te {symbol}** nga {_fmt(pos['entry'])}. "
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


@st.fragment(run_every=REFRESH)
def tab_chart(cfg, exchange, symbol):
    tf = st.segmented_control("Intervali i grafikut", CHART_TIMEFRAMES, key="chart_tf",
                              default=cfg.timeframe if cfg.timeframe in CHART_TIMEFRAMES else "4h") or cfg.timeframe
    live = _candles(cfg.exchange, symbol, tf, 500)
    strat = live if tf == cfg.timeframe else _candles(cfg.exchange, symbol, cfg.timeframe, max(cfg.candles, 400))
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

    if pos:
        levels = [("Hyrja", pos["entry"], "entry"), ("Stop-loss", pos["sl"], "stop")]
        if pos["tp"]:
            levels.append(("Fitimi (TP)", pos["tp"], "target"))
    elif a["engulf"]:
        e = a["engulf"]
        levels = [("Maja e sesionit", e["session_high"], "level"), ("50% e sesionit", e["session_mid"], "level"),
                  ("Fundi i sesionit", e["session_low"], "level")]
        if a["signal"] in ("BLI", "SHORT"):
            levels += [("Stop-loss", a["plan"]["stop_loss"], "stop"), ("Fitimi (TP)", a["plan"]["take_profit"], "target")]
    elif cfg.strategy == "breakout":
        levels = [("Blerje mbi", a["buy_above"], "level")] + (
            [("Short nën", a["short_below"], "level")] if cfg.allow_short else [])
    else:
        levels = []
    shift = _shift(cfg)
    marks = _marks(state, symbol, "Roboti", shift) + _marks(mb.state, symbol, "Ti", shift)
    ema_n = cfg.momentum_ema if cfg.strategy == "momentum" else cfg.trend_ema
    live_chart(chart_payload(live, symbol, tf, ema_n, levels, marks, _change(tickers, symbol), height=430),
               key="live_chart")
    st.caption(f"Vija vjollcë është mesatarja EMA{ema_n}. Vijat horizontale janë nivelet; shigjetat shënojnë hyrjet, "
               "rrathët daljet. Sinjalet llogariten vetëm mbi qirinjtë e mbyllur "
               f"({cfg.timeframe}); grafiku rifreskohet çdo {REFRESH} sekonda.")

    st.markdown("**Provo vetë me para demo**")
    b = st.columns(3)
    for col, label, side in ((b[0], "🟢 Bli", 1), (b[1], "🔻 Shit short", -1)):
        if col.button(label, width="stretch", disabled=symbol in mb.positions, key=f"open{side}"):
            pos = mb.buy(symbol, price, mb.equity({symbol: price}), cfg.stop_loss_pct, side)
            if pos:
                notify.emit(cfg, "tregti", symbol, notify.trade_message("BLI" if side > 0 else "SHORT", symbol, pos,
                                                                        cfg.quote).replace("Roboti", "Prova jote"))
            st.rerun(scope="fragment")
    if b[2].button("Mbyll", width="stretch", disabled=symbol not in mb.positions, key="close"):
        t = mb.sell(symbol, price, "me dorë")
        notify.emit(cfg, "tregti", symbol, notify.trade_message("SHIT", symbol, t, cfg.quote).replace("Roboti", "Prova jote"))
        st.rerun(scope="fragment")
    done = mb.state["trades"]
    st.caption(f"Para demo të tuat: {mb.cash():,.2f} {cfg.quote} të lira · {len(done)} tregti të mbyllura, gjithsej "
               f"{sum(t['pnl'] for t in done):+.2f} {cfg.quote}. Stop-loss {cfg.stop_loss_pct:g}% larg"
               + (f", fitimi {cfg.take_profit_pct:g}% larg." if cfg.take_profit_pct else ", fitimi lihet i hapur."))
    with st.expander("Më shumë detaje për analizën"):
        p, f = a["plan"], a["forecast"]
        st.markdown(
            f"- Arsyeja e sinjalit: {a['signal_reason']}\n"
            f"- Plani nëse hyn tani: stop-loss {_fmt(p['stop_loss'])} (−{p['stop_pct']:.3g}%), "
            f"madhësia {p['position_pct']:.3g}% e kapitalit\n"
            f"- Brezi i zakonshëm i lëvizjes për {f['horizon_candles']} qirinj: {_fmt(f['low'])} – {_fmt(f['high'])}\n"
            f"- Mbështetja / rezistenca: {_fmt(a['support'])} / {_fmt(a['resistance'])}\n"
            f"- Pikët e treguesve: {a['score']:+.0f}/100 ({a['direction']})")


def tab_market(cfg, exchange):
    st.caption("Ecuria e monedhave më të tregtuara: ndryshimet, lëvizja 14-ditore, gjendja e trendit dhe sinjali i robotit.")
    n = st.select_slider("Sa monedha", [10, 20, 30], 20)
    if st.button("Rifresko pamjen e tregut", type="primary") or st.session_state.get("market_n") == n:
        st.session_state["market_n"] = n
        with st.spinner("Duke parë tregun (deri në një minutë herën e parë)..."):
            symbols = tuple(_top(cfg.exchange, cfg.quote, n)) if cfg.exchange != "mt5" else tuple(cfg.symbols)
            df = _overview(cfg.exchange, _cfg_json(replace(cfg, timeframe="4h") if cfg.timeframe != "4h" else cfg), symbols)
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
            "Gjasat lart 24h %": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.0f%%",
                help="Sa herë, në gjendje të ngjashme në të kaluarën, çmimi ishte më lart pas 24 orësh."),
            "Raste": st.column_config.NumberColumn(help="Sa raste historike qëndrojnë pas përqindjes"),
        })
    st.caption("“Gjasat lart 24h” nuk janë parashikim: janë sa herë në të kaluarën, në gjendje të ngjashme, çmimi "
               "ishte më lart pas 24 orësh. Në një provë jashtë mostrës (40 monedha, 2024–2026) kjo e qëlloi drejtimin "
               "51% të herëve, sa hedhja e një monedhe. Njëjtë si “AI Analysis” i MEXC, merre si informacion, jo si sinjal.")


def tab_alerts(cfg, symbol, price):
    tg = notify.telegram_settings()
    st.markdown("**Njoftime në telefon (Telegram)**")
    if tg:
        c = st.columns([2, 1])
        c[0].success("Telegram-i është lidhur.")
        if c[1].button("Dërgo një mesazh provë", width="stretch"):
            st.toast("Mesazhi u dërgua." if notify.telegram_send("✅ Prova nga paneli i robotit.") else "Mesazhi nuk shkoi.")
    else:
        st.info("Telegram-i nuk është lidhur ende. Njoftimet shfaqen vetëm këtu në panel.")
    with st.expander("Si ta lidhësh Telegram-in"):
        st.markdown(
            "1. Në Telegram hap **@BotFather**, shkruaj `/newbot` dhe ndiq hapat; merr një **token**.\n"
            "2. Hap robotin tënd të ri dhe shtyp **Start**.\n"
            "3. **Në kompjuter:** `python -m crypto_bot njoftime lidh` (të kërkon tokenin dhe gjen vetë bisedën).\n"
            "4. **Në Streamlit Cloud:** te aplikacioni → Settings → Secrets shto\n"
            "   `TELEGRAM_BOT_TOKEN = \"...\"` dhe `TELEGRAM_CHAT_ID = \"...\"`.\n\n"
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


def _positions_table(positions: dict, exchange) -> pd.DataFrame:
    rows = []
    for sym, p in positions.items():
        try:
            price = float(exchange.fetch_ticker(sym)["last"])
        except Exception:
            price = p["entry"]
        side = p.get("side", 1)
        rows.append({"Monedha": sym, "Drejtimi": "long" if side > 0 else "short", "Hyrja": p["entry"],
                     "Çmimi tani": price, "Fitim/humbje %": round((price / p["entry"] - 1) * 100 * side, 2),
                     "Vlera": round(Broker.value(p, price), 2), "Stop-loss": p["sl"], "Fitimi (TP)": p["tp"]})
    return pd.DataFrame(rows)


@st.fragment(run_every=20)
def tab_robot(cfg, exchange):
    state = _read_state(cfg)
    running = is_running(cfg, state or {})
    whole = st.toggle("Skano gjithë tregun (jo vetëm monedhën e zgjedhur)", True, disabled=running)
    c1, c2 = st.columns(2)
    if c1.button("▶ Nis robotin", disabled=running, width="stretch", type="primary"):
        # Roboti niset me pikërisht rregullimet që shihen në panel.
        Path(UI_CONFIG).write_text(json.dumps(asdict(replace(cfg, scan_market=whole)), indent=2))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open("crypto_bot_output.log", "a", encoding="utf-8") as out:
            subprocess.Popen([sys.executable, "-m", "crypto_bot", "nis", "--config", UI_CONFIG],
                             stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
        st.toast("Roboti po niset; gjendja shfaqet pas ciklit të parë.")
    if c2.button("■ Ndalo robotin", disabled=not running, width="stretch"):
        stop_file(cfg).write_text("stop")
        st.toast("U kërkua ndalimi; roboti ndalet brenda pak sekondash.")
    if state is None:
        return st.info("Roboti nuk është nisur ende. Tregton vetë me para demo (virtuale) mbi çmime reale.")
    ago = time.time() - state.get("heartbeat", 0)
    table = _positions_table(state["positions"], exchange)
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
    if len(table):
        st.markdown("**Pozicionet e hapura**")
        st.dataframe(table, width="stretch", hide_index=True,
                     column_config={"Fitim/humbje %": st.column_config.NumberColumn(format="%+.2f")})
    if trades:
        st.markdown("**Tregtitë e mbyllura**")
        t = pd.DataFrame(trades).iloc[::-1]
        t["closed"] = pd.to_datetime(t["closed"], unit="s").dt.strftime("%d %b %H:%M")
        cols = {"closed": "Mbyllur", "symbol": "Monedha", "side": "Drejtimi", "entry": "Hyrja", "exit": "Dalja",
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
    pick = st.pills("Monedha", FAVORITES + ["Tjetër"], key="coin", default=base.symbols[0] if base.symbols[0] in FAVORITES
                    else "Tjetër", format_func=lambda s: s.split("/")[0] if "/" in s else s)
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
        name = r[0].selectbox("Platforma", PLATFORMS, key=f"ex_{mode}",
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
def _strip(name, selected):
    ticker_strip(_tickers(name), FAVORITES, selected)


def render():
    st.subheader("📈 Roboti i kriptove")
    st.caption("Çmime reale, para demo. Nuk është këshillë financiare.")
    base = load_config()
    _strip(base.exchange if base.exchange != "mt5" else "mexc", st.session_state.get("coin") or base.symbols[0])
    got = _settings(_tickers(base.exchange))
    if got is None:
        return
    cfg, exchange, symbol = got
    tabs = st.tabs(["📈 Grafiku", "🌐 Tregu", "🤖 Roboti", "🔔 Njoftime", "🧪 Prova"])
    calls = [(tab_chart, (cfg, exchange, symbol)), (tab_market, (cfg, exchange)), (tab_robot, (cfg, exchange)),
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
