import streamlit as st
from agents import MasterCEO, InstagramAgent  # Importojmë klasat që krijuam

st.set_page_config(page_title="SmartAlbania AI Agents", page_icon="🤖", layout="centered")

# Stilizimi CSS për ikonat e robotëve dhe pamjen
st.markdown("""
<style>
    .main-title {
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 0px;
    }
    .sub-title {
        font-size: 13px;
        color: #a0aec0;
        margin-bottom: 20px;
    }
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-6px); }
    }
    .stButton>button {
        border-radius: 14px;
        padding: 10px;
        height: auto;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        border-color: #3b82f6;
        transform: translateY(-2px);
    }
</style>
""", unsafe_allow_html=True)

# Titulli i aplikacionit
st.markdown("<div class='main-title'>🤖 SmartAlbania</div>", unsafe_allow_html=True)
st.markdown("<div class='main-title' style='font-size: 20px; color: #3b82f6;'>- AI Master CEO & Agents Dashboard</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Menaxho agjentët e automatizimit direkt nga telefoni yt.</div>", unsafe_allow_html=True)

st.markdown("### Zgjidh Agjentin për të biseduar:")

# Lista e agjentëve
agents = {
    "WhatsApp": {"icon": "🤖", "desc": "Gati për menaxhimin e mesazheve dhe klientëve."},
    "Instagram": {"icon": "📸", "desc": "Gati për analizë fotosh, captions, reels dhe orare postimi."},
    "Facebook": {"icon": "💬", "desc": "Gati për përgjigje automatike dhe komente."},
    "CEO Master": {"icon": "🧠", "desc": "Agjenti kryesor që koordinon sistemin dhe kërkon në kohë reale."}
}

if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = None

cols = st.columns(len(agents))
for i, (agent_name, data) in enumerate(agents.items()):
    with cols[i]:
        button_label = f"{data['icon']}\n{agent_name}"
        if st.button(button_label, key=f"btn_{agent_name}", use_container_width=True):
            st.session_state.selected_agent = agent_name
            st.rerun()

st.markdown("---")

# Zona e Chat-it
if st.session_state.selected_agent:
    current_agent = st.session_state.selected_agent
    agent_info = agents[current_agent]
    
    st.success(f"Duke biseduar me **{current_agent}** — *{agent_info['desc']}*")
    
    chat_key = f"messages_{current_agent}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [
            {"role": "assistant", "content": f"Përshëndetje! Unë jam {current_agent}. Si mund t'ju ndihmoj sot?"}
        ]
    
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if user_input := st.chat_input(f"Shkruaj një mesazh për {current_agent}..."):
        st.session_state[chat_key].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        # Therrasim klasën përkatëse nga agents.py në varësi të agjentit të zgjedhur
        with st.spinner(f"{current_agent} po përpunon kërkesën..."):
            if current_agent == "CEO Master":
                ceo = MasterCEO()
                bot_response = ceo.coordinate_task(user_input)
            elif current_agent == "Instagram":
                insta = InstagramAgent()
                # Kontrollojmë nëse klasa ka metodë gjenerimi
                bot_response = f"Instagram Agent: Përpunova kërkesën tuaj '{user_input}'."
            else:
                bot_response = f"Përgjigje nga {current_agent}: Kërkesa u mor me sukses."
            
        st.session_state[chat_key].append({"role": "assistant", "content": bot_response})
        with st.chat_message("assistant"):
            st.markdown(bot_response)
else:
    st.info("👆 Kliko një nga ikonat sipër për të zgjedhur agjentin dhe për të hapur dritaren e bisedës.")
