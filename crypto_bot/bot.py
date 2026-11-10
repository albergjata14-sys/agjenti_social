"""Cikli kryesor i robotit: skanon tregun, analizon, hap dhe mbyll pozicione."""
import json
import time
from datetime import datetime, timezone

from .data import fetch_candles, fetch_daily, spread_pct, top_symbols
from .strategy import analyze


def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def watchlist(exchange, cfg) -> list:
    return top_symbols(exchange, cfg.quote, cfg.scan_top_n) if cfg.scan_market else list(cfg.symbols)


def scan(exchange, cfg, symbols=None) -> list:
    """Analizon çdo monedhë dhe i rendit sipas pikëve (më të mirat për blerje në fillim)."""
    results = []
    for sym in symbols or watchlist(exchange, cfg):
        try:
            df = fetch_candles(exchange, sym, cfg.timeframe, cfg.candles)
            results.append(analyze(df, cfg, sym, daily=fetch_daily(exchange, sym, cfg, df)))
        except Exception as e:  # një monedhë e dështuar nuk duhet të ndalë skanimin
            log(f"{sym}: u anashkalua ({e})")
    return sorted(results, key=lambda a: a["score"], reverse=True)


def record(cfg, **entry):
    """Shton një rresht te regjistri i vendimeve (JSON Lines)."""
    if cfg.log_file:
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
        with open(cfg.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def losses_in_row(trades: list, today: str) -> int:
    """Sa tregtitë e fundit të sotme (UTC) janë mbyllur me humbje radhazi."""
    n = 0
    for t in reversed(trades):
        day = datetime.fromtimestamp(t["closed"], timezone.utc).strftime("%Y-%m-%d")
        if day != today or t["pnl"] > 0:
            break
        n += 1
    return n


def _sell(broker, cfg, sym, price, reason, actions, score=None):
    t = broker.sell(sym, price, reason)
    actions.append(("SHIT", sym, t))
    record(cfg, symbol=sym, action="SHIT", reason=reason, price=t["exit"], score=score,
           pnl=round(t["pnl"], 4), pnl_pct=round(t["pnl_pct"], 2))
    log(f"SHIT {sym} @ {t['exit']:.6g} ({reason}) → {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")


def run_cycle(exchange, broker, cfg) -> list:
    """Një kalim i plotë. Kthen listën e veprimeve të kryera."""
    actions, st = [], broker.state
    # 1) Menaxho pozicionet e hapura me çmimin aktual: stop-loss / take-profit / trailing.
    prices = {}
    for sym in list(broker.positions):
        price = prices[sym] = float(exchange.fetch_ticker(sym)["last"])
        reason = broker.check_exit(sym, price)
        if reason:
            _sell(broker, cfg, sym, price, reason, actions)

    # 2) Analizo tregun dhe mbyll pozicionet me sinjal shitjeje.
    symbols = list(dict.fromkeys(watchlist(exchange, cfg) + list(broker.positions)))
    results = scan(exchange, cfg, symbols)
    for a in results:
        sym = a["symbol"]
        prices.setdefault(sym, a["price"])
        if sym in broker.positions and a["signal"] == "SHIT":
            _sell(broker, cfg, sym, prices[sym], "sinjal: " + a["signal_reason"], actions, a["score"])

    # 3) Kufiri ditor i humbjes: pasi preket, sot nuk hapen blerje të reja.
    equity = broker.equity(prices)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["day_start_equity"] = today, equity
    day_pct = (equity / st["day_start_equity"] - 1) * 100 if st["day_start_equity"] else 0.0
    halted = None
    if cfg.max_daily_loss_pct and day_pct <= -cfg.max_daily_loss_pct:
        halted = f"kufiri ditor i humbjes u prek ({day_pct:+.2f}%)"
    elif cfg.max_consecutive_losses and losses_in_row(st["trades"], today) >= cfg.max_consecutive_losses:
        halted = f"{cfg.max_consecutive_losses} humbje radhazi sot"

    # 4) Hap pozicione të reja. Çdo vendim regjistrohet një herë për çdo qiri të ri.
    seen, entered = st.setdefault("last_logged", {}), st.setdefault("last_entry_signal", {})
    for a in results:
        sym, new_candle = a["symbol"], seen.get(a["symbol"]) != a["time"]
        seen[sym] = a["time"]
        skip = None
        if a["signal"] != "BLI":
            skip = a["signal_reason"]
        elif sym in broker.positions:
            skip = "pozicioni është tashmë i hapur"
        elif entered.get(sym) == a["time"]:
            skip = "ky sinjal është përdorur tashmë (pa ri-hyrje në të njëjtin qiri)"
        elif halted:
            skip = halted
        elif len(broker.positions) >= cfg.max_open_positions:
            skip = f"numri maksimal i pozicioneve ({cfg.max_open_positions})"
        elif cfg.max_spread_pct and (spread := spread_pct(exchange, sym) or 0) > cfg.max_spread_pct:
            skip = f"diferenca blerje/shitje shumë e madhe ({spread:.2f}% > {cfg.max_spread_pct:g}%)"
        else:
            pos = broker.buy(sym, a["price"], equity, a["plan"]["stop_pct"])
            if pos:
                entered[sym] = a["time"]
                actions.append(("BLI", sym, pos))
                record(cfg, symbol=sym, action="BLI", reason=a["signal_reason"], price=pos["entry"],
                       score=a["score"], stop_loss=pos["sl"], take_profit=pos["tp"])
                log(f"BLI {sym} @ {pos['entry']:.6g} ({a['signal_reason']}) | fitim → "
                    f"{'%.6g' % pos['tp'] if pos['tp'] else 'i hapur'} | stop → {pos['sl']:.6g}")
                continue
            skip = "fonde të pamjaftueshme ose nën minimumin e platformës"
        if new_candle:
            record(cfg, symbol=sym, action="ANASHKALO" if a["signal"] == "BLI" else a["signal"],
                   reason=skip, price=a["price"], score=a["score"])
    broker.save()
    log(f"Kapitali: {broker.equity(prices):.2f} {cfg.quote} (sot {day_pct:+.2f}%"
        f"{', BLERJET TË NDALURA' if halted else ''}) | pozicione të hapura: "
        f"{', '.join(broker.positions) or 'asnjë'}")
    return actions


def run_forever(exchange, broker, cfg):
    log(f"Roboti u nis në modalitetin {'REAL' if broker.live else 'SIMULIM'} në {cfg.exchange}. Ctrl+C për ta ndalur.")
    while True:
        try:
            run_cycle(exchange, broker, cfg)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log(f"Gabim në cikël (do të riprovohet): {e}")
        time.sleep(cfg.poll_seconds)
