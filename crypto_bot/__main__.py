"""Rreshti i komandës:  python -m crypto_bot {analizo|skano|backtest|nis}"""
import argparse
import time

from . import journal, notify
from .bot import log
from .backtest import backtest, format_backtest, format_portfolio, portfolio_backtest
from .bot import run_forever, scan
from .broker import Broker
from .config import ACTIVE, load_config
from .data import connect, fetch_candles, fetch_daily, top_symbols
from .strategy import format_report


def telegram_setup(action: str):
    """Lidh Telegram-in: ruan tokenin e robotit dhe gjen vetë chat_id pasi i shkruan robotit."""
    if action == "test":
        ok = notify.telegram_send("✅ Njoftimet e robotit të kriptove punojnë.")
        return print("Mesazhi u dërgua në Telegram." if ok else
                     "Telegram-i nuk është lidhur ose mesazhi nuk shkoi. Lidhe me: python -m crypto_bot njoftime lidh")
    import getpass

    print("1) Në Telegram hap @BotFather, shkruaj /newbot dhe ndiq hapat. Do të marrësh një token.")
    token = getpass.getpass("2) Ngjite tokenin këtu (nuk shfaqet në ekran) dhe shtyp Enter: ").strip()
    input("3) Hap robotin tënd të ri në Telegram, shtyp Start ose shkruaji një mesazh, pastaj shtyp Enter këtu...")
    chat = notify.telegram_find_chat(token)
    if not chat:
        return print("Nuk u gjet asnjë mesazh. Shkruaji robotit në Telegram dhe provo prapë.")
    notify.telegram_save(token, chat)
    ok = notify.telegram_send("✅ Roboti i kriptove u lidh. Këtu do të marrësh njoftimet.", (token, chat))
    print(f"U lidh dhe u ruajt te {notify.TELEGRAM_FILE}." + ("" if ok else " Por mesazhi provë nuk shkoi."))


def run_alerts(exchange, cfg):
    """Vetëm njoftime, pa tregtuar: sinjale të reja, lëvizje të mëdha dhe alarme çmimi."""
    from .bot import scan, watchlist

    state = {}
    log(f"Njoftimet u nisën për {'gjithë tregun' if cfg.scan_market else ', '.join(cfg.symbols)}. Ctrl+C për t'i ndalur.")
    if not notify.telegram_settings():
        log("Telegram-i nuk është lidhur: njoftimet shfaqen vetëm në panel. Lidhe me: njoftime lidh")
    while True:
        try:
            symbols = list(dict.fromkeys(watchlist(exchange, cfg) + [x["symbol"] for x in notify.load_alerts(cfg)]))
            results = scan(exchange, cfg, symbols)
            sent = notify.check_market(cfg, state, results)
            sent += notify.check_price_alerts(cfg, {r["symbol"]: r["price"] for r in results})
            for e in sent:
                log(e["text"])
        except Exception as e:
            log(f"Gabim gjatë kontrollit (do të riprovohet): {e}")
        time.sleep(cfg.poll_seconds)


def main(argv=None):
    p = argparse.ArgumentParser(prog="crypto_bot", description="Robot analize dhe tregtimi për kriptomonedha")
    p.add_argument("komanda", choices=["analizo", "skano", "backtest", "portofol", "nis", "ditar", "njoftime"])
    p.add_argument("veprimi", nargs="?", choices=["shto", "lidh", "test"],
                   help="ditar: shto | njoftime: lidh (Telegram), test, shto (alarm çmimi)")
    p.add_argument("--mbi", type=float, help="njoftime shto: njofto kur çmimi ngjitet mbi këtë nivel")
    p.add_argument("--nen", type=float, help="njoftime shto: njofto kur çmimi bie nën këtë nivel")
    p.add_argument("--drejtimi", choices=["rritje", "renie", "rënie"], help="ditar: drejtimi i parashikuar")
    p.add_argument("--ore", type=float, default=24, help="ditar: afati i parashikimit në orë")
    p.add_argument("--perqindja", type=float, help="ditar: sa %% siguri jep burimi")
    p.add_argument("--objektivi", type=float, help="ditar: çmimi objektiv i parashikuar")
    p.add_argument("--burimi", default="mexc-ai", help="ditar: kush e dha parashikimin")
    p.add_argument("--config", help="rruga e config.json")
    p.add_argument("--symbol", help="p.sh. BTC/USDT; disa me presje: XAUUSD,BTCUSD")
    p.add_argument("--exchange", help="mexc, binance, bybit ose mt5")
    p.add_argument("--testnet", action="store_true", help="rrjeti i testimit i platformës (Binance, Bybit)")
    p.add_argument("--timeframe", help="p.sh. 15m, 1h, 4h, 1d")
    p.add_argument("--strategjia", dest="strategy", choices=["breakout", "momentum", "score", "engulf"], help="strategjia")
    p.add_argument("--aktiv", action="store_true",
                   help="mënyra aktive: lart ose poshtë sipas lëvizjes, në gjithë tregun, me këmbim mes monedhave")
    p.add_argument("--fitim", type=float, dest="take_profit_pct", help="take-profit në %% (0 = i fikur)")
    p.add_argument("--humbje", type=float, dest="stop_loss_pct", help="stop-loss në %%")
    p.add_argument("--trailing", type=float, dest="trailing_stop_pct", help="trailing stop në %%")
    p.add_argument("--candles", type=int, help="numri i qirinjve historikë")
    p.add_argument("--gjithe-tregun", action="store_true", help="skano gjithë tregun, jo vetëm listën")
    p.add_argument("--short", action="store_true", help="lejo edhe shitje short (vetëm MT5 ose simulim)")
    p.add_argument("--live", action="store_true", help="tregto me para reale (kërkon çelësat API)")
    a = p.parse_args(argv)

    overrides = dict(exchange=a.exchange, testnet=True if a.testnet else None, timeframe=a.timeframe,
                     candles=a.candles, strategy=a.strategy, take_profit_pct=a.take_profit_pct,
                     stop_loss_pct=a.stop_loss_pct, trailing_stop_pct=a.trailing_stop_pct,
                     symbols=[x.strip() for x in a.symbol.split(",") if x.strip()] if a.symbol else None,
                     scan_market=True if a.gjithe_tregun else None, allow_short=True if a.short else None)
    if a.aktiv:     # mënyra aktive plotëson vetëm ato që nuk janë dhënë shprehimisht
        overrides.update({k: v for k, v in ACTIVE.items() if overrides.get(k) is None})
    cfg = load_config(a.config, **overrides)

    if a.komanda == "nis":
        exchange = connect(cfg, with_keys=a.live)
        if a.live and cfg.allow_short and not getattr(exchange, "stop_on_order", False):
            raise ValueError("shitja short me urdhra realë punon vetëm në MT5; në platformat spot përdor simulimin")
        if a.live:
            what = ("urdhra në rrjetin e TESTIMIT (para demo)" if cfg.testnet else
                    f"urdhra në llogarinë MT5 {exchange.account_label()}" if hasattr(exchange, "account_label") else
                    "urdhra me PARA REALE")
            if input(f"KUJDES: roboti do të dërgojë {what} në {cfg.exchange}. "
                     "Shkruaj 'PO' për të vazhduar: ").strip().upper() != "PO":
                return print("U anulua.")
            tag = f"_{cfg.exchange}_testnet" if cfg.testnet else f"_{cfg.exchange}_live"
            cfg.state_file = cfg.state_file.replace(".json", tag + ".json")
            cfg.log_file = cfg.log_file.replace(".jsonl", tag + ".jsonl")
        return run_forever(exchange, Broker(cfg, exchange if a.live else None), cfg)

    if a.komanda == "njoftime" and a.veprimi in ("lidh", "test"):
        return telegram_setup(a.veprimi)
    exchange = connect(cfg)
    if a.komanda == "njoftime":
        if a.veprimi == "shto":
            if (a.mbi is None) == (a.nen is None):
                raise ValueError("jep njërin nga --mbi ose --nen, p.sh. --mbi 80000")
            al = notify.add_alert(cfg, cfg.symbols[0], "mbi" if a.mbi is not None else "nen", a.mbi or a.nen)
            return print(f"Alarmi u ruajt: {al['symbol']} {al['direction']} {al['price']:,.6g}. "
                         "Kontrollohet kur punon `nis` ose `njoftime`.")
        return run_alerts(exchange, cfg)
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
        rows.sort(key=lambda r: ({"BLI": 0, "SHORT": 1, "PRIT": 2, "SHIT": 3}[r["signal"]], -r["score"]))
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
        if cfg.allow_short:
            print(f"\nSinjale short: {', '.join(r['symbol'] for r in rows if r['signal'] == 'SHORT') or 'asnjë'}")
        print(f"\n{len(rows)} monedha | sinjale blerjeje: {buys} | trend ditor rritës: {sum(r['daily_up'] for r in rows)}")
    elif a.komanda == "portofol":
        if cfg.strategy == "engulf":
            raise ValueError("prova e portofolit nuk mbështet strategjinë engulf")
        symbols = top_symbols(exchange, cfg.quote, cfg.scan_top_n) if (cfg.scan_market or not a.symbol) else cfg.symbols
        frames = {}
        for sym in symbols:
            try:
                df = fetch_candles(exchange, sym, cfg.timeframe, cfg.candles)
                if len(df) >= cfg.candles * 0.98:     # vetëm monedha me histori të plotë
                    frames[sym] = (df, fetch_daily(exchange, sym, cfg, df))
                    print(f"  {sym}: {len(df)} qirinj", flush=True)
            except Exception as e:
                print(f"  {sym}: u anashkalua ({e})")
        market = None
        if cfg.market_filter_symbol:
            m = fetch_candles(exchange, cfg.market_filter_symbol, cfg.timeframe, cfg.candles)
            market = (m, fetch_daily(exchange, cfg.market_filter_symbol, cfg, m))
        print(format_portfolio(portfolio_backtest(frames, cfg, market), cfg))
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
