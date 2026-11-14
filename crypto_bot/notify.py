"""Njoftimet: në aplikacion (regjistër) dhe në telefon përmes Telegram-it.

Llojet: veprimet e robotit (hyrje / dalje), sinjale të reja te monedhat e ndjekura, lëvizje të mëdha të
çmimit dhe alarme çmimi që i vendos vetë përdoruesi. Çdo njoftim ruhet te `notify_file`, që paneli ta
shfaqë; nëse Telegram-i është lidhur, dërgohet edhe atje. Asnjë gabim njoftimi nuk e ndalon robotin.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

TELEGRAM_FILE = "crypto_bot_telegram.json"   # tokeni dhe chat_id i ruajtur në kompjuter (jashtë git-it)
API = "https://api.telegram.org/bot{token}/{method}"


def _raw_settings():
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        try:
            import streamlit as st

            token = token or st.secrets.get("TELEGRAM_BOT_TOKEN")
            chat = chat or st.secrets.get("TELEGRAM_CHAT_ID")
        except Exception:
            pass
    if not (token and chat) and Path(TELEGRAM_FILE).exists():
        saved = json.loads(Path(TELEGRAM_FILE).read_text())
        token, chat = token or saved.get("token"), chat or saved.get("chat_id")
    return (str(token).strip(), str(chat).strip()) if token and chat else None


def is_numeric_chat(chat: str) -> bool:
    return chat.lstrip("-").isdigit()


_resolved = {}


def telegram_settings():
    """(token, chat_id) nga variablat e mjedisit, sekretet e Streamlit ose skedari lokal; None nëse mungon.

    Telegram-i dërgon vetëm te një chat_id numerik. Nëse në vend të tij është shkruar emri i llogarisë
    (p.sh. @emri), numri gjendet vetë nga mesazhet që i ke dërguar robotit.
    """
    raw = _raw_settings()
    if not raw:
        return None
    token, chat = raw
    if is_numeric_chat(chat):
        return token, chat
    if (token, chat) not in _resolved:
        try:
            _resolved[(token, chat)] = telegram_find_chat(token, username=chat)
        except Exception:
            _resolved[(token, chat)] = None
    found = _resolved[(token, chat)]
    return (token, found) if found else (token, chat)


def telegram_check(text: str = "✅ Prova nga paneli i robotit.", settings=None):
    """Dërgon një mesazh dhe kthen (u dërgua, shpjegimi i gabimit në shqip ose "")."""
    raw = _raw_settings()
    settings = settings or telegram_settings()
    if not settings:
        return False, "Mungon tokeni ose TELEGRAM_CHAT_ID."
    token, chat = settings
    if not is_numeric_chat(chat):
        return False, (f"TELEGRAM_CHAT_ID duhet të jetë numër (p.sh. 123456789), jo emri i llogarisë “{chat}”. "
                       "Hap robotin tënd në Telegram, shtyp Start ose shkruaji “përshëndetje”, pastaj shtyp "
                       "“Gjej chat_id” këtu poshtë.")
    try:
        r = requests.post(API.format(token=token, method="sendMessage"),
                          json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=10)
        body = r.json()
    except (requests.RequestException, ValueError) as e:
        return False, f"Telegram-i nuk u arrit: {e}"
    if body.get("ok"):
        return True, ""
    desc = body.get("description", "")
    hint = {401: "Tokeni është i gabuar: kopjoje prapë të plotë nga @BotFather.",
            400: "Biseda nuk u gjet: kontrollo TELEGRAM_CHAT_ID dhe shtyp Start te roboti yt në Telegram.",
            403: "Roboti nuk lejohet të të shkruajë: hap robotin në Telegram dhe shtyp Start (ose zhbllokoje)."}
    return False, f"{hint.get(body.get('error_code'), 'Telegram-i e refuzoi mesazhin.')} ({desc})"


def telegram_send(text: str, settings=None) -> bool:
    return telegram_check(text, settings)[0]


def telegram_photo(png: bytes, caption: str, settings=None) -> bool:
    """Dërgon një foto (grafikun) me tekstin si përshkrim. Telegram-i lejon deri në 1024 shkronja."""
    settings = settings or telegram_settings()
    if not settings or not is_numeric_chat(settings[1]):
        return False
    token, chat = settings
    try:
        r = requests.post(API.format(token=token, method="sendPhoto"), data={"chat_id": chat, "caption": caption[:1024]},
                          files={"photo": ("grafiku.png", png, "image/png")}, timeout=20)
        return bool(r.json().get("ok"))
    except (requests.RequestException, ValueError):
        return False


def wants_images(cfg) -> bool:
    """A ia vlen të vizatohet grafiku: vetëm kur njoftimet shkojnë vërtet në Telegram."""
    return bool(cfg.notify_telegram and telegram_settings())


def telegram_find_chat(token: str, username: str = None):
    """chat_id i bisedës me robotin. Me `username` kërkohet pikërisht ajo llogari; përndryshe biseda e fundit.
    Përdoruesi duhet t'i ketë shkruar robotit më parë (Telegram-i i ruan mesazhet rreth 24 orë)."""
    r = requests.get(API.format(token=token, method="getUpdates"), timeout=10)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram e refuzoi tokenin"))
    want = (username or "").lstrip("@").lower()
    for upd in reversed(data.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat.get("id") is None:
            continue
        if want and want not in (str(chat.get("username", "")).lower(), str(msg.get("from", {}).get("username", "")).lower()):
            continue
        return str(chat["id"])
    return None


def telegram_save(token: str, chat_id: str):
    Path(TELEGRAM_FILE).write_text(json.dumps({"token": token, "chat_id": chat_id}))


# --- regjistri i njoftimeve ------------------------------------------------------------------------
def emit(cfg, kind: str, symbol: str, text: str, image: bytes = None, **extra) -> dict:
    """Ruan një njoftim te regjistri dhe e dërgon në Telegram (nëse është lidhur), me grafik kur ka."""
    entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": time.time(), "kind": kind,
             "symbol": symbol, "text": text, **extra}
    sent = False
    if cfg.notify_telegram:
        sent = (telegram_photo(image, text) if image else False) or telegram_send(text)
    entry["telegram"] = sent
    entry["image"] = bool(image)
    if cfg.notify_file:
        with open(cfg.notify_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def recent(cfg, limit: int = 50) -> list:
    p = Path(cfg.notify_file)
    if not cfg.notify_file or not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]


# --- alarmet e çmimit ------------------------------------------------------------------------------
def load_alerts(cfg) -> list:
    if not cfg.alerts_file:
        return []
    p = Path(cfg.alerts_file)
    return json.loads(p.read_text()) if p.is_file() else []


def save_alerts(cfg, alerts: list):
    Path(cfg.alerts_file).write_text(json.dumps(alerts, indent=2))


def add_alert(cfg, symbol: str, direction: str, price: float) -> dict:
    """direction: "mbi" (njofto kur çmimi ngjitet mbi nivelin) ose "nen" (kur bie nën të)."""
    if direction not in ("mbi", "nen"):
        raise ValueError("drejtimi i alarmit duhet të jetë 'mbi' ose 'nen'")
    alerts = load_alerts(cfg)
    alert = {"symbol": symbol, "direction": direction, "price": float(price), "created": time.time()}
    alerts.append(alert)
    save_alerts(cfg, alerts)
    return alert


def _name(sym: str) -> str:
    from .config import display

    return display(sym)


def _fmt(x) -> str:
    return f"{x:,.6g}"


def check_price_alerts(cfg, prices: dict) -> list:
    """Alarmet e përmbushura dërgohen një herë dhe hiqen. `prices`: {simboli: çmimi tani}."""
    alerts, keep, fired = load_alerts(cfg), [], []
    for a in alerts:
        p = prices.get(a["symbol"])
        hit = p is not None and (p >= a["price"] if a["direction"] == "mbi" else p <= a["price"])
        if hit:
            word = "u ngjit mbi" if a["direction"] == "mbi" else "ra nën"
            fired.append(emit(cfg, "alarm", a["symbol"], f"🔔 {a['symbol']} {word} {_fmt(a['price'])} (tani {_fmt(p)})"))
        else:
            keep.append(a)
    if fired:
        save_alerts(cfg, keep)
    return fired


# --- njoftimet automatike nga analiza --------------------------------------------------------------
SIGNAL_TEXT = {"BLI": "🟢 sinjal blerjeje", "SHORT": "🔻 sinjal shitjeje short", "SHIT": "⚪ sinjal daljeje"}


def check_market(cfg, state: dict, analyses: list, chart=None) -> list:
    """Sinjale të reja dhe lëvizje të mëdha çmimi te monedhat e analizuara. `state` ruhet nga thirrësi."""
    sent, last_sig, base = [], state.setdefault("notify_signal", {}), state.setdefault("notify_base", {})
    for a in analyses:
        sym, sig, price = a["symbol"], a["signal"], a["price"]
        key = f"{sig}|{a['time']}"
        if cfg.notify_signals and sig in SIGNAL_TEXT and last_sig.get(sym, "").split("|")[0] != sig:
            p = a.get("plan") or {}
            levels = (f"\nHyrja {_fmt(price)} · Stop-loss {_fmt(p.get('stop_loss'))} · "
                      f"{'Objektivi ' + _fmt(p['take_profit']) if p.get('take_profit') else 'fitimi i hapur'}") if p else ""
            image = None
            if chart and sig in ("BLI", "SHORT") and p:
                try:
                    image = chart(a)
                except Exception:
                    image = None
            sent.append(emit(cfg, "sinjal", sym, f"{SIGNAL_TEXT[sig]} te {_name(sym)} @ {_fmt(price)}: "
                                                 f"{a['signal_reason']}{levels}", image=image))
        last_sig[sym] = key if sig in SIGNAL_TEXT else ""
        if cfg.alert_move_pct:
            ref = base.get(sym)
            if ref is None:
                base[sym] = price
            elif abs(price / ref - 1) * 100 >= cfg.alert_move_pct:
                move = (price / ref - 1) * 100
                sent.append(emit(cfg, "levizje", sym, f"{'📈' if move > 0 else '📉'} {sym} {move:+.1f}% "
                                                     f"(nga {_fmt(ref)} në {_fmt(price)})"))
                base[sym] = price
    return sent


def trade_message(kind: str, symbol: str, info: dict, quote: str) -> str:
    if kind in ("BLI", "SHORT"):
        what = "🟢 Roboti BLEU" if kind == "BLI" else "🔻 Roboti hapi SHORT"
        tp = f" | objektivi (TP) {_fmt(info['tp'])}" if info.get("tp") else " | fitimi i hapur"
        return f"{what} {_name(symbol)} @ {_fmt(info['entry'])} | stop-loss {_fmt(info['sl'])}{tp}"
    return (f"{'✅' if info['pnl'] > 0 else '❌'} Roboti mbylli {info.get('side', 'long')} {_name(symbol)} @ {_fmt(info['exit'])}: "
            f"{info['pnl']:+.2f} {quote} ({info['pnl_pct']:+.2f}%), {info['reason']}")
