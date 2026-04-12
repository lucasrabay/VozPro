from __future__ import annotations

import json
import os
import urllib.parse
from typing import Protocol

from google import genai
from google.genai import types as gtypes

from .models import Curriculo

GEMINI_JOBS_MODEL = os.environ.get("BIU_JOBS_MODEL", "gemini-3-flash-preview")

_FALLBACK_PORTAIS = [
    ("Indeed", "https://www.indeed.com.br/jobs?q={q}&l={l}"),
    ("Catho", "https://www.catho.com.br/vagas/{q}/{l}/"),
    ("Vagas.com", "https://www.vagas.com.br/vagas-de-{q}-em-{l}"),
]


class GeminiJobsClient(Protocol):
    async def find_jobs(self, curriculo: Curriculo) -> str: ...


def _fallback_message(curriculo: Curriculo) -> str:
    objetivo_raw = curriculo.objetivo or "emprego"
    cidade_raw = curriculo.dados_pessoais.cidade or "sua cidade"

    q_slug = urllib.parse.quote_plus(objetivo_raw.split(" ou ")[0].strip())
    l_slug = urllib.parse.quote_plus(cidade_raw)
    q_dash = objetivo_raw.split(" ou ")[0].strip().lower().replace(" ", "-")
    l_dash = cidade_raw.lower().replace(" ", "-")

    lines = [
        "Seu currículo ficou pronto e já já você recebe o PDF!",
        f"Com base no que você me contou, dá pra procurar vaga de \"{objetivo_raw}\" em {cidade_raw}. Olha onde pesquisar:",
        "",
    ]
    for i, (nome, template) in enumerate(_FALLBACK_PORTAIS, 1):
        url = template.format(q=q_slug if "{q}" in template and "+" in template else q_dash, l=l_slug if "{l}" in template and "+" in template else l_dash)
        lines.append(f"{i}. {nome}: {url}")
    lines.append("")
    lines.append("Boa sorte! Tô torcendo por você.")
    return "\n".join(lines)


class RealGeminiJobsClient:
    def __init__(self, api_key: str | None = None, model: str = GEMINI_JOBS_MODEL):
        self.model = model
        self._client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))

    async def find_jobs(self, curriculo: Curriculo) -> str:
        objetivo = curriculo.objetivo
        cidade = curriculo.dados_pessoais.cidade
        nome = curriculo.dados_pessoais.nome.split(" ")[0]

        experiencia_txt = "; ".join(
            f"{e.cargo} na {e.empresa}" for e in curriculo.experiencia
        ) or "sem experiência formal relevante"

        prompt = f"""Você é o Biu, assistente de emprego via WhatsApp. Uma pessoa chamada {nome} acaba de terminar o currículo dela.

Objetivo profissional: {objetivo}
Cidade: {cidade}
Experiências: {experiencia_txt}

Busque no Google 3 a 4 VAGAS REAIS para essa pessoa. Priorize portais brasileiros confiáveis: Indeed, Catho, Gupy, SINE, Vagas.com, InfoJobs.

Escreva uma mensagem curta e calorosa em PT-BR (como áudio de WhatsApp), com:
1. Uma abertura dizendo que o currículo ficou pronto.
2. Lista de 3 a 4 vagas concretas no formato "- Cargo na Empresa — link".
3. Uma despedida curta e encorajadora.

Use "você", frases curtas, tom de amigo. Máximo 8 linhas. Inclua os links encontrados DIRETAMENTE no texto."""

        config = gtypes.GenerateContentConfig(
            tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())],
            temperature=0.7,
        )

        import asyncio

        def sync_call() -> str:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=prompt)])],
                config=config,
            )
            return resp.text or ""

        try:
            text = await asyncio.to_thread(sync_call)
            if not text or len(text.strip()) < 40:
                return _fallback_message(curriculo)
            return text
        except Exception:
            return _fallback_message(curriculo)
