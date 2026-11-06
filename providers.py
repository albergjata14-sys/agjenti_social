""""Truri" i agjentëve: Gemini (Google), Claude (Anthropic) ose Ollama (model lokal).

Çdo funksion `stream_*` merr udhëzimet e sistemit dhe historinë e bisedës dhe kthen
përgjigjen copë-copë (streaming). Gabimet kthehen si tekst që fillon me "⚠️".
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterator

import httpx

ERROR_PREFIX = "⚠️"

# Sa mesazhe të fundit i dërgohen modelit si kontekst (kufizon koston dhe shpejtësinë)
MAX_HISTORY_MESSAGES = 40


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    models: dict[str, str]
    secret_name: str | None  # emri i çelësit te secrets.toml (None = s'ka nevojë për çelës)
    note: str
    extra: dict = field(default_factory=dict)


PROVIDERS: dict[str, Provider] = {
    "gemini": Provider(
        key="gemini",
        label="Gemini (Google) - ka nivel falas",
        models={
            "Gemini Flash (i shpejtë, falas)": "gemini-flash-latest",
            "Gemini Flash-Lite (më i lehti)": "gemini-flash-lite-latest",
            "Gemini Pro (më i fuqishmi)": "gemini-pro-latest",
        },
        secret_name="GEMINI_API_KEY",
        note="Interneti: kërkim në Google + leximi i linkeve.",
    ),
    "claude": Provider(
        key="claude",
        label="Claude (Anthropic) - me pagesë",
        models={
            "Claude Opus 5.5 (më i fuqishmi)": "claude-opus-5-5",
            "Claude Sonnet 5.5 (i shpejtë)": "claude-sonnet-5-5",
            "Claude Haiku 5.5 (më i liri)": "claude-haiku-5-5",
        },
        secret_name="ANTHROPIC_API_KEY",
        note="Interneti: kërkim në web + leximi i linkeve.",
    ),
    "ollama": Provider(
        key="ollama",
        label="Ollama (lokal në kompjuterin tënd) - falas",
        models={},  # emri i modelit shkruhet nga përdoruesi (p.sh. llama3.2, qwen2.5-coder)
        secret_name=None,
        note="Punon pa internet. Me internetin aktiv lexon linket që i jep në mesazh.",
    ),
}

DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def get_setting(name: str, secrets: dict | None = None, default: str | None = None) -> str | None:
    """Kërko një vlerë te st.secrets dhe pastaj te variablat e mjedisit."""
    if secrets and secrets.get(name):
        return str(secrets[name])
    return os.environ.get(name) or default


def build_history(messages: list[dict]) -> list[dict]:
    """Merr mesazhet e fundit dhe sigurohu që historia të fillojë me përdoruesin."""
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-MAX_HISTORY_MESSAGES:]
        if m["role"] in ("user", "assistant") and m["content"]
    ]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------
def stream_gemini(
    system_prompt: str, messages: list[dict], api_key: str, model: str, web: bool
) -> Iterator[str]:
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in build_history(messages)
    ]
    tools = (
        [types.Tool(google_search=types.GoogleSearch()), types.Tool(url_context=types.UrlContext())]
        if web
        else None
    )
    config = types.GenerateContentConfig(system_instruction=system_prompt, tools=tools)

    try:
        for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
            if chunk.text:
                yield chunk.text
    except errors.ClientError as e:
        if e.code == 429:
            yield f"{ERROR_PREFIX} U arrit kufiri falas i Gemini-t. Prit pak ose provo një model tjetër (p.sh. Flash-Lite)."
        elif e.code in (400, 401, 403) and "API key" in str(e.message):
            yield f"{ERROR_PREFIX} Çelësi i Gemini-t është i pavlefshëm. Kontrollo `GEMINI_API_KEY`."
        elif e.code == 404:
            yield f"{ERROR_PREFIX} Modeli `{model}` nuk u gjet. Zgjidh një model tjetër nga paneli."
        else:
            yield f"{ERROR_PREFIX} Gabim nga Gemini ({e.code}): {e.message}"
    except errors.APIError as e:
        yield f"{ERROR_PREFIX} Gabim nga serveri i Gemini-t ({e.code}). Provo përsëri pas pak."
    except httpx.HTTPError:
        yield f"{ERROR_PREFIX} Nuk u lidh dot me Gemini. Kontrollo internetin."


# ---------------------------------------------------------------------------
# CLAUDE
# ---------------------------------------------------------------------------
_CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


def stream_claude(
    system_prompt: str, messages: list[dict], api_key: str, model: str, web: bool
) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    params: dict = dict(
        model=model,
        max_tokens=16000,
        system=system_prompt,
        messages=build_history(messages),
        output_config={"effort": "medium"},
    )
    if web:
        params["tools"] = [
            {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 5},
        ]
    if model in _CLAUDE_FALLBACK_MODELS:
        # Nëse modeli refuzon kërkesën, API e rikalon automatikisht te një model tjetër
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"

    try:
        with client.beta.messages.stream(**params) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n_Kërkesa u refuzua nga modeli. Provo ta riformulosh._"
        elif final.stop_reason in ("max_tokens", "pause_turn"):
            yield "\n\n_Përgjigjja u ndërpre. Shkruaj \"vazhdo\"._"
    except anthropic.AuthenticationError:
        yield f"{ERROR_PREFIX} Çelësi i Claude është i pavlefshëm. Kontrollo `ANTHROPIC_API_KEY`."
    except anthropic.PermissionDeniedError:
        yield f"{ERROR_PREFIX} Çelësi i Claude nuk ka leje për këtë model."
    except anthropic.RateLimitError:
        yield f"{ERROR_PREFIX} Shumë kërkesa njëherësh. Prit pak sekonda dhe provo përsëri."
    except anthropic.APIStatusError as e:
        yield f"{ERROR_PREFIX} Gabim nga Claude ({e.status_code}): {e.message}"
    except anthropic.APIConnectionError:
        yield f"{ERROR_PREFIX} Nuk u lidh dot me Claude. Kontrollo internetin."


# ---------------------------------------------------------------------------
# OLLAMA (model lokal)
# ---------------------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
_MAX_PAGE_CHARS = 8000


class _TextExtractor(HTMLParser):
    """Nxjerr tekstin e dukshëm nga një faqe HTML (pa script/style)."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def fetch_url_text(url: str) -> str:
    """Shkarko një faqe interneti dhe kthe tekstin e saj (i shkurtuar)."""
    resp = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": "SmartAlbaniaAgent/1.0"})
    resp.raise_for_status()
    if "html" in resp.headers.get("content-type", ""):
        parser = _TextExtractor()
        parser.feed(resp.text)
        text = " ".join(parser.parts)
    else:
        text = resp.text
    return html.unescape(text)[:_MAX_PAGE_CHARS]


def _web_context_for(message: str) -> str:
    """Për çdo link në mesazh, shkarko përmbajtjen që modeli lokal ta lexojë."""
    blocks = []
    urls = [u.rstrip(".,;:!?") for u in _URL_RE.findall(message)]
    for url in dict.fromkeys(urls):  # pa dublikata, në rend
        try:
            blocks.append(f"--- Përmbajtja e {url} ---\n{fetch_url_text(url)}")
        except httpx.HTTPError as e:
            blocks.append(f"--- {url}: nuk u lexua dot ({type(e).__name__}) ---")
        if len(blocks) == 3:
            break
    return "\n\n".join(blocks)


def stream_ollama(
    system_prompt: str, messages: list[dict], host: str, model: str, web: bool
) -> Iterator[str]:
    import ollama

    history = build_history(messages)
    if web and history and history[-1]["role"] == "user":
        page_text = _web_context_for(history[-1]["content"])
        if page_text:
            history[-1] = {
                "role": "user",
                "content": f"{history[-1]['content']}\n\n[Të dhëna nga interneti]\n{page_text}",
            }

    client = ollama.Client(host=host)
    try:
        for chunk in client.chat(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, *history],
            stream=True,
        ):
            if chunk.message.content:
                yield chunk.message.content
    except ollama.ResponseError as e:
        if e.status_code == 404:
            yield f"{ERROR_PREFIX} Modeli `{model}` nuk është i shkarkuar. Në kompjuter ekzekuto: `ollama pull {model}`"
        else:
            yield f"{ERROR_PREFIX} Gabim nga Ollama: {e.error}"
    except (ConnectionError, httpx.ConnectError):
        yield (
            f"{ERROR_PREFIX} Nuk u lidh dot me Ollama te `{host}`. Sigurohu që Ollama është i instaluar "
            "dhe po punon në kompjuter (shiko README.md)."
        )
    except httpx.HTTPError as e:
        yield f"{ERROR_PREFIX} Gabim lidhjeje me Ollama: {type(e).__name__}"
