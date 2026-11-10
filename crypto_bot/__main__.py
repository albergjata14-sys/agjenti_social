"""Rreshti i komandës:  python -m crypto_bot {analizo|skano|backtest|nis}"""
import argparse

from .backtest import backtest, format_backtest
from .bot import run_forever, scan
from .broker import Broker
from .config import load_config
from .data import fetch_candles, make_exchange
from .strategy import format_report


def main(argv=None):
    p = argparse.ArgumentParser(prog="crypto_bot", description="Robot analize dhe tregtimi për kriptomonedha")
    p.add_argument("komanda", choices=["analizo", "skano", "backtest", "nis"])
    p.add_argument("--config", help="rruga e config.json")
    p.add_argument("--symbol", help="p.sh. BTC/USDT")
    p.add_argument("--exchange", help="p.sh. binance, kraken, bybit")
    p.add_argument("--timeframe", help="p.sh. 15m, 1h, 4h, 1d")
    p.add_argument("--fitim", type=float, dest="take_profit_pct", help="take-profit në %%")
    p.add_argument("--humbje", type=float, dest="stop_loss_pct", help="stop-loss në %%")
    p.add_argument("--trailing", type=float, dest="trailing_stop_pct", help="trailing stop në %%")
    p.add_argument("--candles", type=int, help="numri i qirinjve historikë")
    p.add_argument("--gjithe-tregun", action="store_true", help="skano gjithë tregun, jo vetëm listën")
    p.add_argument("--live", action="store_true", help="tregto me para reale (kërkon çelësat API)")
    a = p.parse_args(argv)

    cfg = load_config(a.config, exchange=a.exchange, timeframe=a.timeframe, candles=a.candles,
                      take_profit_pct=a.take_profit_pct, stop_loss_pct=a.stop_loss_pct,
                      trailing_stop_pct=a.trailing_stop_pct,
                      symbols=[a.symbol] if a.symbol else None,
                      scan_market=True if a.gjithe_tregun else None)

    if a.komanda == "nis":
        if a.live:
            if input("KUJDES: do të tregtohet me PARA REALE. Shkruaj 'PO' për të vazhduar: ").strip() != "PO":
                return print("U anulua.")
            cfg.state_file = cfg.state_file.replace(".json", "_live.json")
        exchange = make_exchange(cfg, with_keys=a.live)
        return run_forever(exchange, Broker(cfg, exchange if a.live else None), cfg)

    exchange = make_exchange(cfg)
    if a.komanda == "analizo":
        for r in scan(exchange, cfg, cfg.symbols):
            print(format_report(r, cfg), end="\n\n")
    elif a.komanda == "skano":
        cfg.scan_market = True
        print(f"{'Monedha':<14}{'Çmimi':>14}{'Pikët':>8}  {'Sinjali':<6} Drejtimi")
        for r in scan(exchange, cfg):
            print(f"{r['symbol']:<14}{r['price']:>14.6g}{r['score']:>+8.1f}  {r['signal']:<6} {r['direction']}")
    elif a.komanda == "backtest":
        for sym in cfg.symbols:
            df = fetch_candles(exchange, sym, cfg.timeframe, cfg.candles)
            print(format_backtest(backtest(df, cfg), cfg, sym), end="\n\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nRoboti u ndal.")
