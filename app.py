"""Smart Albania - Qendra e Agjentëve AI (aplikacioni Streamlit)."""

import json

import streamlit as st

import storage
from agents import AGENTS, Agent, build_system_prompt, demo_reply
from providers import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    ERROR_PREFIX,
    PROVIDERS,
    get_setting,
    stream_claude,
    stream_gemini,
    stream_ollama,
)

st.set_page_config(page_title="Smart Albania - AI Agents", page_icon="🤖", layout="centered")

st.markdown(
    """
<style>
    .main-title { font-size: 28px; font-weight: 800; margin-bottom: 0; }
    .main-subtitle { font-size: 20px; font-weight: 700; color: #3b82f6; margin-bottom: 4px; }
    .sub-title { font-size: 14px; opacity: 0.7; margin-bottom: 20px; }
    div[data-testid="stButton"] button { border-radius: 14px; min-height: 64px; }
    div[data-testid="stButton"] button[kind="primary"] { animation: bounce 0.6s ease 1; }
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-6px); }
    }
</style>
""",
    unsafe_allow_html=True,
)


def _secrets() -> dict:
    """st.secrets hedh gabim kur nuk ekziston secrets.toml, prandaj e mbështjellim."""
    try:
        return dict(st.secrets)
    except Exception:
        return {}


SECRETS = _secrets()
KEYS = {p.key: get_setting(p.secret_name, SECRETS) for p in PROVIDERS.values() if p.secret_name}

if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = "ceo"

# --- KOKA E FAQES ---
st.markdown("<div class='main-title'>🤖 Smart Albania</div>", unsafe_allow_html=True)
st.markdown("<div class='main-subtitle'>AI Master CEO & Agents Dashboard</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Menaxho agjentët e automatizimit dhe rrjetet sociale direkt nga telefoni yt.</div>",
    unsafe_allow_html=True,
)

# --- ZGJEDHJA E AGJENTIT (butona me ikona) ---
cols = st.columns(len(AGENTS))
for col, agent in zip(cols, AGENTS.values()):
    with col:
        is_selected = st.session_state.selected_agent == agent.key
        if st.button(
            f"{agent.icon}  \n{agent.name}",
            key=f"btn_{agent.key}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
            help=agent.description,
        ):
            st.session_state.selected_agent = agent.key
            st.rerun()

agent: Agent = AGENTS[st.session_state.selected_agent]

# --- PANELI ANËSOR ---
with st.sidebar:
    st.title("🧭 Paneli i Kontrollit")

    # Truri i AI: si parazgjedhje merret i pari që ka çelës (Gemini → Claude), përndryshe Ollama
    provider_keys = list(PROVIDERS)
    default_provider = next((k for k in ("gemini", "claude") if KEYS.get(k)), "ollama")
    provider_key = st.selectbox(
        "🧠 Truri i AI:",
        provider_keys,
        index=provider_keys.index(default_provider),
        format_func=lambda k: PROVIDERS[k].label,
    )
    provider = PROVIDERS[provider_key]

    if provider_key == "ollama":
        ollama_host = st.text_input("Adresa e Ollama:", get_setting("OLLAMA_HOST", SECRETS, DEFAULT_OLLAMA_HOST))
        model = st.text_input(
            "Modeli lokal:",
            get_setting("OLLAMA_MODEL", SECRETS, DEFAULT_OLLAMA_MODEL),
            help="Duhet shkarkuar më parë me `ollama pull <emri>`. Për kodim: qwen2.5-coder",
        ).strip()
        ready = bool(model)
    else:
        labels = list(provider.models)
        preferred = get_setting(f"{provider_key.upper()}_MODEL", SECRETS)
        values = list(provider.models.values())
        index = values.index(preferred) if preferred in values else 0
        model = provider.models[st.selectbox("Modeli:", labels, index=index)]
        ready = bool(KEYS.get(provider_key))
        if ready:
            st.success("I lidhur ✅")
        else:
            st.warning(f"Mungon `{provider.secret_name}` → modaliteti demo. Shiko README.md.")

    web = st.toggle("🌐 Lidhja me internetin", value=True, help=provider.note)
    st.caption(provider.note)

    st.markdown("---")
    st.subheader(f"{agent.icon} {agent.name}")
    history = storage.load_messages(agent.key)
    st.caption(f"{len(history)} mesazhe të ruajtura")

    if history:
        st.download_button(
            "⬇️ Shkarko historikun (JSON)",
            data=json.dumps(history, ensure_ascii=False, indent=2),
            file_name=f"historiku_{agent.key}.json",
            mime="application/json",
            use_container_width=True,
        )
        if st.button("🗑️ Fshi historikun e këtij agjenti", use_container_width=True):
            storage.clear_messages(agent.key)
            st.rerun()

    counts = storage.count_messages()
    if counts:
        st.markdown("---")
        st.caption("Mesazhe për çdo agjent:")
        for a in AGENTS.values():
            st.caption(f"{a.icon} {a.name}: {counts.get(a.key, 0)}")


# --- MEMORIA AFATGJATË (e përbashkët për të gjithë agjentët, menaxhohet nga CEO) ---
notes = storage.load_notes()

if agent.key == "ceo":
    with st.expander(f"🧠 Memoria afatgjatë ({len(notes)} fakte)"):
        st.caption(
            "Fakte për biznesin që i mbajnë mend të gjithë agjentët në çdo bisedë "
            "(p.sh. çmime, produkte, orari, numri i telefonit)."
        )
        for note in notes:
            c1, c2 = st.columns([0.85, 0.15])
            c1.markdown(f"- {note['content']}")
            if c2.button("✖", key=f"del_note_{note['id']}", help="Fshi"):
                storage.delete_note(note["id"])
                st.rerun()
        with st.form("add_note", clear_on_submit=True):
            new_note = st.text_input("Shto një fakt të ri:", placeholder="p.sh. Instalimi i 4 kamerave nis nga 250€")
            if st.form_submit_button("💾 Ruaj në memorie") and new_note.strip():
                storage.add_note(new_note.strip())
                st.rerun()


# --- VEGLAT E SHPEJTA PËR ÇDO AGJENT ---
def queue_prompt(text: str) -> None:
    st.session_state.pending_prompt = text


with st.expander(f"⚡ Veglat e shpejta - {agent.name}"):
    if agent.key == "ceo":
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
        if st.button("Gjenero Prompt Inxhinierik"):
            if last_user:
                st.code(
                    f"Act as an elite AI Architect for Smart Albania. Task: {last_user}. "
                    "Deliver clean, complete, production-ready code with step-by-step instructions.",
                    language=None,
                )
            else:
                st.warning("Shkruani një mesazh në chat në fillim.")
        if st.button("Planifiko javën e marketingut"):
            queue_prompt(
                "Bëj një plan marketingu për javën që vjen për Instagram, Facebook, TikTok dhe "
                "WhatsApp, me detyra konkrete për secilin agjent."
            )
        if st.button("Shqyrto kodin e aplikacionit"):
            queue_prompt(
                "Je arkitekti i këtij aplikacioni Streamlit (app.py, agents.py, providers.py, storage.py). "
                "Propozo 5 përmirësimet më të rëndësishme që duhen bërë tani, me radhë prioriteti."
            )

    elif agent.key == "instagram":
        product = st.text_input("Për çfarë produkti/instalimi do bëjmë postim?", "Kamerat Hikvision ColorVu")
        if st.button("Gjenero Caption & Skenar Reel", disabled=not product.strip()):
            queue_prompt(
                f"Krijo një caption për Instagram, një skenar reel-i dhe hashtag-ët për: {product}"
            )

    elif agent.key == "whatsapp":
        client_msg = st.text_area("Ngjit mesazhin e klientit nga WhatsApp:")
        if st.button("Përgatit përgjigjen", disabled=not client_msg.strip()):
            queue_prompt(f"Klienti shkroi në WhatsApp:\n\n\"{client_msg.strip()}\"\n\nPërgatit përgjigjen.")

    elif agent.key == "facebook":
        fb_topic = st.text_input("Tema e postimit ose komenti për t'iu përgjigjur:")
        c1, c2 = st.columns(2)
        if c1.button("Shkruaj postim", disabled=not fb_topic.strip(), use_container_width=True):
            queue_prompt(f"Shkruaj një postim për faqen e Facebook-ut për: {fb_topic}")
        if c2.button("Përgjigju komentit", disabled=not fb_topic.strip(), use_container_width=True):
            queue_prompt(f"Shkruaj një përgjigje për këtë koment në Facebook:\n\n\"{fb_topic}\"")

    elif agent.key == "tiktok":
        tt_topic = st.text_input("Cili instalim/temë?", "Instalim alarmi në një dyqan")
        if st.button("Gjenero 3 ide për video", disabled=not tt_topic.strip()):
            queue_prompt(f"Më jep 3 ide për video TikTok rreth: {tt_topic}")


# --- ZONA E CHAT-IT ---
st.info(f"Duke biseduar me **{agent.label}** - {agent.description}")

with st.chat_message("assistant", avatar=agent.icon):
    st.markdown(agent.greeting)

for msg in history:
    with st.chat_message(msg["role"], avatar=agent.icon if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])

prompt = st.chat_input(f"Shkruaj një mesazh për {agent.name}...")
prompt = prompt or st.session_state.pop("pending_prompt", None)

if prompt:
    storage.add_message(agent.key, "user", prompt)
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    system_prompt = build_system_prompt(agent, [n["content"] for n in notes])
    with st.chat_message("assistant", avatar=agent.icon):
        if not ready:
            reply = demo_reply(agent, prompt)
            st.markdown(reply)
        elif provider_key == "gemini":
            reply = st.write_stream(stream_gemini(system_prompt, history, KEYS["gemini"], model, web))
        elif provider_key == "claude":
            reply = st.write_stream(stream_claude(system_prompt, history, KEYS["claude"], model, web))
        else:
            reply = st.write_stream(stream_ollama(system_prompt, history, ollama_host, model, web))

    # Gabimet (që fillojnë me ⚠️) shfaqen, por nuk ruhen në historik
    if isinstance(reply, str) and reply.strip() and not reply.startswith(ERROR_PREFIX):
        storage.add_message(agent.key, "assistant", reply)
        st.rerun()
