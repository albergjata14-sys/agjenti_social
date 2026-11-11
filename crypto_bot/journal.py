"""Ditari i parashikimeve: regjistron parashikime (p.sh. nga AI i MEXC) dhe mat sa dalin të sakta."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import fetch_candles

DIRECTIONS = {"rritje": 1, "renie": -1, "rënie": -1}


def load(path) -> list:
    p = Path(path)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else []


def save(path, entries: list):
    Path(path).write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")


def add(path, source: str, symbol: str, direction: str, hours: float, price: float,
        probability=None, target=None, now=None) -> dict:
    """Shton një parashikim: `direction` është 'rritje' ose 'rënie' brenda `hours` orësh."""
    if direction.lower() not in DIRECTIONS:
        raise ValueError("drejtimi duhet të jetë 'rritje' ose 'rënie'")
    now = now or datetime.now(timezone.utc)
    entry = {"time": now.isoformat(timespec="seconds"), "due": (now + timedelta(hours=hours)).isoformat(timespec="seconds"),
             "source": source, "symbol": symbol, "direction": "rritje" if DIRECTIONS[direction.lower()] > 0 else "rënie",
             "hours": hours, "price": price, "probability": probability, "target": target,
             "result_price": None, "correct": None, "target_hit": None}
    entries = load(path)
    entries.append(entry)
    save(path, entries)
    return entry


def check(path, exchange, now=None) -> int:
    """Plotëson rezultatin e parashikimeve që u ka ardhur afati. Kthen sa u mbyllën."""
    now = now or datetime.now(timezone.utc)
    entries, done, cache = load(path), 0, {}
    for e in entries:
        start, due = datetime.fromisoformat(e["time"]), datetime.fromisoformat(e["due"])
        if e["correct"] is not None or due > now:
            continue
        if e["symbol"] not in cache:
            oldest = min(datetime.fromisoformat(x["time"]) for x in entries
                         if x["symbol"] == e["symbol"] and x["correct"] is None)
            hours = int((now - oldest).total_seconds() // 3600) + 3
            cache[e["symbol"]] = fetch_candles(exchange, e["symbol"], "1h", hours, closed_only=False)
        df = cache[e["symbol"]]
        after = df[df.index >= due]
        if after.empty:
            continue
        e["result_price"] = float(after["open"].iloc[0])
        sign = 1 if e["direction"] == "rritje" else -1
        e["correct"] = bool((e["result_price"] - e["price"]) * sign > 0)
        if e["target"]:
            # A u prek objektivi në ndonjë çast brenda afatit?
            window = df[(df.index >= start.replace(minute=0, second=0, microsecond=0)) & (df.index < due)]
            e["target_hit"] = bool((window["high"].max() >= e["target"]) if sign > 0 else (window["low"].min() <= e["target"]))
        done += 1
    save(path, entries)
    return done


def report(path) -> str:
    entries = load(path)
    if not entries:
        return "Ditari është bosh. Shto një parashikim me: python -m crypto_bot ditar shto --drejtimi rënie --ore 24"
    lines = [f"{'Burimi':<12}{'Gjithsej':>9}{'Të mbyllura':>12}{'Të sakta':>10}{'Saktësia':>10}{'Objektivi u prek':>18}"]
    for src in sorted({e["source"] for e in entries}):
        mine = [e for e in entries if e["source"] == src]
        closed = [e for e in mine if e["correct"] is not None]
        ok = sum(e["correct"] for e in closed)
        tg = [e for e in closed if e["target_hit"] is not None]
        lines.append(f"{src:<12}{len(mine):>9}{len(closed):>12}{ok:>10}"
                     f"{(f'{ok / len(closed) * 100:.0f}%' if closed else '-'):>10}"
                     f"{(f'{sum(e['target_hit'] for e in tg)}/{len(tg)}' if tg else '-'):>18}")
    closed_n = max((sum(e["correct"] is not None for e in entries if e["source"] == s) for s in {e["source"] for e in entries}))
    if closed_n < 30:
        lines.append(f"\nShënim: me më pak se 30 parashikime të mbyllura ({closed_n} tani) përqindja është ende rastësi.")
    lines.append("\nTë fundit:")
    for e in entries[-8:]:
        res = "në pritje" if e["correct"] is None else f"{'SAKTË' if e['correct'] else 'GABIM'} (çmimi {e['result_price']:.6g})"
        lines.append(f"  {e['time'][:16]}  {e['source']:<10} {e['symbol']:<10} {e['direction']:<6} {e['hours']:g}h "
                     f"nga {e['price']:.6g} → {res}")
    return "\n".join(lines)
