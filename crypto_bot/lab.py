"""Laboratori: krijon strategji të reja, i provon dhe i çon më të mirat në turne.

Rruga e një strategjie të re:
  1. krijohet duke ndryshuar 1–2 parametra të një strategjie të mirë, ose rastësisht brenda kufijve të arsyeshëm;
  2. provohet si analisti: periudha e mësimit dhe 120 ditët e fundit;
  3. nëse fiton në të dyja, hyn në TURNE (para demo, kohë reale) – kjo është prova e vërtetë, sepse laboratori
     provon shumë variante dhe disa do të duken mirë rastësisht;
  4. pas `promote_days` ditësh në turne me të paktën 15 tregti dhe fitim, bëhet anëtare e EKIPIT (analisti
     mund ta miratojë); nëse humbet qartë, hidhet poshtë.
"""
import hashlib
import json
import math
import random
import time

from . import memory
from .analyst import base_candidates, evaluate

SPACE = {
    "momentum": {"timeframe": ["1h", "4h"], "momentum_days": [3.0, 5.0, 7.0, 10.0, 14.0, 21.0, 30.0],
                 "momentum_min_pct": [0.0, 2.0, 5.0, 10.0], "momentum_ema": [50, 100, 200],
                 "stop_loss_pct": [4.0, 6.0, 8.0, 12.0], "take_profit_pct": [0.0, 0.0, 10.0, 20.0],
                 "allow_short": [True, False], "trailing_stop_pct": [0.0, 0.0, 5.0, 10.0],
                 "momentum_daily_filter": [False, True], "daily_trend_ema": [20, 50], "scan_top_n": [10, 20, 30]},
    "breakout": {"timeframe": ["1h", "4h"], "breakout_entry": [20, 30, 55, 100], "breakout_exit": [10, 20, 40],
                 "trend_ema": [100, 200], "daily_trend_ema": [0, 20, 50], "stop_loss_pct": [4.0, 6.0, 8.0, 12.0],
                 "take_profit_pct": [0.0, 0.0, 10.0, 20.0], "allow_short": [False, True],
                 "trailing_stop_pct": [0.0, 0.0, 5.0, 10.0], "scan_top_n": [10, 20, 30]},
}
# Hapësira për mënyrën Fokus (ari, BTC, EURUSD, GBPUSD): stop dhe objektiv sipas luhatshmërisë (ATR dhe R),
# pragje lëvizjeje më të vogla për forex-in, qirinj 1h dhe 4h, lart dhe poshtë.
FOCUS_SPACE = {
    "momentum": {"timeframe": ["15m", "1h", "4h", "1d"], "momentum_days": [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 14.0, 21.0, 30.0],
                 "momentum_min_pct": [0.0, 0.5, 1.0, 2.0, 5.0], "momentum_ema": [50, 100, 200],
                 "stop_loss_atr": [1.0, 1.5, 2.0, 3.0], "take_profit_r": [0.0, 1.5, 2.0, 3.0],
                 "allow_short": [True, False], "momentum_daily_filter": [False, True], "daily_trend_ema": [20, 50]},
    "breakout": {"timeframe": ["15m", "1h", "4h", "1d"], "breakout_entry": [20, 30, 55, 100],
                 "breakout_exit": [10, 20, 40], "trend_ema": [100, 200], "daily_trend_ema": [0, 20, 50],
                 "stop_loss_atr": [1.0, 1.5, 2.0, 3.0],
                 "take_profit_r": [0.0, 1.5, 2.0, 3.0], "allow_short": [True, False]},
}
FIELDS = {k for sp in (SPACE, FOCUS_SPACE) for space in sp.values() for k in space} | {"strategy"}


def space(cfg=None) -> dict:
    return FOCUS_SPACE if cfg is not None and cfg.focus else SPACE


def canonical(o: dict) -> dict:
    """Heq parametrat që nuk kanë efekt, që dy strategji që sillen njësoj të kenë të njëjtin identitet."""
    o = dict(o)
    if o.get("strategy") == "momentum" and not o.get("momentum_daily_filter"):
        o.pop("daily_trend_ema", None)       # pa filtrin ditor, mesatarja ditore nuk përdoret
    return o


def strategy_id(overrides: dict) -> str:
    return "evo_" + hashlib.sha1(json.dumps(canonical(overrides), sort_keys=True).encode()).hexdigest()[:8]


def describe(o: dict) -> str:
    side = "lart+poshtë" if o.get("allow_short") else "vetëm blerje"
    tp = f", fitim {o['take_profit_pct']:g}%" if o.get("take_profit_pct") else ""
    tp += f", objektiv {o['take_profit_r']:g}R" if o.get("take_profit_r") else ""
    tp += f", stop ndjekës {o['trailing_stop_pct']:g}%" if o.get("trailing_stop_pct") else ""
    tp += f", {o['scan_top_n']} monedha" if o.get("scan_top_n", 20) != 20 else ""
    if o["strategy"] == "momentum":
        core = (f"momentum {o['momentum_days']:g}d, prag {o['momentum_min_pct']:g}%, EMA{o['momentum_ema']}"
                + (f", trend ditor EMA{o['daily_trend_ema']}" if o.get("momentum_daily_filter") else ""))
    else:
        core = (f"thyerje {o['breakout_entry']}/{o['breakout_exit']}, EMA{o['trend_ema']}, "
                f"ditor {'pa' if not o['daily_trend_ema'] else 'EMA' + str(o['daily_trend_ema'])}")
    stop = f"stop {o['stop_loss_atr']:g}×ATR" if o.get("stop_loss_atr") else f"stop {o['stop_loss_pct']:g}%"
    return f"Evo: {core}, {stop}{tp}, {o['timeframe']}, {side}"


def learned(cfg) -> dict:
    """Çfarë ka mësuar laboratori nga të gjitha provat: rezultati mesatar në kontroll për çdo vlerë parametri.

    {(familja, parametri, vlera): (mesatarja %, sa prova)}. Përdoret që provat e reja të zgjedhin më shpesh
    vlerat që kanë dalë mirë, pa i hequr krejt të tjerat (tregu ndryshon)."""
    stats = {}
    for s in memory.strategies(cfg):
        if s["test"] is None:
            continue
        o = s["overrides"]
        for k, v in o.items():
            if k != "strategy":
                stats.setdefault((o.get("strategy"), k, json.dumps(v)), []).append(float(s["test"]))
    return {key: (sum(v) / len(v), len(v)) for key, v in stats.items()}


def _pick(rng, family, key, values, stats):
    """Zgjedh një vlerë, me peshë më të madhe për ato që kanë dalë mirë (të paktën 4 prova)."""
    if not stats:
        return rng.choice(values)
    weights = []
    for v in values:
        mean, n = stats.get((family, key, json.dumps(v)), (0.0, 0))
        weights.append(math.exp(max(-3.0, min(3.0, mean / 10))) if n >= 4 else 1.0)
    return rng.choices(values, weights=weights)[0]


def random_overrides(rng: random.Random, cfg=None, stats=None) -> dict:
    sp = space(cfg)
    family = rng.choice(list(sp))
    return {"strategy": family, **{k: _pick(rng, family, k, v, stats) for k, v in sp[family].items()}}


def lessons(cfg, min_tests: int = 4) -> list:
    """Përmbledhja për panelin: për çdo parametër, vlera më e mirë dhe më e dobët sipas provave."""
    by = {}
    for (fam, key, val), (mean, n) in learned(cfg).items():
        if n >= min_tests:
            by.setdefault((fam, key), []).append((mean, json.loads(val), n))
    out = []
    for (fam, key), vals in sorted(by.items()):
        if len(vals) < 2:
            continue
        vals.sort(key=lambda x: -x[0])
        out.append({"family": fam, "param": key, "best": vals[0][1], "best_mean": vals[0][0], "best_n": vals[0][2],
                    "worst": vals[-1][1], "worst_mean": vals[-1][0], "worst_n": vals[-1][2]})
    return out


def complete(o: dict, rng: random.Random, cfg=None) -> dict:
    """Plotëson parametrat që mungojnë (p.sh. kur prindi është një strategji bazë)."""
    defaults = {"timeframe": "4h", "scan_top_n": 20, "trailing_stop_pct": 0.0, "momentum_daily_filter": False,
                "daily_trend_ema": 50}
    sp = space(cfg)
    defaults.update({"stop_loss_atr": 2.0, "take_profit_r": 0.0, "momentum_min_pct": 1.0} if sp is FOCUS_SPACE else {})
    full = {"strategy": o["strategy"]}
    for k, v in sp[o["strategy"]].items():
        full[k] = o.get(k, defaults.get(k, v[0]))
    return full


def mutate(parent: dict, rng: random.Random, cfg=None, stats=None) -> dict:
    sp = space(cfg)
    child = complete(parent, rng, cfg)
    for k in rng.sample(list(sp[child["strategy"]]), rng.choice([1, 2])):
        child[k] = _pick(rng, child["strategy"], k, sp[child["strategy"]][k], stats)
    return child


def run_lab(frames_by_tf: dict, base_cfg, n: int = 24, seed=None, test_days: int = 120, log=print) -> list:
    """Krijon dhe provon `n` strategji të reja; ruan rezultatet në kujtesë. Kthen rezultatet e provës."""
    rng = random.Random(seed if seed is not None else time.time())
    stats = learned(base_cfg)          # çfarë kanë treguar provat e mëparshme
    known = {s["id"] for s in memory.strategies(base_cfg)}
    parents = [c["overrides"] for c in base_candidates(base_cfg) if c["overrides"].get("strategy") in space(base_cfg)]
    parents += [s["overrides"] for s in memory.strategies(base_cfg, ["turne", "ekip"])]
    good = sorted((s for s in memory.strategies(base_cfg, ["provuar"]) if (s["test"] or 0) > 0),
                  key=lambda s: -s["test"])[:5]
    parents += [s["overrides"] for s in good]
    children, tries = {}, 0
    while len(children) < n and tries < n * 20:
        tries += 1
        o = (mutate(rng.choice(parents), rng, base_cfg, stats) if parents and rng.random() < 0.7
             else random_overrides(rng, base_cfg, stats))
        sid = strategy_id(o)
        if sid not in known and sid not in children:
            children[sid] = o
    cands = [{"id": sid, "name": describe(o), "overrides": o} for sid, o in children.items()]
    log(f"Laboratori po provon {len(cands)} strategji të reja...")
    rows = evaluate(frames_by_tf, base_cfg, cands, test_days=test_days)
    for r in rows:
        if "test" not in r:
            continue
        memory.upsert_strategy(base_cfg, r["id"], r["name"], r["overrides"], "laboratori", "provuar",
                               r["train"]["return_pct"], r["test"]["return_pct"], r["test"]["drawdown_pct"],
                               r["test"]["trades"], "kaloi të dyja periudhat" if r["eligible"] else "")
    fill_tournament(base_cfg)
    return rows


def fill_tournament(base_cfg) -> list:
    """Vendet e lira në turne u jepen strategjive të provuara me rezultatin më të mirë në kontroll."""
    free = base_cfg.max_evolved - len(memory.strategies(base_cfg, ["turne"]))
    if free <= 0:
        return []
    waiting = [s for s in memory.strategies(base_cfg, ["provuar"])
               if (s["train"] or 0) > 0 and (s["test"] or 0) > 0 and (s["test_trades"] or 0) >= 8]
    chosen = sorted(waiting, key=lambda s: -s["test"])[:free]
    for s in chosen:
        memory.set_status(base_cfg, s["id"], "turne", "hyri në turne")
    return chosen


def review_tournament(base_cfg, forward: dict, now=None) -> list:
    """Ngre në ekip strategjitë e laboratorit që fitojnë në turne dhe hedh ato që humbin. Kthen ndryshimet."""
    now = now or time.time()
    changes = []
    for s in memory.strategies(base_cfg, ["turne", "ekip"]):
        f = forward.get(s["id"])
        if not f:
            continue
        days = (now - (f.get("since") or now)) / 86400
        if f["trades"] >= 15 and f["return_pct"] < -5:
            memory.set_status(base_cfg, s["id"], "hedhur", f"humbi {f['return_pct']:+.1f}% në turne")
            changes.append((s["name"], "hedhur"))
        elif s["status"] == "turne" and days >= base_cfg.promote_days and f["trades"] >= 15 and f["return_pct"] > 0:
            memory.set_status(base_cfg, s["id"], "ekip", f"fitoi {f['return_pct']:+.1f}% në {days:.0f} ditë turne")
            changes.append((s["name"], "ekip"))
        elif s["status"] == "turne" and days >= base_cfg.tournament_days:
            memory.set_status(base_cfg, s["id"], "hedhur",
                              f"pa fitim të qartë pas {days:.0f} ditësh ({f['return_pct']:+.1f}%, {f['trades']} tregti)")
            changes.append((s["name"], "hedhur"))
    if changes:
        fill_tournament(base_cfg)
    return changes
