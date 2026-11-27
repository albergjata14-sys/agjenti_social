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


def test_ready_only_with_prompt():
    ready = {cls.name for cls in ALL_BOTS if cls().ready}
    assert ready == {"Chart Feeder", "Math Geometry"}
    assert get_bot("chart feeder").prompt.startswith("You are Chart Feeder.")
