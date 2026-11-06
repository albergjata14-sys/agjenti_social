# 🤖 Smart Albania - Qendra e Agjentëve AI

Aplikacion Streamlit me 5 agjentë AI (Master CEO, Instagram, WhatsApp, Facebook, TikTok) të lidhur me Claude.
Çdo agjent ka udhëzimet, chat-in dhe memorien e vet. Bisedat ruhen në një databazë SQLite (`data/chat_history.db`),
kështu që nuk humbasin kur rifreskohet faqja.

## Struktura

| Skedari | Roli |
|---|---|
| `app.py` | Ndërfaqja Streamlit: zgjedhja e agjentit, chat-i, veglat e shpejta, paneli anësor |
| `agents.py` | Përkufizimi i agjentëve (prompt-et) dhe lidhja me Claude API (streaming) |
| `storage.py` | Ruajtja e bisedave në SQLite |

## Instalimi

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # vendos çelësin tënd
streamlit run app.py
```

Çelësi mund të vendoset edhe si variabël mjedisi: `export ANTHROPIC_API_KEY=sk-ant-...`.
Pa çelës, aplikacioni punon në **modalitetin demo**.

Çelësin e merr te https://platform.claude.com.

## Shënime

- **Modeli** zgjidhet nga paneli anësor (parazgjedhja: Claude Opus 5.5). Haiku është më i liri.
- Modelit i dërgohen vetëm 40 mesazhet e fundit të bisedës, për të kufizuar koston.
- Në Streamlit Community Cloud skedarët lokalë fshihen kur aplikacioni rinis. Nëse të duhet memorie
  e përhershme atje, `storage.py` mund të kalohet te një databazë e jashtme (p.sh. Supabase/Postgres).
  Vendndodhja e databazës mund të ndryshohet me variablin `AGJENTI_DB_PATH`.
