"""Paneli i robotit të kriptove (Streamlit). Hapet si aplikacion më vete me crypto_app.py."""
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from . import journal
from .backtest import backtest
from .bot import is_running, scan, stop_file
from .broker import Broker
from .config import load_config
from .data import fetch_candles, fetch_daily, make_exchange
from .strategy import analyze, signal_frame

PLATFORMS = ["mexc", "binance", "bybit", "mt5"]
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
# Ngjyra të kontrolluara për shikim me daltonizëm: blu = qiri rritës, portokalli = rënës.
COLORS = {"light": {"up": "#2a78d6", "down": "#eb6834", "ema": "#6250d6", "ink": "#52514e"},
          "dark": {"up": "#3987e5", "down": "#d95926", "ema": "#9085e9", "ink": "#c3c2b7"}}


def _theme() -> dict:
    try:
        return COLORS["dark" if st.context.theme.type == "dark" else "light"]
    except Exception:
        return COLORS["light"]


@st.cache_resource(show_spinner=False)
def _exchange(name: str, testnet: bool):
    return make_exchange(load_config(exchange=name, testnet=testnet))


@st.cache_data(ttl=60, show_spinner=False)
def _market(name: str, symbol: str, timeframe: str, candles: int, daily_ema: int):
    """Qirinjtë dhe qirinjtë ditorë, të ruajtur 60 sekonda që paneli të mos e ngarkojë platformën."""
    cfg = load_config(exchange=name, timeframe=timeframe, daily_trend_ema=daily_ema)
    ex = _exchange(name, False)
    df = fetch_candles(ex, symbol, timeframe, candles)
    return df, fetch_daily(ex, symbol, cfg, df)


def price_chart(s: pd.DataFrame, a: dict, cfg, bars: int = 150):
    """Qirinjtë me EMA200 dhe nivelet e planit (blerje, stop, dalje), secili me etiketë."""
    c = _theme()
    d = s.tail(bars).reset_index().rename(columns={"time": "koha"})
    d["drejtimi"] = (d["close"] >= d["open"]).map({True: "Qiri rritës", False: "Qiri rënës"})
    tips = [alt.Tooltip("koha:T", title="Koha", format="%d %b %H:%M"),
            alt.Tooltip("open:Q", title="Hapja", format=",.6~g"), alt.Tooltip("high:Q", title="Maja", format=",.6~g"),
            alt.Tooltip("low:Q", title="Fundi", format=",.6~g"), alt.Tooltip("close:Q", title="Mbyllja", format=",.6~g")]
    color = alt.Color("drejtimi:N", title=None, legend=alt.Legend(orient="top"),
                      scale=alt.Scale(domain=["Qiri rritës", "Qiri rënës"], range=[c["up"], c["down"]]))
    x = alt.X("koha:T", title=None, axis=alt.Axis(format="%d %b", grid=False))
    levels = [("Blerje mbi", a["buy_above"]), ("Stop-loss", a["plan"]["stop_loss"])]
    if a["plan"]["exit_level"]:
        levels.append(("Dalje nga trendi", a["plan"]["exit_level"]))
    if a["plan"]["take_profit"]:
        levels.append(("Fitimi", a["plan"]["take_profit"]))
    lv = pd.DataFrame(levels, columns=["niveli", "cmimi"])
    lv["etiketa"] = lv.apply(lambda r: f"{r['niveli']} {r['cmimi']:,.6g}", axis=1)
    # Etiketat vendosen djathtas qirinjve, në një hapësirë të lënë bosh për to.
    span = d["koha"].iloc[-1] - d["koha"].iloc[0]
    lv["koha"] = d["koha"].iloc[-1] + span * 0.015
    x = alt.X("koha:T", title=None, axis=alt.Axis(format="%d %b", grid=False),
              scale=alt.Scale(domain=[d["koha"].iloc[0].isoformat(), (d["koha"].iloc[-1] + span * 0.2).isoformat()]))
    lo = min(d["low"].min(), lv["cmimi"].min())
    hi = max(d["high"].max(), lv["cmimi"].max())
    pad = (hi - lo) * 0.04
    y = alt.Y("low:Q", title=None, scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False),
              axis=alt.Axis(format=",.6~g", gridOpacity=0.25))
    base = alt.Chart(d)
    wicks = base.mark_rule(strokeWidth=1).encode(x=x, y=y, y2="high:Q", color=color, tooltip=tips)
    bodies = base.mark_bar(size=max(2, 520 // bars)).encode(x=x, y="open:Q", y2="close:Q", color=color, tooltip=tips)
    ema = base.mark_line(strokeWidth=2, color=c["ema"]).encode(
        x=x, y=alt.Y("trend_ema:Q"), tooltip=[alt.Tooltip("trend_ema:Q", title=f"EMA{cfg.trend_ema}", format=",.6~g")])
    rules = alt.Chart(lv).mark_rule(strokeDash=[6, 4], strokeWidth=1.5, color=c["ink"]).encode(
        y="cmimi:Q", tooltip=[alt.Tooltip("niveli:N", title="Niveli"), alt.Tooltip("cmimi:Q", title="Çmimi", format=",.6~g")])
    labels = alt.Chart(lv).mark_text(align="left", dy=-8, fontSize=12, color=c["ink"]).encode(
        x="koha:T", y="cmimi:Q", text="etiketa:N")
    return (wicks + bodies + ema + rules + labels).properties(height=430)


def _manual_cfg(cfg):
    return replace(cfg, state_file="crypto_bot_manual.json", log_file="")


def _positions_table(broker, exchange) -> pd.DataFrame:
    rows = []
    for sym, p in broker.positions.items():
        try:
            price = float(exchange.fetch_ticker(sym)["last"])
        except Exception:
            price = p["entry"]
        rows.append({"Monedha": sym, "Hyrja": p["entry"], "Çmimi tani": price,
                     "Fitim/humbje %": round((price / p["entry"] - 1) * 100, 2),
                     "Vlera": round(p["qty"] * price, 2), "Stop-loss": p["sl"], "Fitimi": p["tp"]})
    return pd.DataFrame(rows)


def tab_chart(cfg, exchange, symbol):
    df, daily = _market(cfg.exchange, symbol, cfg.timeframe, max(cfg.candles, 500), cfg.daily_trend_ema)
    a = analyze(df, cfg, symbol, daily=daily)
    gap = (a["buy_above"] / a["price"] - 1) * 100
    m = st.columns(4)
    m[0].metric("Çmimi (qiriri i fundit i mbyllur)", f"{a['price']:,.6g}")
    m[1].metric("Sinjali", a["signal"])
    m[2].metric("Blerje mbi", f"{a['buy_above']:,.6g}", f"{gap:+.1f}% larg", delta_color="off")
    m[3].metric("Trendi ditor", "rritës" if a["daily_up"] else "jo rritës")
    st.caption(f"Arsyeja: {a['signal_reason']}")
    st.altair_chart(price_chart(signal_frame(df, cfg, daily), a, cfg), width="stretch")
    st.caption(f"Vija e plotë është EMA{cfg.trend_ema}. Vijat me ndërprerje janë nivelet e planit, me çmimin përkrah.")
    p, f = a["plan"], a["forecast"]
    st.markdown(
        f"**Plani nëse hyn tani:** hyrje {p['entry']:,.6g} · stop-loss {p['stop_loss']:,.6g} (−{p['stop_pct']:.3g}%) · "
        f"madhësia {p['position_pct']:.3g}% e kapitalit"
        + (f" · dalje nga trendi nën {p['exit_level']:,.6g}" if p["exit_level"] else "")
        + f"\n\n**Brezi i pritshëm ({f['horizon_candles']} qirinj):** {f['low']:,.6g} – {f['high']:,.6g} · "
        f"**Mbështetja / rezistenca:** {a['support']:,.6g} / {a['resistance']:,.6g} · "
        f"**Pikët e treguesve:** {a['score']:+.0f}/100 ({a['direction']})")
    with st.expander("Të dhënat e grafikut si tabelë"):
        st.dataframe(df.tail(150).iloc[::-1], width="stretch")

    st.subheader("Provat e mia me para demo")
    st.caption("Portofol më vete nga ai i robotit, për të provuar hyrjet e tua. Stop-loss kontrollohet vetëm kur "
               "ky panel është i hapur.")
    mb = Broker(_manual_cfg(cfg))
    for sym in list(mb.positions):
        try:
            now = float(exchange.fetch_ticker(sym)["last"])
            reason = mb.check_exit(sym, now)
            if reason:
                t = mb.sell(sym, now, reason)
                st.warning(f"{sym} u mbyll nga {reason}: {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")
        except Exception as e:
            st.caption(f"{sym}: çmimi nuk u mor ({e})")
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button(f"Bli demo {symbol}", width="stretch", disabled=symbol in mb.positions):
        price = float(exchange.fetch_ticker(symbol)["last"])
        equity = mb.equity({symbol: price})
        pos = mb.buy(symbol, price, equity, p["stop_pct"])
        st.success(f"U ble {symbol} me {pos['cost']:.2f} {cfg.quote} në {price:,.6g}; stop {pos['sl']:,.6g}"
                   if pos else "Nuk u ble: fonde të pamjaftueshme.")
    if c2.button(f"Shit demo {symbol}", width="stretch", disabled=symbol not in mb.positions):
        t = mb.sell(symbol, float(exchange.fetch_ticker(symbol)["last"]), "me dorë")
        st.success(f"U shit: {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")
    done = mb.state["trades"]
    c3.metric("Para demo të lira", f"{mb.cash():,.2f} {cfg.quote}",
              f"{sum(t['pnl'] for t in done):+.2f} nga {len(done)} tregti të mbyllura", delta_color="off")
    if mb.positions:
        st.dataframe(_positions_table(mb, exchange), width="stretch", hide_index=True)


def tab_scan(cfg, exchange):
    n = st.slider("Sa monedha të skanohen (sipas volumit)", 10, 100, cfg.scan_top_n, 10)
    if st.button("Skano tregun tani"):
        with st.spinner("Duke skanuar tregun..."):
            st.session_state["scan"] = scan(exchange, replace(cfg, scan_market=True, scan_top_n=n))
    rows = st.session_state.get("scan")
    if not rows:
        return st.info("Shtyp butonin për të skanuar monedhat më të tregtuara të platformës.")
    order = {"BLI": 0, "PRIT": 1, "SHIT": 2}
    rows = sorted(rows, key=lambda r: (order[r["signal"]], r["buy_above"] / r["price"]))
    m = st.columns(3)
    m[0].metric("Monedha të skanuara", len(rows))
    m[1].metric("Sinjale blerjeje", sum(r["signal"] == "BLI" for r in rows))
    m[2].metric("Me trend ditor rritës", sum(r["daily_up"] for r in rows))
    st.dataframe(pd.DataFrame([{
        "Monedha": r["symbol"], "Çmimi": r["price"], "Sinjali": r["signal"], "Blerje mbi": r["buy_above"],
        "Larg %": round((r["buy_above"] / r["price"] - 1) * 100, 1),
        "Trendi ditor": "rritës" if r["daily_up"] else "jo rritës", "Pikët": r["score"]} for r in rows]),
        width="stretch", hide_index=True)
    st.caption("“Larg %” tregon sa duhet të ngjitet çmimi që një mbyllje të japë sinjal blerjeje.")


@st.fragment(run_every=30)
def tab_robot(cfg, exchange):
    state_path = Path(cfg.state_file)
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    running = is_running(cfg, state or {})
    c1, c2, c3 = st.columns([1, 1, 2])
    whole = c3.checkbox("Skano gjithë tregun (jo vetëm monedhën e zgjedhur)", True, disabled=running)
    if c1.button("▶ Nis robotin", disabled=running, width="stretch"):
        cmd = [sys.executable, "-m", "crypto_bot", "nis", "--exchange", cfg.exchange] + (["--gjithe-tregun"] if whole else [])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open("crypto_bot_output.log", "a", encoding="utf-8") as out:
            subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
        st.success("Roboti po niset; gjendja shfaqet pas ciklit të parë (deri në një minutë).")
    if c2.button("■ Ndalo robotin", disabled=not running, width="stretch"):
        stop_file(cfg).write_text("stop")
        st.success("U kërkua ndalimi; roboti ndalet brenda pak sekondash.")
    if state is None:
        return st.info("Roboti nuk është nisur ende. Punon me para demo (virtuale) mbi çmime reale.")
    ago = time.time() - state.get("heartbeat", 0)
    st.markdown(f"**Gjendja:** {'🟢 po punon' if running else '⚪ i ndalur'}"
                + (f" · cikli i fundit para {ago:.0f} sekondash" if running else ""))
    broker_view = Broker.__new__(Broker)      # vetëm lexim: roboti është pronari i skedarit
    broker_view.cfg, broker_view.exchange, broker_view.live, broker_view.state = cfg, None, False, state
    table = _positions_table(broker_view, exchange)
    value = float(table["Vlera"].sum()) if len(table) else 0.0
    trades = state["trades"]
    equity = state["cash"] + value
    m = st.columns(4)
    m[0].metric("Kapitali demo", f"{equity:,.2f} {cfg.quote}", f"{(equity / cfg.paper_balance - 1) * 100:+.2f}% nga fillimi")
    m[1].metric("Pozicione të hapura", len(state["positions"]))
    m[2].metric("Tregti të mbyllura", len(trades))
    wins = sum(t["pnl"] > 0 for t in trades)
    m[3].metric("Tregti fituese", f"{wins / len(trades) * 100:.0f}%" if trades else "–")
    if len(table):
        st.subheader("Pozicionet e hapura")
        st.dataframe(table, width="stretch", hide_index=True)
    if trades:
        st.subheader("Tregtitë e mbyllura")
        t = pd.DataFrame(trades).iloc[::-1]
        t["closed"] = pd.to_datetime(t["closed"], unit="s").dt.strftime("%d %b %H:%M")
        st.dataframe(t.rename(columns={"symbol": "Monedha", "entry": "Hyrja", "exit": "Dalja", "reason": "Arsyeja",
                                       "pnl": "Fitim/humbje", "pnl_pct": "%", "closed": "Mbyllur"}),
                     width="stretch", hide_index=True)
    log = Path(cfg.log_file)
    if cfg.log_file and log.exists():
        st.subheader("Vendimet e fundit")
        lines = log.read_text(encoding="utf-8").splitlines()[-200:]
        d = pd.DataFrame([json.loads(x) for x in lines]).iloc[::-1]
        d["time"] = d["time"].str.slice(0, 16).str.replace("T", " ")
        only = st.checkbox("Vetëm blerjet dhe shitjet", False)
        if only:
            d = d[d["action"].isin(["BLI", "SHIT"])]
        cols = {"time": "Koha (UTC)", "symbol": "Monedha", "action": "Vendimi", "reason": "Arsyeja", "price": "Çmimi"}
        st.dataframe(d[[c for c in cols if c in d]].rename(columns=cols).head(60), width="stretch", hide_index=True)


def tab_journal(cfg, exchange, symbol):
    st.caption("Fut parashikimet e një burimi (p.sh. AI Analysis i MEXC). Pasi kalon afati, paneli kontrollon "
               "çmimin dhe llogarit sa shpesh ka pasur të drejtë. Çdo herë regjistrohet edhe mendimi i robotit.")
    with st.form("parashikim"):
        c = st.columns(5)
        source = c[0].text_input("Burimi", "mexc-ai")
        direction = c[1].selectbox("Drejtimi", ["rënie", "rritje"])
        hours = c[2].number_input("Afati (orë)", 1.0, 720.0, 24.0, 1.0)
        prob = c[3].number_input("Siguria %", 0.0, 100.0, 0.0, 1.0)
        target = c[4].number_input("Objektivi (0 = pa)", 0.0, value=0.0)
        if st.form_submit_button(f"Shto parashikim për {symbol}"):
            price = float(exchange.fetch_ticker(symbol)["last"])
            journal.add(cfg.predictions_file, source, symbol, direction, hours, price, prob or None, target or None)
            mine = scan(exchange, cfg, [symbol])
            if mine and mine[0]["direction"] != "ANASH":
                journal.add(cfg.predictions_file, "roboti", symbol,
                            "rritje" if mine[0]["direction"] == "RRITJE" else "rënie", hours, price)
            st.success(f"U shtua (çmimi tani {price:,.6g}).")
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
    d = pd.DataFrame(entries).iloc[::-1]
    d["time"] = d["time"].str.slice(0, 16).str.replace("T", " ")
    d["Rezultati"] = d["correct"].map({True: "saktë", False: "gabim"}).fillna("në pritje")
    cols = {"time": "Koha (UTC)", "source": "Burimi", "symbol": "Monedha", "direction": "Drejtimi", "hours": "Orë",
            "price": "Çmimi", "result_price": "Çmimi në afat", "Rezultati": "Rezultati"}
    st.dataframe(d[list(cols)].rename(columns=cols), width="stretch", hide_index=True)


def tab_backtest(cfg, exchange, symbol):
    n = st.select_slider("Sa qirinj historikë", [1000, 2000, 3000, 5000], 3000)
    if not st.button("Provo strategjinë në të kaluarën"):
        return
    with st.spinner("Duke shkarkuar historinë..."):
        df = fetch_candles(exchange, symbol, cfg.timeframe, n)
        r = backtest(df, cfg, fetch_daily(exchange, symbol, cfg, df))
    m = st.columns(5)
    m[0].metric("Roboti", f"{r['return_pct']:+.2f}%")
    m[1].metric("Mbajtja pa tregtuar", f"{r['buy_hold_pct']:+.2f}%")
    m[2].metric("Tregti", r["trades"])
    m[3].metric("Fituese", f"{r['win_rate_pct']:.0f}%")
    m[4].metric("Rënia maksimale", f"{r['max_drawdown_pct']:.1f}%")
    st.caption(f"Periudha: {df.index[0]:%d %b %Y} – {df.index[-1]:%d %b %Y}. Rezultati i së kaluarës nuk garanton të ardhmen.")
    eq = pd.DataFrame({"koha": df.index[-len(r["equity"]):], "kapitali": r["equity"]})
    st.altair_chart(alt.Chart(eq).mark_line(strokeWidth=2, color=_theme()["up"]).encode(
        x=alt.X("koha:T", title=None, axis=alt.Axis(grid=False)),
        y=alt.Y("kapitali:Q", title=f"Kapitali ({cfg.quote})", scale=alt.Scale(zero=False), axis=alt.Axis(gridOpacity=0.25)),
        tooltip=[alt.Tooltip("koha:T", title="Koha"), alt.Tooltip("kapitali:Q", title="Kapitali", format=",.2f")],
    ).properties(height=280), width="stretch")
    if r["trade_list"]:
        t = pd.DataFrame(r["trade_list"]).iloc[::-1]
        for col in ("entry_time", "exit_time"):
            t[col] = t[col].str.slice(0, 16)
        st.dataframe(t.rename(columns={"entry_time": "Hyrja (koha)", "exit_time": "Dalja (koha)", "entry": "Çmimi i hyrjes",
                                       "exit": "Çmimi i daljes", "reason": "Arsyeja", "pnl": "Fitim/humbje", "pnl_pct": "%"}),
                     width="stretch", hide_index=True)


def render():
    st.header("📈 Roboti i kriptove")
    st.caption("Analizë, pika hyrjeje dhe tregtim me para demo. Nuk është këshillë financiare; "
               "nivelet janë rregulla të strategjisë, jo garanci.")
    base = load_config()
    c = st.columns(4)
    name = c[0].selectbox("Platforma", PLATFORMS, index=PLATFORMS.index(base.exchange) if base.exchange in PLATFORMS else 0)
    symbol = c[1].text_input("Monedha", base.symbols[0]).strip().upper()
    timeframe = c[2].selectbox("Intervali", TIMEFRAMES,
                               index=TIMEFRAMES.index(base.timeframe) if base.timeframe in TIMEFRAMES else 2)
    stop = c[3].number_input("Stop-loss %", 0.5, 50.0, float(base.stop_loss_pct), 0.5)
    try:
        cfg = load_config(exchange=name, symbols=[symbol], timeframe=timeframe, stop_loss_pct=stop)
        exchange = _exchange(name, False)
        if hasattr(exchange, "account_currency"):   # MT5: monedha bazë është ajo e llogarisë
            cfg.quote = exchange.account_currency()
    except Exception as e:
        return st.error(f"Gabim: {e}")
    tabs = st.tabs(["Grafiku dhe pikat e hyrjes", "Skanimi i tregut", "Roboti (demo)", "Ditari i parashikimeve",
                    "Prova në të kaluarën"])
    for tab, fn, args in zip(tabs, [tab_chart, tab_scan, tab_robot, tab_journal, tab_backtest],
                             [(cfg, exchange, symbol), (cfg, exchange), (cfg, exchange), (cfg, exchange, symbol),
                              (cfg, exchange, symbol)]):
        with tab:
            try:
                fn(*args)
            except Exception as e:
                st.error(f"Gabim: {e}")
