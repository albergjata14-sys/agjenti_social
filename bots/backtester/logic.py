"""Backtester: provon në historinë reale të MEXC çdo setup Strong/Very Strong që Math Geometry do të kishte gjetur.

Ecën qiri pas qiri dhe sheh vetëm të kaluarën (asnjë vështrim në të ardhmen). Hyrja: urdhër limit te mesi i zonës,
i vlefshëm 15 qirinj; dalja: stop-i ose Target 1. Kur stop-i dhe objektivi preken në të njëjtin qiri, llogaritet
humbje. Rreziku 1% i kapitalit për tregti; komisionet + rrëshqitja zbriten nga çdo tregti.
"""
from dataclasses import dataclass

import numpy as np

from bots.math_geometry.logic import Geometry

MIN_TRADES, MIN_PF, MIN_EXP, MAX_DD, COST_PCT = 40, 1.45, 0.32, 20.0, 0.15
ORDER_BARS, WARMUP, RISK_PCT = 15, 260, 1.0


@dataclass
class Stats:
    trades: int
    wins: int
    profit_factor: float
    expectancy: float          # R mesatar për tregti, pas kostove
    max_dd: float              # % nga maja e kapitalit
    cost_pct: float
    results: list              # R e çdo tregtie

    @property
    def win_rate(self):
        return 100 * self.wins / self.trades if self.trades else 0.0

    def checks(self):
        return [(f"Trades in sample ≥ {MIN_TRADES}", self.trades >= MIN_TRADES, f"{self.trades}"),
                (f"Profit Factor ≥ {MIN_PF}", self.profit_factor >= MIN_PF, f"{self.profit_factor:.2f}"),
                (f"Expectancy ≥ {MIN_EXP}R", self.expectancy >= MIN_EXP, f"{self.expectancy:.2f}R"),
                (f"Max Drawdown ≤ {MAX_DD:.0f}%", self.max_dd <= MAX_DD, f"{self.max_dd:.1f}%"),
                (f"Fees + slippage ≥ 0.15%", self.cost_pct >= 0.15, f"{self.cost_pct:.2f}% per trade")]

    @property
    def passed(self):
        return all(ok for _, ok, _ in self.checks())


def backtest(df, min_score=3, cost_pct=COST_PCT):
    g = Geometry(df)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    results, t, n = [], WARMUP, len(df)
    while t < n - 1:
        s = g.setup_at(t)
        if s is None or s.score < min_score:
            t += 1
            continue
        side = s.side
        # Kur çmimi është tashmë brenda zonës, hyrja bëhet me hapjen e qiririt tjetër.
        fill_at, entry = None, s.entry
        if (c[t] - s.entry) * side <= 0:
            if (o[t + 1] - s.stop) * side > 0:
                fill_at, entry = t + 1, o[t + 1]
        else:
            for j in range(t + 1, min(n, t + 1 + ORDER_BARS)):
                if (l[j] <= entry) if side == 1 else (h[j] >= entry):
                    fill_at = j
                    break
                if (h[j] >= s.target1) if side == 1 else (l[j] <= s.target1):
                    break                                      # çmimi iku drejt objektivit pa na mbushur
        if fill_at is None:
            t += 1
            continue
        risk = abs(entry - s.stop)
        reward = abs(s.target1 - entry)
        cost_r = (cost_pct / 100) * entry / risk
        r, j = None, fill_at
        while j < n:
            hit_stop = (l[j] <= s.stop) if side == 1 else (h[j] >= s.stop)
            hit_tp = (h[j] >= s.target1) if side == 1 else (l[j] <= s.target1)
            if hit_stop:
                r = -1.0
                break
            if hit_tp:
                r = reward / risk
                break
            j += 1
        if r is None:                                          # tregtia ende e hapur: nuk numërohet
            break
        results.append(r - cost_r)
        t = j + 1
    return stats(results, cost_pct)


def stats(results, cost_pct=COST_PCT):
    r = np.asarray(results, dtype=float)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    pf = float(wins / losses) if losses > 0 else (float("inf") if wins > 0 else 0.0)
    equity = np.cumprod(1 + r * RISK_PCT / 100) if len(r) else np.array([1.0])
    peak = np.maximum.accumulate(np.r_[1.0, equity])
    dd = float(((peak - np.r_[1.0, equity]) / peak).max() * 100)
    return Stats(len(r), int((r > 0).sum()), pf, float(r.mean()) if len(r) else 0.0, dd, cost_pct, list(r))


def check(chart, setup):
    """Kthen (Stats, mesazhi i botit)."""
    st = backtest(chart.df)
    lines = [f"Backtest {chart.pair} {chart.timeframe}: {len(chart.df)} candles "
             f"({chart.df.index[0]:%Y-%m-%d} → {chart.df.index[-1]:%Y-%m-%d}), Strong/Very Strong setups only, "
             f"exit at Target 1, 1% risk per trade."]
    lines += [f"{'✔' if ok else '✘'} {name}: {val}" for name, ok, val in st.checks()]
    lines.append(f"Win rate: {st.win_rate:.0f}% ({st.wins}/{st.trades})")
    lines.append("→ Passing to Signal Cleaner" if st.passed else "REJECTED – fails the minimum requirements.")
    return st, "\n".join(lines)
