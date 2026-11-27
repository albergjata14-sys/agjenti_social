"""Ekipi i 6 botëve, më vete nga roboti i kriptove:  streamlit run bots_app.py  (ose dopio-klik te start_bots.bat).

I njëjti panel gjendet edhe te app.py (Smart Albania), si zgjedhja "Ekipi i Botëve".
"""
import streamlit as st

def _load_bots_panel():
    """Kthen panelin e botëve, duke ringarkuar kodin e tyre kur skedarët kanë ndryshuar (si te roboti i kriptove)."""
    import pathlib
    import sys

    folder = pathlib.Path(__file__).parent / "bots"
    stamp = max(f.stat().st_mtime for f in folder.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    loaded = [name for name in sys.modules if name == "bots" or name.startswith("bots.")]
    if loaded and getattr(sys, "_bots_stamp", None) != stamp:
        for name in loaded:
            del sys.modules[name]
    sys._bots_stamp = stamp
    from bots.ui import render

    return render


st.set_page_config(page_title="Ekipi i Botëve 3D", page_icon="🤖", layout="wide")
_load_bots_panel()()
