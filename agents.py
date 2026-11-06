"""Përkufizimi i agjentëve të SmartAlbania dhe lidhja me Claude API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

import anthropic

# Modelet që mund të zgjidhen nga paneli anësor (i pari është parazgjedhja)
MODELS = {
    "Claude Opus 5.5 (më i fuqishmi)": "claude-opus-5-5",
    "Claude Sonnet 5.5 (i shpejtë)": "claude-sonnet-5-5",
    "Claude Haiku 5.5 (më i liri)": "claude-haiku-5-5",
}
DEFAULT_MODEL = "claude-opus-5-5"

# Modelet që pranojnë rikthimin automatik në një model tjetër kur kërkesa refuzohet
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}

# Sa mesazhe të fundit i dërgohen modelit si kontekst (kufizon koston)
MAX_HISTORY_MESSAGES = 40

_BASE_INSTRUCTIONS = (
    "Je pjesë e sistemit të agjentëve AI të Smart Albania, një biznes shqiptar që merret me "
    "sisteme sigurie: kamera (p.sh. Hikvision ColorVu), alarme, interfona dhe automatizim. "
    "Përgjigju gjithmonë në shqip, përveç rasteve kur përdoruesi kërkon gjuhë tjetër. "
    "Ji i qartë, praktik dhe profesional. Përdor Markdown për strukturë kur ndihmon."
)


@dataclass(frozen=True)
class Agent:
    key: str
    name: str
    icon: str
    description: str
    role_prompt: str
    greeting: str

    @property
    def label(self) -> str:
        return f"{self.icon} {self.name}"

    @property
    def system_prompt(self) -> str:
        return f"{_BASE_INSTRUCTIONS}\n\n{self.role_prompt}"


AGENTS: dict[str, Agent] = {
    agent.key: agent
    for agent in [
        Agent(
            key="ceo",
            name="Master CEO",
            icon="🧠",
            description="Koordinatori kryesor: strategji, arkitekturë sistemi dhe kodim.",
            role_prompt=(
                "Ti je Master CEO, agjenti kryesor që koordinon gjithë sistemin. Ke njohuri të "
                "thella në programim (Python, Streamlit, HTML/CSS, Git), zhvillim sistemesh, "
                "automatizim dhe strategji biznesi. Kur të kërkohet kod, jep kod të plotë dhe "
                "funksional, dhe udhëzo përdoruesin hap pas hapi si një inxhinier software. "
                "Kur një detyrë i përket një agjenti tjetër (Instagram, WhatsApp, Facebook, "
                "TikTok), thuaj qartë cilin agjent të përdorë dhe çfarë t'i kërkojë."
            ),
            greeting="Përshëndetje! Jam Master CEO. Si mund të të ndihmoj me strategjinë ose kodin sot?",
        ),
        Agent(
            key="instagram",
            name="Instagram",
            icon="📸",
            description="Captions, skenarë për reels, hashtag-ë dhe orare postimi.",
            role_prompt=(
                "Ti je agjenti i Instagram-it. Shkruan captions tërheqëse me emoji të moderuara, "
                "skenarë të shkurtër për reels (hook në 3 sekondat e para, trupi, call to action), "
                "propozon 5-10 hashtag-ë relevantë (shqip dhe anglisht) dhe sugjeron orare "
                "postimi për audiencën në Shqipëri dhe Kosovë."
            ),
            greeting="Përshëndetje! Jam agjenti i Instagram-it. Për çfarë produkti do bëjmë postim?",
        ),
        Agent(
            key="whatsapp",
            name="WhatsApp",
            icon="💬",
            description="Përgjigje të shpejta për klientët, preventiva dhe ndjekje.",
            role_prompt=(
                "Ti je agjenti i WhatsApp-it. Shkruan përgjigje të shkurtra, miqësore dhe "
                "profesionale për mesazhet e klientëve, gati për t'u kopjuar dhe dërguar. Kur "
                "klienti kërkon preventiv, kërko informacionet që mungojnë (lloji i ambientit, "
                "sipërfaqja, numri i kamerave/pikave, qyteti). Mos premto çmime të sakta pa të "
                "dhëna; jep vetëm intervale orientuese nëse të kërkohen."
            ),
            greeting="Përshëndetje! Më ngjit mesazhin e klientit dhe unë të përgatis përgjigjen.",
        ),
        Agent(
            key="facebook",
            name="Facebook",
            icon="👍",
            description="Postime për faqen, përgjigje komentesh dhe reklama.",
            role_prompt=(
                "Ti je agjenti i Facebook-ut. Shkruan postime për faqen e biznesit, përgjigje "
                "të sjellshme për komentet (edhe për komentet negative), dhe tekste për reklama "
                "(titull, tekst kryesor, call to action) duke përcaktuar edhe audiencën e synuar."
            ),
            greeting="Përshëndetje! Jam agjenti i Facebook-ut. Çfarë do publikojmë sot?",
        ),
        Agent(
            key="tiktok",
            name="TikTok",
            icon="🎵",
            description="Ide videosh, skenarë dhe trende për instalimet teknike.",
            role_prompt=(
                "Ti je agjenti i TikTok-ut. Krijon ide për video të shkurtra (15-60 sekonda) që "
                "tregojnë instalime teknike, para/pas, dhe këshilla sigurie. Për çdo ide jep: "
                "hook-un, skenat me kohëzgjatje, tekstin mbi ekran, muzikën/trendin e sugjeruar "
                "dhe përshkrimin me hashtag-ë."
            ),
            greeting="Përshëndetje! Jam agjenti i TikTok-ut. Cilin instalim do e kthejmë në video virale?",
        ),
    ]
}


def get_api_key(secrets: dict | None = None) -> str | None:
    """Kërko çelësin e API-së te st.secrets dhe pastaj te variablat e mjedisit."""
    if secrets:
        key = secrets.get("ANTHROPIC_API_KEY")
        if key:
            return key
    return os.environ.get("ANTHROPIC_API_KEY")


def _build_history(messages: list[dict]) -> list[dict]:
    """Merr mesazhet e fundit dhe sigurohu që historia të fillojë me përdoruesin."""
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages[-MAX_HISTORY_MESSAGES:]
        if m["role"] in ("user", "assistant") and m["content"]
    ]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def demo_reply(agent: Agent, user_message: str) -> str:
    """Përgjigje kur nuk ka çelës API (modaliteti demo)."""
    return (
        f"**[{agent.name} - modaliteti demo]** E mora kërkesën: *{user_message}*\n\n"
        "Për përgjigje të vërteta nga AI, vendos `ANTHROPIC_API_KEY` te "
        "`.streamlit/secrets.toml` ose si variabël mjedisi (shiko README.md)."
    )


def stream_reply(
    agent: Agent,
    messages: list[dict],
    api_key: str,
    model: str = DEFAULT_MODEL,
) -> Iterator[str]:
    """Dërgo bisedën te Claude dhe kthe përgjigjen copë-copë (streaming)."""
    client = anthropic.Anthropic(api_key=api_key)
    params: dict = dict(
        model=model,
        max_tokens=16000,
        system=agent.system_prompt,
        messages=_build_history(messages),
        output_config={"effort": "medium"},
    )
    if model in _FALLBACK_MODELS:
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
        elif final.stop_reason == "max_tokens":
            yield "\n\n_Përgjigjja u ndërpre sepse ishte shumë e gjatë. Shkruaj \"vazhdo\"._"
    except anthropic.AuthenticationError:
        yield "⚠️ Çelësi i API-së është i pavlefshëm. Kontrollo `ANTHROPIC_API_KEY`."
    except anthropic.PermissionDeniedError:
        yield "⚠️ Çelësi i API-së nuk ka leje për këtë model."
    except anthropic.RateLimitError:
        yield "⚠️ Shumë kërkesa njëherësh. Prit pak sekonda dhe provo përsëri."
    except anthropic.APIStatusError as e:
        yield f"⚠️ Gabim nga API ({e.status_code}): {e.message}"
    except anthropic.APIConnectionError:
        yield "⚠️ Nuk u lidh dot me Claude. Kontrollo internetin."
