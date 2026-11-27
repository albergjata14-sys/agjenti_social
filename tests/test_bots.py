import pytest

from bots import ALL_BOTS, get_bot


def test_six_separate_bots():
    names = [cls.name for cls in ALL_BOTS]
    assert names == ["Chart Feeder", "Math Geometry", "Backtester", "Signal Cleaner", "Sniper", "Alert Manager"]
    folders = {cls().folder for cls in ALL_BOTS}
    assert len(folders) == 6                      # çdo bot në dosjen e vet
    for cls in ALL_BOTS:
        assert cls().prompt_file.exists()


def test_get_bot_by_name():
    assert get_bot("sniper").name == "Sniper"
    assert get_bot("signal_cleaner").name == "Signal Cleaner"
    with pytest.raises(KeyError):
        get_bot("nuk ekziston")


def test_all_bots_have_prompts():
    for cls in ALL_BOTS:
        bot = cls()
        assert bot.ready
        assert bot.prompt.startswith("You are")
    assert get_bot("chart feeder").prompt.startswith("You are Chart Feeder.")


# ---------------------------------------------------------------- logjika e botëve (pa internet)
import numpy as np
import pandas as pd

from bots._base import Chart, Setup
from bots.alert_manager import logic as alert_logic
from bots.backtester.logic import stats
from bots.chain import run_chain
from bots.chart_feeder import logic as feeder
from bots.math_geometry.logic import Geometry, analyze, volume_profile
from bots.signal_cleaner.logic import clean
from bots.sniper.logic import snipe


def path(knots, vol=None):
    """Grafik me vija të drejta mes pikave (indeksi, çmimi)."""
    x = np.arange(knots[-1][0] + 1)
    close = np.interp(x, [k[0] for k in knots], [k[1] for k in knots])
    idx = pd.date_range("2026-01-01", periods=len(x), freq="h", tz="UTC")
    return pd.DataFrame({"open": np.r_[close[0], close[:-1]], "high": close * 1.002, "low": close * 0.998,
                         "close": close, "volume": vol if vol is not None else 100.0}, index=idx)


UPTREND = [(0, 105), (20, 100), (40, 120), (60, 110), (80, 140), (99, 121)]


def test_geometry_finds_long_pullback_with_exact_levels():
    vol = np.full(100, 100.0)
    vol[99] = 20000                                   # volumi i madh te 121 → POC brenda zonës
    df = path(UPTREND, vol)
    setup = Geometry(df).setup_at(99)
    assert setup.direction == "Long"
    leg = setup.leg[1] - setup.leg[0]
    assert setup.entry_low == pytest.approx(setup.leg[1] - 0.65 * leg)
    assert setup.entry_high == pytest.approx(setup.leg[1] - 0.618 * leg)
    assert setup.stop < setup.leg[1] - 0.786 * leg     # stop-i përtej 0.786
    assert setup.target1 == setup.leg[1]
    assert setup.score >= 3 and any("Volume Profile" in t for t in setup.tools)
    assert any("flips to support" in t for t in setup.tools)
    _, msg = analyze(Chart("TEST/USDT", "1h", df))
    assert msg.endswith("→ Passing to Backtester")


def test_geometry_rejects_when_structure_unclear():
    df = path([(0, 100), (20, 120), (40, 100), (60, 120), (80, 100), (99, 110)])
    assert Geometry(df).setup_at(99) is None
    assert analyze(Chart("T", "1h", df)) == (None, "No clean geometric setup.")


def test_geometry_never_uses_future_candles():
    df = path(UPTREND)
    g_full, g_cut = Geometry(df), Geometry(df.iloc[:90])
    assert g_full.swings(89) == g_cut.swings(89)


def test_volume_profile_poc():
    df = path([(0, 100), (49, 110)], vol=np.r_[np.full(25, 1.0), np.full(25, 50.0)])
    vp = volume_profile(df)
    assert vp["VAL"] <= vp["POC"] <= vp["VAH"] and vp["POC"] > 105


def test_backtest_stats():
    st = stats([2.0, -1.0, 2.0, -1.0], cost_pct=0.15)
    assert st.trades == 4 and st.profit_factor == pytest.approx(2.0) and st.expectancy == pytest.approx(0.5)
    assert not st.passed                              # më pak se 40 tregti
    assert stats([1.0] * 30 + [-1.0] * 15).passed


def setup(score=4, rr_reward=4.0):
    return Setup("Long", 99.0, 101.0, 100.0, 99.0, 100 + rr_reward, 106.0, atr=1.0, score=score, tools=[], leg=(90, 104))


def test_signal_cleaner_needs_everything():
    up = path([(0, 100), (40, 110), (60, 105), (100, 120), (120, 113), (160, 130), (180, 124), (220, 140)])
    chart = Chart("T", "1h", up, "4h", up)
    ok, msg = clean(chart, setup(), stats([1.0] * 30 + [-1.0] * 15))
    assert ok and msg.endswith("→ Passing to Sniper")
    ok, msg = clean(chart, setup(), stats([1.0, -1.0]))
    assert not ok and msg.endswith("REJECTED.")
    ok, _ = clean(chart, setup(rr_reward=2.0), stats([1.0] * 30 + [-1.0] * 15))
    assert not ok                                     # RR 1:2 < 1:2.8


def test_sniper_format_and_silent_reject():
    df = path([(0, 100), (10, 100)])
    chart = Chart("BTC/USDT", "1h", df, "4h", None)
    ok, msg, _ = snipe(chart, setup(), True)
    assert ok and msg.splitlines()[0] == "SNIPER SIGNAL" and msg.endswith("→ Passing to Alert Manager")
    assert "Confluence: Very Strong" in msg
    ok, msg, why = snipe(chart, setup(score=3), True)
    assert not ok and msg == "" and "✘ Confluence = Very Strong" in why


def test_alert_manager_format_and_no_repeat():
    sniper = ("SNIPER SIGNAL\nPair: BTC/USDT\nDirection: Long\nEntry Zone: 99 – 101\nStop: 98\n"
              "Target 1: 104\nTarget 2: 106\nRR: 1:4.00\nConfluence: Very Strong\n→ Passing to Alert Manager")
    alert, new = alert_logic.send(sniper, "1h")
    assert new and alert == ("SNIPER SIGNAL\nPair: BTC/USDT\nDirection: Long\nEntry: 99 – 101\nStop: 98\n"
                             "Targets: 104 / 106\nRR: 1:4.00")
    assert alert_logic.send(sniper, "1h") == (alert, False)
    assert alert_logic.send("hello", "1h") == ("", False)


def test_fetch_candles_pages_back_with_start_and_end(monkeypatch):
    hour = 3_600_000
    now = 1_800_000_000_000
    def fake_get(path, **p):
        end = p.get("endTime", now)
        start = p.get("startTime", end - 500 * hour)
        ts = [t for t in range(now - 1200 * hour, now, hour) if start <= t <= end][-p["limit"]:]
        return [[t, "1", "2", "0.5", "1.5", "10", t + hour - 1, "15"] for t in ts]
    monkeypatch.setattr(feeder, "_get", fake_get)
    monkeypatch.setattr(feeder.time, "time", lambda: now / 1000 + 10 * 3600)
    df = feeder.fetch_candles("btc/usdt", "1h", 1100)
    assert len(df) == 1100 and df.index.is_monotonic_increasing and not df.index.duplicated().any()


def test_chain_runs_offline_and_stops_at_first_reject():
    df = path([(0, 100), (20, 120), (40, 100), (60, 120), (80, 100), (99, 110)])
    res = run_chain("BTC/USDT", "1h", fetch=lambda p, tf, n: df)
    assert [s.status for s in res.steps] == ["passed", "rejected"]
    assert res.steps[0].output == "Chart ready\nPair: BTC/USDT\nTimeframe: 1h\n→ Passing to Math Geometry"
    assert res.stopped_at == "Math Geometry" and res.statuses[2:] == ["idle"] * 4


def test_chain_reports_network_errors():
    def boom(*a):
        raise OSError("no network")
    res = run_chain("BTC/USDT", "1h", fetch=boom)
    assert res.steps[0].status == "error" and "no network" in res.steps[0].output
