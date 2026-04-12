from __future__ import annotations

import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from . import conversation, db
from .gemini_chat import GeminiChatClient, RealGeminiChatClient
from .gemini_jobs import GeminiJobsClient, RealGeminiJobsClient
from .logging_config import configure_logging, get_logger, mask_phone
from .models import (
    BiuReply,
    Curriculo,
    ForgetRequest,
    MessageRequest,
    MessageResponse,
)
from .pdf import render_pdf
from .retention import retention_loop
from .tts import RealTTSClient, TTSClient


_chat_client: GeminiChatClient | None = None
_jobs_client: GeminiJobsClient | None = None
_tts_client: TTSClient | None = None
_retention_task: asyncio.Task | None = None


def _get_chat() -> GeminiChatClient:
    global _chat_client
    if _chat_client is None:
        _chat_client = RealGeminiChatClient()
    return _chat_client


def _get_jobs() -> GeminiJobsClient:
    global _jobs_client
    if _jobs_client is None:
        _jobs_client = RealGeminiJobsClient()
    return _jobs_client


def _get_tts() -> TTSClient:
    global _tts_client
    if _tts_client is None:
        _tts_client = RealTTSClient()
    return _tts_client


def set_clients(
    *,
    chat: GeminiChatClient | None = None,
    jobs: GeminiJobsClient | None = None,
    tts: TTSClient | None = None,
) -> None:
    """Injection hook for tests."""
    global _chat_client, _jobs_client, _tts_client
    if chat is not None:
        _chat_client = chat
    if jobs is not None:
        _jobs_client = jobs
    if tts is not None:
        _tts_client = tts


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    db.init_db()
    log = get_logger("main")
    log.info("brain_starting", db_path=db.DB_PATH)

    global _retention_task
    if os.environ.get("BIU_DISABLE_RETENTION_LOOP") != "1":
        _retention_task = asyncio.create_task(retention_loop())

    yield

    if _retention_task:
        _retention_task.cancel()


app = FastAPI(title="Biu brain", lifespan=lifespan)
log = get_logger("main")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/message", response_model=MessageResponse)
async def post_message(req: MessageRequest) -> MessageResponse:
    phone_masked = mask_phone(req.phone)
    log.info("message_received", phone=phone_masked, kind=req.kind)

    history = conversation.get_history(req.phone)

    try:
        reply: BiuReply = await _get_chat().reply(
            history=history,
            user_kind=req.kind,
            user_content=req.content,
            user_mime=req.mime,
        )
    except ValidationError as e:
        log.error("chat_validation_error", phone=phone_masked, error=str(e))
        raise HTTPException(status_code=502, detail="Modelo retornou resposta inválida")
    except Exception as e:
        log.error("chat_call_error", phone=phone_masked, error=str(e))
        raise HTTPException(status_code=502, detail="Erro ao chamar o modelo")

    user_text = reply.user_transcript or (req.content if req.kind == "text" else "[áudio]")
    conversation.append_turn(req.phone, "user", user_text)
    conversation.append_turn(
        req.phone, "model", reply.response, extra={"type": reply.type}
    )

    pdf_path: str | None = None
    final_text = reply.response
    final_type = reply.type

    if reply.type == "curriculo" and reply.generate_pdf:
        try:
            curriculo_data = json.loads(reply.response)
            curriculo = Curriculo.model_validate(curriculo_data)
        except (json.JSONDecodeError, ValidationError) as e:
            log.error(
                "curriculo_parse_failed",
                phone=phone_masked,
                error=str(e),
                raw=reply.response[:800],
            )
            final_text = (
                "Tive um probleminha pra montar seu currículo agora. "
                "Me manda 'gerar de novo' que eu tento de novo."
            )
            final_type = "pergunta"
        else:
            try:
                pdf_path = render_pdf(curriculo, phone=req.phone)
                conversation.save_curriculo(
                    req.phone, json.dumps(curriculo.model_dump(), ensure_ascii=False), pdf_path
                )
                log.info("pdf_generated", phone=phone_masked, path=pdf_path)
            except Exception as e:
                log.error("pdf_render_failed", phone=phone_masked, error=str(e))
                final_text = (
                    "Seu currículo tá quase pronto, só tive um problema pro gerar o PDF. "
                    "Manda 'gerar de novo' pra eu tentar outra vez."
                )
                final_type = "pergunta"
                pdf_path = None
            else:
                try:
                    final_text = await _get_jobs().find_jobs(curriculo)
                    final_type = "vagas"
                    conversation.append_turn(
                        req.phone, "model", final_text, extra={"type": "vagas"}
                    )
                    conversation.mark_completed(req.phone)
                except Exception as e:
                    log.error("jobs_call_failed", phone=phone_masked, error=str(e))
                    final_text = (
                        "Seu currículo ficou pronto e já já você recebe o PDF! "
                        "Depois procura vagas no Indeed, Catho ou no Google colocando "
                        f"{curriculo.objetivo} + sua cidade."
                    )
                    final_type = "vagas"

    try:
        audio_bytes = await _get_tts().synthesize(final_text)
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    except Exception as e:
        log.error("tts_failed", phone=phone_masked, error=str(e))
        audio_b64 = None

    return MessageResponse(
        text=final_text,
        type=final_type,
        audio_b64=audio_b64,
        pdf_path=pdf_path,
    )


@app.post("/forget")
async def post_forget(req: ForgetRequest) -> dict[str, Any]:
    phone_masked = mask_phone(req.phone)
    log.info("forget_request", phone=phone_masked)

    pdf_paths = conversation.forget(req.phone)
    removed = 0
    for p in pdf_paths:
        try:
            Path(p).unlink(missing_ok=True)
            removed += 1
        except OSError as e:
            log.warning("pdf_unlink_failed", path=p, error=str(e))

    log.info("forget_done", phone=phone_masked, pdfs_removed=removed)
    return {"ok": True, "pdfs_removed": removed}
