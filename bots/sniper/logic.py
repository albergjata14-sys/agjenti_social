"""Sniper: miraton SNIPER SIGNAL vetëm kur janë të vërteta të gjitha kushtet. Refuzon në heshtje."""
from bots._base import fmt
from bots.math_geometry.logic import Geometry, volume_profile

MIN_RR, MAX_RISK_ATR, IN_ZONE_ATR = 3.2, 1.2, 0.3


def opposing_levels(chart, setup):
    """Majat/fundet dhe POC/VAH/VAL e kohës më të gjatë që qëndrojnë mes hyrjes dhe Target 1."""
    lo, hi = sorted((setup.entry, setup.target1))
    margin = 0.25 * abs(setup.target1 - setup.entry)
    lo, hi = (lo + margin, hi - 0.1 * setup.atr) if setup.side == 1 else (lo + 0.1 * setup.atr, hi - margin)
    found = []
    if chart.htf_df is not None and len(chart.htf_df) > 30:
        want = "H" if setup.side == 1 else "L"
        for _, p, k in Geometry(chart.htf_df).swings(len(chart.htf_df) - 1):
            if k == want and lo < p < hi:
                found.append(f"{chart.htf_timeframe} swing {'high' if want == 'H' else 'low'} {fmt(p)}")
        vp = volume_profile(chart.htf_df.tail(120)) or {}
        found += [f"{chart.htf_timeframe} {k} {fmt(v)}" for k, v in vp.items() if lo < v < hi]
    return found


def snipe(chart, setup, cleaner_passed):
    """Kthen (kaloi?, mesazhi). Kur refuzon, mesazhi është bosh; arsyet kthehen veç për panelin."""
    c = float(chart.df["close"].iloc[-1])
    in_zone = setup.entry_low - IN_ZONE_ATR * setup.atr <= c <= setup.entry_high + IN_ZONE_ATR * setup.atr
    opposing = opposing_levels(chart, setup)
    checks = [
        ("Passed Signal Cleaner", cleaner_passed),
        ("Confluence = Very Strong", setup.score >= 4),
        (f"Risk-Reward ≥ 1:{MIN_RR} (1:{setup.rr:.2f})", setup.rr >= MIN_RR),
        (f"Very tight stop ≤ {MAX_RISK_ATR} ATR ({setup.risk / setup.atr:.2f} ATR)", setup.risk / setup.atr <= MAX_RISK_ATR),
        ("No major opposing structure" + (f" (found: {', '.join(opposing)})" if opposing else ""), not opposing),
        (f"Geometric completion: price {fmt(c)} inside the entry zone", in_zone),
    ]
    reasons = "\n".join(f"{'✔' if ok else '✘'} {name}" for name, ok in checks)
    if not all(ok for _, ok in checks):
        return False, "", reasons
    msg = (f"SNIPER SIGNAL\nPair: {chart.pair}\nDirection: {setup.direction}\n"
           f"Entry Zone: {fmt(setup.entry_low)} – {fmt(setup.entry_high)}\nStop: {fmt(setup.stop)}\n"
           f"Target 1: {fmt(setup.target1)}\nTarget 2: {fmt(setup.target2)}\nRR: 1:{setup.rr:.2f}\n"
           f"Confluence: Very Strong\n→ Passing to Alert Manager")
    return True, msg, reasons
