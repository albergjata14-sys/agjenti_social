"""Cikli kryesor i robotit: skanon tregun, analizon, hap dhe mbyll pozicione."""
import time
from datetime import datetime

from .data import fetch_candles, top_symbols
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
            results.append(analyze(df, cfg, sym))
        except Exception as e:  # një monedhë e dështuar nuk duhet të ndalë skanimin
            log(f"{sym}: u anashkalua ({e})")
    return sorted(results, key=lambda a: a["score"], reverse=True)


def run_cycle(exchange, broker, cfg) -> list:
    """Një kalim i plotë. Kthen listën e veprimeve të kryera."""
    actions = []
    # 1) Menaxho pozicionet e hapura me çmimin aktual: stop-loss / take-profit / trailing.
    prices = {}
    for sym in list(broker.positions):
        price = prices[sym] = float(exchange.fetch_ticker(sym)["last"])
        reason = broker.check_exit(sym, price)
        if reason:
            t = broker.sell(sym, price, reason)
            actions.append(("SHIT", sym, t))
            log(f"SHIT {sym} @ {t['exit']:.6g} ({reason}) → {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")

    # 2) Analizo tregun; mbyll me sinjal shitjeje, hap me sinjal blerjeje.
    symbols = list(dict.fromkeys(watchlist(exchange, cfg) + list(broker.positions)))
    results = scan(exchange, cfg, symbols)
    for a in results:
        sym = a["symbol"]
        prices.setdefault(sym, a["price"])
        if sym in broker.positions and a["signal"] == "SHIT":
            t = broker.sell(sym, prices[sym], "sinjal")
            actions.append(("SHIT", sym, t))
            log(f"SHIT {sym} @ {t['exit']:.6g} (sinjal {a['score']:+.0f}) → {t['pnl']:+.2f} ({t['pnl_pct']:+.2f}%)")
    equity = broker.equity(prices)
    for a in results:
        sym = a["symbol"]
        if len(broker.positions) >= cfg.max_open_positions:
            break
        if a["signal"] == "BLI" and sym not in broker.positions:
            pos = broker.buy(sym, a["price"], equity)
            if pos:
                actions.append(("BLI", sym, pos))
                log(f"BLI {sym} @ {pos['entry']:.6g} (pikët {a['score']:+.0f}) | "
                    f"fitim → {pos['tp']:.6g} | stop → {pos['sl']:.6g}")
    log(f"Kapitali: {broker.equity(prices):.2f} {cfg.quote} | pozicione të hapura: "
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
