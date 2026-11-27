"""Tregtia demo: botët hapin dhe mbyllin vetë tregti me para virtuale mbi çmimet reale të MEXC.

Hyrja vjen nga zinxhiri (sipas nivelit të zgjedhur), pastaj dy ndihmës:
  Size Calc    – rrezik 1% e kapitalit për tregti; një pozicion ≤ 33% e kapitalit; gjithsej ≤ 100% (pa levë)
  Exit Manager – stop-i dhe Target 1 i setup-it; pas +1.5R stop-i kalon te hyrja (breakeven)
Urdhri është limit te mesi i zonës dhe skadon pas 15 qirinjsh. Komisione + rrëshqitje: 0.075% për çdo anë.
Gjithçka llogaritet nga qirinjtë e mbyllur, ndaj nuk ka rëndësi sa shpesh bëhet skanimi.
"""
import json
import time
from pathlib import Path

from bots._base import fmt
from bots.chain import scan
from bots.chart_feeder.logic import MS

STATE_FILE = Path("bots_paper.json")          # jashtë git-it
START_BALANCE = 1000.0
RISK_PCT, MAX_POS_PCT, MAX_TOTAL_PCT = 1.0, 33.0, 100.0
FEE_SIDE_PCT, BE_AT_R, ORDER_BARS = 0.075, 1.5, 15
LEVELS = {"geometry": "Math Geometry (Strong / Very Strong)", "sniper": "Vetëm SNIPER SIGNAL"}


def new_state(level="geometry"):
    now = time.time()
    return {"start_balance": START_BALANCE, "cash": START_BALANCE, "started": now, "level": level,
            "orders": [], "positions": [], "closed": [], "equity": [[now, START_BALANCE]], "events": [],
            "last_prices": {}}


def load(path=STATE_FILE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return new_state()


def save(state, path=STATE_FILE):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def event(state, text, ts=None):
    state["events"].append([ts or time.time(), text])
    del state["events"][:-150]


def equity(state):
    eq = state["cash"]
    for p in state["positions"]:
        price = state["last_prices"].get(p["key"], p["entry"])
        eq += p["qty"] * (price - p["entry"]) * p["side"]
    return eq


# ---------------------------------------------------------------- Size Calc
def size(state, entry, stop):
    """Sasia e monedhës: rrezik 1% e kapitalit, por brenda kufijve të kapitalit (pa levë)."""
    eq = equity(state)
    qty = (RISK_PCT / 100 * eq) / abs(entry - stop)
    used = sum(p["qty"] * p["entry"] for p in state["positions"])
    room = min(MAX_POS_PCT / 100 * eq, MAX_TOTAL_PCT / 100 * eq - used)
    if room <= 0:
        return 0.0
    return min(qty, room / entry)


# ---------------------------------------------------------------- përditësimi me qirinjtë e rinj
def _close(state, p, price, ts, why):
    gross = p["qty"] * (price - p["entry"]) * p["side"]
    fees = p["qty"] * (p["entry"] + price) * FEE_SIDE_PCT / 100
    pnl = gross - fees
    state["cash"] += pnl
    state["positions"].remove(p)
    r = pnl / p["risk_usd"] if p["risk_usd"] else 0.0
    state["closed"].append({"pair": p["pair"], "tf": p["tf"], "side": p["side"], "entry": p["entry"], "exit": price,
                            "pnl": pnl, "r": r, "opened": p["opened"], "closed": ts, "why": why})
    event(state, f"{p['pair']}: Exit Manager mbylli {('Long' if p['side'] == 1 else 'Short')} – {why} · "
                 f"{'+' if pnl >= 0 else '−'}${abs(pnl):.2f} ({r:+.2f}R)", ts)


def update(state, pair, tf, df):
    """Kalon qirinjtë e mbyllur të rinj: mbush urdhrat, lëviz stop-in, mbyll pozicionet."""
    key = f"{pair}|{tf}"
    times = [int(t.timestamp() * 1000) for t in df.index]
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    state["last_prices"][key] = float(c[-1])

    for od in [x for x in state["orders"] if x["key"] == key]:
        for i, t in enumerate(times):
            if t <= od["created"]:
                continue
            if t > od["expires"]:
                state["orders"].remove(od)
                event(state, f"{pair}: urdhri demo skadoi pa u mbushur", t / 1000)
                break
            side = od["side"]
            if (l[i] <= od["entry"]) if side == 1 else (h[i] >= od["entry"]):
                qty = size(state, od["entry"], od["stop"])
                state["orders"].remove(od)
                if qty <= 0:
                    event(state, f"{pair}: Size Calc – s'ka vend në kapital, urdhri anulohet", t / 1000)
                    break
                p = dict(od, qty=qty, risk_usd=qty * abs(od["entry"] - od["stop"]), opened=t, checked=t - 1, be=False)
                state["positions"].append(p)
                event(state, f"{pair}: hyrje demo {('Long' if side == 1 else 'Short')} @ {fmt(od['entry'])} · "
                             f"Size Calc ${qty * od['entry']:.0f} (rrezik ${p['risk_usd']:.2f})", t / 1000)
                break
            if (h[i] >= od["target"]) if side == 1 else (l[i] <= od["target"]):
                state["orders"].remove(od)
                event(state, f"{pair}: çmimi iku drejt objektivit pa e mbushur urdhrin", t / 1000)
                break

    for p in [x for x in state["positions"] if x["key"] == key]:
        for i, t in enumerate(times):
            if t < p["checked"] or t < p["opened"]:
                continue
            p["checked"] = t + 1
            side = p["side"]
            if (l[i] <= p["stop"]) if side == 1 else (h[i] >= p["stop"]):
                _close(state, p, p["stop"], t / 1000, "breakeven" if p["be"] else "stop-loss")
                break
            if (h[i] >= p["target"]) if side == 1 else (l[i] <= p["target"]):
                _close(state, p, p["target"], t / 1000, "Target 1")
                break
            risk = abs(p["entry"] - p["stop0"])
            if not p["be"] and ((h[i] - p["entry"]) if side == 1 else (p["entry"] - l[i])) >= BE_AT_R * risk:
                p["stop"], p["be"] = p["entry"], True
                event(state, f"{pair}: Exit Manager – stop-i te hyrja pas +{BE_AT_R}R", t / 1000)


def consider(state, result):
    """Hap urdhër demo kur zinxhiri arrin nivelin e zgjedhur dhe çifti nuk ka urdhër apo pozicion."""
    if result.setup is None or result.chart is None:
        return False
    level = state.get("level", "geometry")
    reached = {s.bot for s in result.steps if s.status in ("passed", "alert")}
    if level == "sniper" and "Sniper" not in reached:
        return False
    if level == "geometry" and "Math Geometry" not in reached:
        return False
    key = f"{result.pair}|{result.timeframe}"
    if any(x["key"] == key for x in state["orders"] + state["positions"]):
        return False
    s, df = result.setup, result.chart.df
    last = int(df.index[-1].timestamp() * 1000)
    state["orders"].append({"key": key, "pair": result.pair, "tf": result.timeframe, "side": s.side,
                            "entry": s.entry, "stop": s.stop, "stop0": s.stop, "target": s.target1,
                            "created": last, "expires": last + ORDER_BARS * MS[result.timeframe]})
    event(state, f"{result.pair}: urdhër demo {s.direction} @ {fmt(s.entry)} · stop {fmt(s.stop)} · "
                 f"objektivi {fmt(s.target1)} · {s.confluence}")
    return True


def cycle(pairs, timeframe, on_result=None, path=STATE_FILE, **scan_kw):
    """Një skanim i plotë: zinxhiri për çdo çift + tregtia demo. Kthen (rezultatet, gjendja)."""
    state = load(path)
    results = []

    def handle(r):
        if r.chart is not None:
            update(state, r.pair, timeframe, r.chart.df)
            consider(state, r)
        results.append(r)
        if on_result:
            on_result(r)

    scan(pairs, timeframe, on_result=handle, **scan_kw)
    # çiftet me pozicione që nuk ishin në këtë skanim përditësohen gjithsesi
    from bots.chart_feeder.logic import fetch_candles
    scanned = {r.pair for r in results}
    for key in {x["key"] for x in state["positions"] + state["orders"]}:
        pair, tf = key.split("|")
        if pair not in scanned or tf != timeframe:
            try:
                update(state, pair, tf, scan_kw.get("fetch", fetch_candles)(pair, tf, 300))
            except Exception:
                pass
    state["equity"].append([time.time(), equity(state)])
    del state["equity"][:-2000]
    save(state, path)
    return results, state


def summary(state):
    closed = state["closed"]
    wins = [c for c in closed if c["pnl"] > 0]
    eq = equity(state)
    return {"equity": eq, "start": state["start_balance"], "multiple": eq / state["start_balance"],
            "trades": len(closed), "wins": len(wins), "losses": len(closed) - len(wins),
            "pnl": eq - state["start_balance"], "open": len(state["positions"]), "orders": len(state["orders"])}
