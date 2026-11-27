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
from bots.chain import NAMES, run_chain
from bots.chart_feeder.logic import INTERVAL, top_pairs


_DIR = Path(__file__).parent
# three.js (MIT) ruhet brenda projektit, që pamja 3D të punojë edhe pa CDN.
SCENE = (_DIR / "scene.html").read_text(encoding="utf-8").replace(
    "__THREE__", (_DIR / "three" / "three.min.js").read_text(encoding="utf-8"))
ICON = {"passed": "✅", "rejected": "⛔", "alert": "🚨", "error": "⚠️", "running": "⏳", "idle": "⚪"}


def scene(statuses, height=500):
    state = [{"name": n, "status": s} for n, s in zip(NAMES, statuses)]
    page = SCENE.replace("__STATE__", json.dumps(state))      # vetëm emrat dhe gjendjet tona, asgjë nga jashtë
    if hasattr(st, "iframe"):
        st.iframe(page, height=height)
    else:
        components.html(page, height=height)


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

    for k, v in (("bots_results", []), ("bots_last_scan", 0.0), ("bots_selected", None)):
        st.session_state.setdefault(k, v)


    # ---------------------------------------------------------------- paneli (rifreskohet vetë kur skanimi automatik është ndezur)
    @st.fragment(run_every=60 if auto else None)
    def panel():
        due = auto and time.time() - st.session_state.bots_last_scan >= every * 60
        go = st.button("🚀 Skano tani", type="primary") or due
        scene_slot = st.empty()

        if go:
            pairs = custom or cached_top(top_n)
            results = []
            progress = st.progress(0.0, text="Duke filluar...")
            for n, pair in enumerate(pairs):
                progress.progress(n / len(pairs), text=f"{pair} · {timeframe} ({n + 1}/{len(pairs)})")
                r = run_chain(pair, timeframe)
                results.append(r)
                with scene_slot.container():
                    scene(r.statuses)
            progress.empty()
            results.sort(key=lambda r: (not r.alert, -len(r.steps)))      # më lart ato që shkuan më larg
            st.session_state.bots_results = results
            st.session_state.bots_last_scan = time.time()
            st.session_state.bots_selected = results[0].pair if results else None

        results = st.session_state.bots_results
        if not results:
            with scene_slot.container():
                scene(["idle"] * len(NAMES))
            st.info("Shtyp **Skano tani**: Chart Feeder merr vetë grafikët nga MEXC dhe i kalon nëpër botë.")
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
            st.subheader("📊 Sa monedha kaluan te secili bot")
            reached = {n: 0 for n in NAMES}
            for x in results:
                for s in x.steps:
                    if s.status in ("passed", "alert"):
                        reached[s.bot] += 1
            st.dataframe([{"Boti": n, "E kaluan": reached[n]} for n in NAMES], hide_index=True, width="stretch")
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
