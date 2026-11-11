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
    sig_stop, sig_target = s["stop_price"].to_numpy(float), s["target_price"].to_numpy(float)
    days = s.index.strftime("%Y-%m-%d").to_numpy()
    entries_today, today = 0, None

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
                       "pnl": proceeds - pos["cost"], "pnl_pct": (proceeds / pos["cost"] - 1) * 100,
                       "r": (proceeds - pos["cost"]) / pos["risk"] if pos["risk"] else 0.0})
        pos = None

    for i in range(start_i, len(s)):
        if pos is not None and (sell[i - 1] if pos["side"] > 0 else cover[i - 1]):
            close(i, o[i], "sinjal")
        if days[i] != today:
            today, entries_today = days[i], 0
        if (pos is None and (buy[i - 1] or short[i - 1])
                and not (cfg.max_trades_per_day and entries_today >= cfg.max_trades_per_day)):
            side = 1 if buy[i - 1] else -1
            stop_pct = stop_distance_pct(cfg, o[i], atr[i - 1])
            sl, tp = exit_prices(cfg, o[i], stop_pct, side)
            ok = True
            if not np.isnan(sig_stop[i - 1]):     # stop dhe objektiv i vetë sinjalit
                sl, tp = sig_stop[i - 1], sig_target[i - 1]
                # Nëse hapja ka kërcyer përtej stop-it ose objektivit, sinjali nuk vlen më.
                ok = (sl < o[i] < tp) if side > 0 else (tp < o[i] < sl)
                stop_pct = abs(o[i] - sl) / o[i] * 100
            if ok:
                cost = position_cost(cfg, cash, stop_pct)
                pos = {"i": i, "side": side, "entry": o[i], "qty": cost * (1 - fee) / o[i], "cost": cost,
                       "best": o[i], "sl": sl, "tp": tp, "risk": cost * (1 - fee) * stop_pct / 100}
                cash -= cost
                entries_today += 1
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
        # R = fitimi i tregtisë pjesëtuar me rrezikun e saj (largësia deri te stop-i): mat strategjinë
        # pavarësisht madhësisë së pozicionit.
        "avg_r": float(np.mean([t["r"] for t in trades])) if trades else 0.0,
        "total_r": float(np.sum([t["r"] for t in trades])) if trades else 0.0,
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
        f"Në njësi rreziku (R): mesatarisht {r['avg_r']:+.2f}R për tregti, gjithsej {r['total_r']:+.1f}R",
    ])


def portfolio_backtest(frames: dict, cfg, market=None) -> dict:
    """Simulon robotin mbi shumë monedha me kapital të përbashkët, ashtu siç punon realisht.

    `frames`: {simboli: (qirinjtë, qirinjtë ditorë)}; `market`: (qirinjtë, ditorët) e tregut të filtrit
    (p.sh. BTC) ose None. Vetëm blerje (long). Rregullat: deri në `max_open_positions` pozicione, madhësia
    sipas rrezikut, hyrje në hapjen e qiririt pas sinjalit, më të mirat sipas pikëve të parat.
    """
    import pandas as pd

    from .strategy import daily_trend

    syms = list(frames)
    idx = max((frames[k][0].index for k in syms), key=len)
    sig = {k: signal_frame(df, cfg, daily).reindex(idx) for k, (df, daily) in frames.items()}
    col = lambda name, kind=float: np.column_stack([sig[k][name].to_numpy(kind) for k in syms])
    o, h, l, c, score, atr = (col(n) for n in ["open", "high", "low", "close", "score", "atr"])
    buy = np.column_stack([sig[k]["buy"].fillna(False).to_numpy(bool) for k in syms])
    sell = np.column_stack([sig[k]["sell"].fillna(False).to_numpy(bool) for k in syms])
    up = np.ones(len(idx), bool)
    if market is not None and cfg.market_filter_symbol:
        up = daily_trend(market[0], cfg, market[1]).reindex(idx).fillna(False).to_numpy(bool)
    fee, cash, pos, trades, equity = cfg.fee_pct / 100, float(cfg.paper_balance), {}, [], []
    start = warmup(cfg) + 1

    def close(j, i, price, reason):
        nonlocal cash
        p = pos.pop(j)
        got = p["qty"] * price * (1 - fee)
        cash += got
        trades.append({"symbol": syms[j], "entry_time": str(idx[p["i"]]), "exit_time": str(idx[i]), "entry": p["entry"],
                       "exit": price, "reason": reason, "pnl": got - p["cost"], "pnl_pct": (got / p["cost"] - 1) * 100})

    for i in range(start, len(idx)):
        for j in [j for j in pos if sell[i - 1, j] and not np.isnan(o[i, j])]:
            close(j, i, o[i, j], "sinjal")
        if len(pos) < cfg.max_open_positions and up[i - 1]:
            wanted = sorted((j for j in range(len(syms)) if buy[i - 1, j] and j not in pos and not np.isnan(o[i, j])),
                            key=lambda j: -np.nan_to_num(score[i - 1, j], nan=-999))
            total = cash + sum(p["qty"] * c[i - 1, j] for j, p in pos.items())
            for j in wanted[: cfg.max_open_positions - len(pos)]:
                stop_pct = stop_distance_pct(cfg, o[i, j], atr[i - 1, j])
                cost = min(position_cost(cfg, total, stop_pct), cash)
                if cost <= 0:
                    break
                pos[j] = {"i": i, "entry": o[i, j], "qty": cost * (1 - fee) / o[i, j], "cost": cost,
                          "sl": o[i, j] * (1 - stop_pct / 100)}
                cash -= cost
        for j in [j for j in pos if l[i, j] <= pos[j]["sl"]]:
            close(j, i, min(o[i, j], pos[j]["sl"]), "stop-loss")
        equity.append(cash + sum(p["qty"] * (c[i, j] if not np.isnan(c[i, j]) else p["entry"]) for j, p in pos.items()))

    eq = pd.Series(equity, index=idx[start:])
    monthly = eq.resample("ME").last().pct_change().dropna() * 100
    peak = eq.cummax()
    half = len(eq) // 2
    hold = [frames[k][0]["close"].iloc[-1] / frames[k][0]["close"].iloc[min(start, len(frames[k][0]) - 1)] - 1 for k in syms]
    return {
        "symbols": len(syms), "from": str(idx[start].date()), "to": str(idx[-1].date()),
        "start": float(cfg.paper_balance), "end": float(eq.iloc[-1]),
        "return_pct": (eq.iloc[-1] / cfg.paper_balance - 1) * 100,
        "first_half_pct": (eq.iloc[half] / cfg.paper_balance - 1) * 100,
        "second_half_pct": (eq.iloc[-1] / eq.iloc[half] - 1) * 100,
        "max_drawdown_pct": float(((peak - eq) / peak).max() * 100),
        "buy_hold_pct": float(np.mean(hold) * 100),
        "trades": len(trades), "win_rate_pct": sum(t["pnl"] > 0 for t in trades) / len(trades) * 100 if trades else 0.0,
        "months_up": int((monthly > 0.05).sum()), "months_flat": int((monthly.abs() <= 0.05).sum()),
        "months_down": int((monthly < -0.05).sum()),
        "worst_month_pct": float(monthly.min()) if len(monthly) else 0.0,
        "best_month_pct": float(monthly.max()) if len(monthly) else 0.0,
        "monthly": monthly, "equity": eq, "trade_list": trades,
    }


def format_portfolio(r: dict, cfg) -> str:
    return "\n".join([
        f"=== Portofoli: {r['symbols']} monedha, {r['from']} – {r['to']} | deri në {cfg.max_open_positions} pozicione, "
        f"rrezik {cfg.risk_per_trade_pct:g}% për tregti ===",
        f"Kapitali: {r['start']:.2f} → {r['end']:.2f}  ({r['return_pct']:+.2f}%) | rënia maksimale: {r['max_drawdown_pct']:.1f}%",
        f"Gjysma e parë: {r['first_half_pct']:+.1f}% | gjysma e dytë: {r['second_half_pct']:+.1f}%",
        f"Muajt: {r['months_up']} me fitim, {r['months_flat']} rreth zeros, {r['months_down']} me humbje | "
        f"më i miri {r['best_month_pct']:+.1f}%, më i keqi {r['worst_month_pct']:+.1f}%",
        f"Tregti: {r['trades']} | fituese: {r['win_rate_pct']:.0f}%",
        f"Mbajtja pa tregtuar e të gjitha monedhave (mesatarja): {r['buy_hold_pct']:+.1f}%",
        "Kujdes: monedhat janë zgjedhur sipas volumit të sotëm, pra janë ato që mbijetuan; rezultati real ka gjasa të dalë më i dobët.",
    ])
