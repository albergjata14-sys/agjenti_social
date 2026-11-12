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
import random
import time

from . import memory
from .analyst import CANDIDATES, evaluate

SPACE = {
    "momentum": {"timeframe": ["1h", "4h"], "momentum_days": [3.0, 5.0, 7.0, 10.0, 14.0, 21.0, 30.0],
                 "momentum_min_pct": [0.0, 2.0, 5.0, 10.0], "momentum_ema": [50, 100, 200],
                 "stop_loss_pct": [4.0, 6.0, 8.0, 12.0], "take_profit_pct": [0.0, 0.0, 10.0, 20.0],
                 "allow_short": [True, False]},
    "breakout": {"timeframe": ["1h", "4h"], "breakout_entry": [20, 30, 55, 100], "breakout_exit": [10, 20, 40],
                 "trend_ema": [100, 200], "daily_trend_ema": [0, 20, 50], "stop_loss_pct": [4.0, 6.0, 8.0, 12.0],
                 "take_profit_pct": [0.0, 0.0, 10.0, 20.0], "allow_short": [False, True]},
}
FIELDS = {k for space in SPACE.values() for k in space} | {"strategy"}


def strategy_id(overrides: dict) -> str:
    return "evo_" + hashlib.sha1(json.dumps(overrides, sort_keys=True).encode()).hexdigest()[:8]


def describe(o: dict) -> str:
    side = "lart+poshtë" if o.get("allow_short") else "vetëm blerje"
    tp = f", fitim {o['take_profit_pct']:g}%" if o.get("take_profit_pct") else ""
    if o["strategy"] == "momentum":
        core = (f"momentum {o['momentum_days']:g}d, prag {o['momentum_min_pct']:g}%, EMA{o['momentum_ema']}")
    else:
        core = (f"thyerje {o['breakout_entry']}/{o['breakout_exit']}, EMA{o['trend_ema']}, "
                f"ditor {'pa' if not o['daily_trend_ema'] else 'EMA' + str(o['daily_trend_ema'])}")
    return f"Evo: {core}, stop {o['stop_loss_pct']:g}%{tp}, {o['timeframe']}, {side}"


def random_overrides(rng: random.Random) -> dict:
    family = rng.choice(list(SPACE))
    return {"strategy": family, **{k: rng.choice(v) for k, v in SPACE[family].items()}}


def complete(o: dict, rng: random.Random) -> dict:
    """Plotëson parametrat që mungojnë (p.sh. kur prindi është një strategji bazë)."""
    full = {"strategy": o["strategy"]}
    for k, v in SPACE[o["strategy"]].items():
        full[k] = o.get(k, v[0] if k != "timeframe" else "4h")
    return full


def mutate(parent: dict, rng: random.Random) -> dict:
    child = complete(parent, rng)
    for k in rng.sample(list(SPACE[child["strategy"]]), rng.choice([1, 2])):
        child[k] = rng.choice(SPACE[child["strategy"]][k])
    return child


def run_lab(frames_by_tf: dict, base_cfg, n: int = 24, seed=None, test_days: int = 120, log=print) -> list:
    """Krijon dhe provon `n` strategji të reja; ruan rezultatet në kujtesë. Kthen rezultatet e provës."""
    rng = random.Random(seed if seed is not None else time.time())
    known = {s["id"] for s in memory.strategies(base_cfg)}
    parents = [c["overrides"] for c in CANDIDATES if c["overrides"].get("strategy") in SPACE]
    parents += [s["overrides"] for s in memory.strategies(base_cfg, ["turne", "ekip"])]
    good = sorted((s for s in memory.strategies(base_cfg, ["provuar"]) if (s["test"] or 0) > 0),
                  key=lambda s: -s["test"])[:5]
    parents += [s["overrides"] for s in good]
    children, tries = {}, 0
    while len(children) < n and tries < n * 20:
        tries += 1
        o = mutate(rng.choice(parents), rng) if parents and rng.random() < 0.7 else random_overrides(rng)
        sid = strategy_id(o)
        if sid not in known and sid not in children:
            children[sid] = o
    cands = [{"id": sid, "name": describe(o), "overrides": o} for sid, o in children.items()]
    log(f"Laboratori po provon {len(cands)} strategji të reja...")
    rows = evaluate(frames_by_tf, base_cfg, cands, test_days=test_days)
    n_turne = len(memory.strategies(base_cfg, ["turne"]))
    for r in sorted((r for r in rows if "test" in r), key=lambda r: -r["test"]["return_pct"]):
        status = "provuar"
        if r["eligible"] and n_turne < base_cfg.max_evolved:
            status, n_turne = "turne", n_turne + 1
        memory.upsert_strategy(base_cfg, r["id"], r["name"], r["overrides"], "laboratori", status,
                               r["train"]["return_pct"], r["test"]["return_pct"], r["test"]["drawdown_pct"],
                               r["test"]["trades"], "kaloi në turne" if status == "turne" else "")
    return rows


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
    return changes
