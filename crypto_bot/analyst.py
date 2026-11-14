"""Analisti: robot i dytë që vetëm analizon, provon strategji dhe i sugjeron tregtarit cilën të përdorë.

Si vendos: për çdo strategji kandidate llogarit rezultatin mbi shumë monedha njëherësh (si roboti i
vërtetë) në dy periudha: "mësimi" (më e vjetra) dhe "kontrolli" (`test_days` ditët e fundit). Miratohen
të gjitha strategjitë që fituan në të dyja periudhat dhe bënë mjaft tregti; tregtari i luan njëkohësisht,
me kapitalin e ndarë. Nëse asnjë nuk miratohet, rekomandimi është pushim (pa pozicione të reja).

Pse miratim dhe jo "më e mira": në një provë jashtë mostrës (20 monedha, 14 muaj, vendim çdo 60 ditë),
kalimi te strategjia që kishte fituar më shumë së fundmi dha +2.6%, ndërsa luajtja e të gjitha të miratuarave
njëherësh dha +12.7% (dhe të gjitha pa filtër +6.6%). Kjo nuk garanton fitim në të ardhmen.
"""
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .backtest import portfolio_backtest
from .config import ACTIVE
from .data import fetch_candles, fetch_daily, top_symbols
from .strategy import warmup

# Strategjitë që provon analisti. "overrides" ndryshojnë vetëm mënyrën e hyrjes/daljes, jo kufijtë e rrezikut.
CANDIDATES = [
    {"id": "kujdesshme", "name": "Thyerje maje 4h, vetëm blerje",
     "overrides": {"strategy": "breakout", "timeframe": "4h", "allow_short": False}},
    {"id": "aktive", "name": "Momentum 14 ditë, lart dhe poshtë",
     "overrides": {"strategy": "momentum", "timeframe": "4h", "allow_short": True, "momentum_days": 14.0}},
    {"id": "momentum_blerje", "name": "Momentum 14 ditë, vetëm blerje",
     "overrides": {"strategy": "momentum", "timeframe": "4h", "allow_short": False, "momentum_days": 14.0}},
    {"id": "momentum_7", "name": "Momentum 7 ditë, lart dhe poshtë",
     "overrides": {"strategy": "momentum", "timeframe": "4h", "allow_short": True, "momentum_days": 7.0}},
    {"id": "thyerje_1h", "name": "Thyerje maje 1h, vetëm blerje",
     "overrides": {"strategy": "breakout", "timeframe": "1h", "allow_short": False}},
    {"id": "piket", "name": "Pikët e treguesve 4h (fitim 4%, stop 2%)",
     "overrides": {"strategy": "score", "timeframe": "4h", "allow_short": False, "take_profit_pct": 4.0,
                   "stop_loss_pct": 2.0}},
]
# Strategjitë bazë për mënyrën Fokus (vetëm BTCUSDT). Stop sipas luhatshmërisë (ATR), objektivi si shumëfish i
# rrezikut (R). Strategjitë `mtf` e matin trendin nga 1 dita te 30 minutat dhe hyjnë në intervalin e vogël.
def _mtf(tf, ema, align, trigger, exit_tf, atr, r):
    return {"strategy": "mtf", "timeframe": tf, "allow_short": True, "mtf_ema": ema, "mtf_min_align": align,
            "mtf_trigger": trigger, "mtf_trigger_ema": 20, "mtf_exit": exit_tf, "stop_loss_atr": atr, "take_profit_r": r}


FOCUS_CANDIDATES = [
    {"id": "f_mtf15_terheqje", "name": "Shumë-intervale 15m: tërheqje, 4/4 në trend, stop 2.5×ATR",
     "overrides": _mtf("15m", 50, 4, "pullback", "4h", 2.5, 0.0)},
    {"id": "f_mtf15_thyerje", "name": "Shumë-intervale 15m: thyerje, 4/4 në trend, stop 2.5×ATR",
     "overrides": _mtf("15m", 50, 4, "breakout", "4h", 2.5, 0.0)},
    {"id": "f_mtf15_r3", "name": "Shumë-intervale 15m: tërheqje, 3/4 në trend, objektiv 3R",
     "overrides": _mtf("15m", 20, 3, "pullback", "4h", 2.5, 3.0)},
    {"id": "f_mtf30", "name": "Shumë-intervale 30m: tërheqje, stop 2.5×ATR",
     "overrides": _mtf("30m", 50, 3, "pullback", "4h", 2.5, 0.0)},
    {"id": "f_mtf1h", "name": "Shumë-intervale 1h: tërheqje, stop 2.5×ATR (provë 3-vjeçare)",
     "overrides": _mtf("1h", 50, 3, "pullback", "8h", 2.5, 0.0)},
    {"id": "f_momentum14", "name": "Momentum 14 ditë 4h, stop 2×ATR, lart dhe poshtë",
     "overrides": {"strategy": "momentum", "timeframe": "4h", "allow_short": True, "momentum_days": 14.0,
                   "momentum_min_pct": 1.0, "stop_loss_atr": 2.0, "take_profit_r": 0.0}},
    {"id": "f_thyerje4h_r2", "name": "Thyerje maje 4h, stop 2×ATR, objektiv 2R",
     "overrides": {"strategy": "breakout", "timeframe": "4h", "allow_short": True, "stop_loss_atr": 2.0,
                   "take_profit_r": 2.0}},
    {"id": "f_thyerje_1d", "name": "Thyerje maje ditore, stop 2×ATR",
     "overrides": {"strategy": "breakout", "timeframe": "1d", "allow_short": True, "stop_loss_atr": 2.0,
                   "take_profit_r": 0.0}},
]
# Intervalet që studion analisti në Fokus: nga 15 minuta deri në 1 ditë.
FOCUS_TIMEFRAMES = {"15m": 10000, "30m": 8000, "1h": 5000, "4h": 5000, "8h": 2500, "1d": 1000}


def focus_bars(cfg) -> dict:
    """Sa qirinj shkarkohen për çdo interval që provat të mbulojnë `history_years` vite. Platforma jep aq sa ka
    (MEXC: rreth 1 vit në 15 minuta, më shumë në intervalet e mëdha)."""
    years = max(float(getattr(cfg, "history_years", 0) or 0), 0.0)
    if years <= 0:
        return dict(FOCUS_TIMEFRAMES)
    days = 365 * years
    return {"15m": max(10000, int(days * 96)), "30m": max(8000, int(days * 48)), "1h": max(5000, int(days * 24)),
            "4h": max(5000, int(days * 6)), "8h": max(2500, int(days * 3)), "1d": max(1000, int(days) + 250)}


def yearly(eq: pd.Series, years: int = 3) -> list:
    """Fitimi i çdo viti të fundit (365 ditë), nga më i riu. Viti më i vjetër pranohet kur historia mbulon
    të paktën 9 muaj prej tij (provat nisin pas qirinjve të nevojshëm për treguesit)."""
    out = []
    if eq is None or len(eq) < 2:
        return out
    end = eq.index[-1]
    for k in range(years):
        hi, lo = end - pd.Timedelta(days=365 * k), end - pd.Timedelta(days=365 * (k + 1))
        if lo < eq.index[0] - pd.Timedelta(days=95):
            break
        a, b = eq[:lo], eq[:hi]
        start = float(a.iloc[-1]) if len(a) else float(eq.iloc[0])
        out.append({"from": str(lo.date()), "to": str(hi.date()), "return_pct": round((float(b.iloc[-1]) / start - 1) * 100, 2)})
    return out


def base_candidates(cfg) -> list:
    return FOCUS_CANDIDATES if cfg.focus else CANDIDATES


STRATEGY_FIELDS = {"strategy", "timeframe", "allow_short", "momentum_days", "take_profit_pct", "stop_loss_pct",
                   "momentum_min_pct", "momentum_ema", "breakout_entry", "breakout_exit", "trend_ema", "daily_trend_ema",
                   "trailing_stop_pct", "momentum_daily_filter", "scan_top_n", "stop_loss_atr", "take_profit_r",
                   "mtf_ema", "mtf_min_align", "mtf_trigger", "mtf_trigger_ema", "mtf_exit"}


def _evolved(cfg, statuses):
    from . import memory

    if not cfg.memory_file:
        return []
    try:
        return [{"id": s["id"], "name": s["name"], "overrides": s["overrides"], "origin": "laboratori", "status": s["status"]}
                for s in memory.strategies(cfg, statuses)]
    except Exception:
        return []


def team_candidates(cfg) -> list:
    """Strategjitë që analisti vlerëson dhe ekipi mund t'i luajë: bazë + ato të laboratorit të ngritura në ekip."""
    return base_candidates(cfg) + _evolved(cfg, ["ekip"])


def tournament_candidates(cfg) -> list:
    """Strategjitë që provohen në turne: bazë + ato të laboratorit në turne ose në ekip."""
    return base_candidates(cfg) + _evolved(cfg, ["turne", "ekip"])


def candidate_config(base, cand):
    return replace(base, **cand["overrides"]).validate()


def load_frames(exchange, cfg, symbols, timeframe: str, candles: int, fetch=None, min_frac: float = 0.98) -> dict:
    """{simboli: (qirinjtë, ditorët)} vetëm për monedhat me histori të plotë, sipas renditjes së volumit.

    `fetch(exchange, simboli, intervali, sasia)`: si merren qirinjtë (parazgjedhur nga platforma; analisti i
    vazhdueshëm përdor memorien në disk që merr vetëm qirinjtë e rinj)."""
    fetch = fetch or fetch_candles
    frames = {}
    for sym in symbols:
        try:
            df = fetch(exchange, sym, timeframe, candles)
            # Me `min_frac` të ulët (fokusi) pranohen edhe tregjet e reja që kanë të paktën 600 qirinj.
            if len(df) >= (min(candles * min_frac, 600) if min_frac < 0.5 else candles * min_frac):
                days = (df.index[-1] - df.index[0]).days + 160
                daily = df if timeframe == "1d" else fetch(exchange, sym, "1d", days)
                frames[sym] = (df, daily)
        except Exception:
            continue
    return frames


def _slice(frames: dict, start, end, pad: int) -> dict:
    out = {}
    for sym, (df, daily) in frames.items():
        i0 = max(0, df.index.searchsorted(start) - pad) if start is not None else 0
        i1 = df.index.searchsorted(end) if end is not None else len(df)
        if i1 - i0 > pad + 10:
            out[sym] = (df.iloc[i0:i1], daily)
    return out


def _summary(r: dict) -> dict:
    return {"return_pct": round(float(r["return_pct"]), 2), "drawdown_pct": round(float(r["max_drawdown_pct"]), 1),
            "trades": int(r["trades"]), "win_rate_pct": round(float(r["win_rate_pct"]), 0),
            "months_up": int(r["months_up"]), "months_down": int(r["months_down"])}


def evaluate(frames_by_tf: dict, base_cfg, candidates=None, test_days: int = None, min_trades: int = 8) -> list:
    """Rezultati i çdo kandidati në periudhën e mësimit dhe në atë të kontrollit (ditët e fundit)."""
    candidates = base_candidates(base_cfg) if candidates is None else candidates
    test_days = test_days or base_cfg.test_days
    rows = []
    for cand in candidates:
        cfg = candidate_config(base_cfg, cand)
        all_frames = frames_by_tf.get(cfg.timeframe) or {}
        market = all_frames.get(cfg.market_filter_symbol) if cfg.market_filter_symbol else None
        # Tregtohen vetëm `scan_top_n` monedhat më të tregtuara (renditja e ngarkimit është sipas volumit).
        frames = dict(list(all_frames.items())[:cfg.scan_top_n])
        if not frames:
            rows.append({**cand, "error": f"pa të dhëna {cfg.timeframe}"})
            continue
        end = max(df.index[-1] for df, _ in frames.values())
        cut = end - pd.Timedelta(days=test_days)
        recent_cut = end - pd.Timedelta(days=base_cfg.recent_days)
        pad = warmup(cfg) + 2
        train, test = _slice(frames, None, cut, 0), _slice(frames, cut, None, pad)
        m_train = _slice({"m": market}, None, cut, 0).get("m") if market else None
        m_test = _slice({"m": market}, cut, None, pad).get("m") if market else None
        try:
            r_tr = portfolio_backtest(train, cfg, m_train)
            r_te = portfolio_backtest(test, cfg, m_test)
            # Periudha e shkurtër: si po sillet në ditët më të fundit (tregu ndryshon).
            recent = _slice(frames, recent_cut, None, pad)
            r_re = portfolio_backtest(recent, cfg, _slice({"m": market}, recent_cut, None, pad).get("m") if market else None)
            # E gjithë historia (deri në 2–3 vjet), dhe fitimi vit për vit.
            r_all = portfolio_backtest(frames, cfg, market)
        except Exception as e:
            rows.append({**cand, "error": str(e)})
            continue
        years = yearly(r_all["equity"], max(int(round(getattr(base_cfg, "history_years", 0) or 0)), 1))
        up = sum(1 for y in years if y["return_pct"] > 0)
        long_ok = len(years) < 2 or (r_all["return_pct"] > 0 and up * 2 >= len(years))
        ok = bool(r_tr["return_pct"] > 0 and r_te["return_pct"] > 0 and r_te["trades"] >= min_trades and long_ok)
        if cand.get("status") == "turne":
            ok = False      # strategjitë e reja të laboratorit janë të paktën provizore derisa të kalojnë turneun
        # Provizore: fiton qartë në periudhën e kontrollit dhe nuk po humbet në ditët e fundit, edhe pse
        # periudha e vjetër doli negative (tregu ka ndryshuar). Tregton me rrezik më të vogël.
        # Në afat të gjatë nuk lejohet as provizore një strategji që e ka humbur shumicën e viteve.
        prov = bool(not ok and r_te["return_pct"] > 0 and r_re["return_pct"] >= 0 and r_te["trades"] >= min_trades
                    and (len(years) < 2 or up >= 1 and r_all["return_pct"] > -10))
        days = (r_all["equity"].index[-1] - r_all["equity"].index[0]).days if len(r_all["equity"]) else 0
        long = {**_summary(r_all), "days": int(days), "years": years, "years_up": up, "ok": bool(long_ok)}
        rows.append({**cand, "train": _summary(r_tr), "test": _summary(r_te), "recent": _summary(r_re), "long": long,
                     "eligible": ok,
                     "provisional": prov, "train_from": r_tr["from"], "test_from": r_te["from"], "test_to": r_te["to"]})
    return rows


def choose(rows: list, forward: dict = None, max_active: int = 4) -> dict:
    """Rekomandimi nga rezultatet: kandidati më i mirë në kontroll, ose pushim kur asnjë nuk kualifikohet.

    `forward`: rezultatet e turneut me para demo ({id: {"return_pct", "trades"}}); një kandidat që po humbet
    qartë në kohë reale (nën −5% me të paktën 15 tregti) nuk rekomandohet.
    """
    forward = forward or {}
    def alive(r):        # jo një strategji që po humbet qartë në turne
        f = forward.get(r["id"])
        return not (f and f["trades"] >= 15 and f["return_pct"] < -5)
    score = lambda r: -(r["test"]["return_pct"] + r.get("recent", {}).get("return_pct", 0))
    good = sorted((r for r in rows if r.get("eligible") and alive(r)), key=score)[:max_active]
    prov = sorted((r for r in rows if r.get("provisional") and alive(r)), key=score)[:max(0, max_active - len(good))]
    if not good and not prov:
        return {"action": "pause", "id": None, "name": "Pushim: asnjë strategji nuk fiton tani",
                "overrides": {}, "approved": [], "provisional": [],
                "reason": "Asnjë strategji nuk doli me fitim në periudhën e kontrollit pa humbur në ditët e fundit "
                          "(ose bëri shumë pak tregti). Tregtari nuk hap pozicione të reja derisa të ndryshojë kjo."}
    best = (good or prov)[0]
    t, tr = best["test"], best["train"]
    return {"action": "trade", "id": best["id"], "name": best["name"], "overrides": best["overrides"],
            "approved": [r["id"] for r in good], "provisional": [r["id"] for r in prov],
            "reason": f"Në ditët e fundit ({best['test_from']} – {best['test_to']}) dha {t['return_pct']:+.1f}% me rënie "
                      f"maksimale {t['drawdown_pct']:.0f}% dhe {t['trades']} tregti; në periudhën e mësimit "
                      f"{tr['return_pct']:+.1f}%" + (f"; në {best.get('recent_days', 30)} ditët e fundit "
                                                       f"{best['recent']['return_pct']:+.1f}%" if best.get("recent") else "")
                      + ("" if good else ". Provizore: periudha e vjetër doli negative, ndaj tregton me rrezik më të vogël.")}


def forward_results(base_cfg) -> dict:
    """Rezultatet e turneut (prova paralele me para demo në kohë reale) nga skedarët e gjendjes."""
    out = {}
    for cand in tournament_candidates(base_cfg):
        p = Path(shadow_state_file(base_cfg, cand))
        if not p.exists():
            continue
        try:
            st = json.loads(p.read_text())
        except ValueError:
            continue
        equity = st.get("last_equity", st.get("cash", base_cfg.paper_balance))
        out[cand["id"]] = {"return_pct": (equity / base_cfg.paper_balance - 1) * 100, "trades": len(st.get("trades", [])),
                           "open": len(st.get("positions", {})), "since": st.get("started"),
                           "wins": sum(t["pnl"] > 0 for t in st.get("trades", []))}
    return out


def shadow_state_file(base_cfg, cand) -> str:
    return base_cfg.state_file.replace(".json", f"_turne_{cand['id']}.json")


def lab_due(cfg) -> bool:
    from . import memory

    if not cfg.lab_hours or not cfg.memory_file:
        return False
    try:
        last = memory.query(cfg, "SELECT MAX(ts) AS t FROM events WHERE kind='laboratori'")["t"].iloc[0]
    except Exception:
        return True
    return last is None or pd.isna(last) or time.time() - float(last) > cfg.lab_hours * 3600


def analyze_market(exchange, base_cfg, n_symbols: int = 20, test_days: int = None, log=print, run_lab=None) -> dict:
    """Shkarkon historinë, (kur i vjen radha) nis laboratorin, provon kandidatët dhe ruan rekomandimin."""
    t0 = time.time()
    test_days = test_days or base_cfg.test_days
    symbols = list(base_cfg.symbols) if base_cfg.focus else top_symbols(exchange, base_cfg.quote, n_symbols)
    if base_cfg.market_filter_symbol and base_cfg.market_filter_symbol not in symbols:
        symbols.append(base_cfg.market_filter_symbol)
    candidates = tournament_candidates(base_cfg)
    run_lab = lab_due(base_cfg) if run_lab is None else run_lab
    need = focus_bars(base_cfg) if base_cfg.focus else ({"4h": 5000, "1h": 4000} if run_lab else {})
    for cand in candidates:
        tf = cand["overrides"].get("timeframe", base_cfg.timeframe)
        if not base_cfg.focus:
            need[tf] = 5000 if tf in ("4h", "1d") else 4000
    frames_by_tf = {}
    for tf, n in need.items():
        log(f"Analisti po shkarkon {n} qirinj {tf} për {len(symbols)} monedha...")
        frames_by_tf[tf] = load_frames(exchange, base_cfg, symbols, tf, n, min_frac=0.2 if base_cfg.focus else 0.98)
    lab_rows = []
    if run_lab:
        from . import lab, memory

        lab_rows = lab.run_lab(frames_by_tf, base_cfg, n=base_cfg.lab_candidates, test_days=test_days, log=log)
        passed = sum(1 for r in lab_rows if r.get("eligible"))
        memory.log_event(base_cfg, "laboratori", detail={"tested": len(lab_rows), "passed": passed})
        log(f"Laboratori provoi {len(lab_rows)} strategji të reja; {passed} fituan në të dyja periudhat.")
    rows = evaluate(frames_by_tf, base_cfg, candidates, test_days=test_days)
    fwd = forward_results(base_cfg)
    rec = choose(rows, fwd, base_cfg.max_active)
    rec.update({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": time.time(),
                "test_days": test_days, "symbols": len(frames_by_tf.get("4h", {})), "results": rows, "forward": fwd,
                "seconds": round(time.time() - t0), "lab_tested": len(lab_rows),
                "lab_passed": sum(1 for r in lab_rows if r.get("eligible"))})
    Path(base_cfg.recommendation_file).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def team_config(base_cfg, cand, approved, n_members: int = None, provisional=()):
    """Konfigurimi i një anëtari të ekipit: kapitali i tij, skedari i tij, dhe pa hyrje të reja kur nuk është aktiv.
    Strategjitë provizore tregtojnë me `provisional_risk` (p.sh. gjysmën) e rrezikut."""
    n = n_members or len(base_candidates(base_cfg))
    risk = base_cfg.risk_per_trade_pct * (base_cfg.provisional_risk if cand["id"] in provisional else 1.0)
    # Anëtarët njoftojnë hyrjet dhe daljet e tyre; sinjalet dhe lëvizjet i njofton analisti (radari), jo pesë herë.
    return replace(candidate_config(base_cfg, cand), label=cand["name"], scan_market=not base_cfg.focus,
                   notify_signals=False, alert_move_pct=0.0, risk_per_trade_pct=risk,
                   paper_balance=base_cfg.paper_balance / n,
                   pause_entries=cand["id"] not in approved and cand["id"] not in provisional,
                   state_file=base_cfg.state_file.replace(".json", f"_ekip_{cand['id']}.json"))


def tournament_config(base_cfg, cand):
    """Prova paralele: çdo strategji me gjithë kapitalin demo, pa njoftime, gjithmonë aktive."""
    return replace(candidate_config(base_cfg, cand), label=f"Turne · {cand['name']}", scan_market=not base_cfg.focus,
                   pause_entries=False,
                   state_file=shadow_state_file(base_cfg, cand), log_file="", notify_file="", notify_telegram=False,
                   notify_trades=False, notify_signals=False, alert_move_pct=0.0, alerts_file="")


def load_recommendation(cfg):
    p = Path(cfg.recommendation_file)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except ValueError:
        return None


def apply_recommendation(base_cfg, rec):
    """Konfigurimi që përdor tregtari: strategjia e rekomanduar mbi rregullimet e rrezikut të përdoruesit."""
    if not rec:
        return base_cfg
    if rec.get("action") == "pause":
        return replace(base_cfg, pause_entries=True)
    ov = {k: v for k, v in rec.get("overrides", {}).items() if k in STRATEGY_FIELDS}
    return replace(base_cfg, pause_entries=False, **ov).validate()
