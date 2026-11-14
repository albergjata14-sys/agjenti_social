"""Analisti i vazhdueshëm: kërkon, studion dhe informon tregtarin pa ndalur.

Në çdo rreth:
  * çdo `radar_minutes`: rifreskon radarin e monedhave në trend dhe njofton kur hyn një monedhë e re ndër 5 më të fortat;
  * çdo `research_minutes`: merr qirinjtë e rinj (vetëm pjesën që mungon) dhe provon `lab_batch` strategji të reja;
  * çdo `analyst_hours`: rivlerëson strategjitë e ekipit, shqyrton turneun dhe shkruan rekomandimin që lexon tregtari.
Të gjitha ruhen në kujtesë, që të shihen te paneli.
"""
import json
import os
import time
from pathlib import Path

import pandas as pd

from . import cache, lab, memory, notify, radar
from .analyst import (focus_bars, candidate_config, choose, evaluate, forward_results, load_recommendation,
                      tournament_candidates)
from .data import top_symbols


def status(cfg):
    p = Path(cfg.research_file)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except ValueError:
        return None


def is_alive(cfg, st=None) -> bool:
    st = st or status(cfg) or {}
    return time.time() - st.get("heartbeat", 0) < max(cfg.research_minutes, cfg.radar_minutes) * 60 * 2 + 300


def _save(cfg, st):
    st["heartbeat"] = time.time()
    tmp = Path(cfg.research_file + ".tmp")
    tmp.write_text(json.dumps(st, indent=2, ensure_ascii=False))
    os.replace(tmp, cfg.research_file)


def _frames(exchange, cfg, symbols):
    from .analyst import load_frames

    if cfg.focus:   # afate të shkurtra dhe të gjata (deri në 3 vjet): 15 minuta, 1 orë, 4 orë dhe 1 ditë
        # ari ka më pak histori (kontrata e re), ndaj pranohen edhe historitë më të shkurtra
        return {tf: load_frames(exchange, cfg, symbols, tf, n, fetch=cache.candles, min_frac=0.15)
                for tf, n in focus_bars(cfg).items()}
    return {"4h": load_frames(exchange, cfg, symbols, "4h", 5000, fetch=cache.candles),
            "1h": load_frames(exchange, cfg, symbols, "1h", 4000, fetch=cache.candles)}


def research_once(exchange, cfg, st: dict, log=print, now=None) -> dict:
    """Një rreth i analistit: bën ato punë që u ka ardhur radha. Kthen gjendjen e përditësuar."""
    now = now or time.time()
    if now - st.get("last_radar", 0) >= cfg.radar_minutes * 60:
        try:
            rd, entered = radar.update(exchange, cfg)
            for side, word in (("up", "📈 në trend rritës"), ("down", "📉 në trend rënës")):
                for r in entered[side]:
                    notify.emit(cfg, "radar", r["symbol"], f"Radari: {r['symbol']} {word} (14 ditë {r['m14']:+.1f}%, "
                                                           f"7 ditë {r['m7']:+.1f}%)")
            st.update(last_radar=now, radar_up=[r["symbol"] for r in rd["up"][:5]],
                      radar_down=[r["symbol"] for r in rd["down"][:5]])
        except Exception as e:
            log(f"Radari dështoi: {e}")
    # Fokus: në çdo qiri të ri (p.sh. çdo 15 minuta, 20 sekonda pas mbylljes) raporti i trendit dhe sinjalet.
    slot = int((now - 20) // (cfg.trend_minutes * 60)) if cfg.focus and cfg.trend_minutes else None
    if slot is not None and slot != st.get("trend_slot"):
        st["trend_slot"] = slot
        try:
            send_trend(exchange, cfg, st, log)
        except Exception as e:
            log(f"Raporti i trendit dështoi: {e}")
    if (slot is not None and st.get("signal_slot") != slot) or (slot is None and
                                                                 now - st.get("last_signals", 0) >= cfg.radar_minutes * 60):
        try:
            send_signals(exchange, cfg, st, log)
        except Exception as e:
            log(f"Sinjalet dështuan: {e}")
        st["last_signals"], st["signal_slot"] = now, slot
    rec_due = now - st.get("last_rec", 0) >= cfg.analyst_hours * 3600 or not load_recommendation(cfg)
    lab_due = now - st.get("last_lab", 0) >= cfg.research_minutes * 60
    if not (rec_due or lab_due):
        return st
    symbols = list(cfg.symbols) if cfg.focus else top_symbols(exchange, cfg.quote, cfg.research_symbols)
    if cfg.market_filter_symbol and cfg.market_filter_symbol not in symbols:
        symbols.append(cfg.market_filter_symbol)
    st["status"] = "duke marrë qirinjtë e rinj"
    _save(cfg, st)
    frames = _frames(exchange, cfg, symbols)
    if lab_due:
        st["status"] = "laboratori po provon strategji"
        _save(cfg, st)
        rows = lab.run_lab(frames, cfg, n=cfg.lab_batch, log=lambda *_: None)
        passed = sum(1 for r in rows if r.get("eligible"))
        memory.log_event(cfg, "laboratori", detail={"tested": len(rows), "passed": passed})
        st["tested_total"] = st.get("tested_total", 0) + len(rows)
        st["passed_total"] = st.get("passed_total", 0) + passed
        st["last_lab"] = now
        log(f"Laboratori provoi {len(rows)} strategji ({passed} fituan në të dyja periudhat); gjithsej {st['tested_total']}.")
    if rec_due:
        st["status"] = "analisti po rivlerëson ekipin"
        _save(cfg, st)
        for name, change in lab.review_tournament(cfg, forward_results(cfg)):
            msg = f"🧪 “{name}” {'hyri në ekip pas turneut' if change == 'ekip' else 'u hoq nga turneu'}"
            notify.emit(cfg, "laboratori", "", msg)
            log(msg)
        old = load_recommendation(cfg) or {}
        rows = evaluate(frames, cfg, tournament_candidates(cfg))
        rec = choose(rows, forward_results(cfg), cfg.max_active)
        rec.update({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "ts": now, "test_days": cfg.test_days,
                    "symbols": len(frames["4h"]), "results": rows, "forward": forward_results(cfg),
                    "lab_tested": st.get("tested_total", 0), "lab_passed": st.get("passed_total", 0)})
        Path(cfg.recommendation_file).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        names = {r["id"]: r["name"] for r in rows}
        if (set(rec["approved"]), set(rec["provisional"])) != (set(old.get("approved", [])), set(old.get("provisional", []))):
            lines = [f"✅ {names[i]}" for i in rec["approved"]] + [f"🟡 {names[i]} (provizore, gjysma e rrezikut)"
                                                                   for i in rec["provisional"]]
            notify.emit(cfg, "analist", "", "🧠 Analisti: " + ("pushim, asnjë strategji nuk fiton tani" if rec["action"] == "pause"
                                                              else "strategjitë aktive:\n" + "\n".join(lines)))
        st["last_rec"] = now
        log(f"Analisti: {rec['name']} | miratuar: {', '.join(rec['approved']) or 'asnjë'} | provizore: "
            f"{', '.join(rec['provisional']) or 'asnjë'}")
    st["status"] = "në pritje të rrethit tjetër"
    return st


def trend_config(cfg):
    """Rregullimet e raportit të trendit: strategjia shumë-intervalëshe mbi qirinjtë e `trend_minutes`."""
    from dataclasses import replace

    tf = {15: "15m", 30: "30m", 60: "1h"}.get(int(cfg.trend_minutes), "15m")
    return replace(cfg, strategy="mtf", timeframe=tf, allow_short=True)


def trend_report(df, cfg, symbol: str) -> dict:
    """Trendi i çdo intervali, vendimi dhe nivelet (hyrje, stop, objektiv) që roboti i llogarit vetë."""
    from .config import display
    from .mtf import ARROWS, LABELS, trend_text
    from .strategy import analyze

    tcfg = trend_config(cfg)
    a = analyze(df, tcfg, symbol)
    mtf, price, ind = a["mtf"], a["price"], a["indicators"]
    up, down = sum(v > 0 for v in mtf.values()), sum(v < 0 for v in mtf.values())
    small = 1 if price > ind["ema20"] and ind["ema20"] > ind["ema50"] else -1 if price < ind["ema20"] and ind["ema20"] < ind["ema50"] else 0
    need = min(tcfg.mtf_min_align, len(mtf))
    side = 1 if up >= need and not down else -1 if down >= need and not up else 0
    if a["signal"] == "BLI":
        verdict = "🟢 SINJAL BLERJE: të gjitha intervalet lart dhe 15 min e konfirmoi"
    elif a["signal"] == "SHORT":
        verdict = "🔻 SINJAL SHITJE (short): të gjitha intervalet poshtë dhe 15 min e konfirmoi"
    elif side:
        verdict = (f"{'🟢 Trend rritës' if side > 0 else '🔻 Trend rënës'} në të gjitha intervalet · pritet "
                   f"{'tërheqja dhe rikthimi' if tcfg.mtf_trigger == 'pullback' else 'thyerja'} në {LABELS.get(tcfg.timeframe, tcfg.timeframe)}")
    else:
        verdict = f"⏸ Prit: {up} lart, {down} poshtë nga {len(mtf)} (duhen {need} në një drejtim, asnjë kundër)"
    step = df.index[-1] - df.index[-2]
    ch = lambda n: (price / float(df["close"].iloc[-1 - n]) - 1) * 100
    bars = lambda minutes: max(1, int(round(pd.Timedelta(minutes=minutes) / step)))
    text = (f"📊 {display(symbol)} · {price:,.1f} · trendi çdo {cfg.trend_minutes:g} min\n"
            f"{trend_text(mtf)} · {LABELS.get(tcfg.timeframe, tcfg.timeframe)} {ARROWS[small]}\n{verdict}\n"
            f"Lëvizja: {LABELS.get(tcfg.timeframe, tcfg.timeframe)} {ch(1):+.2f}% · 4 orë {ch(bars(240)):+.2f}% · 24 orë {ch(bars(1440)):+.2f}% · RSI {ind['rsi']:.0f}")
    plan = None
    if side or a["signal"] in ("BLI", "SHORT"):
        d = 1 if a["signal"] == "BLI" else -1 if a["signal"] == "SHORT" else side
        stop_pct = a["plan"]["stop_pct"]
        r = tcfg.take_profit_r or 2.0
        plan = {"side": d, "entry": price, "stop": price * (1 - d * stop_pct / 100),
                "target": price * (1 + d * r * stop_pct / 100), "stop_pct": stop_pct, "r": r}
        text += (f"\nPlani {'long' if d > 0 else 'short'}: hyrje ~{price:,.1f} · stop {plan['stop']:,.1f} "
                 f"(−{stop_pct:.2f}%) · objektiv {plan['target']:,.1f} ({r:g}R) · rrezik {cfg.risk_per_trade_pct:g}% e buxhetit")
    return {"text": text, "mtf": mtf, "small": small, "side": side, "signal": a["signal"], "price": price,
            "time": a["time"], "plan": plan, "up": up, "down": down}


def send_trend(exchange, cfg, st: dict, log=print) -> list:
    """Raporti i trendit për çdo treg të fokusit, një herë për qiri. Gjendja ruhet edhe për panelin."""
    from .strategy import warmup

    tcfg, out = trend_config(cfg), []
    for sym in cfg.symbols:
        df = cache.candles(exchange, sym, tcfg.timeframe, max(cfg.candles, warmup(tcfg) + 100))
        rep = trend_report(df, cfg, sym)
        if st.get("trend_time", {}).get(sym) == rep["time"]:
            continue
        st.setdefault("trend_time", {})[sym] = rep["time"]
        st.setdefault("trend", {})[sym] = {k: rep[k] for k in ("mtf", "small", "side", "signal", "price", "time", "plan", "text")}
        out.append(notify.emit(cfg, "trend", sym, rep["text"]))
        log(f"Trendi {sym}: {rep['up']} lart, {rep['down']} poshtë · {rep['signal']}")
    return out


def send_signals(exchange, cfg, st: dict, log=print) -> list:
    """Për çdo strategji aktive dhe çdo treg: nëse ka sinjal të ri hyrjeje, dërgon njoftim me grafik
    (hyrja, stop-loss, objektivi, rreziku). Çdo sinjal dërgohet një herë për qiri."""
    from .config import display
    from .data import fetch_candles, fetch_daily
    from .snapshot import render
    from .strategy import analyze, warmup

    rec = load_recommendation(cfg)
    if not rec or rec.get("action") == "pause":
        return []
    status = {i: "✅ e miratuar" for i in rec.get("approved", [])}
    status.update({i: "🟡 provizore" for i in rec.get("provisional", [])})
    cands = {c["id"]: c for c in tournament_candidates(cfg)}
    seen = st.setdefault("sent_signals", [])
    found = {}          # (tregu, drejtimi) → sinjalet e strategjive që pajtohen
    for cid, label in status.items():
        cand = cands.get(cid)
        if not cand:
            continue
        ccfg = candidate_config(cfg, cand)
        for sym in cfg.symbols:
            try:
                df = cache.candles(exchange, sym, ccfg.timeframe, max(ccfg.candles, warmup(ccfg) + 100, 600))
                a = analyze(df, ccfg, sym, daily=fetch_daily(exchange, sym, ccfg, df))
            except Exception:
                continue
            key = f"{cid}|{sym}|{a['time']}"
            if a["signal"] not in ("BLI", "SHORT") or key in seen:
                continue
            seen.append(key)
            found.setdefault((sym, a["signal"]), []).append((cid, cand, label, ccfg, df, a))
    sent = []
    images = notify.wants_images(cfg)
    for (sym, signal), group in found.items():
        # Një mesazh për treg dhe drejtim: plani i strategjisë më të mirë (të miratuarat para provizoreve).
        cid, cand, label, ccfg, df, a = group[0]
        p = a["plan"]
        side = "🟢 BLERJE (long)" if signal == "BLI" else "🔻 SHITJE (short)"
        risk = cfg.risk_per_trade_pct * (cfg.provisional_risk if cid in rec.get("provisional", []) else 1)
        also = [g[1]["name"] for g in group[1:]]
        text = (f"{side} {display(sym)} · {ccfg.timeframe}\n"
                f"Hyrja {p['entry']:,.6g} · Stop-loss {p['stop_loss']:,.6g} (largësia {p['stop_pct']:.2f}%)"
                + (f" · Objektivi {p['take_profit']:,.6g}" if p.get("take_profit") else " · fitimi i hapur (dalje me sinjal)")
                + f"\nRreziku {risk:g}% e buxhetit · Strategjia: {cand['name']} ({label})"
                + (f"\nPajtohen edhe: {'; '.join(also)}" if also else "")
                + f"\nArsyeja: {a['signal_reason']}")
        image = None
        if images:
            try:
                image = render(df, f"{display(sym)} {ccfg.timeframe} · {side.split(' ', 1)[1]}", p["entry"],
                               p["stop_loss"], p.get("take_profit"), 1 if signal == "BLI" else -1)
            except Exception:
                image = None
        sent.append(notify.emit(cfg, "sinjal", sym, text, image=image))
        log(f"Sinjal: {display(sym)} {signal} ({cand['name']}{', +' + str(len(also)) if also else ''})")
    del seen[:-500]
    return sent


def research_forever(exchange, cfg, log=print, parent_state: str = None):
    """Analisti që nuk ndalet. Me `parent_state` mbyllet vetë kur ekipi që e nisi nuk punon më."""
    st = status(cfg) or {"started": time.time()}
    st.update(pid=os.getpid(), started=st.get("started", time.time()))
    log("Analisti i vazhdueshëm u nis: radar çdo %g min, strategji të reja çdo %g min, rivlerësim çdo %g orë."
        % (cfg.radar_minutes, cfg.research_minutes, cfg.analyst_hours))
    while True:
        if parent_state:
            try:
                hb = json.loads(Path(parent_state).read_text()).get("heartbeat", 0)
            except Exception:
                hb = time.time()
            if time.time() - hb > 1800:
                log("Ekipi nuk punon më; analisti ndalet.")
                break
        try:
            st = research_once(exchange, cfg, st, log)
        except Exception as e:
            st["status"] = f"gabim: {e}"
            log(f"Gabim te analisti (do të riprovohet): {e}")
        _save(cfg, st)
        time.sleep(20 if cfg.focus else 60)
