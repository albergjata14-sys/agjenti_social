"""Rreshti i komandës:  python -m crypto_bot {analizo|skano|backtest|nis}"""
import argparse

from .backtest import backtest, format_backtest
from .bot import run_forever, scan
from .broker import Broker
from .config import load_config
from .data import fetch_candles, fetch_daily, make_exchange
from .strategy import format_report


def main(argv=None):
    p = argparse.ArgumentParser(prog="crypto_bot", description="Robot analize dhe tregtimi për kriptomonedha")
    p.add_argument("komanda", choices=["analizo", "skano", "backtest", "nis"])
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
    if a.komanda == "analizo":
        for r in scan(exchange, cfg, cfg.symbols):
            print(format_report(r, cfg), end="\n\n")
    elif a.komanda == "skano":
        cfg.scan_market = True
        print(f"{'Monedha':<16}{'Çmimi':>14}{'Pikët':>8}  {'Sinjali':<6} Arsyeja")
        rows = scan(exchange, cfg)
        for r in sorted(rows, key=lambda r: ({"BLI": 0, "PRIT": 1, "SHIT": 2}[r["signal"]], -r["score"])):
            print(f"{r['symbol']:<16}{r['price']:>14.6g}{r['score']:>+8.1f}  {r['signal']:<6} {r['signal_reason']}")
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
