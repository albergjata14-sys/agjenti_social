"""Alert Manager: vepron vetëm për mesazhet që nisin me "SNIPER SIGNAL"; ruan alarmin pa e përsëritur."""
import json
import time
from pathlib import Path

ALERTS_FILE = Path("bots_alerts.jsonl")       # jashtë git-it
REPEAT_HOURS = 24


def _field(msg, name):
    for line in msg.splitlines():
        if line.startswith(name + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def format_alert(sniper_msg):
    if not sniper_msg.strip().upper().startswith("SNIPER SIGNAL"):
        return ""
    t1, t2 = _field(sniper_msg, "Target 1"), _field(sniper_msg, "Target 2")
    return (f"SNIPER SIGNAL\nPair: {_field(sniper_msg, 'Pair')}\nDirection: {_field(sniper_msg, 'Direction')}\n"
            f"Entry: {_field(sniper_msg, 'Entry Zone')}\nStop: {_field(sniper_msg, 'Stop')}\n"
            f"Targets: {t1} / {t2}\nRR: {_field(sniper_msg, 'RR')}")


def recent_alerts(limit=50):
    try:
        lines = ALERTS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out[::-1]


def send(sniper_msg, timeframe=""):
    """Kthen (alarmi, i ri?). I njëjti sinjal (çifti, drejtimi, zona) nuk ruhet dy herë brenda 24 orësh."""
    alert = format_alert(sniper_msg)
    if not alert:
        return "", False
    key = "|".join([_field(alert, "Pair"), timeframe, _field(alert, "Direction"), _field(alert, "Entry")])
    now = time.time()
    if any(a.get("key") == key and now - a.get("time", 0) < REPEAT_HOURS * 3600 for a in recent_alerts(200)):
        return alert, False
    with ALERTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": now, "key": key, "timeframe": timeframe, "alert": alert}, ensure_ascii=False) + "\n")
    return alert, True
