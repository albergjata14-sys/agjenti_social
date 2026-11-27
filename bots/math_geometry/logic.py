"""Math Geometry: gjen setup-in gjeometrik me nivele dhe raporte të sakta, pa parë kurrë qirinjtë e ardhshëm.

Setup-i: trend i qartë (maja dhe funde më të larta / më të ulëta), lëvizja e fundit A→B dhe tërheqja drejt
zonës 0.618–0.65 të Fibonacci-t. Konfluenca numëron sa mjete të tjera bien te e njëjta zonë:
  Fibonacci retracement (baza, 1 pikë) · Fibonacci cluster · Volume Profile (POC/VAH/VAL) ·
  Pitchfork (vija mesatare / tela) · strukturë: maja/fundi i vjetër që ndryshon rol.
Strong = 3 pikë, Very Strong = 4+. Harmonikët dhe Gann nuk përdoren: në tërheqjet e trendit raportet e tyre
"të sakta" pothuajse nuk përputhen kurrë, dhe një mjet që nuk e kontrollojmë dot me saktësi nuk numërohet.
"""
import numpy as np
import pandas as pd

from bots._base import Setup, fmt

PIVOT = 5            # një majë/fund konfirmohet pasi 5 qirinj në të dyja anët janë më poshtë/më lart
ZONE = (0.618, 0.65)
STOP_FIB, STOP_ATR = 0.786, 0.25
TOL_ATR = 0.3        # sa larg zonës mund të jetë një nivel që të numërohet
MAX_DIST_ATR = 3.0   # çmimi duhet të jetë afër zonës që setup-i të ketë kuptim tani
VP_BARS, VP_BINS = 240, 48


def atr(df, n=14):
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def volume_profile(df):
    """POC, VAH, VAL (70% e volumit) mbi qirinjtë e dhënë."""
    tp = ((df["high"] + df["low"] + df["close"]) / 3).to_numpy()
    vol = df["volume"].to_numpy()
    lo, hi = df["low"].min(), df["high"].max()
    if hi <= lo or vol.sum() <= 0:
        return None
    hist, edges = np.histogram(tp, bins=VP_BINS, range=(lo, hi), weights=vol)
    mids = (edges[:-1] + edges[1:]) / 2
    poc = int(hist.argmax())
    a = b = poc
    total, acc = hist.sum(), hist[poc]
    while acc < 0.7 * total and (a > 0 or b < len(hist) - 1):
        up = hist[b + 1] if b < len(hist) - 1 else -1
        dn = hist[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1
            acc += hist[b]
        else:
            a -= 1
            acc += hist[a]
    return {"POC": mids[poc], "VAH": mids[b], "VAL": mids[a]}


class Geometry:
    """Llogaritjet bëhen një herë për gjithë grafikun; `setup_at(t)` përdor vetëm qirinjtë deri te t."""

    def __init__(self, df):
        self.df = df
        self.high, self.low = df["high"].to_numpy(), df["low"].to_numpy()
        self.close = df["close"].to_numpy()
        self.atr = atr(df).to_numpy()
        w = 2 * PIVOT + 1
        hmax = df["high"].rolling(w, center=True).max().to_numpy()
        lmin = df["low"].rolling(w, center=True).min().to_numpy()
        piv = [(i, self.high[i], "H") for i in range(len(df)) if self.high[i] == hmax[i]]
        piv += [(i, self.low[i], "L") for i in range(len(df)) if self.low[i] == lmin[i]]
        self.pivots = sorted(piv)                # (indeksi, çmimi, lloji); i konfirmuar te indeksi + PIVOT

    def swings(self, t, keep=8):
        """Majat dhe fundet e alternuara, të konfirmuara deri te qiriri t."""
        out = []
        for i, p, kind in self.pivots:
            if i + PIVOT > t:
                break
            if out and out[-1][2] == kind:
                if (kind == "H" and p > out[-1][1]) or (kind == "L" and p < out[-1][1]):
                    out[-1] = (i, p, kind)
            elif out and out[-1][0] == i:
                continue
            else:
                out.append((i, p, kind))
        return out[-keep:]

    def setup_at(self, t):
        """Setup-i në qiririn t, ose None kur gjeometria nuk është e pastër."""
        s = self.swings(t)
        if len(s) < 4 or not np.isfinite(self.atr[t]):
            return None
        (i0, p0, _), (i1, h1, _), (ia, a, _), (ib, b, kb) = s[-4:]
        if kb == "H" and b > h1 and a > p0:
            side = 1                                # maja dhe funde më të larta, lëvizja e fundit lart
        elif kb == "L" and b < h1 and a < p0:
            side = -1                               # maja dhe funde më të ulëta, lëvizja e fundit poshtë
        else:
            return None
        A, B, leg = a, b, abs(b - a)
        x = self.atr[t]
        lvl = lambda r: B - side * r * leg          # niveli i tërheqjes r
        zone = sorted((lvl(ZONE[0]), lvl(ZONE[1])))
        entry = lvl(sum(ZONE) / 2)
        stop = lvl(STOP_FIB) - side * STOP_ATR * x
        after_hi, after_lo = self.high[ib + 1:t + 1], self.low[ib + 1:t + 1]
        if len(after_hi):
            if side == 1 and (after_hi.max() > B or after_lo.min() <= stop):
                return None                         # majë e re ose stop-i i prekur: setup-i nuk vlen më
            if side == -1 and (after_lo.min() < B or after_hi.max() >= stop):
                return None
        c = self.close[t]
        dist = (c - zone[1]) if side == 1 else (zone[0] - c)
        if dist > MAX_DIST_ATR * x:
            return None                             # çmimi ende larg zonës

        lo_z, hi_z = zone[0] - TOL_ATR * x, zone[1] + TOL_ATR * x
        inside = lambda v: lo_z <= v <= hi_z
        tools = [f"Fibonacci retracement {ZONE[0]}–{ZONE[1]} of {fmt(A)} → {fmt(B)}: {fmt(zone[0])} – {fmt(zone[1])}"]

        # Fibonacci cluster: nivelet e lëvizjes së madhe (fundi/maja e vjetër → B) dhe e lëvizjes së mëparshme
        cluster = []
        for name, frm, to in (("big leg", p0, B), ("prior leg", p0, h1)):
            for r in (0.382, 0.5, 0.618, 0.786):
                v = to - (to - frm) * r
                if inside(v):
                    cluster.append(f"{r} of {name} {fmt(frm)} → {fmt(to)} = {fmt(v)}")
        if cluster:
            tools.append("Fibonacci cluster: " + "; ".join(cluster[:2]))

        vp = volume_profile(self.df.iloc[max(0, t - VP_BARS + 1):t + 1])
        if vp:
            hits = [f"{k} {fmt(v)}" for k, v in vp.items() if inside(v)]
            if hits:
                tools.append(f"Volume Profile ({VP_BARS} bars): " + ", ".join(hits))

        # Pitchfork (Andrews) nga tre pikat e fundit para B: P0, P1, P2
        mid_i, mid_p = (i1 + ia) / 2, (h1 + a) / 2
        if mid_i != i0:
            slope = (mid_p - p0) / (mid_i - i0)
            median = p0 + slope * (t - i0)
            tine = a + slope * (t - ia)             # teli që kalon nga P2
            hits = [f"{n} {fmt(v)}" for n, v in (("median line", median), ("P2 tine", tine)) if inside(v)]
            if hits:
                tools.append(f"Pitchfork {fmt(p0)} / {fmt(h1)} / {fmt(a)}: " + ", ".join(hits))

        if inside(h1):
            tools.append(f"Market structure: old {'high' if side == 1 else 'low'} {fmt(h1)} flips to "
                         f"{'support' if side == 1 else 'resistance'}")

        return Setup("Long" if side == 1 else "Short", zone[0], zone[1], entry, stop, B, B + side * 0.272 * leg,
                     x, len(tools), tools, (A, B))


def analyze(chart):
    """Kthen (setup ose None, mesazhi i botit) për qiririn e fundit të mbyllur."""
    setup = Geometry(chart.df).setup_at(len(chart.df) - 1)
    if setup is None or setup.score < 3:
        return None, "No clean geometric setup."
    lines = [f"{chart.pair} {chart.timeframe} – {setup.direction} – Confluence: {setup.confluence} ({setup.score} tools)"]
    lines += [f"• {t}" for t in setup.tools]
    lines += [f"Entry zone: {fmt(setup.entry_low)} – {fmt(setup.entry_high)} (mid {fmt(setup.entry)})",
              f"Invalidation: {fmt(setup.stop)} (0.786 − {STOP_ATR} ATR)",
              f"Target 1: {fmt(setup.target1)} (swing B) · Target 2: {fmt(setup.target2)} (1.272 extension)",
              f"RR to Target 1: 1:{setup.rr:.2f}", "→ Passing to Backtester"]
    return setup, "\n".join(lines)
