import streamlit as st
from agents import MasterCEO, InstagramAgent

st.set_page_config(page_title="SmartAlbania AI Agents", page_icon="🤖", layout="wide")

st.title("🤖 SmartAlbania - AI Master CEO & Agents Dashboard")
st.markdown("Menaxho agjentët e automatizimit dhe Instagramin direkt nga telefoni yt.")

# Inicializimi i CEO-s
ceo = MasterCEO()
instagram_agent = InstagramAgent()

st.sidebar.header("Paneli i Kontrollit")
menu = st.sidebar.selectbox("Zgjidh Opsionin", ["Dashboard CEO", "Agjenti i Instagramit"])

if menu == "Dashboard CEO":
    st.subheader("Përmbledhja e Agjentëve aktivë")
    for agent_name, desc in ceo.agents.items():
        st.info(f"**{agent_name.upper()}**: {desc}")
        
    st.markdown("---")
    st.subheader("Cakto një Detyrë të Re")
    target_agent = st.selectbox("Zgjidh Agjentin", list(ceo.agents.keys()))
    task_desc = st.text_area("Përshkrimi i Detyrës:")
    
    if st.button("Dërgo Detyrën te Agjenti"):
        if task_desc:
            res = ceo.assign_task(target_agent, task_desc)
            st.success(res)
        else:
            st.warning("Ju lutem shkruani një detyrë.")

elif menu == "Agjenti i Instagramit":
    st.subheader("📸 Agjenti i Instagramit - Krijimi i Postimeve")
    user_prompt = st.text_input("Përshkruaj punën ose pajisjen e instaluar (p.sh. Kamera Hikvision në Tiranë):")
    
    if st.button("Gjenero Caption & Orare me AI"):
        if user_prompt:
            with st.spinner("Agjenti po analizon dhe po përgatit postimin..."):
                post_data = instagram_agent.process_image_and_prepare_post("dummy.jpg", user_prompt)
                
                st.success("Përmbajtja u përgatit me sukses!")
                st.text_area("Sugjerimi i Caption & Hashtag-ve:", value=post_data["caption_suggestion"], height=150)
                st.info(f"⏰ Orari ideal i sugjeruar: **{post_data['best_posting_time']}**")
                
                if st.button("Aprovo & Dërgo për Publikim"):
                    st.balloons()
                    st.success("Postimi u aprovua dhe u shtua në radhën e publikimit!")
        else:
            st.warning("Ju lutem shkruani një përshkrim të shkurtër.")
