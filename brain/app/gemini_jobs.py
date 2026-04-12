from __future__ import annotations

import asyncio
import os
import re
import urllib.parse
from typing import Protocol

import structlog
from google import genai
from google.genai import types as gtypes

from .models import Curriculo
from .retry import retry_async

log = structlog.get_logger()

GEMINI_JOBS_MODEL = os.environ.get("BIU_JOBS_MODEL", "gemini-3-flash-preview")

_FALLBACK_PORTAIS = [
    ("Indeed", "https://www.indeed.com.br/jobs?q={q}&l={l}"),
    ("Catho", "https://www.catho.com.br/vagas/{q_dash}/{l_dash}/"),
    ("Vagas.com", "https://www.vagas.com.br/vagas-de-{q_dash}-em-{l_dash}"),
]

_STOPWORDS = {
    "atuar", "nas", "na", "no", "nos", "em", "de", "da", "do", "das", "dos",
    "com", "como", "para", "por", "e", "ou", "a", "o", "as", "os", "um",
    "uma", "uns", "umas", "áreas", "área", "setor", "setores", "aplicando",
    "trabalhar", "trabalho", "vaga", "vagas", "ser", "conhecimentos",
    "facilidade", "público",
}


def _extract_keyword(objetivo: str) -> str:
    """Extract a short, search-friendly keyword phrase from a (possibly long)
    objective sentence. Keeps the first 2-3 meaningful content words."""
    first_clause = re.split(r"\s+ou\s+|,|\.|\s+aplicando\s+", objetivo.strip(), maxsplit=1)[0]
    tokens = re.findall(r"[\wÀ-ÿ]+", first_clause.lower())
    content = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]
    if not content:
        return objetivo.strip()
    return " ".join(content[:3])


def _fallback_message(curriculo: Curriculo) -> str:
    objetivo_raw = curriculo.objetivo or "emprego"
    cidade_raw = curriculo.dados_pessoais.cidade or "sua cidade"

    keyword = _extract_keyword(objetivo_raw)
    q_plus = urllib.parse.quote_plus(keyword)
    l_plus = urllib.parse.quote_plus(cidade_raw)
    q_dash = urllib.parse.quote(keyword.replace(" ", "-"))
    l_dash = urllib.parse.quote(cidade_raw.lower().replace(" ", "-"))

    lines = [
        "Seu currículo ficou pronto e já já você recebe o PDF!",
        f"Com base no que você me contou, dá pra procurar vaga de \"{keyword}\" em {cidade_raw}. Olha onde pesquisar:",
        "",
    ]
    for i, (nome, template) in enumerate(_FALLBACK_PORTAIS, 1):
        url = template.format(q=q_plus, l=l_plus, q_dash=q_dash, l_dash=l_dash)
        lines.append(f"{i}. {nome}: {url}")
    lines.append("")
    lines.append("Boa sorte! Tô torcendo por você.")
    return "\n".join(lines)


class GeminiJobsClient(Protocol):
    async def find_jobs(self, curriculo: Curriculo) -> str: ...


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

        def sync_call() -> str:
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[gtypes.Content(role="user", parts=[gtypes.Part.from_text(text=prompt)])],
                config=config,
            )
            return resp.text or ""

        async def _once() -> str:
            return await asyncio.to_thread(sync_call)

        try:
            text = await retry_async(_once, attempts=3, base_delay=2.0, factor=3.0)
        except Exception as e:
            log.warning("jobs_fallback", reason="exception", error=str(e))
            return _fallback_message(curriculo)

        if not text or len(text.strip()) < 40:
            log.warning("jobs_fallback", reason="empty_response", length=len(text or ""))
            return _fallback_message(curriculo)
        return text
