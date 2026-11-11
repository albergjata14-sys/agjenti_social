"""Testimi i strategjisë mbi të dhëna historike me fitim/humbje në përqindje."""
import numpy as np

from .strategy import exit_prices, position_cost, signal_frame, stop_distance_pct, warmup


def backtest(df, cfg, daily=None) -> dict:
    """Simulon strategjinë qiri pas qiriu. Hyrja bëhet në hapjen e qiririt pasardhës."""
    s = signal_frame(df, cfg, daily)
    atr = s["atr"].to_numpy()
    start_i = warmup(cfg)
    fee = cfg.fee_pct / 100
    cash = start = float(cfg.paper_balance)
    pos = None
    trades, equity = [], []
    o, h, l, c, buy, sell, short, cover = (s[k].to_numpy() for k in
                                           ["open", "high", "low", "close", "buy", "sell", "short", "cover"])

    def value(price):
        # Vlera e pozicionit: long = sasia × çmimi; short = marzhi + fitimi nga rënia.
        return pos["qty"] * (price if pos["side"] > 0 else 2 * pos["entry"] - price)

    def close(i, price, reason):
        nonlocal cash, pos
        proceeds = max(value(price) - pos["qty"] * price * fee, 0.0)
        cash += proceeds
        trades.append({"entry_time": str(s.index[pos["i"]]), "exit_time": str(s.index[i]),
                       "side": "long" if pos["side"] > 0 else "short",
                       "entry": pos["entry"], "exit": price, "reason": reason,
                       "pnl": proceeds - pos["cost"], "pnl_pct": (proceeds / pos["cost"] - 1) * 100})
        pos = None

    for i in range(start_i, len(s)):
        if pos is not None and (sell[i - 1] if pos["side"] > 0 else cover[i - 1]):
            close(i, o[i], "sinjal")
        if pos is None and (buy[i - 1] or short[i - 1]):
            side = 1 if buy[i - 1] else -1
            stop_pct = stop_distance_pct(cfg, o[i], atr[i - 1])
            cost = position_cost(cfg, cash, stop_pct)
            sl, tp = exit_prices(cfg, o[i], stop_pct, side)
            pos = {"i": i, "side": side, "entry": o[i], "qty": cost * (1 - fee) / o[i], "cost": cost,
                   "best": o[i], "sl": sl, "tp": tp}
            cash -= cost
        if pos is not None:
            # Nëse i njëjti qiri prek edhe stop-in edhe fitimin, supozohet rasti më i keq (stop).
            long = pos["side"] > 0
            if (l[i] <= pos["sl"]) if long else (h[i] >= pos["sl"]):
                close(i, min(o[i], pos["sl"]) if long else max(o[i], pos["sl"]), "stop-loss")
            elif pos["tp"] and ((h[i] >= pos["tp"]) if long else (l[i] <= pos["tp"])):
                close(i, max(o[i], pos["tp"]) if long else min(o[i], pos["tp"]), "take-profit")
            elif cfg.trailing_stop_pct:
                t = cfg.trailing_stop_pct / 100
                if long:
                    pos["best"] = max(pos["best"], h[i])
                    pos["sl"] = max(pos["sl"], pos["best"] * (1 - t))
                else:
                    pos["best"] = min(pos["best"], l[i])
                    pos["sl"] = min(pos["sl"], pos["best"] * (1 + t))
        equity.append(cash + (value(c[i]) if pos else 0))
    if pos is not None:
        close(len(s) - 1, c[-1], "fund-testi")
        equity[-1] = cash

    eq = np.array(equity) if equity else np.array([start])
    wins = [t for t in trades if t["pnl"] > 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    peak = np.maximum.accumulate(eq)
    first = c[start_i] if len(s) > start_i else c[-1]
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
        f"=== Backtest {symbol} ({cfg.timeframe}, strategjia {cfg.strategy}) | fitim "
        f"{'+%g%%' % cfg.take_profit_pct if cfg.take_profit_pct else 'i hapur'} / humbje "
        f"{'%g × ATR' % cfg.stop_loss_atr if cfg.stop_loss_atr else '−%g%%' % cfg.stop_loss_pct} ===",
        f"Kapitali: {r['start']:.2f} → {r['end']:.2f}  ({r['return_pct']:+.2f}%)",
        f"Mbajtja pa tregtuar (buy & hold) për krahasim: {r['buy_hold_pct']:+.2f}% e çmimit",
        f"Tregti: {r['trades']} | fituese: {r['wins']} ({r['win_rate_pct']:.1f}%) | "
        f"faktori i fitimit: {r['profit_factor']:.2f} | rënia maksimale: {r['max_drawdown_pct']:.2f}%",
    ])
