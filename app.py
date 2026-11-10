import streamlit as st
import datetime

# Konfigurimi i faqes
st.set_page_config(page_title="Smart Albania - Multi-Agent System", page_icon="🤖", layout="centered")

st.title("🤖 Smart Albania - Qendra e Agjentëve AI")
st.write("Sistemi i unifikuar: Master CEO, Memoria e Bisedës dhe Agjentët e Specializuar.")

# Inicializimi i memories globale për bisedat
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- MENYJA ANËSORE (ZGJEDHJA E AGJENTIT) ---
st.sidebar.title("🧭 Paneli i Kontrollit")
selected_agent = st.sidebar.radio(
    "Zgjidh Agjentin / Qendrën:",
    ["Master CEO (Qendra & Memoria)", "Instagram Agent", "WhatsApp Agent", "Facebook Agent", "TikTok Agent", "Crypto Trading Agent"]
)

st.sidebar.markdown("---")

# 1. LOGJIKA E MASTER CEO (ME MEMORIE DHE MJETE INXHINIERIKE)
if selected_agent == "Master CEO (Qendra & Memoria)":
    st.header("👔 Master CEO & Arkitekti i Sistemit")
    st.write("Këtu menaxhohet strategjia e përgjithshme, kujtesa e bisedave dhe mjetet e kodimit.")

    # Shfaqja e historikut të bisedave (Memory)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Fusha e bisedës me CEO
    if user_prompt := st.chat_input("Shkruaj kërkesën tënde për Master CEO..."):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            ceo_reply = (
                f"**Analiza e Master CEO (Smart Albania):**\n"
                f"E kam ruajtur në memorie kërkesën tuaj: *'{user_prompt}'*.\n\n"
                f"Ky hap po integrohet në arkitekturën e përgjithshme për shërbimet e sigurisë dhe automatizimit."
            )
            st.markdown(ceo_reply)
            st.session_state.messages.append({"role": "assistant", "content": ceo_reply})

    # Mjetet shtesë në Sidebar për CEO-n
    st.sidebar.subheader("✨ Mjetet Inxhinierike")
    if st.sidebar.button("Gjenero Prompt Inxhinierik"):
        if st.session_state.messages:
            last_msg = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
            ctx = last_msg[-1] if last_msg else "Smart Albania sistem"
            st.sidebar.markdown(f"**Prompt i Gatshëm:**\n`Act as elite AI Architect for Smart Albania. Task: {ctx}. Deliver clean code.`")
        else:
            st.sidebar.warning("Shkruani një mesazh në chat në fillim.")

    if st.sidebar.button("Krijo Kod Teknik Snippet"):
        st.sidebar.markdown("`# Kod i gjeneruar nga CEO për Smart Albania`")

# 2. ROBOTI I KRIPTOVE (ANALIZË, PARASHIKIM, BACKTEST)
elif selected_agent == "Crypto Trading Agent":
    from crypto_bot.ui import render as render_crypto
    render_crypto()

# 3. LOGJIKA E AGJENTEVE TË TJERË (QË NUK HUMBASIN MË)
else:
    st.header(f"🛠️ Agjenti i Specializuar: {selected_agent}")
    st.write(f"Ky është moduli i dedikuar për menaxhimin e {selected_agent} për Smart Albania.")
    
    # Hapsirë pune specifike për secilin agjent
    if selected_agent == "Instagram Agent":
        st.info("Funksioni aktiv: Menaxhimi i DM automatike dhe gjenerimi i postimeve/reels për Instagram.")
        product_input = st.text_input("Për çfarë produkti/instalimi do të bëjmë postim?", "Kamerat Hikvision ColorVu")
        if st.button("Gjenero Caption & Skenar Reel"):
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
            st.success("Përmbajtja u gjenerua me sukses:")
            st.markdown(f"**Caption:** Siguria me Smart Albania për {product_input}! Na shkruani në DM. 🛡️ #{timestamp}")
            st.markdown("**Skenari i Reel:** Pamje e instalimit -> Shpjegimi i cilësisë -> Call to Action.")
            
    elif selected_agent == "WhatsApp Agent":
        st.info("Funksioni aktiv: Kthimi i menjëhershëm i mesazheve të klientëve për preventiva kamerash dhe alarmesh.")
        client_q = st.text_area("Simulo mesazhin e klientit në WhatsApp:")
        if st.button("Dërgo Përgjigjen Automatike"):
            st.write("Përgjigjja e dërguar: 'Përshëndetje nga Smart Albania! Për preventiv na dërgoni planimetrinë ose specifikimet e ambientit.'")
            
    elif selected_agent == "Facebook Agent":
        st.info("Funksioni aktiv: Sinkronizimi i faqeve të biznesit dhe komenteve.")
        
    elif selected_agent == "TikTok Agent":
        st.info("Funksioni aktiv: Optimizimi i videove të instalimeve teknike për rritjen e audiencës.")
