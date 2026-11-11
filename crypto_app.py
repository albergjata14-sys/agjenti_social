"""Aplikacioni i robotit të kriptove:  streamlit run crypto_app.py  (ose dopio-klik te start_robot.bat)."""
import streamlit as st

from crypto_bot.ui import render

st.set_page_config(page_title="Roboti i kriptove", page_icon="📈", layout="wide")
render()
