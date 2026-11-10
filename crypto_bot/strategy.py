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


def signal_from_score(score: float, cfg) -> str:
    if np.isnan(score):
        return "PRIT"
    if score >= cfg.buy_threshold:
        return "BLI"
    if score <= cfg.sell_threshold:
        return "SHIT"
    return "PRIT"


def analyze(df: pd.DataFrame, cfg, symbol: str = "", horizon: int = 12) -> dict:
    """Analizë e plotë e qiririt të fundit të mbyllur + parashikim për `horizon` qirinj."""
    if len(df) < WARMUP + 5:
        raise ValueError(f"Duhen të paktën {WARMUP + 5} qirinj, u morën {len(df)}")
    s = score_frame(df)
    last = s.iloc[-1]
    price, a = float(last["close"]), float(last["atr"])
    score = float(last["score"])
    signal = signal_from_score(score, cfg)
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
    return {
        "symbol": symbol,
        "time": str(s.index[-1]),
        "price": price,
        "score": round(score, 1),
        "signal": signal,
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
            "take_profit": price * (1 + cfg.take_profit_pct / 100),
            "stop_loss": price * (1 - cfg.stop_loss_pct / 100),
            "risk_reward": cfg.take_profit_pct / cfg.stop_loss_pct,
        },
    }


def format_report(a: dict, cfg) -> str:
    f, p, i = a["forecast"], a["plan"], a["indicators"]
    lines = [
        f"=== {a['symbol']} ({cfg.timeframe}) – {a['time']} ===",
        f"Çmimi: {a['price']:.6g}   Sinjali: {a['signal']}   Pikët: {a['score']:+.1f}/100",
        f"Drejtimi i pritshëm: {a['direction']} (besueshmëria {a['confidence']:.0f}%)",
        "Arsyet:",
        *[f"  - {r}" for r in a["reasons"]],
        f"EMA20 {i['ema20']:.6g} | EMA50 {i['ema50']:.6g} | EMA200 {i['ema200']:.6g} | RSI {i['rsi']:.1f}",
        f"Mbështetja: {a['support']:.6g}   Rezistenca: {a['resistance']:.6g}",
        f"Parashikimi për {f['horizon_candles']} qirinjtë e ardhshëm: ~{f['expected']:.6g} "
        f"(brezi {f['low']:.6g} – {f['high']:.6g}, luhatshmëria {f['volatility_pct']:.2f}%/qiri)",
        f"Plani: hyrje {p['entry']:.6g} | fitim +{cfg.take_profit_pct}% → {p['take_profit']:.6g} | "
        f"humbje −{cfg.stop_loss_pct}% → {p['stop_loss']:.6g} | raporti fitim/rrezik {p['risk_reward']:.2f}",
    ]
    return "\n".join(lines)
