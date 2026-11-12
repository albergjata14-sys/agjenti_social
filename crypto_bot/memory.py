"""Kujtesa e robotit: një bazë të dhënash SQLite ku ruhet çdo gjë që ndodh, ditë pas dite.

Tabelat: `events` (çdo vendim: hyrje, dalje, mosblerje me arsyen), `trades` (çdo tregti e mbyllur),
`equity` (kapitali i çdo strategjie në çdo cikël), `market` (çmimet e monedhave çdo orë), `reports`
(raporti i çdo dite) dhe `strategies` (strategjitë e laboratorit me rezultatet e tyre).
"""
import json
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (ts REAL, day TEXT, kind TEXT, strategy TEXT, symbol TEXT, action TEXT,
                                   price REAL, detail TEXT);
CREATE TABLE IF NOT EXISTS trades (ts_open REAL, ts_close REAL, day TEXT, strategy TEXT, symbol TEXT, side TEXT,
                                   entry REAL, exit REAL, pnl REAL, pnl_pct REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS equity (ts REAL, day TEXT, strategy TEXT, equity REAL, open INTEGER);
CREATE TABLE IF NOT EXISTS market (ts REAL, day TEXT, symbol TEXT, price REAL, change24 REAL);
CREATE TABLE IF NOT EXISTS reports (day TEXT PRIMARY KEY, created REAL, text TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS strategies (id TEXT PRIMARY KEY, name TEXT, overrides TEXT, origin TEXT, status TEXT,
                                       created REAL, updated REAL, train REAL, test REAL, test_dd REAL,
                                       test_trades INTEGER, note TEXT);
CREATE INDEX IF NOT EXISTS ev_day ON events(day);
CREATE INDEX IF NOT EXISTS tr_day ON trades(day);
CREATE INDEX IF NOT EXISTS eq_day ON equity(day);
"""


def _day(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def connect(cfg):
    con = sqlite3.connect(cfg.memory_file, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")      # paneli lexon ndërsa roboti shkruan
    con.executescript(SCHEMA)
    return con


def _write(cfg, sql: str, rows):
    if not cfg.memory_file or not rows:
        return
    with closing(connect(cfg)) as con, con:
        con.executemany(sql, rows)


def log_event(cfg, kind: str, symbol: str = "", action: str = "", price=None, detail=None, ts=None):
    ts = ts or time.time()
    _write(cfg, "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
           [(ts, _day(ts), kind, cfg.label, symbol, action, price, json.dumps(detail or {}, ensure_ascii=False))])


def log_trade(cfg, symbol: str, t: dict):
    closed = t.get("closed", time.time())
    _write(cfg, "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           [(t.get("opened"), closed, _day(closed), cfg.label or "kryesori", symbol, t.get("side", "long"), t["entry"],
             t["exit"], t["pnl"], t["pnl_pct"], t["reason"])])


def log_equity(cfg, rows):
    """rows: [(strategjia, kapitali, pozicione të hapura)]."""
    ts = time.time()
    _write(cfg, "INSERT INTO equity VALUES (?,?,?,?,?)", [(ts, _day(ts), s, e, o) for s, e, o in rows])


def log_market(cfg, rows):
    """rows: [(simboli, çmimi, ndryshimi 24 orë %)]."""
    ts = time.time()
    _write(cfg, "INSERT INTO market VALUES (?,?,?,?,?)", [(ts, _day(ts), s, p, c) for s, p, c in rows])


def query(cfg, sql: str, params=()) -> pd.DataFrame:
    with closing(connect(cfg)) as con:
        return pd.read_sql_query(sql, con, params=params)


# --- raporti i ditës -------------------------------------------------------------------------------
def daily_report(cfg, day: str) -> dict:
    """Përmbledhja e një dite (UTC): kapitali i çdo strategjie, tregtitë, tregu dhe vendimet."""
    eq = query(cfg, "SELECT strategy, ts, equity FROM equity WHERE day=? ORDER BY ts", (day,))
    tr = query(cfg, "SELECT * FROM trades WHERE day=?", (day,))
    mk = query(cfg, "SELECT symbol, ts, price FROM market WHERE day=? ORDER BY ts", (day,))
    ev = query(cfg, "SELECT kind, action, strategy FROM events WHERE day=?", (day,))
    strategies = []
    for name, g in eq.groupby("strategy"):
        start, end = float(g["equity"].iloc[0]), float(g["equity"].iloc[-1])
        t = tr[tr["strategy"] == name]
        strategies.append({"name": name, "start": start, "end": end, "pct": (end / start - 1) * 100 if start else 0.0,
                           "trades": len(t), "wins": int((t["pnl"] > 0).sum())})
    movers = []
    for sym, g in mk.groupby("symbol"):
        if len(g) > 1:
            movers.append({"symbol": sym, "pct": (g["price"].iloc[-1] / g["price"].iloc[0] - 1) * 100})
    movers.sort(key=lambda m: m["pct"])
    return {"day": day, "strategies": strategies, "trades": len(tr), "wins": int((tr["pnl"] > 0).sum()) if len(tr) else 0,
            "pnl": float(tr["pnl"].sum()) if len(tr) else 0.0, "decisions": len(ev),
            "entries": int(ev["action"].isin(["BLI", "SHORT"]).sum()) if len(ev) else 0,
            "worst": movers[:3], "best": movers[-3:][::-1],
            "btc": next((m["pct"] for m in movers if m["symbol"].startswith("BTC/")), None)}


def report_text(r: dict, team_name: str = "Ekipi") -> str:
    lines = [f"📔 Raporti i {r['day']}"]
    team = next((s for s in r["strategies"] if s["name"] == team_name), None)
    if team:
        lines.append(f"{team_name}: {team['start']:.2f} → {team['end']:.2f} ({team['pct']:+.2f}%)")
    lines.append(f"Tregti të mbyllura: {r['trades']} ({r['wins']} fituese), gjithsej {r['pnl']:+.2f}")
    others = [s for s in r["strategies"] if s["name"] != team_name]
    if others:
        best = max(others, key=lambda s: s["pct"])
        worst = min(others, key=lambda s: s["pct"])
        lines.append(f"Më e mira: {best['name']} {best['pct']:+.2f}% · më e dobëta: {worst['name']} {worst['pct']:+.2f}%")
    if r["btc"] is not None:
        lines.append(f"BTC gjatë ditës: {r['btc']:+.2f}%")
    if r["best"]:
        lines.append("U ngritën më shumë: " + ", ".join(f"{m['symbol'].split('/')[0]} {m['pct']:+.1f}%" for m in r["best"]))
    return "\n".join(lines)


def save_report(cfg, r: dict) -> str:
    text = report_text(r)
    _write(cfg, "INSERT OR REPLACE INTO reports VALUES (?,?,?,?)",
           [(r["day"], time.time(), text, json.dumps(r, ensure_ascii=False))])
    return text


def yesterday() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


# --- strategjitë e laboratorit ---------------------------------------------------------------------
def upsert_strategy(cfg, sid, name, overrides, origin, status, train=None, test=None, test_dd=None, test_trades=None,
                    note=""):
    now = time.time()
    with closing(connect(cfg)) as con, con:
        old = con.execute("SELECT created FROM strategies WHERE id=?", (sid,)).fetchone()
        con.execute("INSERT OR REPLACE INTO strategies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (sid, name, json.dumps(overrides), origin, status, old[0] if old else now, now, train, test,
                     test_dd, test_trades, note))


def strategies(cfg, statuses=None) -> list:
    df = query(cfg, "SELECT * FROM strategies ORDER BY test DESC")
    if statuses:
        df = df[df["status"].isin(statuses)]
    out = df.to_dict("records")
    for r in out:
        r["overrides"] = json.loads(r["overrides"])
    return out


def set_status(cfg, sid: str, status: str, note: str = ""):
    _write(cfg, "UPDATE strategies SET status=?, note=?, updated=? WHERE id=?", [(status, note, time.time(), sid)])
