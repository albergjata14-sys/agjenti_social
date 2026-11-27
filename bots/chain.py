"""Zinxhiri i botëve: Chart Feeder → Math Geometry → Backtester → Signal Cleaner → Sniper → Alert Manager.

Çdo bot është një thirrje e veçantë te Claude me promptin e vet (bots/<emri>/prompt.md).
Grafiku kalon nga një bot te tjetri vetëm kur boti i mëparshëm e miraton.
"""
import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from bots import ALL_BOTS

MODEL = "claude-opus-5-5"
KEY_FILE = Path("bots_anthropic_key.json")          # jashtë git-it

# Sa thellë mendon secili bot: etiketimi dhe alarmi janë punë e thjeshtë, analiza jo.
EFFORT = {"Chart Feeder": "low", "Math Geometry": "high", "Backtester": "high",
          "Signal Cleaner": "high", "Sniper": "high", "Alert Manager": "low"}


@dataclass
class Step:
    bot: str
    status: str            # "passed" | "rejected" | "alert" | "error"
    output: str = ""


@dataclass
class ChainResult:
    steps: list = field(default_factory=list)

    @property
    def alert(self):
        last = self.steps[-1] if self.steps else None
        return last.output if last and last.status == "alert" else ""

    @property
    def stopped_at(self):
        last = self.steps[-1] if self.steps else None
        return last.bot if last and last.status in ("rejected", "error") else ""


# ---------------------------------------------------------------- çelësi i API-së

def load_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        return json.loads(KEY_FILE.read_text(encoding="utf-8")).get("api_key", "")
    except (OSError, ValueError):
        return ""


def save_api_key(key):
    KEY_FILE.write_text(json.dumps({"api_key": key.strip()}), encoding="utf-8")


def make_client(api_key=None):
    import anthropic

    key = api_key or load_api_key()
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


# ---------------------------------------------------------------- vendimi i çdo boti

def passes(bot_name, text):
    """A e miratoi boti grafikun? Lexohet nga formati që kërkon prompti i tij."""
    t = text.strip()
    if bot_name == "Sniper":
        return t.upper().startswith("SNIPER SIGNAL")       # refuzimi i Sniper-it është i heshtur
    if bot_name == "Alert Manager":
        return t.upper().startswith("SNIPER SIGNAL")
    return "passing to" in t.lower()


def _request_text(bot_name, pair, timeframe, indicators, history):
    if bot_name == "Alert Manager":
        return history[-1].output                          # vetëm mesazhi i Sniper-it
    lines = []
    if bot_name == "Chart Feeder":
        lines.append(f"Pair: {pair or '-'}\nTimeframe: {timeframe or '-'}")
        if indicators:
            lines.append(f"Indicators: {indicators}")
        lines.append("Chart screenshot attached.")
    else:
        lines.append("Messages from the previous bots in the chain:")
        for s in history:
            lines.append(f"--- {s.bot} ---\n{s.output}")
    return "\n\n".join(x for x in lines if x)


def _ask(client, bot, content, effort):
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=bot.prompt,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        return None
    return "".join(b.text for b in response.content if b.type == "text").strip()


def run_chain(image_bytes, media_type, pair="", timeframe="", indicators="", client=None, on_step=None):
    """Kalon grafikun nëpër 6 botët. `on_step(index, Step|None)` thirret kur nis (None) dhe kur mbaron çdo bot."""
    client = client or make_client()
    image = {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.standard_b64encode(image_bytes).decode()}}
    result = ChainResult()
    for i, cls in enumerate(ALL_BOTS):
        bot = cls()
        if on_step:
            on_step(i, None)
        text = _request_text(bot.name, pair, timeframe, indicators, result.steps)
        content = text if bot.name == "Alert Manager" else [image, {"type": "text", "text": text}]
        try:
            output = _ask(client, bot, content, EFFORT[bot.name])
        except Exception as exc:                            # gabim rrjeti / çelësi / API
            step = Step(bot.name, "error", f"{type(exc).__name__}: {exc}")
        else:
            if output is None:
                step = Step(bot.name, "error", "Modeli e refuzoi kërkesën.")
            elif bot.name == "Alert Manager" and passes(bot.name, output):
                step = Step(bot.name, "alert", output)
            elif passes(bot.name, output):
                step = Step(bot.name, "passed", output)
            else:
                step = Step(bot.name, "rejected", output or "(refuzuar në heshtje)")
        result.steps.append(step)
        if on_step:
            on_step(i, step)
        if step.status in ("rejected", "error"):
            break
    return result
