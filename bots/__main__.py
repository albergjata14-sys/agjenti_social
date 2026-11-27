"""python -m bots                                   -> lista e botëve
python -m bots sniper                            -> roli dhe prompti i një boti
python -m bots skano --top 10 --tf 4h            -> kalon 10 monedhat më të tregtuara të MEXC nëpër zinxhir
python -m bots skano --pairs BTC/USDT ETH/USDT --tf 1h --cdo 15   -> njësoj, çdo 15 minuta pa u ndalur"""
import argparse
import sys
import time

from bots import ALL_BOTS, get_bot


def _scan(args):
    from bots.chain import scan
    from bots.chart_feeder.logic import top_pairs

    while True:
        pairs = args.pairs or top_pairs(args.top)
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M')}] {args.tf} · {len(pairs)} çifte")

        def show(r):
            mark = "🚨 ALARM" if r.alert else f"u ndal te {r.stopped_at}"
            print(f"  {r.pair:14} {mark}")
            if r.alert:
                print("    " + r.alert.replace("\n", "\n    ") + ("" if r.new_alert else "\n    (i dërguar më parë)"))

        scan(pairs, args.tf, on_result=show)
        if not args.cdo:
            break
        time.sleep(args.cdo * 60)


if len(sys.argv) > 1 and sys.argv[1] == "skano":
    ap = argparse.ArgumentParser(prog="python -m bots skano")
    ap.add_argument("--pairs", nargs="*", help="p.sh. BTC/USDT ETH/USDT (parazgjedhur: më të tregtuarat)")
    ap.add_argument("--top", type=int, default=10, help="sa monedha nga më të tregtuarat e MEXC")
    ap.add_argument("--tf", default="4h", help="1m 5m 15m 30m 1h 4h 1d 1w")
    ap.add_argument("--cdo", type=float, default=0, help="përsërite çdo kaq minuta (0 = një herë)")
    _scan(ap.parse_args(sys.argv[2:]))
elif len(sys.argv) > 1:
    bot = get_bot(" ".join(sys.argv[1:]))
    print(f"{bot.name}\nRoli: {bot.role}\nPrompti: {bot.prompt_file}\n")
    print(bot.prompt or "(ende pa prompt)")
else:
    for cls in ALL_BOTS:
        bot = cls()
        print(f"{'✅' if bot.ready else '⏳'} {bot.name:15} {bot.role}")
