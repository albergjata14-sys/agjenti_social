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


def daily_trend(df: pd.DataFrame, cfg, daily=None) -> pd.Series:
    """True aty ku mbyllja ditore është mbi EMA ditore. Përdoren vetëm ditë të mbyllura.

    `daily` janë qirinjtë ditorë; pa to, ditët nxirren nga vetë `df`.
    """
    step = df.index.to_series().diff().median()
    if not cfg.daily_trend_ema or step >= pd.Timedelta(days=1):
        return pd.Series(True, index=df.index)
    if daily is None:
        daily = df[["close"]].resample("1D").last().dropna()
    d = daily["close"]
    n = cfg.daily_trend_ema
    up = d > d.ewm(span=n, adjust=False, min_periods=n).mean()   # pa histori të mjaftueshme → False
    up.index = up.index + pd.Timedelta(days=1)                    # dita njihet vetëm pasi mbyllet
    known = up.reindex(df.index + step, method="ffill")           # krahaso me çastin e mbylljes së qiririt
    return pd.Series(known.fillna(False).to_numpy(dtype=bool), index=df.index)


def stop_distance_pct(cfg, price: float, atr: float) -> float:
    """Largësia e stop-loss nga hyrja, në %: sipas ATR nëse është vendosur, përndryshe përqindje fikse."""
    if cfg.stop_loss_atr and atr and not np.isnan(atr):
        return min(cfg.stop_loss_atr * atr / price * 100, 99.0)
    return cfg.stop_loss_pct


def position_cost(cfg, equity: float, stop_pct: float) -> float:
    """Sa para vihen në një blerje: rrezik fiks i kapitalit, i kufizuar nga position_size_pct."""
    cap = equity * cfg.position_size_pct / 100
    if cfg.risk_per_trade_pct and stop_pct > 0:
        return min(equity * cfg.risk_per_trade_pct / stop_pct, cap)
    return cap


def signal_frame(df: pd.DataFrame, cfg, daily=None) -> pd.DataFrame:
    """score_frame + kolonat `buy` / `sell` sipas strategjisë së zgjedhur te konfigurimi."""
    s = score_frame(df)
    s["daily_up"] = daily_trend(df, cfg, daily)
    c = s["close"]
    # Niveli i thyerjes: maja / fundi i qirinjve të mëparshëm (pa qiririn aktual).
    s["breakout_high"] = s["high"].rolling(cfg.breakout_entry).max().shift()
    s["breakout_low"] = s["low"].rolling(cfg.breakout_exit).min().shift()
    s["trend_ema"] = c.ewm(span=cfg.trend_ema, adjust=False, min_periods=cfg.trend_ema).mean()
    if cfg.strategy == "breakout":
        s["buy"] = (c > s["breakout_high"]) & (c > s["trend_ema"]) & s["daily_up"]
        s["sell"] = c < s["breakout_low"]
    else:
        s["buy"] = s["score"] >= cfg.buy_threshold
        s["sell"] = s["score"] <= cfg.sell_threshold
    return s


def warmup(cfg) -> int:
    """Qirinjtë e nevojshëm para sinjalit të parë të besueshëm."""
    return max(WARMUP, cfg.trend_ema, cfg.breakout_entry + 1, cfg.breakout_exit + 1)


def analyze(df: pd.DataFrame, cfg, symbol: str = "", horizon: int = 12, daily=None) -> dict:
    """Analizë e plotë e qiririt të fundit të mbyllur + parashikim për `horizon` qirinj."""
    need = warmup(cfg) + 5
    if len(df) < need:
        raise ValueError(f"Duhen të paktën {need} qirinj, u morën {len(df)}")
    s = signal_frame(df, cfg, daily)
    last = s.iloc[-1]
    price, a = float(last["close"]), float(last["atr"])
    score = float(last["score"])
    signal = "BLI" if last["buy"] else "SHIT" if last["sell"] else "PRIT"
    if cfg.strategy == "breakout":
        up = price > last["trend_ema"]
        why = (f"çmimi theu majën e {cfg.breakout_entry} qirinjve ({last['breakout_high']:.6g}) në trend rritës"
               if signal == "BLI" else
               f"çmimi ra nën fundin e {cfg.breakout_exit} qirinjve ({last['breakout_low']:.6g})"
               if signal == "SHIT" else
               f"pa thyerje: duhet mbyllje mbi {last['breakout_high']:.6g}"
               + ("" if up else f" dhe mbi EMA{cfg.trend_ema} ({last['trend_ema']:.6g})"))
        if signal != "SHIT" and not last["daily_up"]:
            why = (f"trendi ditor nuk është rritës (çmimi nën EMA{cfg.daily_trend_ema} ditore, "
                   f"ose histori ditore e pamjaftueshme); {why}" if signal == "PRIT" else why)
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
    return {
        "symbol": symbol,
        "time": str(s.index[-1]),
        "price": price,
        "score": round(score, 1),
        "signal": signal,
        "signal_reason": why,
        "breakout_high": float(last["breakout_high"]),
        "buy_above": float(max(last["breakout_high"], last["trend_ema"])),   # mbyllja që do të jepte sinjal
        "daily_up": bool(last["daily_up"]),
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
            "take_profit": price * (1 + cfg.take_profit_pct / 100) if cfg.take_profit_pct else None,
            "stop_loss": price * (1 - stop_pct / 100),
            "stop_pct": stop_pct,
            "position_pct": position_cost(cfg, 100.0, stop_pct),
            "exit_level": float(last["breakout_low"]) if cfg.strategy == "breakout" else None,
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
        "Plani: hyrje {:.6g} | fitim {} | humbje −{:.3g}% → {:.6g}{}".format(
            p["entry"],
            f"+{cfg.take_profit_pct:g}% → {p['take_profit']:.6g}" if p["take_profit"] else "i hapur (pa kufi)",
            p["stop_pct"], p["stop_loss"],
            f" | dalje nga trendi nën {p['exit_level']:.6g}" if p["exit_level"] else ""),
        f"Madhësia e blerjes: {p['position_pct']:.3g}% e kapitalit"
        + (f" (rrezik {cfg.risk_per_trade_pct:g}% e kapitalit nëse preket stop-i)" if cfg.risk_per_trade_pct else ""),
    ]
    return "\n".join(lines)
