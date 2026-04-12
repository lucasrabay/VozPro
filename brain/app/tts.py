from __future__ import annotations

import asyncio
import os
import struct
import subprocess
from typing import Protocol

from google import genai
from google.genai import types as gtypes

from .retry import retry_async

TTS_MODEL = os.environ.get("BIU_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TTS_VOICE = os.environ.get("BIU_TTS_VOICE", "Algenib")


class TTSClient(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


def _parse_audio_mime_type(mime_type: str) -> tuple[int, int]:
    bits_per_sample = 16
    rate = 24000
    for param in mime_type.split(";"):
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass
    return bits_per_sample, rate


def _wrap_wav(audio_data: bytes, mime_type: str) -> bytes:
    bits_per_sample, sample_rate = _parse_audio_mime_type(mime_type)
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def _to_ogg_opus(wav_bytes: bytes) -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "32k",
            "-f", "ogg",
            "pipe:1",
            "-y",
            "-loglevel", "error",
        ],
        input=wav_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout


class RealTTSClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = TTS_MODEL,
        voice: str = TTS_VOICE,
    ):
        self.model = model
        self.voice = voice
        self._client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    async def synthesize(self, text: str) -> bytes:
        prompt = (
            "Read aloud in a warm and friendly tone, in Brazilian Portuguese:\n" + text
        )
        config = gtypes.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=gtypes.SpeechConfig(
                voice_config=gtypes.VoiceConfig(
                    prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(voice_name=self.voice)
                )
            ),
        )

        def sync_call() -> bytes:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=prompt)])],
                config=config,
            )
            if not resp.candidates:
                raise RuntimeError("TTS returned no candidates")
            parts = resp.candidates[0].content.parts or []
            for part in parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    data = part.inline_data.data
                    mime = part.inline_data.mime_type or "audio/L16;rate=24000"
                    if mime.startswith("audio/wav") or mime.startswith("audio/x-wav"):
                        return _to_ogg_opus(data)
                    return _to_ogg_opus(_wrap_wav(data, mime))
            raise RuntimeError("TTS returned no audio data")

        async def _once() -> bytes:
            return await asyncio.to_thread(sync_call)

        return await retry_async(_once, attempts=3, base_delay=1.0, factor=3.0)
