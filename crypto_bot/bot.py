"""Cikli kryesor i robotit: skanon tregun, analizon, hap dhe mbyll pozicione."""
import json
import time
from pathlib import Path
from datetime import datetime, timezone

from . import memory, notify
from .data import fetch_candles, fetch_daily, spread_pct, top_symbols
from .strategy import analyze


def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


_skipped = set()


def stop_file(cfg) -> Path:
    """Skedari që i kërkon robotit të ndalet (e krijon paneli me butonin Ndalo)."""
    return Path(cfg.state_file + ".stop")


def is_running(cfg, state=None) -> bool:
    """A po punon një robot mbi këtë skedar gjendjeje? (sipas rrahjes së fundit të ruajtur)"""
    if state is None:
        p = Path(cfg.state_file)
        state = json.loads(p.read_text()) if p.exists() else {}
    return time.time() - state.get("heartbeat", 0) < cfg.poll_seconds * 2 + 30


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
            if sym not in _skipped:  # njofto vetëm herën e parë, jo në çdo cikël
                _skipped.add(sym)
                log(f"{sym}: u anashkalua ({e})")
    return sorted(results, key=lambda a: a["score"], reverse=True)


def record(cfg, **entry):
    """Shton një rresht te regjistri i vendimeve (JSON Lines)."""
    if cfg.log_file:
        if cfg.memory_file:
            try:
                memory.log_event(cfg, "vendim", entry.get("symbol", ""), entry.get("action", ""), entry.get("price"),
                                 {k: v for k, v in entry.items() if k not in ("symbol", "action", "price")})
            except Exception:
                pass
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
        if cfg.label:
            entry["strategy"] = cfg.label
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


def market_trend_up(exchange, cfg):
    """A është tregu i përgjithshëm (BTC) në trend ditor rritës? None kur filtri është i fikur ose s'matet dot."""
    sym = cfg.market_filter_symbol
    if not sym or not cfg.daily_trend_ema:
        return None
    try:
        daily = fetch_candles(exchange, sym, "1d", 3 * cfg.daily_trend_ema + 10)
        c = daily["close"]
        return bool(c.iloc[-1] > c.ewm(span=cfg.daily_trend_ema, adjust=False).mean().iloc[-1])
    except Exception as e:
        if sym not in _skipped:
            _skipped.add(sym)
            log(f"Filtri i tregut ({sym}) nuk u llogarit dot dhe po anashkalohet: {e}")
        return None


def _rotate(broker, cfg, a, by_symbol, prices, actions) -> bool:
    """Këmbim mes monedhave: kur vendet janë plot, mbyll pozicionin më të dobët nëse sinjali i ri është
    dukshëm më i fortë (të paktën `rotate_margin_pct` pikë). Kthen True kur u lirua një vend."""
    if not (cfg.rotate and cfg.strategy == "momentum"):
        return False

    def lean(sym):   # sa fort po lëviz monedha në drejtimin e pozicionit të mbajtur
        m = by_symbol.get(sym, {}).get("momentum")
        return None if m is None else broker.positions[sym].get("side", 1) * m

    held = {s: lean(s) for s in broker.positions if lean(s) is not None}
    if not held:
        return False
    weak = min(held, key=held.get)
    if a["strength"] <= held[weak] + cfg.rotate_margin_pct:
        return False
    _sell(broker, cfg, weak, prices.get(weak, by_symbol[weak]["price"]),
          f"këmbim me {a['symbol']} (më e fortë: {a['strength']:.1f}% kundrejt {held[weak]:.1f}%)", actions)
    return True


def _trade_chart(exchange, cfg, symbol, info, kind):
    """PNG për njoftimin: qirinjtë e strategjisë me hyrjen, stop-loss dhe objektivin."""
    from .config import display
    from .snapshot import render

    try:
        df = fetch_candles(exchange, symbol, cfg.timeframe, 100)
        side = "BLERJE (long)" if kind == "BLI" else "SHITJE (short)"
        return render(df, f"{display(symbol)} {cfg.timeframe} · {side}", info.get("entry"), info.get("sl"), info.get("tp"),
                      1 if kind == "BLI" else -1)
    except Exception:
        return None


def _sell(broker, cfg, sym, price, reason, actions, score=None):
    t = broker.sell(sym, price, reason)
    actions.append(("SHIT", sym, t))
    if cfg.memory_file:
        try:
            memory.log_trade(cfg, sym, t)
        except Exception:
            pass
    record(cfg, symbol=sym, action="SHIT", reason=reason, price=t["exit"], score=score,
           pnl=round(t["pnl"], 4), pnl_pct=round(t["pnl_pct"], 2))
    log(f"MBYLL {t['side']} {sym} @ {t['exit']:.6g} ({reason}) → {t['pnl']:+.2f} {cfg.quote} ({t['pnl_pct']:+.2f}%)")


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
        pos = broker.positions.get(sym)
        if pos and (a["exit_long"] if pos.get("side", 1) > 0 else a["exit_short"]):
            _sell(broker, cfg, sym, prices[sym], "sinjal: " + a["signal_reason"], actions, a["score"])

    # 3) Kufiri ditor i humbjes: pasi preket, sot nuk hapen blerje të reja.
    equity = broker.equity(prices)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["day_start_equity"], st["entries_today"] = today, equity, 0
    day_pct = (equity / st["day_start_equity"] - 1) * 100 if st["day_start_equity"] else 0.0
    halted = None
    if cfg.max_daily_loss_pct and day_pct <= -cfg.max_daily_loss_pct:
        halted = f"kufiri ditor i humbjes u prek ({day_pct:+.2f}%)"
    elif cfg.max_consecutive_losses and losses_in_row(st["trades"], today) >= cfg.max_consecutive_losses:
        halted = f"{cfg.max_consecutive_losses} humbje radhazi sot"

    market_up = market_trend_up(exchange, cfg)

    # 4) Hap pozicione të reja. Çdo vendim regjistrohet një herë për çdo qiri të ri.
    seen, entered = st.setdefault("last_logged", {}), st.setdefault("last_entry_signal", {})
    by_symbol = {a["symbol"]: a for a in results}
    for a in sorted(results, key=lambda a: -a["strength"]):      # sinjalet më të forta të parat
        sym, new_candle = a["symbol"], seen.get(a["symbol"]) != a["time"]
        seen[sym] = a["time"]
        skip = None
        if a["signal"] not in ("BLI", "SHORT"):
            skip = a["signal_reason"]
        elif sym in broker.positions:
            skip = "pozicioni është tashmë i hapur"
        elif entered.get(sym) == a["time"]:
            skip = "ky sinjal është përdorur tashmë (pa ri-hyrje në të njëjtin qiri)"
        elif cfg.pause_entries:
            skip = "analisti nuk e ka miratuar këtë strategji tani" if cfg.label else "hyrjet e reja janë në pushim"
        elif halted:
            skip = halted
        elif a["signal"] == "BLI" and market_up is False:
            skip = f"tregu i përgjithshëm ({cfg.market_filter_symbol}) nuk është në trend ditor rritës"
        elif a["signal"] == "SHORT" and market_up is True:
            skip = f"tregu i përgjithshëm ({cfg.market_filter_symbol}) është në ngritje: pa shitje short"
        elif cfg.max_trades_per_day and st.get("entries_today", 0) >= cfg.max_trades_per_day:
            skip = f"numri maksimal i hyrjeve në ditë ({cfg.max_trades_per_day})"
        elif len(broker.positions) >= cfg.max_open_positions and not _rotate(broker, cfg, a, by_symbol, prices, actions):
            skip = f"numri maksimal i pozicioneve ({cfg.max_open_positions})"
        elif cfg.max_total_risk_pct < 100 and broker.open_risk() >= equity * cfg.max_total_risk_pct / 100 * 0.999:
            skip = f"rreziku i pozicioneve të hapura ka arritur {cfg.max_total_risk_pct:g}% të kapitalit"
        elif cfg.max_spread_pct and (spread := spread_pct(exchange, sym) or 0) > cfg.max_spread_pct:
            skip = f"diferenca blerje/shitje shumë e madhe ({spread:.2f}% > {cfg.max_spread_pct:g}%)"
        else:
            exact = cfg.strategy == "engulf"      # engulf sjell stop-in dhe objektivin si çmime të sakta
            pos = broker.buy(sym, a["price"], equity, a["plan"]["stop_pct"], a["side"],
                             a["plan"]["stop_loss"] if exact else None, a["plan"]["take_profit"] if exact else None)
            if pos:
                entered[sym] = a["time"]
                st["entries_today"] = st.get("entries_today", 0) + 1
                actions.append((a["signal"], sym, pos))
                record(cfg, symbol=sym, action=a["signal"], reason=a["signal_reason"], price=pos["entry"],
                       score=a["score"], stop_loss=pos["sl"], take_profit=pos["tp"])
                log(f"{a['signal']} {sym} @ {pos['entry']:.6g} ({a['signal_reason']}) | fitim → "
                    f"{'%.6g' % pos['tp'] if pos['tp'] else 'i hapur'} | stop → {pos['sl']:.6g}")
                continue
            skip = "fonde të pamjaftueshme ose nën minimumin e platformës"
        if new_candle:
            record(cfg, symbol=sym, action="ANASHKALO" if a["signal"] in ("BLI", "SHORT") else a["signal"],
                   reason=skip, price=a["price"], score=a["score"])
    # 5) Njoftimet: veprimet e robotit, sinjalet e reja, lëvizjet e mëdha dhe alarmet e çmimit.
    try:
        if cfg.notify_trades:
            images = notify.wants_images(cfg)
            for kind, sym, info in actions:
                text = notify.trade_message(kind, sym, info, cfg.quote)
                image = None
                if images and kind in ("BLI", "SHORT"):
                    image = _trade_chart(exchange, cfg, sym, info, kind)
                notify.emit(cfg, "tregti", sym, f"[{cfg.label}] {text}" if cfg.label else text, image=image)
        chart = None
        if notify.wants_images(cfg):
            chart = lambda a: _trade_chart(exchange, cfg, a["symbol"], {"entry": a["price"], "sl": a["plan"]["stop_loss"],
                                                                         "tp": a["plan"]["take_profit"]}, a["signal"])
        notify.check_market(cfg, st, results, chart)
        notify.check_price_alerts(cfg, {a["symbol"]: a["price"] for a in results} | prices)
    except Exception as e:
        log(f"Njoftimet dështuan (roboti vazhdon): {e}")
    st["heartbeat"] = time.time()
    st.setdefault("started", time.time())
    try:
        st["last_equity"] = broker.equity(prices)
    except Exception:
        pass
    broker.save()
    log(f"Kapitali: {broker.equity(prices):.2f} {cfg.quote} (sot {day_pct:+.2f}%"
        f"{', BLERJET TË NDALURA' if halted else ''}) | pozicione të hapura: "
        f"{', '.join(broker.positions) or 'asnjë'}")
    return actions


def run_forever(exchange, broker, cfg):
    if is_running(cfg, broker.state):
        raise RuntimeError("Roboti po punon tashmë mbi këtë gjendje (në një dritare tjetër ose nga paneli).")
    stop = stop_file(cfg)
    stop.unlink(missing_ok=True)
    log(f"Roboti u nis në modalitetin {'REAL' if broker.live else 'SIMULIM'} në {cfg.exchange}. Ctrl+C për ta ndalur.")
    try:
        while not stop.exists():
            try:
                run_cycle(exchange, broker, cfg)
            except Exception as e:
                log(f"Gabim në cikël (do të riprovohet): {e}")
                broker.state["heartbeat"] = time.time()
                broker.save()
            for _ in range(int(cfg.poll_seconds)):
                if stop.exists():
                    break
                time.sleep(1)
        log("Roboti u ndal nga paneli.")
    finally:
        stop.unlink(missing_ok=True)
        broker.state["heartbeat"] = 0
        broker.save()


class CycleCache:
    """Mbështjellës i platformës që mban të dhënat e tregut për një cikël, që shumë strategji t'i ndajnë."""

    CACHED = {"fetch_ohlcv", "fetch_ticker", "fetch_tickers", "load_markets"}

    def __init__(self, exchange):
        self._ex, self._memo = exchange, {}
        self._now = exchange.milliseconds()

    def milliseconds(self):
        return self._now     # ora ngrihet për gjithë ciklin, që kërkesat e njëjta të njihen si të njëjta

    def __getattr__(self, name):
        attr = getattr(self._ex, name)
        if name not in self.CACHED:
            return attr

        def cached(*args, **kwargs):
            key = (name, args, tuple(sorted(kwargs.items())))
            if key not in self._memo:
                self._memo[key] = attr(*args, **kwargs)
            return self._memo[key]
        return cached


_last_market = [0.0]


def run_team_cycle(exchange, base_cfg, rec, tournament: bool = True) -> dict:
    """Një cikël i ekipit: çdo strategji tregton me pjesën e saj të kapitalit (vetëm të miratuarat hapin
    pozicione të reja), dhe turneu i provon të gjitha me gjithë kapitalin demo. Kthen gjendjen e përbashkët."""
    from .analyst import team_candidates, team_config, tournament_candidates, tournament_config
    from .broker import Broker

    cache = CycleCache(exchange)
    approved = set((rec or {}).get("approved", []))
    team = {"team": True, "live": False, "heartbeat": time.time(), "cash": 0.0, "positions": {}, "trades": [],
            "members": [], "approved": sorted(approved), "recommendation": (rec or {}).get("name")}
    members = team_candidates(base_cfg)
    for cand in members:
        cfg = team_config(base_cfg, cand, approved, len(members))
        broker = Broker(cfg)
        try:
            run_cycle(cache, broker, cfg)
        except Exception as e:
            log(f"[{cand['name']}] gabim në cikël: {e}")
        st = broker.state
        equity = st.get("last_equity", st["cash"])
        team["cash"] += st["cash"]
        for sym, pos in st["positions"].items():
            key = sym if sym not in team["positions"] else f"{sym}#{cand['id']}"
            team["positions"][key] = {**pos, "strategy": cand["name"]}
        team["trades"] += [{**t, "strategy": cand["name"]} for t in st["trades"]]
        team["members"].append({"id": cand["id"], "name": cand["name"], "approved": cand["id"] in approved,
                                "capital": cfg.paper_balance, "equity": equity, "open": len(st["positions"]),
                                "trades": len(st["trades"])})
    team["trades"].sort(key=lambda t: t.get("closed", 0))
    team["last_equity"] = sum(m["equity"] for m in team["members"])
    snapshot = [(m["name"], m["equity"], m["open"]) for m in team["members"]] + [("Ekipi", team["last_equity"],
                                                                                    len(team["positions"]))]
    if tournament:
        for cand in tournament_candidates(base_cfg):
            cfg = tournament_config(base_cfg, cand)
            try:
                b = Broker(cfg)
                run_cycle(cache, b, cfg)
                snapshot.append((cfg.label, b.state.get("last_equity", b.state["cash"]), len(b.state["positions"])))
            except Exception as e:
                log(f"[turne {cand['name']}] gabim: {e}")
    # Kujtesa: kapitali i çdo strategjie në çdo cikël dhe çmimet e tregut një herë në orë.
    if base_cfg.memory_file:
        try:
            memory.log_equity(base_cfg, snapshot)
            if time.time() - _last_market[0] > 3600:
                tick = cache.fetch_tickers()
                memory.log_market(base_cfg, [(s, t.get("last"), t.get("percentage")) for s, t in tick.items()
                                             if s in set(top_symbols(cache, base_cfg.quote, 30)) and t.get("last")])
                _last_market[0] = time.time()
        except Exception as e:
            log(f"Kujtesa nuk u shkrua (roboti vazhdon): {e}")
    Path(base_cfg.state_file).write_text(json.dumps(team, indent=2))
    return team


def ensure_research(cfg):
    """Nis analistin e vazhdueshëm si proces më vete nëse nuk po punon (dhe e rinis nëse ka rënë)."""
    import subprocess
    import sys
    from dataclasses import asdict

    from .research import is_alive, status

    st = status(cfg)
    if st and is_alive(cfg, st):
        return
    started = getattr(ensure_research, "_last", 0)
    if time.time() - started < 600:        # i dhamë kohë të nisë; mos e nis dy herë
        return
    ensure_research._last = time.time()
    conf = cfg.state_file.replace(".json", "_analist_config.json")
    Path(conf).write_text(json.dumps(asdict(cfg), indent=2))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open("crypto_bot_analist.log", "a", encoding="utf-8") as out:
        subprocess.Popen([sys.executable, "-m", "crypto_bot", "analist", "--vazhdimisht", "--config", conf,
                          "--me-ekipin", cfg.state_file], stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
    log("Analisti i vazhdueshëm u nis në sfond (shih crypto_bot_analist.log).")


def run_team_forever(exchange, base_cfg, tournament: bool = True):
    """Tregtari i ekipit: rifreskon rekomandimin e analistit kur vjetrohet dhe luan strategjitë e miratuara."""
    from .analyst import analyze_market, load_recommendation

    stop = stop_file(base_cfg)
    stop.unlink(missing_ok=True)
    log("Ekipi u nis (SIMULIM): analisti miraton strategjitë, tregtari i luan njëkohësisht"
        + (", turneu i provon të gjitha." if tournament else ".") + " Ctrl+C për ta ndalur.")
    last_members = None
    from datetime import datetime as _dt

    from .analyst import forward_results
    from .lab import review_tournament

    today = _dt.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        while not stop.exists():
            # Raporti i ditës: kur ndërron dita (UTC), përmblidhet dita e kaluar dhe dërgohet si njoftim.
            now_day = _dt.now(timezone.utc).strftime("%Y-%m-%d")
            if now_day != today and base_cfg.memory_file:
                try:
                    text = memory.save_report(base_cfg, memory.daily_report(base_cfg, today))
                    notify.emit(base_cfg, "raport", "", text)
                    log(text.replace("\n", " | "))
                    for name, status in review_tournament(base_cfg, forward_results(base_cfg)):
                        msg = (f"🧪 Laboratori: “{name}” {'hyri në ekip pas turneut' if status == 'ekip' else 'u hodh poshtë nga turneu'}")
                        notify.emit(base_cfg, "laboratori", "", msg)
                        log(msg)
                except Exception as e:
                    log(f"Raporti i ditës dështoi: {e}")
                today = now_day
            rec = load_recommendation(base_cfg)
            if base_cfg.research:
                ensure_research(base_cfg)        # analisti punon më vete; tregtari vetëm lexon rekomandimin
            elif not rec or time.time() - rec.get("ts", 0) > base_cfg.analyst_hours * 3600:
                try:
                    rec = analyze_market(exchange, base_cfg, log=log)
                    text = (f"🧠 Analisti: {'pushim, asnjë strategji e miratuar' if rec['action'] == 'pause' else 'miratoi ' + ', '.join(rec['approved'])}")
                    log(text)
                    notify.emit(base_cfg, "analist", "", text)
                except Exception as e:
                    log(f"Analisti dështoi (provohet më vonë, vazhdon me rekomandimin e vjetër): {e}")
            try:
                team = run_team_cycle(exchange, base_cfg, rec, tournament)
                if team["approved"] != last_members:
                    last_members = team["approved"]
                log(f"Ekipi: kapitali {team['last_equity']:.2f} {base_cfg.quote} | pozicione {len(team['positions'])} | "
                    f"miratuar: {', '.join(team['approved']) or 'asnjë'}")
            except Exception as e:
                log(f"Gabim në ciklin e ekipit (do të riprovohet): {e}")
            for _ in range(int(base_cfg.poll_seconds)):
                if stop.exists():
                    break
                time.sleep(1)
        log("Ekipi u ndal nga paneli.")
    finally:
        stop.unlink(missing_ok=True)
        p = Path(base_cfg.state_file)
        if p.exists():
            st = json.loads(p.read_text())
            st["heartbeat"] = 0
            p.write_text(json.dumps(st, indent=2))
