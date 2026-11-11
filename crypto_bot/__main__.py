"""Rreshti i komandës:  python -m crypto_bot {analizo|skano|backtest|nis}"""
import argparse

from . import journal
from .backtest import backtest, format_backtest
from .bot import run_forever, scan
from .broker import Broker
from .config import load_config
from .data import fetch_candles, fetch_daily, make_exchange
from .strategy import format_report


def main(argv=None):
    p = argparse.ArgumentParser(prog="crypto_bot", description="Robot analize dhe tregtimi për kriptomonedha")
    p.add_argument("komanda", choices=["analizo", "skano", "backtest", "nis", "ditar"])
    p.add_argument("veprimi", nargs="?", choices=["shto"], help="vetëm për 'ditar': shto një parashikim")
    p.add_argument("--drejtimi", choices=["rritje", "renie", "rënie"], help="ditar: drejtimi i parashikuar")
    p.add_argument("--ore", type=float, default=24, help="ditar: afati i parashikimit në orë")
    p.add_argument("--perqindja", type=float, help="ditar: sa %% siguri jep burimi")
    p.add_argument("--objektivi", type=float, help="ditar: çmimi objektiv i parashikuar")
    p.add_argument("--burimi", default="mexc-ai", help="ditar: kush e dha parashikimin")
    p.add_argument("--config", help="rruga e config.json")
    p.add_argument("--symbol", help="p.sh. BTC/USDT")
    p.add_argument("--exchange", help="mexc, binance, bybit ose mt5")
    p.add_argument("--testnet", action="store_true", help="rrjeti i testimit i platformës (Binance, Bybit)")
    p.add_argument("--timeframe", help="p.sh. 15m, 1h, 4h, 1d")
    p.add_argument("--strategjia", dest="strategy", choices=["breakout", "score"], help="mënyra e blerjes")
    p.add_argument("--fitim", type=float, dest="take_profit_pct", help="take-profit në %% (0 = i fikur)")
    p.add_argument("--humbje", type=float, dest="stop_loss_pct", help="stop-loss në %%")
    p.add_argument("--trailing", type=float, dest="trailing_stop_pct", help="trailing stop në %%")
    p.add_argument("--candles", type=int, help="numri i qirinjve historikë")
    p.add_argument("--gjithe-tregun", action="store_true", help="skano gjithë tregun, jo vetëm listën")
    p.add_argument("--live", action="store_true", help="tregto me para reale (kërkon çelësat API)")
    a = p.parse_args(argv)

    cfg = load_config(a.config, exchange=a.exchange, testnet=True if a.testnet else None, timeframe=a.timeframe, candles=a.candles,
                      strategy=a.strategy, take_profit_pct=a.take_profit_pct, stop_loss_pct=a.stop_loss_pct,
                      trailing_stop_pct=a.trailing_stop_pct,
                      symbols=[a.symbol] if a.symbol else None,
                      scan_market=True if a.gjithe_tregun else None)

    if a.komanda == "nis":
        if a.live:
            what = ("urdhra në rrjetin e TESTIMIT (para demo)" if cfg.testnet else
                    "urdhra në llogarinë e hapur në terminalin MT5 (reale ose demo)" if cfg.exchange == "mt5" else
                    "urdhra me PARA REALE")
            if input(f"KUJDES: roboti do të dërgojë {what} në {cfg.exchange}. "
                     "Shkruaj 'PO' për të vazhduar: ").strip() != "PO":
                return print("U anulua.")
            tag = f"_{cfg.exchange}_testnet" if cfg.testnet else f"_{cfg.exchange}_live"
            cfg.state_file = cfg.state_file.replace(".json", tag + ".json")
            cfg.log_file = cfg.log_file.replace(".jsonl", tag + ".jsonl")
        exchange = make_exchange(cfg, with_keys=a.live)
        return run_forever(exchange, Broker(cfg, exchange if a.live else None), cfg)

    exchange = make_exchange(cfg)
    if a.komanda == "ditar":
        path = cfg.predictions_file
        if a.veprimi == "shto":
            if not a.drejtimi:
                raise ValueError("jep --drejtimi rritje ose --drejtimi rënie")
            sym = cfg.symbols[0]
            price = float(exchange.fetch_ticker(sym)["last"])
            e = journal.add(path, a.burimi, sym, a.drejtimi, a.ore, price, a.perqindja, a.objektivi)
            print(f"U shtua: {e['source']} parashikon {e['direction']} për {sym} brenda {a.ore:g} orësh (çmimi tani {price:.6g})")
            # Për krahasim regjistrohet edhe mendimi i robotit në të njëjtin çast.
            mine = scan(exchange, cfg, [sym])
            if mine and mine[0]["direction"] != "ANASH":
                d = "rritje" if mine[0]["direction"] == "RRITJE" else "rënie"
                journal.add(path, "roboti", sym, d, a.ore, price)
                print(f"U shtua: roboti parashikon {d} (pikët {mine[0]['score']:+.0f})")
            else:
                print("Roboti nuk ka drejtim të qartë tani, ndaj nuk u regjistrua parashikim i tij.")
        closed = journal.check(path, exchange)
        if closed:
            print(f"U mbyllën {closed} parashikime që u erdhi afati.")
        return print(journal.report(path))
    if a.komanda == "analizo":
        for r in scan(exchange, cfg, cfg.symbols):
            print(format_report(r, cfg), end="\n\n")
    elif a.komanda == "skano":
        cfg.scan_market = True
        rows = scan(exchange, cfg)
        rows.sort(key=lambda r: ({"BLI": 0, "PRIT": 1, "SHIT": 2}[r["signal"]], -r["score"]))
        if cfg.strategy == "breakout":
            # "Larg" = sa % duhet të ngjitet çmimi që një mbyllje të japë sinjal blerjeje.
            print(f"{'Monedha':<16}{'Çmimi':>12}{'Pikët':>8}  {'Sinjali':<8}{'Blerje mbi':>12}{'Larg':>8}  Trendi ditor")
            for r in rows:
                gap = (r["buy_above"] / r["price"] - 1) * 100
                print(f"{r['symbol']:<16}{r['price']:>12.6g}{r['score']:>+8.1f}  {r['signal']:<8}"
                      f"{r['buy_above']:>12.6g}{gap:>+7.1f}%  {'rritës' if r['daily_up'] else 'jo rritës'}")
        else:
            print(f"{'Monedha':<16}{'Çmimi':>12}{'Pikët':>8}  {'Sinjali':<8}Arsyeja")
            for r in rows:
                print(f"{r['symbol']:<16}{r['price']:>12.6g}{r['score']:>+8.1f}  {r['signal']:<8}{r['signal_reason']}")
        buys = sum(r["signal"] == "BLI" for r in rows)
        print(f"\n{len(rows)} monedha | sinjale blerjeje: {buys} | trend ditor rritës: {sum(r['daily_up'] for r in rows)}")
    elif a.komanda == "backtest":
        for sym in cfg.symbols:
            df = fetch_candles(exchange, sym, cfg.timeframe, cfg.candles)
            daily = fetch_daily(exchange, sym, cfg, df)
            print(format_backtest(backtest(df, cfg, daily), cfg, sym), end="\n\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nRoboti u ndal.")
    except (RuntimeError, ValueError) as e:
        raise SystemExit(f"Gabim: {e}")
