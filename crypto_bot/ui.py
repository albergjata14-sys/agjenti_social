"""Paneli Streamlit i robotit të kriptove (thirret nga app.py)."""
import pandas as pd
import streamlit as st

from .backtest import backtest
from .bot import scan
from .config import load_config
from .data import fetch_candles, make_exchange
from .strategy import score_frame


def render():
    st.header("📈 Crypto Trading Agent")
    st.caption("Analizë teknike, parashikim dhe testim strategjie. Nuk është këshillë financiare – "
               "parashikimet janë vlerësime, jo garanci.")
    base = load_config()
    c1, c2, c3 = st.columns(3)
    exchange_name = c1.text_input("Platforma", base.exchange)
    symbol = c2.text_input("Monedha", base.symbols[0])
    timeframe = c3.selectbox("Intervali", ["15m", "1h", "4h", "1d"], index=1)
    c1, c2, c3 = st.columns(3)
    tp = c1.number_input("Fitimi (take-profit) %", 0.1, 500.0, float(base.take_profit_pct), 0.5)
    sl = c2.number_input("Humbja (stop-loss) %", 0.1, 99.0, float(base.stop_loss_pct), 0.5)
    trail = c3.number_input("Trailing stop % (0 = fikur)", 0.0, 99.0, float(base.trailing_stop_pct), 0.5)
    cfg = load_config(exchange=exchange_name, symbols=[symbol], timeframe=timeframe,
                      take_profit_pct=tp, stop_loss_pct=sl, trailing_stop_pct=trail)

    b1, b2, b3 = st.columns(3)
    try:
        if b1.button("Analizo", width="stretch"):
            ex = make_exchange(cfg)
            df = fetch_candles(ex, symbol, timeframe, cfg.candles)
            a = scan(ex, cfg, [symbol])[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("Çmimi", f"{a['price']:.6g}")
            m2.metric("Sinjali", a["signal"], f"{a['score']:+.0f} pikë")
            m3.metric("Drejtimi", a["direction"], f"besueshmëria {a['confidence']:.0f}%")
            st.line_chart(score_frame(df)[["close", "ema20", "ema50", "ema200"]].tail(200))
            f, p = a["forecast"], a["plan"]
            st.markdown("**Arsyet:**\n" + "\n".join(f"- {r}" for r in a["reasons"]))
            st.markdown(
                f"**Parashikimi ({f['horizon_candles']} qirinj):** ~{f['expected']:.6g} "
                f"(brezi {f['low']:.6g} – {f['high']:.6g})\n\n"
                f"**Mbështetja / Rezistenca:** {a['support']:.6g} / {a['resistance']:.6g}\n\n"
                f"**Plani:** hyrje {p['entry']:.6g} · fitim {p['take_profit']:.6g} · stop {p['stop_loss']:.6g}")
        if b2.button("Skano tregun", width="stretch"):
            cfg.scan_market = True
            with st.spinner("Duke skanuar tregun..."):
                rows = scan(make_exchange(cfg), cfg)
            st.dataframe(pd.DataFrame([{"Monedha": r["symbol"], "Çmimi": r["price"], "Pikët": r["score"],
                                        "Sinjali": r["signal"], "Drejtimi": r["direction"]} for r in rows]),
                         width="stretch", hide_index=True)
        if b3.button("Backtest", width="stretch"):
            df = fetch_candles(make_exchange(cfg), symbol, timeframe, max(cfg.candles, 1000))
            r = backtest(df, cfg)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kthimi", f"{r['return_pct']:+.2f}%")
            m2.metric("Tregti", r["trades"])
            m3.metric("Fituese", f"{r['win_rate_pct']:.0f}%")
            m4.metric("Rënia maks.", f"{r['max_drawdown_pct']:.1f}%")
            st.line_chart(pd.Series(r["equity"], name="Kapitali"))
            if r["trade_list"]:
                st.dataframe(pd.DataFrame(r["trade_list"]), width="stretch", hide_index=True)
    except Exception as e:
        st.error(f"Gabim: {e}")
    st.info("Për ta lënë robotin të tregtojë vetë: `python -m crypto_bot nis` (simulim) — shih README.md.")
