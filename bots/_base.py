"""Bazë e vogël e përbashkët: çdo bot ka emrin, rolin dhe promptin e vet në dosjen e vet."""
from pathlib import Path

PLACEHOLDER = "<!-- PROMPTI DO TË SHTOHET -->"


class Bot:
    name = ""
    role = ""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.prompt_file = self.folder / "prompt.md"

    @property
    def prompt(self):
        text = self.prompt_file.read_text(encoding="utf-8").strip() if self.prompt_file.exists() else ""
        return "" if text == PLACEHOLDER else text

    @property
    def ready(self):
        return bool(self.prompt)

    def set_prompt(self, text):
        self.prompt_file.write_text(text.strip() + "\n", encoding="utf-8")

    def __repr__(self):
        return f"<{self.name} ({'gati' if self.ready else 'pa prompt'})>"
