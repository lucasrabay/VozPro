# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Biu is a WhatsApp assistant (Brazilian Portuguese) that helps low-literacy users build a Harvard-format CV via voice conversation and surfaces matching job links. Full design spec: `docs/superpowers/specs/2026-04-12-biu-whatsapp-assistant-design.md`.

## Architecture

Two Docker services on an internal network — do **not** collapse them:

- **`gateway/`** (Node 20, `whatsapp-web.js` + headless Chromium): owns the WhatsApp session, classifies incoming media, serializes messages per phone via `phoneQueue.js` (FIFO + 120s AbortController timeout), forwards to brain over HTTP, sends replies back (audio + PDF + text).
- **`brain/`** (Python 3.12, FastAPI): owns conversation history (SQLite WAL), calls Gemini (chat/STT, jobs-with-grounding, TTS), renders the CV PDF (Jinja2 + WeasyPrint).

Communication is `gateway → brain` only, over `http://brain:8000`, endpoints `/message`, `/forget`, `/health`. The PDF volume `./data/pdfs` is mounted read-only into gateway so it can ship files by path without re-uploading bytes — `brain/app/main.py` returns `pdf_path` and `gateway/src/handler.js::resolvePdfPath` rewrites the brain-side path to the gateway-side mount.

### Brain request flow (`brain/app/main.py::post_message`)

1. Load history for phone → call Gemini chat with text or audio bytes → parse `BiuReply` (pydantic).
2. Append user+model turns to SQLite.
3. If `reply.type == "curriculo"` and `generate_pdf`: parse `Curriculo` JSON from `reply.response`, render PDF, call jobs client (Gemini + Google Search grounding), append "vagas" turn, mark conversation completed. Any failure in this chain falls back to a friendly pergunta-type reply; never raises.
4. TTS the final text (URLs stripped by `_text_for_tts` so the voice doesn't read links), base64-encode, return `MessageResponse`.

### Gemini clients are pluggable

`main.py` exposes `set_clients(chat=, jobs=, tts=)` for test injection. Tests use `FakeGeminiClient` etc. Do not import the real clients directly in tests — go through `set_clients`.

### Prompt is a mounted volume

`brain/prompts/biu_system.md` is mounted **read-only** at `/app/prompts`. Editing it needs only `docker compose restart brain` — no rebuild. Treat the prompt as a runtime config, not source to recompile.

## Commands

### Full stack (Docker)

```bash
docker compose up --build           # first boot; QR code prints in gateway logs
docker compose restart brain        # after editing prompts/biu_system.md
docker compose down                 # stop, keep volumes (WA session, DB, PDFs)
docker compose down -v && rm -rf data/   # nuke everything
docker compose logs -f brain        # JSON logs; also written to data/logs/brain.log
```

First run: scan QR with a **test phone** (WhatsApp allows only one Web session per number). Session persists in `./data/wwebjs-auth/`.

### Brain tests (no Docker)

```bash
cd brain
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
pytest                                              # full 16-test suite
pytest tests/test_parsers.py::test_biu_reply_pergunta   # single test
```

Windows without WeasyPrint native deps (Pango/Cairo): skip PDF tests with
`pytest tests/test_parsers.py tests/test_conversation.py tests/test_prompt.py`.

### Gateway locally

Temporarily switch `brain` from `expose: 8000` to `ports: ["8000:8000"]` in `docker-compose.yml`, then:

```bash
cd gateway && npm install
BRAIN_URL=http://localhost:8000 node src/index.js
```

There is no lint/test setup for gateway — it's a thin adapter.

## Conventions

- **Language**: user-facing strings, prompts, and docs are in **Brazilian Portuguese**. Code identifiers, comments, and logs are in English. Don't translate one into the other.
- **Logs**: always use `structlog` via `get_logger(...)` and mask phones with `mask_phone()` (`+5581****1234`). Never log raw phone numbers or audio bytes.
- **Persistence**: store transcripts, not audio bytes. Retention loop in `retention.py` deletes conversations after `BIU_DATA_RETENTION_DAYS` and PDFs after `BIU_PDF_RETENTION_DAYS`.
- **Error handling in `/message`**: downstream failures (PDF render, jobs search, TTS) degrade gracefully to a user-visible text reply — they must never 500 the endpoint. Only chat-model validation/call errors return 502.
- **Per-phone serialization**: the gateway's `phoneQueue` guarantees one in-flight brain request per phone. Don't add concurrency on the brain side assuming ordering — it's enforced upstream.

## Environment

All config via `.env` (template `.env.example`). `GEMINI_API_KEY` is required. Model names (`BIU_CHAT_MODEL`, `BIU_JOBS_MODEL`, `BIU_TTS_MODEL`, `BIU_TTS_VOICE`) are overridable — defaults target Gemini 3 Flash Preview / 2.5 Flash TTS with voice "Algenib".
