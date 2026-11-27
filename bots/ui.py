"""Paneli i ekipit të 6 botëve. Përdoret nga bots_app.py (faqe më vete) dhe nga app.py (Smart Albania).

Falas, pa API të AI-së: grafiku merret vetë nga MEXC dhe çdo bot zbaton rregullat e promptit të vet me kod.
"""
import html
import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from bots import ALL_BOTS
from bots.alert_manager.logic import recent_alerts
from bots import paper
from bots._base import fmt
from bots.chain import NAMES
from bots.chart_feeder.logic import INTERVAL, MS, top_pairs


_DIR = Path(__file__).parent
_ASSETS = {}


def _asset(name):
    """Lexon skedarin HTML sa herë ndryshon në disk (pas një përditësimi nuk mbetet versioni i vjetër në memorie)."""
    path = _DIR / name
    stamp = path.stat().st_mtime
    if _ASSETS.get(name, (None,))[0] != stamp:
        text = path.read_text(encoding="utf-8")
        if name == "scene.html":   # three.js (MIT) ruhet brenda projektit, që pamja 3D të punojë edhe pa CDN
            text = text.replace("__THREE__", (_DIR / "three" / "three.min.js").read_text(encoding="utf-8"))
        _ASSETS[name] = (stamp, text)
    return _ASSETS[name][1]
ICON = {"passed": "✅", "rejected": "⛔", "alert": "🚨", "error": "⚠️", "running": "⏳", "idle": "⚪"}


def scene(statuses, height=500):
    state = [{"name": n, "status": s} for n, s in zip(NAMES, statuses)]
    page = _asset("scene.html").replace("__STATE__", json.dumps(state))      # vetëm emrat dhe gjendjet tona, asgjë nga jashtë
    if hasattr(st, "iframe"):
        st.iframe(page, height=height)
    else:
        components.html(page, height=height)


AGENT_STYLE = {   # ikona dhe ngjyra e çdo agjenti në panel
    "Chart Feeder": ("C", "#4dc3ff"), "Math Geometry": ("∠", "#b57bff"), "Backtester": ("B", "#ffcf5a"),
    "Signal Cleaner": ("F", "#2ee6a0"), "Sniper": ("◎", "#ff7ab6"), "Alert Manager": ("!", "#ff4d6a"),
    "Size Calc": ("%", "#ff9a4d"), "Exit Manager": ("E", "#4dffd8"),
}


def dashboard_data(results, state, tf, brain):
    reached = {n: 0 for n in NAMES}
    for r in results:
        for s in r.steps:
            if s.status in ("passed", "alert"):
                reached[s.bot] += 1
    n = len(results)
    summ = paper.summary(state)
    stats = {
        "Chart Feeder": f"{reached['Chart Feeder']} grafikë · MEXC" if n else "pret skanimin",
        "Math Geometry": f"{reached['Math Geometry']}/{n} setup Strong+",
        "Backtester": f"{reached['Backtester']}/{n} kaluan provën",
        "Signal Cleaner": f"{reached['Signal Cleaner']}/{n} të pastra",
        "Sniper": f"{reached['Sniper']} SNIPER SIGNAL",
        "Alert Manager": f"{len(recent_alerts(200))} alarme gjithsej",
        "Size Calc": f"rrezik {paper.RISK_PCT:g}% · max {paper.MAX_POS_PCT:g}%",
        "Exit Manager": f"{summ['open']} hapur · BE +{paper.BE_AT_R:g}R",
    }
    on = dict(reached)
    on["Size Calc"] = summ["open"] + summ["orders"]
    on["Exit Manager"] = summ["open"]
    agents = [{"name": k, "icon": AGENT_STYLE[k][0], "color": AGENT_STYLE[k][1], "stat": v,
               "state": "on" if on.get(k) else ""} for k, v in stats.items()]
    chips = []
    for r in results:
        if r.chart is None:
            continue
        c = r.chart.df["close"]
        back = max(1, min(len(c) - 1, int(86_400_000 / MS[r.timeframe])))
        chips.append({"pair": r.pair, "chg": float(c.iloc[-1] / c.iloc[-1 - back] - 1) * 100,
                      "on": any(s.bot == "Math Geometry" and s.status == "passed" for s in r.steps)})
    for key in {p["key"] for p in state["positions"]}:
        if not any(ch["pair"] == key.split("|")[0] for ch in chips):
            chips.append({"pair": key.split("|")[0], "chg": 0.0, "on": True})
    positions = [{"pair": p["pair"], "side": p["side"], "entry": fmt(p["entry"]),
                  "upnl": p["qty"] * (state["last_prices"].get(p["key"], p["entry"]) - p["entry"]) * p["side"]}
                 for p in state["positions"]]
    orders = [{"pair": o["pair"], "side": o["side"], "entry": fmt(o["entry"])} for o in state["orders"]]
    closed = [{"pair": c["pair"], "pnl": c["pnl"], "r": c["r"], "why": c["why"]} for c in state["closed"]]
    return {"tf": tf, "started": state["started"], "summary": summ, "equity": state["equity"][-600:],
            "chips": chips, "agents": agents, "brain": brain, "positions": positions, "orders": orders,
            "closed": closed[-200:], "lastClosed": closed[-1] if closed else None, "events": state["events"][::-1][:40]}


def dashboard(results, state, tf, brain):
    page = _asset("dashboard.html").replace("__DATA__", json.dumps(dashboard_data(results, state, tf, brain)).replace("</", "<\\/"))
    if hasattr(st, "iframe"):
        st.iframe(page, height="content")         # lartësia ndjek përmbajtjen (kompjuter ose telefon)
    else:
        components.html(page, height=1300, scrolling=True)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_top(n):
    return top_pairs(n)


def render():
    """Vizaton gjithë panelin (pa st.set_page_config, që të futet edhe brenda një aplikacioni tjetër)."""

    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; }
      h1 { background: linear-gradient(90deg,#4dc3ff,#b57bff,#37e29b); -webkit-background-clip: text; color: transparent; }
      .alert-box { border: 1px solid #4dc3ff; border-radius: 12px; padding: 12px 16px; background: #071a2b; margin-bottom: 8px;
                   font-family: ui-monospace, Consolas, monospace; white-space: pre-wrap; color: #e8f6ff; font-size: 14px; }
    </style>""", unsafe_allow_html=True)
    st.title("🤖 Ekipi i Botëve")
    st.caption("Chart Feeder → Math Geometry → Backtester → Signal Cleaner → Sniper → Alert Manager · "
               "grafiku merret vetë nga MEXC · falas, pa API të AI-së")

    # ---------------------------------------------------------------- rregullimet
    with st.sidebar:
        st.header("⚙️ Skanimi")
        tf_list = list(INTERVAL)
        timeframe = st.selectbox("Timeframe", tf_list, index=tf_list.index("4h"))
        source = st.radio("Cilat monedha", ["Më të tregtuarat në MEXC", "Të zgjedhurat nga unë"])
        top_n, custom = 10, []
        if source.startswith("Më"):
            top_n = st.slider("Sa monedha", 3, 30, 10)
        else:
            custom = [p.strip() for p in st.text_area("Çiftet (një për rresht)", "BTC/USDT\nETH/USDT\nSOL/USDT").splitlines()
                      if p.strip()]
        auto = st.toggle("🔁 Skano automatikisht", value=False)
        every = st.number_input("Çdo sa minuta", 5, 240, 30, step=5, disabled=not auto)
        st.caption("Skanimi automatik punon sa kohë është e hapur kjo faqe. Për ta lënë gjithë kohën ndezur pa faqe: "
                   "`python -m bots skano --top 10 --tf 4h --cdo 30`")
        st.divider()
        st.subheader("Promptet (rregullat e botëve)")
        for cls in ALL_BOTS:
            bot = cls()
            with st.expander(bot.name):
                st.caption(bot.role)
                st.code(bot.prompt or "(pa prompt)", language=None)

    for k, v in (("bots_results", []), ("bots_last_scan", 0.0), ("bots_selected", None), ("bots_brain", "dëgjon")):
        st.session_state.setdefault(k, v)

    with st.sidebar:
        st.divider()
        st.subheader("💵 Tregtia demo")
        state = paper.load()
        levels = list(paper.LEVELS)
        level = st.radio("Botët hyjnë në demo kur", levels, format_func=paper.LEVELS.get,
                         index=levels.index(state.get("level", "geometry")))
        if level != state.get("level"):
            state["level"] = level
            paper.save(state)
        st.caption("Math Geometry: hyn sa herë ka setup Strong+, që të shohim nëse gjeometria fiton vërtet. "
                   "SNIPER SIGNAL: vetëm sinjalet që kalojnë të gjithë botët (shumë të rralla).")
        if st.button("↺ Rinis demon nga $1,000"):
            paper.save(paper.new_state(level))
            st.rerun()

    # ---------------------------------------------------------------- paneli (rifreskohet vetë kur skanimi automatik është ndezur)
    @st.fragment(run_every=60 if auto else None)
    def panel():
        due = auto and time.time() - st.session_state.bots_last_scan >= every * 60
        go = st.button("🚀 Skano tani", type="primary") or due
        tab_dash, tab_3d = st.tabs(["📊 Paneli", "🤖 Zinxhiri 3D"])
        with tab_dash:
            dash_slot = st.empty()
        with tab_3d:
            scene_slot = st.empty()

        if go:
            pairs = custom or cached_top(top_n)
            progress = st.progress(0.0, text="Duke filluar...")
            started = time.time()
            done = []

            def on_result(r):
                done.append(r)
                progress.progress(min(1.0, len(done) / len(pairs)), text=f"{r.pair} · {timeframe} ({len(done)}/{len(pairs)})")

            results, state_now = paper.cycle(pairs, timeframe, on_result=on_result)
            progress.empty()
            results.sort(key=lambda r: (not r.alert, -len(r.steps)))      # më lart ato që shkuan më larg
            st.session_state.bots_results = results
            st.session_state.bots_last_scan = time.time()
            st.session_state.bots_selected = results[0].pair if results else None
            bought = any(e[0] >= started and "urdhër demo" in e[1] for e in state_now["events"])
            st.session_state.bots_brain = "blen" if bought else ("mban pozicione" if state_now["positions"] else "dëgjon")

        results = st.session_state.bots_results
        state_now = paper.load()
        with dash_slot.container():
            dashboard(results, state_now, results[0].timeframe if results else timeframe, st.session_state.bots_brain)
        if not results:
            with scene_slot.container():
                scene(["idle"] * len(NAMES))
            st.info("Shtyp **Skano tani**: Chart Feeder merr vetë grafikët nga MEXC, botët i kalojnë dhe tregtojnë në demo.")
            return

        when = datetime.fromtimestamp(st.session_state.bots_last_scan).strftime("%H:%M")
        nxt = max(0, int((st.session_state.bots_last_scan + every * 60 - time.time()) / 60))
        st.caption(f"Skanimi i fundit: {when} · {results[0].timeframe} · {len(results)} monedha"
                   + (f" · tjetri pas ~{nxt} min" if auto else ""))

        labels = {r.pair: f"{'🚨' if r.alert else ICON[r.steps[-1].status] if r.steps else '⚪'} {r.pair} – "
                          f"{'ALARM' if r.alert else 'u ndal te ' + r.stopped_at}" for r in results}
        keys = list(labels)
        pick = st.selectbox("Shiko zinxhirin e", keys, format_func=labels.get,
                            index=keys.index(st.session_state.bots_selected) if st.session_state.bots_selected in keys else 0)
        st.session_state.bots_selected = pick
        r = next(x for x in results if x.pair == pick)
        with scene_slot.container():
            scene(r.statuses)

        left, right = st.columns([3, 2])
        with left:
            st.subheader(f"🧾 {r.pair} · {r.timeframe}")
            for step in r.steps:
                with st.expander(f"{ICON[step.status]} {step.bot}", expanded=step is r.steps[-1]):
                    st.code(step.output, language=None)
        with right:
            st.subheader("🚨 Alarmet e fundit")
            alerts = recent_alerts(10)
            if not alerts:
                st.caption("Ende asnjë alarm. Sniper miraton vetëm setup-et më të mira – mund të kalojnë ditë pa asnjë.")
            for a in alerts:
                st.caption(f"{datetime.fromtimestamp(a['time']):%Y-%m-%d %H:%M} · {a.get('timeframe', '')}")
                st.markdown(f"<div class='alert-box'>{html.escape(a['alert'])}</div>", unsafe_allow_html=True)

    panel()
    st.caption("⚠️ Nuk është këshillë financiare. Të dhënat: MEXC spot. Backtester provon rregullat e Math Geometry "
               "në historinë reale të çdo monedhe (komisione + rrëshqitje 0.15%).")
