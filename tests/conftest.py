import pytest


@pytest.fixture(autouse=True)
def _isolated_dir(tmp_path, monkeypatch):
    """Çdo test punon në dosjen e vet, që skedarët e robotit (njoftime, gjendje) të mos përzihen."""
    monkeypatch.chdir(tmp_path)
    for var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)
