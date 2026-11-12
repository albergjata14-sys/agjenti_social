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
STRATEGY_FIELDS = {"strategy", "timeframe", "allow_short", "momentum_days", "take_profit_pct", "stop_loss_pct"}


def candidate_config(base, cand):
    return replace(base, **cand["overrides"]).validate()


def load_frames(exchange, cfg, symbols, timeframe: str, candles: int) -> dict:
    """{simboli: (qirinjtë, ditorët)} vetëm për monedhat me histori të plotë."""
    frames = {}
    tf_cfg = replace(cfg, timeframe=timeframe)
    for sym in symbols:
        try:
            df = fetch_candles(exchange, sym, timeframe, candles)
            if len(df) >= candles * 0.98:
                frames[sym] = (df, fetch_daily(exchange, sym, tf_cfg, df))
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


def evaluate(frames_by_tf: dict, base_cfg, candidates=CANDIDATES, test_days: int = 120, min_trades: int = 8) -> list:
    """Rezultati i çdo kandidati në periudhën e mësimit dhe në atë të kontrollit (ditët e fundit)."""
    rows = []
    for cand in candidates:
        cfg = candidate_config(base_cfg, cand)
        frames = frames_by_tf.get(cfg.timeframe) or {}
        market = frames.get(cfg.market_filter_symbol) if cfg.market_filter_symbol else None
        if not frames:
            rows.append({**cand, "error": f"pa të dhëna {cfg.timeframe}"})
            continue
        end = max(df.index[-1] for df, _ in frames.values())
        cut = end - pd.Timedelta(days=test_days)
        pad = warmup(cfg) + 2
        train, test = _slice(frames, None, cut, 0), _slice(frames, cut, None, pad)
        m_train = _slice({"m": market}, None, cut, 0).get("m") if market else None
        m_test = _slice({"m": market}, cut, None, pad).get("m") if market else None
        try:
            r_tr = portfolio_backtest(train, cfg, m_train)
            r_te = portfolio_backtest(test, cfg, m_test)
        except Exception as e:
            rows.append({**cand, "error": str(e)})
            continue
        ok = bool(r_tr["return_pct"] > 0 and r_te["return_pct"] > 0 and r_te["trades"] >= min_trades)
        rows.append({**cand, "train": _summary(r_tr), "test": _summary(r_te), "eligible": ok,
                     "train_from": r_tr["from"], "test_from": r_te["from"], "test_to": r_te["to"]})
    return rows


def choose(rows: list, forward: dict = None) -> dict:
    """Rekomandimi nga rezultatet: kandidati më i mirë në kontroll, ose pushim kur asnjë nuk kualifikohet.

    `forward`: rezultatet e turneut me para demo ({id: {"return_pct", "trades"}}); një kandidat që po humbet
    qartë në kohë reale (nën −5% me të paktën 15 tregti) nuk rekomandohet.
    """
    forward = forward or {}
    def ok(r):
        f = forward.get(r["id"])
        return r.get("eligible") and not (f and f["trades"] >= 15 and f["return_pct"] < -5)
    good = sorted((r for r in rows if ok(r)), key=lambda r: -r["test"]["return_pct"])
    if not good:
        return {"action": "pause", "id": None, "name": "Pushim: asnjë strategji nuk fitoi në të dyja periudhat",
                "overrides": {}, "approved": [],
                "reason": "Asnjë strategji nuk doli me fitim si në periudhën e mësimit ashtu edhe në ditët e fundit "
                          "(ose bëri shumë pak tregti). Tregtari nuk hap pozicione të reja derisa të ndryshojë kjo."}
    best = good[0]
    t, tr = best["test"], best["train"]
    return {"action": "trade", "id": best["id"], "name": best["name"], "overrides": best["overrides"],
            "approved": [r["id"] for r in good],
            "reason": f"Në ditët e fundit ({best['test_from']} – {best['test_to']}) dha {t['return_pct']:+.1f}% me rënie "
                      f"maksimale {t['drawdown_pct']:.0f}% dhe {t['trades']} tregti; në periudhën e mësimit "
                      f"{tr['return_pct']:+.1f}%."}


def forward_results(base_cfg) -> dict:
    """Rezultatet e turneut (prova paralele me para demo në kohë reale) nga skedarët e gjendjes."""
    out = {}
    for cand in CANDIDATES:
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


def analyze_market(exchange, base_cfg, n_symbols: int = 20, test_days: int = 120, log=print) -> dict:
    """Shkarkon historinë, provon kandidatët dhe ruan rekomandimin te `recommendation_file`."""
    t0 = time.time()
    symbols = top_symbols(exchange, base_cfg.quote, n_symbols)
    if base_cfg.market_filter_symbol and base_cfg.market_filter_symbol not in symbols:
        symbols.append(base_cfg.market_filter_symbol)
    need = {}
    for cand in CANDIDATES:
        tf = cand["overrides"].get("timeframe", base_cfg.timeframe)
        need[tf] = 5000 if tf in ("4h", "1d") else 4000
    frames_by_tf = {}
    for tf, n in need.items():
        log(f"Analisti po shkarkon {n} qirinj {tf} për {len(symbols)} monedha...")
        frames_by_tf[tf] = load_frames(exchange, base_cfg, symbols, tf, n)
    rows = evaluate(frames_by_tf, base_cfg, test_days=test_days)
    fwd = forward_results(base_cfg)
    rec = choose(rows, fwd)
    rec.update({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": time.time(),
                "test_days": test_days, "symbols": len(frames_by_tf.get("4h", {})), "results": rows, "forward": fwd,
                "seconds": round(time.time() - t0)})
    Path(base_cfg.recommendation_file).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def team_config(base_cfg, cand, approved, n_members: int = None):
    """Konfigurimi i një anëtari të ekipit: kapitali i tij, skedari i tij, dhe pa hyrje të reja kur nuk miratohet."""
    n = n_members or len(CANDIDATES)
    return replace(candidate_config(base_cfg, cand), label=cand["name"], scan_market=True,
                   paper_balance=base_cfg.paper_balance / n, pause_entries=cand["id"] not in approved,
                   state_file=base_cfg.state_file.replace(".json", f"_ekip_{cand['id']}.json"))


def tournament_config(base_cfg, cand):
    """Prova paralele: çdo strategji me gjithë kapitalin demo, pa njoftime, gjithmonë aktive."""
    return replace(candidate_config(base_cfg, cand), label=cand["name"], scan_market=True, pause_entries=False,
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
