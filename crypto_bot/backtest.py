"""Testimi i strategjisë mbi të dhëna historike me fitim/humbje në përqindje."""
import numpy as np

from .strategy import WARMUP, score_frame


def backtest(df, cfg) -> dict:
    """Simulon strategjinë qiri pas qiriu. Hyrja bëhet në hapjen e qiririt pasardhës."""
    s = score_frame(df)
    fee = cfg.fee_pct / 100
    cash = start = float(cfg.paper_balance)
    pos = None
    trades, equity = [], []
    o, h, l, c, score = (s[k].to_numpy() for k in ["open", "high", "low", "close", "score"])

    def close(i, price, reason):
        nonlocal cash, pos
        proceeds = pos["qty"] * price * (1 - fee)
        cash += proceeds
        trades.append({"entry_time": str(s.index[pos["i"]]), "exit_time": str(s.index[i]),
                       "entry": pos["entry"], "exit": price, "reason": reason,
                       "pnl": proceeds - pos["cost"], "pnl_pct": (proceeds / pos["cost"] - 1) * 100})
        pos = None

    for i in range(WARMUP, len(s)):
        prev = score[i - 1]
        if pos is None and prev >= cfg.buy_threshold:
            cost = cash * cfg.position_size_pct / 100
            pos = {"i": i, "entry": o[i], "qty": cost * (1 - fee) / o[i], "cost": cost, "high": o[i],
                   "sl": o[i] * (1 - cfg.stop_loss_pct / 100), "tp": o[i] * (1 + cfg.take_profit_pct / 100)}
            cash -= cost
        elif pos is not None and prev <= cfg.sell_threshold:
            close(i, o[i], "sinjal")
        if pos is not None:
            # Nëse i njëjti qiri prek edhe stop-in edhe fitimin, supozohet rasti më i keq (stop).
            if l[i] <= pos["sl"]:
                close(i, min(o[i], pos["sl"]), "stop-loss")
            elif h[i] >= pos["tp"]:
                close(i, max(o[i], pos["tp"]), "take-profit")
            elif cfg.trailing_stop_pct:
                pos["high"] = max(pos["high"], h[i])
                pos["sl"] = max(pos["sl"], pos["high"] * (1 - cfg.trailing_stop_pct / 100))
        equity.append(cash + (pos["qty"] * c[i] if pos else 0))
    if pos is not None:
        close(len(s) - 1, c[-1], "fund-testi")
        equity[-1] = cash

    eq = np.array(equity) if equity else np.array([start])
    wins = [t for t in trades if t["pnl"] > 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    peak = np.maximum.accumulate(eq)
    first = c[WARMUP] if len(s) > WARMUP else c[-1]
    return {
        "start": start, "end": float(eq[-1]),
        "return_pct": (eq[-1] / start - 1) * 100,
        "buy_hold_pct": (c[-1] / first - 1) * 100,
        "trades": len(trades), "wins": len(wins),
        "win_rate_pct": len(wins) / len(trades) * 100 if trades else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss else float("inf") if gross_win else 0.0,
        "max_drawdown_pct": float(((peak - eq) / peak).max() * 100),
        "trade_list": trades, "equity": eq.tolist(),
    }


def format_backtest(r: dict, cfg, symbol: str) -> str:
    return "\n".join([
        f"=== Backtest {symbol} ({cfg.timeframe}) | fitim +{cfg.take_profit_pct}% / humbje −{cfg.stop_loss_pct}% ===",
        f"Kapitali: {r['start']:.2f} → {r['end']:.2f}  ({r['return_pct']:+.2f}%)",
        f"Mbajtja pa tregtuar (buy & hold) për krahasim: {r['buy_hold_pct']:+.2f}% e çmimit",
        f"Tregti: {r['trades']} | fituese: {r['wins']} ({r['win_rate_pct']:.1f}%) | "
        f"faktori i fitimit: {r['profit_factor']:.2f} | rënia maksimale: {r['max_drawdown_pct']:.2f}%",
    ])
