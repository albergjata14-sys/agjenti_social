import streamlit as st

# Konfigurimi i faqes
st.set_page_config(page_title="Smart Albania - Master CEO AI", page_icon="👔", layout="centered")

st.title("👔 Smart Albania - Master CEO & AI Architect")
st.write("Sistemi qendror me memorie, gjenerim kodi dhe optimizim promptesh.")

# Inicializimi i memories (Chat History)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Shfaqja e historikut të bisedës (Memory)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Fusha e shkrimit për përdoruesin
if user_prompt := st.chat_input("Shkruaj kërkesën tënde për Master CEO..."):
    # Shto mesazhin e përdoruesit në memorie
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # Logjika e Master CEO për të përpunuar kërkesën
    with st.chat_message("assistant"):
        response_container = st.empty()
        
        # Përgjigjja strategjike e CEO-s
        ceo_reply = (
            f"**Analiza e Master CEO (Smart Albania):**\n"
            f"E kam regjistruar kërkesën: *'{user_prompt}'*.\n\n"
            f"Për ta ekzekutuar këtë në mënyrë perfekte, po hartoj strategjinë teknike dhe tregtare për sistemet e tua të sigurisë dhe automatizimit."
        )
        response_container.markdown(ceo_reply)
        
        # Ruaj përgjigjen në memorie
        st.session_state.messages.append({"role": "assistant", "content": ceo_reply})

# --- MJETET ANËSORE (PROMPT ENGINEERING & CODE GENERATION) ---
st.sidebar.title("🛠️ Mjetet e CEO-s")

if st.sidebar.button("✨ Gjenero Prompt Inxhinierik Perfekt"):
    if st.session_state.messages:
        # Merr mesazhin e fundit të përdoruesit për ta optimizuar
        last_user_msg = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
        context_query = last_user_msg[-1] if last_user_msg else "Zhvillim sistemi për Smart Albania"
        
        engineered_prompt = (
            f"### 🤖 Prompt i Optimizuar Inxhinierik\n"
            f"Kopjo këtë tekst dhe dërgoja modelit të AI për rezultatin më të lartë:\n\n"
            f"```text\n"
            f"Act as an elite Senior Software Architect and Marketing Automation Expert specialized in security systems (Hikvision, Dahua, Smart Home). "
            f"Context: Operating Smart Albania business in Tirana. "
            f"Task: {context_query}. "
            f"Requirements: Provide production-ready, clean, error-free Python/Streamlit code and exact step-by-step execution logic. "
            f"No placeholders, no generic summaries. Deliver professional execution.\n"
            f"```"
        )
        st.sidebar.markdown(engineered_prompt)
    else:
        st.sidebar.warning("Shkruaj një mesazh në fillim që CEO të gjenerojë promptin.")

if st.sidebar.button("💻 Krijo Kod Teknik (Snippet)"):
    code_snippet = (
        "```python\n"
        "# Moduli automatik i Smart Albania për Instagram DM & Leads\n"
        "import requests\n\n"
        "def send_auto_reply(client_phone, message):\n"
        "    print(f'Duke dërguar mesazh te {client_phone}: {message}')\n"
        "    # Lidhja me Meta API / WhatsApp / Instagram\n"
        "    return True\n"
        "```"
    )
    st.sidebar.markdown("### Kodi i Gjeneruar:")
    st.sidebar.markdown(code_snippet)
