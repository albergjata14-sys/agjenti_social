"""Ekipi i 6 botëve, më vete nga roboti i kriptove:  streamlit run bots_app.py  (ose dopio-klik te start_bots.bat).

I njëjti panel gjendet edhe te app.py (Smart Albania), si zgjedhja "Ekipi i Botëve".
"""
import streamlit as st

from bots.ui import render

st.set_page_config(page_title="Ekipi i Botëve 3D", page_icon="🤖", layout="wide")
render()
