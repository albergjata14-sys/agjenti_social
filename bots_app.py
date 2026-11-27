"""Ekipi i 6 botëve, më vete nga roboti i kriptove:  streamlit run bots_app.py  (ose dopio-klik te start_bots.bat)."""
import html
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from bots import ALL_BOTS
from bots.chain import MODEL, load_api_key, make_client, run_chain, save_api_key

st.set_page_config(page_title="Ekipi i Botëve 3D", page_icon="🤖", layout="wide")

_DIR = Path(__file__).parent / "bots"
# three.js (MIT) ruhet brenda projektit, që pamja 3D të punojë edhe pa CDN.
SCENE = (_DIR / "scene.html").read_text(encoding="utf-8").replace(
    "__THREE__", (_DIR / "three" / "three.min.js").read_text(encoding="utf-8"))
STATUS_ICON = {"passed": "✅", "rejected": "⛔", "alert": "🚨", "error": "⚠️", "running": "⏳", "idle": "⚪"}


def scene(statuses, height=520):
    state = [{"name": cls.name, "status": s} for cls, s in zip(ALL_BOTS, statuses)]
    page = SCENE.replace("__STATE__", json.dumps(state))      # vetëm emrat dhe gjendjet tona, asgjë nga jashtë
    if hasattr(st, "iframe"):
        st.iframe(page, height=height)
    else:
        components.html(page, height=height)


st.markdown("""
<style>
  .block-container { padding-top: 1.2rem; }
  h1 { background: linear-gradient(90deg,#4dc3ff,#b57bff,#37e29b); -webkit-background-clip: text; color: transparent; }
  .alert-box { border: 1px solid #4dc3ff; border-radius: 12px; padding: 14px 18px; background: #071a2b;
               font-family: ui-monospace, Consolas, monospace; white-space: pre-wrap; color: #e8f6ff; }
</style>""", unsafe_allow_html=True)
st.title("🤖 Ekipi i Botëve")
st.caption("Chart Feeder → Math Geometry → Backtester → Signal Cleaner → Sniper → Alert Manager · "
           f"secili bot me promptin e vet · modeli {MODEL}")

# ---------------------------------------------------------------- çelësi
with st.sidebar:
    st.header("⚙️ Rregullime")
    has_key = bool(load_api_key())
    st.write("Çelësi i Anthropic API:", "✅ i vendosur" if has_key else "❌ mungon")
    new_key = st.text_input("Vendos / ndrysho çelësin", type="password", placeholder="sk-ant-...")
    if st.button("Ruaj çelësin", disabled=not new_key.strip()):
        save_api_key(new_key)
        st.success("U ruajt te bots_anthropic_key.json (vetëm në këtë kompjuter).")
        st.rerun()
    st.markdown("Çelësin e merr te [console.anthropic.com](https://console.anthropic.com/settings/keys).")
    st.divider()
    st.subheader("Promptet")
    for cls in ALL_BOTS:
        bot = cls()
        with st.expander(f"{'✅' if bot.ready else '⏳'} {bot.name}"):
            st.caption(bot.role)
            st.code(bot.prompt or "(pa prompt)", language=None)

# ---------------------------------------------------------------- skena 3D
if "statuses" not in st.session_state:
    st.session_state.statuses = ["idle"] * len(ALL_BOTS)
    st.session_state.result = None
scene_slot = st.empty()
with scene_slot.container():
    scene(st.session_state.statuses)

# ---------------------------------------------------------------- grafiku
left, right = st.columns([1, 1])
with left:
    st.subheader("📥 Jepi grafikun Chart Feeder-it")
    upload = st.file_uploader("Screenshot i grafikut", type=["png", "jpg", "jpeg", "webp"])
    c1, c2 = st.columns(2)
    pair = c1.text_input("Pair", placeholder="BTC/USDT")
    timeframe = c2.text_input("Timeframe", placeholder="4h")
    indicators = st.text_input("Indikatorët (opsionale)", placeholder="Volume Profile, Fibonacci...")
    go = st.button("🚀 Nis zinxhirin", type="primary", width="stretch",
                   disabled=upload is None or not has_key)
    if upload is None:
        st.caption("Ngarko një grafik për të nisur.")
    elif not has_key:
        st.caption("Vendos çelësin e API-së te ⚙️ Rregullime.")
    if upload is not None:
        st.image(upload, width="stretch")

with right:
    st.subheader("🧾 Çfarë tha secili bot")
    live = st.container()

if go:
    statuses = ["idle"] * len(ALL_BOTS)
    st.session_state.result = None

    def on_step(i, step):
        statuses[i] = "running" if step is None else step.status
        with scene_slot.container():
            scene(statuses)
        if step is not None:
            with live:
                with st.expander(f"{STATUS_ICON[step.status]} {step.bot}", expanded=True):
                    st.code(step.output, language=None)

    mime = upload.type if upload.type in ("image/png", "image/jpeg", "image/webp") else "image/png"
    with st.spinner("Botët po punojnë..."):
        result = run_chain(upload.getvalue(), mime, pair, timeframe, indicators, client=make_client(), on_step=on_step)
    st.session_state.statuses = statuses
    st.session_state.result = result
    st.rerun()

result = st.session_state.result
if result:
    with live:
        for step in result.steps:
            with st.expander(f"{STATUS_ICON[step.status]} {step.bot}", expanded=step is result.steps[-1]):
                st.code(step.output, language=None)
        if result.alert:
            st.markdown("#### 🚨 Alarmi")
            st.markdown(f"<div class='alert-box'>{html.escape(result.alert)}</div>", unsafe_allow_html=True)
        elif result.stopped_at:
            st.info(f"Zinxhiri u ndal te **{result.stopped_at}** – grafiku nuk i plotësoi kushtet e tij.")
else:
    with live:
        st.caption("Rezultatet shfaqen këtu, bot pas boti.")

st.caption("⚠️ Nuk është këshillë financiare. Botët gjykojnë nga fotoja e grafikut; Backtester nuk ka të dhëna "
           "historike reale, ndaj vlerësimi i tij është i përafërt.")
