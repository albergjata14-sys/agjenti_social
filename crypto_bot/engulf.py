"""Strategjia "engulf": bias ditor nga zonat engulf, marrje (sweep) e nivelit të sesionit aziatik
dhe hyrje me engulf të freskët në intervalin e hyrjes (p.sh. 15m).

Rregullat që janë INTERPRETIM (strategjia nuk i përcakton saktë) janë të shënuara me [INTERPRETIM]
dhe secila ka një parametër te konfigurimi. Nuk përdoret asnjë e dhënë nga e ardhmja: çdo vendim
bëhet në mbylljen e një qiriri dhe ekzekutohet në hapjen e qiririt pasardhës.
"""
import numpy as np
import pandas as pd

UK = "Europe/London"


def find_engulfs(o, h, l, c, max_bars: int):
    """Zonat engulf të konfirmuara.

    Engulf bullish: qiriri i fundit rënës para lëvizjes; konfirmohet kur një qiri mbyllet mbi majën e tij.
    Engulf bearish: pasqyra. [INTERPRETIM] konfirmimi duhet të vijë brenda `max_bars` qirinjve.
    Kthen (bull, bull_low, bear, bear_high): flamujt në qiririn e konfirmimit dhe kufirin e zonës që e
    zhvlerëson setup-in (fundi më i ulët / maja më e lartë nga qiriri i zonës deri te konfirmimi).
    """
    n = len(c)
    bull, bear = np.zeros(n, bool), np.zeros(n, bool)
    bull_low, bear_high = np.full(n, np.nan), np.full(n, np.nan)
    last_bear = last_bull = -1          # qiriri i fundit rënës / rritës ende i pakonfirmuar
    for i in range(n):
        j = last_bear
        if j >= 0 and i - j <= max_bars and c[i] > h[j]:
            bull[i], bull_low[i], last_bear = True, l[j:i + 1].min(), -1
        j = last_bull
        if j >= 0 and i - j <= max_bars and c[i] < l[j]:
            bear[i], bear_high[i], last_bull = True, h[j:i + 1].max(), -1
        if c[i] < o[i]:
            last_bear = i
        elif c[i] > o[i]:
            last_bull = i
    return bull, bull_low, bear, bear_high


def daily_context(daily: pd.DataFrame, cfg) -> dict:
    """Bias-i ditor dhe reversal areas ditore, për çdo ditë të mbyllur.

    Bias: drejtimi i engulf-it të fundit ditor. [INTERPRETIM] vlen deri sa çmimi të arrijë swing-un e
    jashtëm pasues (`engulf_bias_until_swing`) ose të kalojnë `engulf_bias_max_days` ditë; pastaj neutral.
    Swing ditor: [INTERPRETIM] maja/fundi më ekstrem se `engulf_swing_strength` ditë në secilën anë;
    njihet vetëm pasi të jenë mbyllur ditët e anës së djathtë.
    """
    o, h, l, c = (daily[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    n, k = len(c), cfg.engulf_swing_strength
    bull, _, bear, _ = find_engulfs(o, h, l, c, cfg.engulf_max_bars)
    swing_hi = [s for s in range(k, n - k) if h[s] > h[s - k:s].max() and h[s] > h[s + 1:s + k + 1].max()]
    swing_lo = [s for s in range(k, n - k) if l[s] < l[s - k:s].min() and l[s] < l[s + 1:s + k + 1].min()]
    bias = np.zeros(n, int)
    state, since, level = 0, 0, None
    for d in range(n):
        known_hi = [h[s] for s in swing_hi if s + k <= d and d - s <= cfg.engulf_swing_lookback_days]
        known_lo = [l[s] for s in swing_lo if s + k <= d and d - s <= cfg.engulf_swing_lookback_days]
        if bull[d]:
            state, since = 1, d
            level = min((x for x in known_hi if x > c[d]), default=None)
        elif bear[d]:
            state, since = -1, d
            level = max((x for x in known_lo if x < c[d]), default=None)
        elif state:
            reached = cfg.engulf_bias_until_swing and level is not None and (
                h[d] >= level if state > 0 else l[d] <= level)
            if reached or d - since > cfg.engulf_bias_max_days:
                state = 0
        bias[d] = state
    return {"bias": bias, "high": h, "low": l, "swing_hi": swing_hi, "swing_lo": swing_lo,
            "close_time": daily.index + pd.Timedelta(days=1)}


def uk_clock(index: pd.DatetimeIndex, cfg):
    """Data dhe ora në Mbretërinë e Bashkuar (GMT/BST automatikisht) për kohën e hapjes së çdo qiriri.

    `data_tz` është ora e të dhënave: UTC për bursat e kriptove; për MT5 ora e serverit të brokerit.
    """
    tz = "UTC" if cfg.data_tz == "auto" else cfg.data_tz
    local = index.tz_localize(None).tz_localize(tz, ambiguous=np.zeros(len(index), bool), nonexistent="shift_forward")
    uk = local.tz_convert(UK)
    return uk.strftime("%Y-%m-%d").to_numpy(), (uk.hour + uk.minute / 60).to_numpy()


def engulf_signals(s: pd.DataFrame, cfg, daily=None) -> pd.DataFrame:
    """Sinjalet e strategjisë engulf për çdo qiri të `s` (që duhet të ketë kolonën `atr`)."""
    idx = s.index
    step = idx.to_series().diff().median()
    if daily is None:
        daily = s[["open", "high", "low", "close"]].resample("1D").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    ctx = daily_context(daily, cfg)
    # Dita e fundit e mbyllur për çdo qiri (krahasohet me çastin e mbylljes së qiririt).
    # (të dy indekset kthehen në nanosekonda: burime të ndryshme mund të kenë njësi të ndryshme kohe)
    day_of = np.searchsorted(ctx["close_time"].as_unit("ns").asi8, (idx + step).as_unit("ns").asi8, side="right") - 1
    o, h, l, c = (s[k].to_numpy(float) for k in ["open", "high", "low", "close"])
    atr = s["atr"].to_numpy(float)
    bull, bull_low, bear, bear_high = find_engulfs(o, h, l, c, cfg.engulf_max_bars)
    date, hour = uk_clock(idx, cfg)
    n, k = len(c), cfg.engulf_swing_strength
    out = {key: np.full(n, np.nan) for key in ["stop_price", "target_price", "sess_high", "sess_low", "sess_mid"]}
    buy, short = np.zeros(n, bool), np.zeros(n, bool)
    bias_col, swept_lo_col, swept_hi_col = np.zeros(n, int), np.zeros(n, bool), np.zeros(n, bool)
    note = np.full(n, "", dtype=object)

    def pick_target(i, d, side, stop):
        """Reversal area e jashtme pasuese në drejtim të bias-it: high/low i ditës së mëparshme ose swing
        ditor. [INTERPRETIM] merret niveli më i afërt që jep të paktën `engulf_min_rr` fitim/rrezik."""
        risk = abs(c[i] - stop)
        if risk <= 0:
            return None
        if side > 0:
            lv = [ctx["high"][d]] + [ctx["high"][x] for x in ctx["swing_hi"]
                                     if x + k <= d and d - x <= cfg.engulf_swing_lookback_days]
            lv = sorted(x for x in lv if x > c[i])
        else:
            lv = [ctx["low"][d]] + [ctx["low"][x] for x in ctx["swing_lo"]
                                    if x + k <= d and d - x <= cfg.engulf_swing_lookback_days]
            lv = sorted((x for x in lv if x < c[i]), reverse=True)
        return next((x for x in lv if abs(x - c[i]) / risk >= cfg.engulf_min_rr), None)

    cur = None
    for i in range(n):
        if date[i] != cur:      # ditë e re (ora UK): nivelet e sesionit fillojnë nga e para
            cur, hi, lo = date[i], -np.inf, np.inf
            swept_lo = swept_hi = long_done = short_done = False
            run_min, run_max = np.inf, -np.inf
        d = day_of[i]
        b = ctx["bias"][d] if d >= 0 else 0
        bias_col[i] = b
        if cfg.session_start_hour <= hour[i] < cfg.session_end_hour:
            hi, lo = max(hi, h[i]), min(lo, l[i])
            note[i] = "sesioni aziatik po formohet"
            continue
        if hour[i] < cfg.session_start_hour or not np.isfinite(lo) or d < 0:
            note[i] = "para sesionit aziatik" if hour[i] < cfg.session_start_hour else "pa të dhëna sesioni/ditore"
            continue
        mid = (hi + lo) / 2
        out["sess_high"][i], out["sess_low"][i], out["sess_mid"][i] = hi, lo, mid
        # Marrja (sweep) e nivelit: fundi i sesionit, ose edhe low/high i ditës së mëparshme.
        low_levels = [lo] + ([ctx["low"][d]] if cfg.engulf_sweep_prev_day else [])
        high_levels = [hi] + ([ctx["high"][d]] if cfg.engulf_sweep_prev_day else [])
        run_min, run_max = min(run_min, l[i]), max(run_max, h[i])
        swept_lo = swept_lo or any(l[i] < x for x in low_levels)
        swept_hi = swept_hi or any(h[i] > x for x in high_levels)
        swept_lo_col[i], swept_hi_col[i] = swept_lo, swept_hi
        if hour[i] >= cfg.engulf_trade_end_hour:
            note[i] = "jashtë orarit të tregtimit"
            continue
        if b == 0 and not cfg.engulf_neutral_mode:
            note[i] = "bias-i ditor i paqartë: pa tregti"
            continue
        buf = cfg.engulf_stop_buffer_atr * (atr[i] if np.isfinite(atr[i]) else 0.0)
        strong_up = i >= cfg.engulf_structure_bars and c[i] > h[i - cfg.engulf_structure_bars:i].max()
        strong_dn = i >= cfg.engulf_structure_bars and c[i] < l[i - cfg.engulf_structure_bars:i].min()
        for side in ([1] if b > 0 else [-1] if b < 0 else [1, -1]):
            name = "bullish" if side > 0 else "bearish"
            if side < 0 and not cfg.allow_short:
                note[i] = "bias bearish, por shitja short nuk është e lejuar"
                continue
            swept, done = (swept_lo, long_done) if side > 0 else (swept_hi, short_done)
            engulf = bull[i] if side > 0 else bear[i]
            if not swept:
                note[i] = f"bias {name}: pritet marrja e {'low' if side > 0 else 'high'} të sesionit"
                continue
            if not engulf:
                note[i] = f"bias {name}, niveli u mor: pritet engulf {name} në intervalin e hyrjes"
                continue
            if cfg.engulf_require_strong and not (strong_up if side > 0 else strong_dn):
                note[i] = "engulf i dobët (pa thyerje strukture) dhe kërkohet engulf i fortë"
                continue
            if not done:        # hyrja normale: stop përtej swing-ut të marrjes së nivelit
                stop = (run_min - buf) if side > 0 else (run_max + buf)
                kind = "hyrje normale"
            else:               # vazhdim: çmimi duhet të jetë në anën e duhur të 50% (kur përdoret)
                if not cfg.engulf_continuation:
                    note[i] = "hyrjet e vazhdimit janë të fikura"
                    continue
                if cfg.engulf_use_mid and not (c[i] > mid if side > 0 else c[i] < mid):
                    note[i] = "vazhdim i refuzuar: çmimi në anën e gabuar të 50% të sesionit"
                    continue
                stop = (bull_low[i] - buf) if side > 0 else (bear_high[i] + buf)
                kind = "hyrje vazhdimi"
            target = pick_target(i, d, side, stop)
            if target is None:
                note[i] = f"engulf {name}, por asnjë objektiv me raport ≥ {cfg.engulf_min_rr:g}"
                continue
            out["stop_price"][i], out["target_price"][i] = stop, target
            if side > 0:
                buy[i], long_done = True, True
            else:
                short[i], short_done = True, True
            note[i] = f"{kind}: bias {name}, niveli i sesionit u mor, engulf {name} i konfirmuar"
            break
    res = pd.DataFrame(out, index=idx)
    res["buy"], res["short"], res["bias"] = buy, short, bias_col
    res["swept_low"], res["swept_high"], res["engulf_note"] = swept_lo_col, swept_hi_col, note
    return res
