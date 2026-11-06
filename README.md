# 🤖 Smart Albania - Qendra e Agjentëve AI

Aplikacion Streamlit me 5 agjentë AI: **Master CEO** (agjenti kryesor, për strategji dhe kodim),
Instagram, WhatsApp, Facebook dhe TikTok. Çdo agjent ka udhëzimet, chat-in dhe historikun e vet.

## Tre "trurë" të zgjedhshëm

Zgjidhet nga paneli anësor, te **🧠 Truri i AI**.

| Truri | Kosto | Ku punon | Interneti |
|---|---|---|---|
| **Gemini** (Google) | ka nivel falas | kudo, edhe në Streamlit Cloud | kërkim në Google + lexim linkesh |
| **Claude** (Anthropic) | me pagesë (kredit API) | kudo | kërkim në web + lexim linkesh |
| **Ollama** (lokal) | falas | vetëm në kompjuterin ku punon Ollama | lexon linket që i jep në mesazh |

Pa asnjë tru të lidhur, aplikacioni punon në **modalitetin demo**.

## Memoria

- **Historiku i bisedave** ruhet në SQLite (`data/chat_history.db`), veçmas për çdo agjent.
  Nuk humbet kur rifreskohet faqja.
- **Memoria afatgjatë** te CEO-ja (seksioni *🧠 Memoria afatgjatë*): fakte për biznesin, si çmime,
  produkte apo orari. Të gjithë agjentët i mbajnë mend në çdo bisedë.

Të dyja ruhen lokalisht. Me Ollama, edhe truri është lokal, kështu që asgjë nuk del nga kompjuteri yt
(përveç linkeve që i kërkon të lexojë).

## Instalimi

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # vendos çelësin tënd
streamlit run app.py
```

### Gemini (falas)
1. Hyr te https://aistudio.google.com/apikey me llogarinë Google dhe krijo një çelës.
2. Vendose te `.streamlit/secrets.toml`: `GEMINI_API_KEY = "AIza..."`
3. Kufijtë e nivelit falas i shikon te Google AI Studio. Nëse arrin kufirin, kalo te *Flash-Lite*.

### Ollama (truri lokal, pa internet)
Kërkon kompjuter (Windows, Mac ose Linux), mundësisht me të paktën 8 GB RAM. Nuk punon në telefon.
1. Shkarko Ollama nga https://ollama.com/download dhe instaloje.
2. Shkarko një model:
   - `ollama pull llama3.2` për përdorim të përgjithshëm (i lehtë)
   - `ollama pull qwen2.5-coder:7b` për CEO-n dhe kodimin
3. Nis aplikacionin në të njëjtin kompjuter dhe zgjidh **Ollama** te paneli.
   Shkruaj emrin e modelit te *Modeli lokal*.

### Claude (me pagesë)
Çelësi merret te https://platform.claude.com (Billing → shto kredit, pastaj API Keys).
Abonimi Claude Pro nuk përfshin kredit API.

## Struktura

| Skedari | Roli |
|---|---|
| `app.py` | Ndërfaqja Streamlit: agjentët, chat-i, veglat e shpejta, memoria, paneli anësor |
| `agents.py` | Përkufizimi i agjentëve dhe udhëzimet e tyre |
| `providers.py` | Lidhja me Gemini, Claude dhe Ollama (streaming, interneti) |
| `storage.py` | Ruajtja e bisedave dhe e memories afatgjatë në SQLite |

## Shënime
- Modelit i dërgohen vetëm 40 mesazhet e fundit të bisedës.
- Në Streamlit Community Cloud skedarët lokalë fshihen kur aplikacioni rinis. Për memorie të përhershme
  atje, `storage.py` mund të kalohet te një databazë e jashtme (p.sh. Supabase/Postgres).
  Vendndodhja e databazës lokale ndryshohet me variablin `AGJENTI_DB_PATH`.
