"""Analiza e grafikut: pikëzimi i tregut, sinjali dhe parashikimi i detajuar."""
import numpy as np
import pandas as pd

from .indicators import add_indicators

WEIGHTS = {"trend": 0.35, "macd": 0.25, "rsi": 0.20, "bollinger": 0.10, "volume": 0.10}
WARMUP = 200  # qirinj të nevojshëm para se treguesit të jenë të besueshëm


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Shton treguesit, komponentët (−1..1) dhe `score` (−100..100) për çdo qiri."""
    df = add_indicators(df)
    c = df["close"]
    comp = pd.DataFrame(index=df.index)
    comp["trend"] = (np.sign(c - df["ema50"]) + np.sign(df["ema20"] - df["ema50"])
                     + np.sign(df["ema50"] - df["ema200"])) / 3
    comp["macd"] = (df["macd_hist"] / (0.5 * df["atr"])).clip(-1, 1)
    r = df["rsi"]
    comp["rsi"] = ((r - 50) / 20).clip(-1, 1)
    comp.loc[r > 75, "rsi"] = -0.5   # i mbiblerë: rrezik kthimi poshtë
    comp.loc[r < 25, "rsi"] = 0.5    # i mbishitur: mundësi kthimi lart
    width = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    comp["bollinger"] = ((0.5 - (c - df["bb_lower"]) / width) * 2).clip(-1, 1)
    vol_ratio = df["volume"] / df["vol_sma"].replace(0, np.nan)
    comp["volume"] = np.sign(c - df["open"]) * (vol_ratio - 1).clip(0, 1)
    # Rreshtat pa histori të mjaftueshme mbeten NaN (asnjë sinjal).
    comp["volume"] = comp["volume"].fillna(0).where(df["ema200"].notna())
    comp["bollinger"] = comp["bollinger"].fillna(0).where(df["ema200"].notna())
    score = sum(comp[k] * w for k, w in WEIGHTS.items()) * 100
    for k in WEIGHTS:
        df[f"c_{k}"] = comp[k]
    df["score"] = score
    return df


def daily_trend(df: pd.DataFrame, cfg, daily=None, down: bool = False) -> pd.Series:
    """True aty ku mbyllja ditore është mbi EMA ditore (ose nën të, me `down`). Vetëm ditë të mbyllura.

    `daily` janë qirinjtë ditorë; pa to, ditët nxirren nga vetë `df`.
    """
    step = df.index.to_series().diff().median()
    if not cfg.daily_trend_ema or step >= pd.Timedelta(days=1):
        return pd.Series(True, index=df.index)
    if daily is None:
        daily = df[["close"]].resample("1D").last().dropna()
    d = daily["close"]
    n = cfg.daily_trend_ema
    avg = d.ewm(span=n, adjust=False, min_periods=n).mean()
    up = (d < avg) if down else (d > avg)                         # pa histori të mjaftueshme → False
    up.index = up.index + pd.Timedelta(days=1)                    # dita njihet vetëm pasi mbyllet
    known = up.reindex(df.index + step, method="ffill")           # krahaso me çastin e mbylljes së qiririt
    return pd.Series(known.fillna(False).to_numpy(dtype=bool), index=df.index)


def stop_distance_pct(cfg, price: float, atr: float) -> float:
    """Largësia e stop-loss nga hyrja, në %: sipas ATR nëse është vendosur, përndryshe përqindje fikse."""
    if cfg.stop_loss_atr and atr and not np.isnan(atr):
        return min(cfg.stop_loss_atr * atr / price * 100, 99.0)
    return cfg.stop_loss_pct


def position_cost(cfg, equity: float, stop_pct: float) -> float:
    """Vlera e pozicionit (sasia × çmimi): rrezik fiks i kapitalit, i kufizuar nga position_size_pct × leva."""
    cap = equity * cfg.position_size_pct / 100 * cfg.leverage
    if cfg.risk_per_trade_pct and stop_pct > 0:
        return min(equity * cfg.risk_per_trade_pct / stop_pct, cap)
    return cap


def size_position(cfg, equity: float, cash: float, price: float, stop_pct: float, open_risk: float = 0.0):
    """Madhësia e një pozicioni të ri, duke respektuar rrezikun për tregti, rrezikun e përbashkët dhe paratë.

    Kthen (marzhi që paguhet, sasia, marzhi neto pas komisionit) ose None kur nuk lejohet asnjë sasi.
    Pa levë (leverage = 1) marzhi është e gjithë vlera e pozicionit, si më parë.
    """
    fee = cfg.fee_pct / 100
    notional = position_cost(cfg, equity, stop_pct)
    room = equity * cfg.max_total_risk_pct / 100 - open_risk
    if stop_pct > 0:
        notional = min(notional, max(room, 0) / (stop_pct / 100))
    cost = min(notional / cfg.leverage, cash)
    if cost <= 0 or price <= 0:
        return None
    notional = cost * cfg.leverage
    return cost, notional * (1 - fee) / price, cost - notional * fee


def position_value(p: dict, price: float) -> float:
    """Vlera e një pozicioni: marzhi + fitimi ose humbja (pa levë: long = sasia × çmimi)."""
    margin = p.get("margin", p["qty"] * p["entry"])
    return max(margin + p.get("side", 1) * p["qty"] * (price - p["entry"]), 0.0)


def position_risk(p: dict) -> float:
    """Sa humbet pozicioni nëse preket stop-i tani (0 kur stop-i ndjekës ka kaluar hyrjen)."""
    return max(0.0, (p["entry"] - p["sl"]) * p.get("side", 1)) * p["qty"]


def signal_frame(df: pd.DataFrame, cfg, daily=None) -> pd.DataFrame:
    """score_frame + kolonat `buy` / `sell` sipas strategjisë së zgjedhur te konfigurimi."""
    s = score_frame(df)
    s["daily_up"] = daily_trend(df, cfg, daily)
    c = s["close"]
    # Niveli i thyerjes: maja / fundi i qirinjve të mëparshëm (pa qiririn aktual).
    s["breakout_high"] = s["high"].rolling(cfg.breakout_entry).max().shift()
    s["breakout_low"] = s["low"].rolling(cfg.breakout_exit).min().shift()
    s["trend_ema"] = c.ewm(span=cfg.trend_ema, adjust=False, min_periods=cfg.trend_ema).mean()
    # Pasqyra për shitjen short: thyerje e fundit për hyrje, thyerje e majës për dalje.
    s["short_low"] = s["low"].rolling(cfg.breakout_entry).min().shift()
    s["cover_high"] = s["high"].rolling(cfg.breakout_exit).max().shift()
    s["daily_down"] = daily_trend(df, cfg, daily, down=True)
    s["stop_price"] = s["target_price"] = np.nan   # stop/objektiv i vetë sinjalit (vetëm engulf)
    if cfg.strategy == "engulf":
        from .engulf import engulf_signals

        e = engulf_signals(s, cfg, daily)
        for col in e:
            s[col] = e[col]
        s["sell"] = s["cover"] = False                # dalja bëhet vetëm me stop ose objektiv
    elif cfg.strategy == "mtf":
        from .mtf import mtf_signals

        for name, val in mtf_signals(s, cfg).items():
            s[name] = val
    elif cfg.strategy == "momentum":
        # Lëvizja e `momentum_days` ditëve të fundit, në %. Hyrje në drejtimin e saj kur kalon pragun dhe
        # çmimi është në anën e duhur të mesatares; dalje kur lëvizja kthehet në anën tjetër.
        step = df.index.to_series().diff().median()
        bars = max(1, int(round(pd.Timedelta(days=cfg.momentum_days) / step)))
        m = (c / c.shift(bars) - 1) * 100
        avg = c.ewm(span=cfg.momentum_ema, adjust=False, min_periods=cfg.momentum_ema).mean()
        s["momentum"] = m
        s["buy"] = (m > cfg.momentum_min_pct) & (c > avg)
        s["sell"] = m < 0
        s["short"] = (m < -cfg.momentum_min_pct) & (c < avg)
        s["cover"] = m > 0
        if cfg.momentum_daily_filter:
            s["buy"] = s["buy"] & s["daily_up"]
            s["short"] = s["short"] & s["daily_down"]
    elif cfg.strategy == "breakout":
        s["buy"] = (c > s["breakout_high"]) & (c > s["trend_ema"]) & s["daily_up"]
        s["sell"] = c < s["breakout_low"]
        s["short"] = (c < s["short_low"]) & (c < s["trend_ema"]) & s["daily_down"]
        s["cover"] = c > s["cover_high"]
    else:
        s["buy"] = s["score"] >= cfg.buy_threshold
        s["sell"] = s["score"] <= cfg.sell_threshold
        s["short"], s["cover"] = s["sell"], s["buy"]
    if not cfg.allow_short:
        s["short"] = False
    return s


def warmup(cfg) -> int:
    """Qirinjtë e nevojshëm para sinjalit të parë të besueshëm."""
    base = max(WARMUP, cfg.trend_ema, cfg.breakout_entry + 1, cfg.breakout_exit + 1)
    if cfg.strategy == "mtf":
        from .mtf import warmup_bars

        return max(base, warmup_bars(cfg))
    return base


def live_candles(cfg) -> int:
    """Sa qirinj merren në punën e drejtpërdrejtë: strategjia mtf ka nevojë për histori më të gjatë (EMA ditore)."""
    return max(cfg.candles, warmup(cfg) + 100) if cfg.strategy == "mtf" else cfg.candles


def exit_prices(cfg, price: float, stop_pct: float, side: int = 1):
    """(stop-loss, take-profit) për një hyrje në `price`. side: 1 = blerje (long), −1 = shitje short."""
    stop = price * (1 - side * stop_pct / 100)
    take = price * (1 + side * cfg.take_profit_pct / 100) if cfg.take_profit_pct else None
    if cfg.take_profit_r:               # objektivi sipas rrezikut: R herë largësia e stop-it
        take = price * (1 + side * cfg.take_profit_r * stop_pct / 100)
    return stop, take


def analyze(df: pd.DataFrame, cfg, symbol: str = "", horizon: int = 12, daily=None) -> dict:
    """Analizë e plotë e qiririt të fundit të mbyllur + parashikim për `horizon` qirinj."""
    need = warmup(cfg) + 5
    if len(df) < need:
        raise ValueError(f"Duhen të paktën {need} qirinj, u morën {len(df)}")
    s = signal_frame(df, cfg, daily)
    last = s.iloc[-1]
    price, a = float(last["close"]), float(last["atr"])
    score = float(last["score"])
    signal = "BLI" if last["buy"] else "SHORT" if last["short"] else "SHIT" if last["sell"] else "PRIT"
    side = -1 if signal == "SHORT" else 1
    momentum = float(last["momentum"]) if cfg.strategy == "momentum" else None
    if cfg.strategy == "momentum":
        days = f"{cfg.momentum_days:g}-ditore"
        why = ("histori e pamjaftueshme për të matur lëvizjen" if np.isnan(momentum) else
               f"lëvizja {days} {momentum:+.1f}% dhe çmimi mbi mesataren" if signal == "BLI" else
               f"lëvizja {days} {momentum:+.1f}% dhe çmimi nën mesataren" if signal == "SHORT" else
               f"lëvizja {days} {momentum:+.1f}%: nën pragun {cfg.momentum_min_pct:g}% ose në anën e gabuar të mesatares")
    elif cfg.strategy == "mtf":
        from .mtf import trend_text

        mtf = {k[2:]: int(last[k]) for k in s.columns if k.startswith("t_")}
        up, down = sum(v > 0 for v in mtf.values()), sum(v < 0 for v in mtf.values())
        need = min(cfg.mtf_min_align, len(mtf))
        why = (trend_text(mtf) + ": " + (
            "të gjitha lart dhe çmimi u rikthye në trend" if signal == "BLI" else
            "të gjitha poshtë dhe çmimi u rikthye në rënie" if signal == "SHORT" else
            f"trendi {cfg.mtf_exit} u kthye" if signal == "SHIT" else
            f"{max(up, down)}/{len(mtf)} në një drejtim (duhen {need}, asnjë kundër)" if max(up, down) < need or min(up, down) else
            "trendi është gati, pritet konfirmimi i qiririt"))
    elif cfg.strategy == "engulf":
        why = last["engulf_note"] or "pa sinjal"
    elif signal == "SHORT":
        why = (f"çmimi theu fundin e {cfg.breakout_entry} qirinjve ({last['short_low']:.6g}) në trend rënës"
               if cfg.strategy == "breakout" else f"pikët {score:+.0f} (shitje ≤ {cfg.sell_threshold:g})")
    elif cfg.strategy == "breakout":
        up = price > last["trend_ema"]
        why = (f"çmimi theu majën e {cfg.breakout_entry} qirinjve ({last['breakout_high']:.6g}) në trend rritës"
               if signal == "BLI" else
               f"çmimi ra nën fundin e {cfg.breakout_exit} qirinjve ({last['breakout_low']:.6g})"
               if signal == "SHIT" else
               f"pa thyerje: duhet mbyllje mbi {last['breakout_high']:.6g}"
               + ("" if up else f" dhe mbi EMA{cfg.trend_ema} ({last['trend_ema']:.6g})"))
        if signal != "SHIT" and not last["daily_up"]:
            why = f"trendi ditor jo rritës (nën EMA{cfg.daily_trend_ema} ditore); {why}" if signal == "PRIT" else why
    else:
        why = f"pikët {score:+.0f} (blerje ≥ {cfg.buy_threshold:g}, shitje ≤ {cfg.sell_threshold:g})"
    recent = s.tail(50)
    move = a * np.sqrt(horizon)  # lëvizja tipike e pritshme sipas luhatshmërisë
    drift = move * score / 100 * 0.5

    def describe(k, v):
        txt = {
            "trend": ("trend rritës (çmimi dhe EMA-t të renditura lart)", "trend rënës", "trend i paqartë"),
            "macd": ("momentum pozitiv (MACD mbi sinjal)", "momentum negativ (MACD nën sinjal)", "momentum neutral"),
            "rsi": (f"RSI {last['rsi']:.0f} – forcë blerësish", f"RSI {last['rsi']:.0f} – forcë shitësish",
                    f"RSI {last['rsi']:.0f} – neutral"),
            "bollinger": ("çmimi pranë brezit të poshtëm Bollinger", "çmimi pranë brezit të sipërm Bollinger",
                          "çmimi në mes të brezave Bollinger"),
            "volume": ("volum i lartë në qiri rritës", "volum i lartë në qiri rënës", "volum normal"),
        }[k]
        return txt[0] if v > 0.2 else txt[1] if v < -0.2 else txt[2]

    components = {k: float(last[f"c_{k}"]) for k in WEIGHTS}
    stop_pct = stop_distance_pct(cfg, price, a)
    plan_stop, plan_take = exit_prices(cfg, price, stop_pct, side)
    if not np.isnan(last["stop_price"]):              # sinjali sjell stop-in dhe objektivin e vet
        plan_stop, plan_take = float(last["stop_price"]), float(last["target_price"])
        stop_pct = abs(price - plan_stop) / price * 100
    engulf = None
    if cfg.strategy == "engulf":
        num = lambda x: None if np.isnan(x) else float(x)
        engulf = {"bias": int(last["bias"]), "session_high": num(last["sess_high"]), "session_low": num(last["sess_low"]),
                  "session_mid": num(last["sess_mid"]), "swept_low": bool(last["swept_low"]),
                  "swept_high": bool(last["swept_high"])}
    return {
        "symbol": symbol,
        "time": str(s.index[-1]),
        "price": price,
        "score": round(score, 1),
        "signal": signal,
        "signal_reason": why,
        "breakout_high": float(last["breakout_high"]),
        "buy_above": float(max(last["breakout_high"], last["trend_ema"])),   # mbyllja që do të jepte sinjal
        "short_below": float(min(last["short_low"], last["trend_ema"])),     # mbyllja që do të jepte short
        "daily_up": bool(last["daily_up"]),
        "daily_down": bool(last["daily_down"]),
        "engulf": engulf,
        "mtf": ({k[2:]: int(last[k]) for k in s.columns if k.startswith("t_")} if cfg.strategy == "mtf" else None),
        "momentum": None if momentum is None or np.isnan(momentum) else momentum,
        # Forca e sinjalit për renditje dhe këmbim: lëvizja në drejtimin e hyrjes, ose pikët e treguesve.
        "strength": (abs(momentum) if momentum is not None and not np.isnan(momentum) else abs(score)),
        "exit_long": bool(last["sell"]),      # pozicioni long duhet mbyllur
        "exit_short": bool(last["cover"]),    # pozicioni short duhet mbyllur
        "side": side,
        "breakout_low": float(last["breakout_low"]),
        "confidence": round(abs(score), 1),
        "direction": "RRITJE" if score > 15 else "RËNIE" if score < -15 else "ANASH",
        "components": components,
        "reasons": [describe(k, v) for k, v in components.items()],
        "indicators": {k: float(last[k]) for k in
                       ["ema20", "ema50", "ema200", "rsi", "macd", "macd_signal", "bb_upper", "bb_lower", "atr"]},
        "support": float(recent["low"].min()),
        "resistance": float(recent["high"].max()),
        "forecast": {
            "horizon_candles": horizon,
            "expected": price + drift,
            "low": price + drift - move,
            "high": price + drift + move,
            "volatility_pct": a / price * 100,
        },
        "plan": {
            "entry": price,
            "take_profit": plan_take,
            "stop_loss": plan_stop,
            "stop_pct": stop_pct,
            "position_pct": position_cost(cfg, 100.0, stop_pct),
            "exit_level": (float(last["cover_high"] if side < 0 else last["breakout_low"])
                           if cfg.strategy == "breakout" else None),
        },
    }


def format_report(a: dict, cfg) -> str:
    f, p, i = a["forecast"], a["plan"], a["indicators"]
    lines = [
        f"=== {a['symbol']} ({cfg.timeframe}) – {a['time']} ===",
        f"Çmimi: {a['price']:.6g}   Sinjali: {a['signal']} – {a['signal_reason']}",
        f"Pikët e treguesve: {a['score']:+.1f}/100 → drejtimi {a['direction']}",
        "Treguesit:",
        *[f"  - {r}" for r in a["reasons"]],
        f"EMA20 {i['ema20']:.6g} | EMA50 {i['ema50']:.6g} | EMA200 {i['ema200']:.6g} | RSI {i['rsi']:.1f}",
        f"Mbështetja: {a['support']:.6g}   Rezistenca: {a['resistance']:.6g}",
        f"Parashikimi për {f['horizon_candles']} qirinjtë e ardhshëm: ~{f['expected']:.6g} "
        f"(brezi {f['low']:.6g} – {f['high']:.6g}, luhatshmëria {f['volatility_pct']:.2f}%/qiri)",
        "Plani{}: hyrje {:.6g} | fitim {} | humbje −{:.3g}% → {:.6g}{}".format(
            " (short)" if a["side"] < 0 else "", p["entry"],
            f"{p['take_profit']:.6g}" if p["take_profit"] else "i hapur (pa kufi)",
            p["stop_pct"], p["stop_loss"],
            f" | dalje nga trendi {'mbi' if a['side'] < 0 else 'nën'} {p['exit_level']:.6g}" if p["exit_level"] else ""),
        f"Madhësia e blerjes: {p['position_pct']:.3g}% e kapitalit"
        + (f" (rrezik {cfg.risk_per_trade_pct:g}% e kapitalit nëse preket stop-i)" if cfg.risk_per_trade_pct else ""),
    ]
    return "\n".join(lines)
