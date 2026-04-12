from __future__ import annotations

import base64
import json
import os
from typing import Any, Protocol

from google import genai
from google.genai import types as gtypes

from .models import BiuReply
from .prompt import system_prompt
from .retry import retry_async

GEMINI_CHAT_MODEL = os.environ.get("BIU_CHAT_MODEL", "gemini-3-flash-preview")


class GeminiChatClient(Protocol):
    async def reply(
        self,
        history: list[dict[str, Any]],
        user_kind: str,
        user_content: str,
        user_mime: str | None = None,
    ) -> BiuReply: ...


_RESPONSE_SCHEMA = gtypes.Schema(
    type=gtypes.Type.OBJECT,
    required=["user_transcript", "response", "type", "generate_pdf"],
    properties={
        "user_transcript": gtypes.Schema(type=gtypes.Type.STRING),
        "response": gtypes.Schema(type=gtypes.Type.STRING),
        "type": gtypes.Schema(
            type=gtypes.Type.STRING,
            enum=[
                "saudacao",
                "pergunta",
                "confirmacao",
                "correcao",
                "curriculo",
                "vagas",
                "despedida",
            ],
        ),
        "generate_pdf": gtypes.Schema(type=gtypes.Type.BOOLEAN),
    },
)


def _build_contents(
    history: list[dict[str, Any]],
    user_kind: str,
    user_content: str,
    user_mime: str | None,
) -> list[gtypes.Content]:
    contents: list[gtypes.Content] = []
    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        text = turn.get("text", "")
        if not text:
            continue
        contents.append(
            gtypes.Content(role=role, parts=[gtypes.Part.from_text(text=text)])
        )

    if user_kind == "audio":
        audio_bytes = base64.b64decode(user_content)
        mime = user_mime or "audio/ogg"
        contents.append(
            gtypes.Content(
                role="user",
                parts=[gtypes.Part.from_bytes(data=audio_bytes, mime_type=mime)],
            )
        )
    else:
        contents.append(
            gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=user_content)])
        )

    return contents


class RealGeminiChatClient:
    def __init__(self, api_key: str | None = None, model: str = GEMINI_CHAT_MODEL):
        self.model = model
        self._client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    async def _call(self, contents: list[gtypes.Content]) -> str:
        config = gtypes.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            system_instruction=[gtypes.Part.from_text(text=system_prompt())],
            thinking_config=gtypes.ThinkingConfig(thinking_level="MEDIUM"),
        )

        def sync_call() -> str:
            resp = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
            return resp.text or ""

        import asyncio

        return await asyncio.to_thread(sync_call)

    async def reply(
        self,
        history: list[dict[str, Any]],
        user_kind: str,
        user_content: str,
        user_mime: str | None = None,
    ) -> BiuReply:
        contents = _build_contents(history, user_kind, user_content, user_mime)

        async def _once() -> BiuReply:
            raw = await self._call(contents)
            data = json.loads(raw)
            return BiuReply.model_validate(data)

        return await retry_async(_once, attempts=3, base_delay=1.0, factor=3.0)
