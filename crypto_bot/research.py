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

from . import cache, lab, memory, notify, radar
from .analyst import choose, evaluate, forward_results, load_recommendation, team_candidates
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

    frac = 0.2 if cfg.focus else 0.98       # në Fokus ari ka më pak histori (kontrata e re), por mbahet
    return {"4h": load_frames(exchange, cfg, symbols, "4h", 5000, fetch=cache.candles, min_frac=frac),
            "1h": load_frames(exchange, cfg, symbols, "1h", 5000 if cfg.focus else 4000, fetch=cache.candles,
                              min_frac=frac)}


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
        rows = evaluate(frames, cfg, team_candidates(cfg))
        rec = choose(rows, forward_results(cfg))
        rec.update({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "ts": now, "test_days": cfg.test_days,
                    "symbols": len(frames["4h"]), "results": rows, "forward": forward_results(cfg),
                    "lab_tested": st.get("tested_total", 0), "lab_passed": st.get("passed_total", 0)})
        Path(cfg.recommendation_file).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
        if set(rec["approved"]) != set(old.get("approved", [])):
            notify.emit(cfg, "analist", "", "🧠 Analisti: " + ("pushim, asnjë strategji e miratuar" if rec["action"] == "pause"
                                                              else "miratoi " + ", ".join(rec["approved"])))
        st["last_rec"] = now
        log(f"Analisti: {rec['name']} | miratuar: {', '.join(rec['approved']) or 'asnjë'}")
    st["status"] = "në pritje të rrethit tjetër"
    return st


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
        time.sleep(60)
