import streamlit as st

st.set_page_config(page_title="SmartAlbania AI Agents", page_icon="🤖", layout="centered")

# Stilizimi CSS për kokat e robotëve, animacionin e klikimit dhe pamjen e përgjithshme
st.markdown("""
<style>
    .main-title {
        font-size: 28px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 0px;
    }
    .sub-title {
        font-size: 14px;
        color: #a0aec0;
        margin-bottom: 25px;
    }
    .agents-container {
        display: flex;
        justify-content: space-around;
        gap: 15px;
        margin-bottom: 30px;
        overflow-x: auto;
        padding: 10px 0;
    }
    .agent-card {
        background-color: #1e293b;
        border: 2px solid #334155;
        border-radius: 16px;
        padding: 15px 10px;
        text-align: center;
        cursor: pointer;
        width: 100px;
        transition: all 0.3s ease;
    }
    .agent-card:hover {
        border-color: #3b82f6;
        transform: translateY(-3px);
    }
    /* Animacioni i lëvizjes lart-poshtë kur zgjidhet */
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
    .agent-card.active {
        border-color: #3b82f6;
        background-color: #1d4ed8;
        animation: bounce 0.5s ease infinite;
    }
    .robot-icon {
        font-size: 32px;
        margin-bottom: 8px;
    }
    .agent-name {
        font-size: 12px;
        font-weight: 600;
        color: #f8fafc;
    }
</style>
""", unsafe_allow_html=True)

# Pjesa e titullit
st.markdown("<div class='main-title'>🤖 SmartAlbania</div>", unsafe_allow_html=True)
st.markdown("<div class='main-title' style='font-size: 22px; color: #3b82f6;'>- AI Master CEO & Agents Dashboard</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Menaxho agjentët e automatizimit dhe Instagramin direkt nga telefoni yt.</div>", unsafe_allow_html=True)

st.markdown("### Zgjidh Agjentin për të biseduar:")

# Lista e agjentëve tanë me ikonat dhe përshkrimet
agents = {
    "WhatsApp": {"icon": "🤖", "desc": "Gati për menaxhimin e mesazheve dhe klientëve."},
    "Instagram": {"icon": "📸", "desc": "Gati për analizë fotosh, captions, reels dhe orare postimi."},
    "Facebook": {"icon": "💬", "desc": "Gati për përgjigje automatike dhe komente."},
    "CEO Master": {"icon": "🧠", "desc": "Agjenti kryesor që koordinon të gjithë sistemin."}
}

# Inicializimi i gjendjes për agjentin e zgjedhur
if "selected_agent" not in st.session_state:
    st.session_state.selected_agent = None

# Krijimi i rreshtit me ikona (koka robotësh)
cols = st.columns(len(agents))
for i, (agent_name, data) in enumerate(agents.items()):
    with cols[i]:
        is_selected = st.session_state.selected_agent == agent_name
        active_class = "active" if is_selected else ""
        
        # Butoni interaktiv në formë koke robotit
        clicked = st.button(f"{data['icon']}\n{agent_name}", key=f"btn_{agent_name}", use_container_width=True)
        if clicked:
            st.session_state.selected_agent = agent_name
            st.rerun()

st.markdown("---")

# Zona e Chat-it e cila shfaqet vetëm pasi të jetë zgjedhur një agjent
if st.session_state.selected_agent:
    current_agent = st.session_state.selected_agent
    agent_info = agents[current_agent]
    
    st.success(qe_mesazhi := f"Duke biseduar me **{current_agent}** ({agent_info['desc']})")
    
    # Historia e mesazheve për sesionin e chat-it
    chat_key = f"messages_{current_agent}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [{"role": "assistant", "content": f"Përshëndetje! Unë jam agjenti yt i {current_agent}. Si mund të të ndihmoj sot?"}]
    
    # Shfaq mesazhet ekzistuese
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Kutia e shkrimit të mesazhit të ri
    if user_input := st.chat_input(f"Shkruaj një mesazh për {current_agent}..."):
        st.session_state[chat_key].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
            
        # Përgjigjja simuluese ose lidhja me Olla/Claude API që ke krijuar
        bot_response = f"Përgjigjja nga {current_agent}: E mora porosinë tënde për '{user_input}'. Po e ekzekutoj tani!"
        st.session_state[chat_key].append({"role": "assistant", "content": bot_response})
        with st.chat_message("assistant"):
            st.markdown(bot_response)
else:
    st.info("👆 Kliko një nga ikonat e agjentëve më sipër për të hapur panelin e bisedës.")