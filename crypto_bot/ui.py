"""Paneli i robotit të kriptove (Streamlit). Hapet më vete me crypto_app.py ose brenda app.py."""
import json
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from . import journal
from .backtest import backtest
from .bot import is_running, scan, stop_file
from .broker import Broker
from .config import ACTIVE, load_config
from .data import fetch_candles, fetch_daily, make_exchange
from .strategy import analyze

PLATFORMS = ["mexc", "binance", "bybit", "mt5"]
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
STRATEGIES = ["breakout", "momentum", "score", "engulf"]
UI_CONFIG = "crypto_bot_ui_config.json"
REFRESH = 15   # sekonda mes rifreskimeve të grafikut
# Dy mënyra pune. Aktive: hyn lart kur tregu (BTC) është në ngritje dhe poshtë kur është në rënie, te
# monedhat me lëvizjen më të fortë, dhe këmben pozicionet e dobëta. E kujdesshme: vetëm blerje në thyerje maje.
MODES = {"Aktive (lart dhe poshtë)": ACTIVE, "E kujdesshme": {}}
# Ngjyra të kontrolluara për shikim me daltonizëm: blu = qiri rritës, portokalli = rënës.
COLORS = {"light": {"up": "#2a78d6", "down": "#eb6834", "ema": "#6250d6", "ink": "#52514e", "surface": "#fcfcfb"},
          "dark": {"up": "#3987e5", "down": "#d95926", "ema": "#9085e9", "ink": "#c3c2b7", "surface": "#1a1a19"}}


def _theme() -> dict:
    try:
        return COLORS["dark" if st.context.theme.type == "dark" else "light"]
    except Exception:
        return COLORS["light"]


@st.cache_resource(show_spinner=False)
def _exchange(name: str):
    return make_exchange(load_config(exchange=name))


@st.cache_data(ttl=REFRESH, show_spinner=False)
def _candles(name: str, symbol: str, timeframe: str, candles: int):
    """Qirinjtë, përfshirë atë që është ende i hapur (për grafikun e gjallë)."""
    return fetch_candles(_exchange(name), symbol, timeframe, candles, closed_only=False)


@st.cache_data(ttl=600, show_spinner=False)
def _daily(name: str, symbol: str, cfg_json: str, first, last):
    cfg = load_config(**json.loads(cfg_json))
    frame = pd.DataFrame(index=pd.DatetimeIndex([first, last]))
    return fetch_daily(_exchange(name), symbol, cfg, frame)


def _shift(cfg) -> pd.Timedelta:
    """Sa orë para UTC është ora e të dhënave (zero në bursa; ora e serverit në MT5)."""
    if cfg.data_tz in ("UTC", "auto"):
        return pd.Timedelta(0)
    return pd.Timestamp.now(tz=cfg.data_tz).utcoffset()


def _closed(live: pd.DataFrame, cfg) -> pd.DataFrame:
    """Vetëm qirinjtë e mbyllur: sinjalet nuk llogariten kurrë mbi qiririn që është ende duke lëvizur."""
    step = live.index.to_series().diff().median()
    now = pd.Timestamp.now(tz="UTC") + _shift(cfg)
    return live[live.index + step <= now]


def _read_state(cfg):
    p = Path(cfg.state_file)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (OSError, ValueError):
        return None     # roboti po e shkruan skedarin pikërisht tani; provohet në rifreskimin tjetër


def _manual_cfg(cfg):
    return replace(cfg, state_file="crypto_bot_manual.json", log_file="")


def _fmt(x) -> str:
    return f"{x:,.6g}"


def _ema_n(cfg) -> int:
    """Mesatarja që përdor strategjia e zgjedhur (dhe që vizatohet në grafik)."""
    return cfg.momentum_ema if cfg.strategy == "momentum" else cfg.trend_ema


def price_chart(live: pd.DataFrame, levels: list, marks: list, cfg, bars: int = 120):
    """Qirinjtë e gjallë me EMA, vijat e niveleve (me etiketë) dhe shenjat e hyrjeve/daljeve.

    levels: [(emri, çmimi)]; marks: [(koha, çmimi, "Hyrje"|"Dalje", përshkrimi)].
    """
    c = _theme()
    frame = live.copy()
    n = _ema_n(cfg)
    frame["trend_ema"] = frame["close"].ewm(span=n, adjust=False, min_periods=n).mean()
    d = frame.tail(bars).reset_index().rename(columns={"time": "koha"})
    d["drejtimi"] = (d["close"] >= d["open"]).map({True: "Qiri rritës", False: "Qiri rënës"})
    tips = [alt.Tooltip("koha:T", title="Koha", format="%d %b %H:%M"),
            alt.Tooltip("open:Q", title="Hapja", format=",.6~g"), alt.Tooltip("high:Q", title="Maja", format=",.6~g"),
            alt.Tooltip("low:Q", title="Fundi", format=",.6~g"), alt.Tooltip("close:Q", title="Mbyllja", format=",.6~g")]
    color = alt.Color("drejtimi:N", title=None, legend=alt.Legend(orient="top"),
                      scale=alt.Scale(domain=["Qiri rritës", "Qiri rënës"], range=[c["up"], c["down"]]))
    lv = pd.DataFrame(levels, columns=["niveli", "cmimi"]).dropna()
    lv["etiketa"] = lv.apply(lambda r: f"{r['niveli']} {_fmt(r['cmimi'])}", axis=1) if len(lv) else []
    # Etiketat vendosen djathtas qirinjve, në një hapësirë të lënë bosh për to.
    span = d["koha"].iloc[-1] - d["koha"].iloc[0]
    lv["koha"] = d["koha"].iloc[-1] + span * 0.015
    x = alt.X("koha:T", title=None, axis=alt.Axis(format="%d %b %H:%M", grid=False, labelAngle=0, tickCount=5),
              scale=alt.Scale(domain=[d["koha"].iloc[0].isoformat(), (d["koha"].iloc[-1] + span * 0.3).isoformat()]))
    lo = min([d["low"].min()] + lv["cmimi"].tolist())
    hi = max([d["high"].max()] + lv["cmimi"].tolist())
    pad = (hi - lo) * 0.05
    y = alt.Y("low:Q", title=None, scale=alt.Scale(domain=[lo - pad, hi + pad], nice=False),
              axis=alt.Axis(format=",.6~g", gridOpacity=0.25))
    base = alt.Chart(d)
    layers = [base.mark_rule(strokeWidth=1).encode(x=x, y=y, y2="high:Q", color=color, tooltip=tips),
              base.mark_bar(size=max(2, 480 // bars)).encode(x=x, y="open:Q", y2="close:Q", color=color, tooltip=tips),
              base.mark_line(strokeWidth=2, color=c["ema"]).encode(
                  x=x, y="trend_ema:Q",
                  tooltip=[alt.Tooltip("trend_ema:Q", title=f"EMA{n}", format=",.6~g")])]
    if len(lv):
        layers.append(alt.Chart(lv).mark_rule(strokeDash=[6, 4], strokeWidth=1.5, color=c["ink"]).encode(
            y="cmimi:Q", tooltip=[alt.Tooltip("niveli:N", title="Niveli"),
                                  alt.Tooltip("cmimi:Q", title="Çmimi", format=",.6~g")]))
        layers.append(alt.Chart(lv).mark_text(align="left", dy=-8, fontSize=12, color=c["ink"]).encode(
            x="koha:T", y="cmimi:Q", text="etiketa:N"))
    mk = pd.DataFrame(marks, columns=["koha", "cmimi", "lloji", "pershkrimi"])
    mk = mk[(mk["koha"] >= d["koha"].iloc[0]) & (mk["koha"] <= d["koha"].iloc[-1] + span * 0.05)] if len(mk) else mk
    if len(mk):   # hyrja = trekëndësh lart, dalja = trekëndësh poshtë (forma, jo vetëm ngjyra)
        layers.append(alt.Chart(mk).mark_point(size=170, filled=True, opacity=1, color=c["ink"],
                                               stroke=c["surface"], strokeWidth=2).encode(
            x="koha:T", y="cmimi:Q",
            shape=alt.Shape("lloji:N", title=None,
                            legend=alt.Legend(orient="top", symbolSize=110, symbolFillColor=c["ink"], symbolStrokeWidth=0),
                            scale=alt.Scale(domain=["Hyrje", "Dalje"], range=["triangle-up", "triangle-down"])),
            tooltip=[alt.Tooltip("lloji:N", title="Veprimi"), alt.Tooltip("pershkrimi:N", title="Kush"),
                     alt.Tooltip("cmimi:Q", title="Çmimi", format=",.6~g"),
                     alt.Tooltip("koha:T", title="Koha", format="%d %b %H:%M")]))
    return alt.layer(*layers).properties(height=400)


def _marks(state, symbol: str, who: str, data_shift=pd.Timedelta(0)) -> list:
    """Shenjat e hyrjeve dhe daljeve të një portofoli për simbolin e dhënë."""
    out = []
    if not state:
        return out
    ts = lambda sec: pd.Timestamp(sec, unit="s", tz="UTC") + data_shift
    for t in state["trades"]:
        if t.get("symbol") != symbol:
            continue
        side = t.get("side", "long")
        if t.get("opened"):
            out.append((ts(t["opened"]), t["entry"], "Hyrje", f"{who}, {side}"))
        out.append((ts(t["closed"]), t["exit"], "Dalje", f"{who}, {t['reason']} ({t['pnl_pct']:+.2f}%)"))
    p = state["positions"].get(symbol)
    if p:
        out.append((ts(p["opened"]), p["entry"], "Hyrje", f"{who}, {'long' if p.get('side', 1) > 0 else 'short'} (i hapur)"))
    return out


def _position_levels(p) -> list:
    return [("Hyrja", p["entry"]), ("Stop-loss", p["sl"])] + ([("Fitimi (TP)", p["tp"])] if p["tp"] else [])


def _status(a, cfg, symbol, price, pos, who):
    """Një fjali e thjeshtë: çfarë po ndodh dhe çfarë pritet."""
    if pos:
        side = pos.get("side", 1)
        pnl = (price / pos["entry"] - 1) * 100 * side
        text = (f"**{'Ti ke' if who == 'Ti' else who + ' ka'} një pozicion {'blerjeje (long)' if side > 0 else 'shitjeje (short)'} te {symbol}** nga "
                f"{_fmt(pos['entry'])}. Tani është **{pnl:+.2f}%**. Mbyllet me humbje te {_fmt(pos['sl'])}"
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
    if cfg.allow_short:
        text += f"; hap short nën {_fmt(a['short_below'])}"
    return st.info(text + ".")


@st.fragment(run_every=REFRESH)
def tab_chart(cfg, exchange, symbol):
    live = _candles(cfg.exchange, symbol, cfg.timeframe, max(cfg.candles, 400))
    closed = _closed(live, cfg)
    daily = _daily(cfg.exchange, symbol, json.dumps(asdict(cfg), sort_keys=True), closed.index[0], closed.index[-1])
    a = analyze(closed, cfg, symbol, daily=daily)
    price = float(live["close"].iloc[-1])
    state, mb = _read_state(cfg), Broker(_manual_cfg(cfg))
    # Stop-loss / fitimi i provave me dorë kontrollohet në çdo rifreskim.
    if symbol in mb.positions:
        reason = mb.check_exit(symbol, price)
        if reason:
            t = mb.sell(symbol, price, reason)
            st.toast(f"{symbol} u mbyll nga {reason}: {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")
    robot_pos = (state or {}).get("positions", {}).get(symbol)
    my_pos = mb.positions.get(symbol)
    pos, who = (robot_pos, "Roboti") if robot_pos else (my_pos, "Ti") if my_pos else (None, "")
    _status(a, cfg, symbol, price, pos, who)

    m = st.columns(3)
    per_day = max(1, int(pd.Timedelta(days=1) / (live.index[1] - live.index[0])))
    day_open = float(live["close"].iloc[-min(len(live), per_day + 1)])
    m[0].metric("Çmimi tani", _fmt(price), f"{(price / day_open - 1) * 100:+.2f}% në 24 orë")
    if pos:
        side = pos.get("side", 1)
        m[1].metric("Fitim / humbje", f"{(price / pos['entry'] - 1) * 100 * side:+.2f}%",
                    f"{Broker.value(pos, price) - pos['cost']:+.2f} {cfg.quote}")
        m[2].metric("Deri te stop-loss", f"{abs(price / pos['sl'] - 1) * 100:.2f}%",
                    f"deri te fitimi {abs(pos['tp'] / price - 1) * 100:.2f}%" if pos["tp"] else "fitimi i hapur",
                    delta_color="off")
    else:
        m[1].metric("Sinjali", {"BLI": "BLI", "SHORT": "SHORT", "SHIT": "DIL", "PRIT": "PRIT"}[a["signal"]])
        m[2].metric("Trendi ditor", "rritës" if a["daily_up"] else "rënës" if a["daily_down"] else "i paqartë")

    if pos:
        levels = _position_levels(pos)
    elif a["engulf"]:
        e = a["engulf"]
        levels = [("Maja e sesionit", e["session_high"]), ("50% e sesionit", e["session_mid"]),
                  ("Fundi i sesionit", e["session_low"])]
        if a["signal"] in ("BLI", "SHORT"):
            levels += [("Stop-loss", a["plan"]["stop_loss"]), ("Fitimi (TP)", a["plan"]["take_profit"])]
        levels = [(n, v) for n, v in levels if v is not None]
    elif cfg.strategy == "breakout":
        levels = [("Blerje mbi", a["buy_above"])] + ([("Short nën", a["short_below"])] if cfg.allow_short else [])
    else:
        levels = []
    marks = _marks(state, symbol, "Roboti", _shift(cfg)) + _marks(mb.state, symbol, "Ti", _shift(cfg))
    st.altair_chart(price_chart(live, levels, marks, cfg), width="stretch")
    st.caption(f"Grafiku rifreskohet vetë çdo {REFRESH} sekonda (i fundit: {datetime.now():%H:%M:%S}). "
               f"Vija e plotë është EMA{_ema_n(cfg)}; vijat me ndërprerje janë nivelet. "
               "Trekëndëshi lart shënon një hyrje, trekëndëshi poshtë një dalje.")

    st.markdown("**Provo vetë me para demo**")
    b = st.columns(3)
    for col, label, side in ((b[0], "Bli", 1), (b[1], "Shit short", -1)):
        if col.button(label, width="stretch", disabled=symbol in mb.positions, key=f"open{side}"):
            mb.buy(symbol, price, mb.equity({symbol: price}), cfg.stop_loss_pct, side)
            st.rerun(scope="fragment")
    if b[2].button("Mbyll", width="stretch", disabled=symbol not in mb.positions, key="close"):
        t = mb.sell(symbol, price, "me dorë")
        st.toast(f"U mbyll: {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")
        st.rerun(scope="fragment")
    done = mb.state["trades"]
    st.caption(f"Para demo të tuat: {mb.cash():,.2f} {cfg.quote} të lira · {len(done)} tregti të mbyllura, "
               f"gjithsej {sum(t['pnl'] for t in done):+.2f} {cfg.quote}. Stop-loss vendoset {cfg.stop_loss_pct:g}% larg"
               + (f", fitimi {cfg.take_profit_pct:g}% larg." if cfg.take_profit_pct else ", fitimi lihet i hapur."))
    with st.expander("Më shumë detaje për analizën"):
        p, f = a["plan"], a["forecast"]
        st.markdown(
            f"- Arsyeja e sinjalit: {a['signal_reason']}\n"
            f"- Plani nëse hyn tani: stop-loss {_fmt(p['stop_loss'])} (−{p['stop_pct']:.3g}%), "
            f"madhësia {p['position_pct']:.3g}% e kapitalit\n"
            f"- Brezi i pritshëm për {f['horizon_candles']} qirinj: {_fmt(f['low'])} – {_fmt(f['high'])}\n"
            f"- Mbështetja / rezistenca: {_fmt(a['support'])} / {_fmt(a['resistance'])}\n"
            f"- Pikët e treguesve: {a['score']:+.0f}/100 ({a['direction']})")


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
        st.dataframe(table, width="stretch", hide_index=True)
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


def tab_scan(cfg, exchange):
    if st.button("Skano tregun tani", type="primary"):
        with st.spinner("Duke skanuar tregun (rreth një minutë)..."):
            st.session_state["scan"] = scan(exchange, replace(cfg, scan_market=True))
    rows = st.session_state.get("scan")
    if not rows:
        return st.info(f"Shtyp butonin për të parë {cfg.scan_top_n} monedhat më të tregtuara dhe cilat janë më afër blerjes.")
    order = {"BLI": 0, "SHORT": 1, "PRIT": 2, "SHIT": 3}
    m = st.columns(3)
    m[0].metric("Monedha të skanuara", len(rows))
    m[1].metric("Sinjale blerjeje", sum(r["signal"] == "BLI" for r in rows))
    if cfg.strategy == "momentum":      # mënyra aktive: renditje sipas forcës së lëvizjes
        m[2].metric("Sinjale short", sum(r["signal"] == "SHORT" for r in rows))
        rows = sorted(rows, key=lambda r: (order[r["signal"]], -r["strength"]))
        st.dataframe(pd.DataFrame([{
            "Monedha": r["symbol"], "Sinjali": {"SHIT": "DIL"}.get(r["signal"], r["signal"]), "Çmimi": r["price"],
            f"Lëvizja {cfg.momentum_days:g} ditë %": None if r["momentum"] is None else round(r["momentum"], 1)}
            for r in rows]), width="stretch", hide_index=True)
        return st.caption("Roboti hyn te lëvizjet më të forta: blerje kur tregu (BTC) është në ngritje, short kur është në rënie.")
    rows = sorted(rows, key=lambda r: (order[r["signal"]], r["buy_above"] / r["price"]))
    m[2].metric("Me trend ditor rritës", sum(r["daily_up"] for r in rows))
    st.dataframe(pd.DataFrame([{
        "Monedha": r["symbol"], "Sinjali": {"SHIT": "DIL"}.get(r["signal"], r["signal"]), "Çmimi": r["price"],
        "Blerje mbi": r["buy_above"], "Larg %": round((r["buy_above"] / r["price"] - 1) * 100, 1),
        "Trendi ditor": "rritës" if r["daily_up"] else "jo rritës"} for r in rows]), width="stretch", hide_index=True)
    st.caption("“Larg %” tregon sa duhet të ngjitet çmimi që një mbyllje të japë sinjal blerjeje.")


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
    st.altair_chart(alt.Chart(eq).mark_line(strokeWidth=2, color=_theme()["up"]).encode(
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
               "dhe llogarit sa shpesh ka pasur të drejtë. Çdo herë regjistrohet edhe mendimi i robotit.")
    with st.form("parashikim"):
        c = st.columns(2)
        source = c[0].text_input("Burimi", "mexc-ai")
        direction = c[1].selectbox("Drejtimi", ["rënie", "rritje"])
        hours = c[0].number_input("Afati (orë)", 1.0, 720.0, 24.0, 1.0)
        target = c[1].number_input("Objektivi (0 = pa)", 0.0, value=0.0)
        if st.form_submit_button(f"Shto parashikim për {symbol}"):
            price = float(exchange.fetch_ticker(symbol)["last"])
            journal.add(cfg.predictions_file, source, symbol, direction, hours, price, None, target or None)
            mine = scan(exchange, cfg, [symbol])
            if mine and mine[0]["direction"] != "ANASH":
                journal.add(cfg.predictions_file, "roboti", symbol,
                            "rritje" if mine[0]["direction"] == "RRITJE" else "rënie", hours, price)
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
    d = pd.DataFrame(entries).iloc[::-1]
    d["time"] = d["time"].str.slice(5, 16).str.replace("T", " ")
    d["Rezultati"] = d["correct"].map({True: "saktë", False: "gabim"}).fillna("në pritje")
    cols = {"time": "Koha (UTC)", "source": "Burimi", "symbol": "Monedha", "direction": "Drejtimi", "hours": "Orë",
            "price": "Çmimi", "result_price": "Çmimi në afat", "Rezultati": "Rezultati"}
    st.dataframe(d[list(cols)].rename(columns=cols), width="stretch", hide_index=True)


def tab_tests(cfg, exchange, symbol):
    with st.expander("Prova në të kaluarën", expanded=True):
        _backtest_section(cfg, exchange, symbol)
    with st.expander("Ditari i parashikimeve"):
        _journal_section(cfg, exchange, symbol)


def _settings():
    """Kontrollet kryesore lart dhe pjesa tjetër te “Rregullime”. Kthen (cfg, simboli) ose None."""
    base = load_config()
    c = st.columns([1, 1])
    symbol = c[0].text_input("Monedha", base.symbols[0]).strip().upper()
    mode = c[1].radio("Mënyra e robotit", list(MODES), horizontal=True,
                      help="Aktive: hyn lart kur tregu është në ngritje dhe poshtë kur është në rënie, në të gjitha "
                           "monedhat, dhe këmben pozicionet e dobëta me monedha më të forta. E kujdesshme: pak tregti, "
                           "vetëm blerje kur tregu është në ngritje.")
    preset = replace(base, **MODES[mode])
    if MODES[mode]:
        st.caption("Mënyra aktive tregton shpesh, në të dy drejtimet. Në prova (20 monedha, 26 muaj) dha +72% me rënie "
                   "deri në 30%; fitimi erdhi nga blerjet, ndërsa shitjet short vetë dolën me humbje.")
    with st.expander("Rregullime"):
        r = st.columns(2)
        name = r[0].selectbox("Platforma", PLATFORMS, key=f"ex_{mode}",
                              index=PLATFORMS.index(base.exchange) if base.exchange in PLATFORMS else 0)
        timeframe = r[1].selectbox("Intervali i qirinjve", TIMEFRAMES, key=f"tf_{mode}",
                                   index=TIMEFRAMES.index(preset.timeframe) if preset.timeframe in TIMEFRAMES else 2)
        stop = r[0].number_input("Stop-loss % (humbja ku mbyllet)", 0.2, 50.0, float(preset.stop_loss_pct), 0.5,
                                 key=f"sl_{mode}")
        take = r[1].number_input("Fitimi % ku mbyllet (0 = i hapur)", 0.0, 500.0, float(preset.take_profit_pct), 0.5,
                                 key=f"tp_{mode}",
                                 help="Me 0 fitimi lihet të rritet derisa trendi të kthehet. Fitimet e vogla e kanë "
                                      "dobësuar rezultatin në prova.")
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


def render():
    st.subheader("📈 Roboti i kriptove")
    st.caption("Para demo mbi çmime reale. Nuk është këshillë financiare.")
    got = _settings()
    if got is None:
        return
    cfg, exchange, symbol = got
    tabs = st.tabs(["Grafiku", "Roboti", "Tregu", "Prova"])
    for tab, fn, args in zip(tabs, [tab_chart, tab_robot, tab_scan, tab_tests],
                             [(cfg, exchange, symbol), (cfg, exchange), (cfg, exchange), (cfg, exchange, symbol)]):
        with tab:
            try:
                fn(*args)
            except Exception as e:
                st.error(f"Gabim: {e}")
