"""Aplikacioni i robotit të kriptove:  streamlit run crypto_app.py  (ose dopio-klik te start_robot.bat)."""
import streamlit as st


def _load_crypto_panel():
    """Kthen panelin e robotit, duke e ringarkuar kodin e tij kur skedarët kanë ndryshuar.

    Pas një përditësimi, serveri mund të mbajë në memorie modulet e vjetra të `crypto_bot` krahas
    skedarëve të rinj; kjo përzierje jep gabime. Prandaj modulet hiqen nga memoria sa herë ndryshon kodi.
    """
    import pathlib
    import sys

    folder = pathlib.Path(__file__).parent / "crypto_bot"
    stamp = max(f.stat().st_mtime for f in folder.iterdir() if f.is_file())
    loaded = [name for name in sys.modules if name == "crypto_bot" or name.startswith("crypto_bot.")]
    if loaded and getattr(sys, "_crypto_bot_stamp", None) != stamp:
        for name in loaded:
            del sys.modules[name]
        st.cache_resource.clear()
        st.cache_data.clear()
    sys._crypto_bot_stamp = stamp
    from crypto_bot.ui import render

    return render


st.set_page_config(page_title="Roboti i kriptove", page_icon="📈", layout="wide")
_load_crypto_panel()()
