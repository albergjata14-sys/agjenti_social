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


# ---------------------------------------------------------------- zinxhiri (pa internet: klient i rremë)
from types import SimpleNamespace

from bots.chain import passes, run_chain


class FakeClient:
    """Kthen përgjigjet e radhës dhe mban mend çfarë iu dërgua secilit bot."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])


SNIPER = "SNIPER SIGNAL\nPair: BTC/USDT\nDirection: Long\nEntry Zone: 60000-60200\nStop: 59500\n" \
         "Target 1: 62000\nTarget 2: 63500\nRR: 1:3.5\nConfluence: Very Strong\n→ Passing to Alert Manager"
ALERT = "SNIPER SIGNAL\nPair: BTC/USDT\nDirection: Long\nEntry: 60000-60200\nStop: 59500\nTargets: 62000 / 63500\nRR: 1:3.5"


def test_chain_full_pass_reaches_alert():
    client = FakeClient(["Chart ready\nPair: BTC/USDT\nTimeframe: 4h\n→ Passing to Math Geometry",
                         "Fib 0.618 ... → Passing to Backtester", "PF 1.6 ... → Passing to Signal Cleaner",
                         "All pass → Passing to Sniper", SNIPER, ALERT])
    res = run_chain(b"img", "image/png", "BTC/USDT", "4h", client=client)
    assert [s.status for s in res.steps] == ["passed"] * 5 + ["alert"]
    assert res.alert == ALERT
    assert client.calls[0]["system"].startswith("You are Chart Feeder")
    assert client.calls[5]["messages"][0]["content"] == SNIPER          # Alert Manager merr vetëm sinjalin
    assert all(c["model"] == "claude-opus-5-5" for c in client.calls)


def test_chain_stops_on_reject():
    client = FakeClient(["Chart ready\nPair: X\nTimeframe: 1h\n→ Passing to Math Geometry", "No clean geometric setup."])
    res = run_chain(b"img", "image/png", "X", "1h", client=client)
    assert res.stopped_at == "Math Geometry" and len(client.calls) == 2 and not res.alert


def test_sniper_silent_reject():
    assert not passes("Sniper", "")
    assert passes("Sniper", SNIPER)
    assert not passes("Backtester", "REJECTED: PF 1.2")
