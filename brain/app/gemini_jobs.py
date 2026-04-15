from __future__ import annotations

import asyncio
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Protocol

import structlog
from google import genai
from google.genai import types as gtypes

from .models import Curriculo
from .retry import retry_async

log = structlog.get_logger()

GEMINI_JOBS_MODEL = os.environ.get("BIU_JOBS_MODEL", "gemini-3-flash-preview")

# Deterministic, date-filtered aggregator search URLs. Always-live by construction —
# used both as the end-of-message safety net and as the full fallback.
_FALLBACK_PORTAIS = [
    ("Indeed", "https://www.indeed.com.br/jobs?q={q}&l={l}&fromage=7&sort=date"),
    ("Vagas.com", "https://www.vagas.com.br/vagas-de-{q_dash}-em-{l_dash}?ordenar=data"),
]

_SHORTENER_RE = re.compile(
    r"https?://(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|is\.gd|buff\.ly|rebrand\.ly|encurtador\.\w+)/\S+",
    re.IGNORECASE,
)

# Only vaga-detail URLs on these hosts are accepted. Anything else is dropped.
_ALLOWED_HOSTS = {
    "indeed.com.br", "www.indeed.com.br", "br.indeed.com",
    "gupy.io", "www.gupy.io",
    "catho.com.br", "www.catho.com.br",
    "vagas.com.br", "www.vagas.com.br",
    "sine.com.br", "www.sine.com.br",
    "infojobs.com.br", "www.infojobs.com.br",
}

# Markers in the FINAL (post-redirect) URL suggesting the listing is no longer active.
_EXPIRED_URL_MARKERS_RE = re.compile(
    r"(encerrada|expirada|unavailable|not[-_]?found|expired|closed)",
    re.IGNORECASE,
)

# One bullet per line: "- <text> <URL>" (also accepts *, •, numeric prefixes).
_BULLET_RE = re.compile(
    r"^\s*(?:[-*\u2022]|\d+[.)])\s*(.+?)(https?://\S+)\s*$",
    re.MULTILINE,
)

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


def _search_urls(curriculo: Curriculo) -> list[tuple[str, str]]:
    objetivo_raw = curriculo.objetivo or "emprego"
    cidade_raw = curriculo.dados_pessoais.cidade or "sua cidade"
    keyword = _extract_keyword(objetivo_raw)
    q = urllib.parse.quote_plus(keyword)
    l = urllib.parse.quote_plus(cidade_raw)
    q_dash = urllib.parse.quote(keyword.replace(" ", "-"))
    l_dash = urllib.parse.quote(cidade_raw.lower().replace(" ", "-"))
    return [
        (name, tpl.format(q=q, l=l, q_dash=q_dash, l_dash=l_dash))
        for name, tpl in _FALLBACK_PORTAIS
    ]


def _fallback_message(curriculo: Curriculo) -> str:
    keyword = _extract_keyword(curriculo.objetivo or "emprego")
    cidade = curriculo.dados_pessoais.cidade or "sua cidade"
    lines = [
        "Seu currículo ficou pronto e já já você recebe o PDF!",
        f'Com base no que você me contou, dá pra procurar vaga de "{keyword}" em {cidade}. Olha onde pesquisar:',
        "",
    ]
    for i, (name, url) in enumerate(_search_urls(curriculo), 1):
        lines.append(f"{i}. {name}: {url}")
    lines.append("")
    lines.append("Boa sorte! Tô torcendo por você.")
    return "\n".join(lines)


def _url_allowed(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _ALLOWED_HOSTS


def _parse_vagas(text: str) -> list[tuple[str, str]]:
    """Parse bullet lines into (description, url) pairs. The description is
    cleaned of trailing separators; the URL is stripped of trailing punctuation."""
    results: list[tuple[str, str]] = []
    for m in _BULLET_RE.finditer(text):
        desc = m.group(1).strip().rstrip("—–-:·|").strip()
        url = m.group(2).rstrip(").,;\"'")
        if desc and url:
            results.append((desc, url))
    return results


def _parse_candidates(gemini_text: str) -> list[tuple[str, str]] | None:
    """Return parsed, host-filtered vaga candidates. Return None when the Gemini
    response signals 'no valid vagas' (NONE sentinel, empty, shortener present)
    so the caller uses the fallback message."""
    text = (gemini_text or "").strip()
    if not text:
        log.warning("jobs_fallback", reason="empty_response")
        return None
    if text.upper() == "NONE":
        log.warning("jobs_fallback", reason="none_sentinel")
        return None
    if _SHORTENER_RE.search(text):
        log.warning("jobs_fallback", reason="shortener_detected",
                    sample=_SHORTENER_RE.search(text).group(0))
        return None

    vagas = _parse_vagas(text)
    allowed = [(d, u) for d, u in vagas if _url_allowed(u)]
    if not allowed:
        log.warning("jobs_fallback", reason="no_allowed_hosts", parsed=len(vagas))
    return allowed


def _check_url_live_sync(url: str, timeout: float = 5.0) -> bool:
    """HEAD-check (GET-fallback on 405) — return True if the final response is
    <400 and the final URL doesn't match expired-listing markers. Any network
    error → False. Safe to call from asyncio.to_thread."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BiuBot/1.0)"}

    def _open(method: str):
        req = urllib.request.Request(url, method=method, headers=headers)
        return urllib.request.urlopen(req, timeout=timeout)

    try:
        resp = _open("HEAD")
    except urllib.error.HTTPError as e:
        if e.code == 405:
            try:
                resp = _open("GET")
            except Exception:
                return False
        else:
            return False
    except Exception:
        return False

    try:
        status = getattr(resp, "status", 200)
        final = resp.geturl()
    finally:
        try:
            resp.close()
        except Exception:
            pass

    if status >= 400:
        return False
    if _EXPIRED_URL_MARKERS_RE.search(final):
        return False
    return True


async def _check_urls_alive(urls: list[str]) -> list[bool]:
    results = await asyncio.gather(
        *(asyncio.to_thread(_check_url_live_sync, u) for u in urls),
        return_exceptions=True,
    )
    return [r is True for r in results]


def _compose_message(curriculo: Curriculo, vagas: list[tuple[str, str]]) -> str:
    nome_full = (curriculo.dados_pessoais.nome or "").strip()
    nome = nome_full.split(" ")[0] if nome_full else ""
    greeting = f"Prontinho, {nome}!" if nome else "Prontinho!"
    lines = [
        f"{greeting} Seu currículo tá pronto e já já você recebe o PDF. Achei algumas vagas pra você:",
        "",
    ]
    for desc, url in vagas:
        lines.append(f"- {desc} — {url}")
    lines += ["", "E se quiser ver mais, olha aqui:"]
    for name, url in _search_urls(curriculo):
        lines.append(f"- {name}: {url}")
    lines += ["", "Boa sorte! Tô torcendo por você."]
    return "\n".join(lines)


def _build_reply_from_candidates(
    curriculo: Curriculo,
    candidates: list[tuple[str, str]],
    alive_flags: list[bool],
) -> str:
    """Pure post-processing: given parsed candidates and a parallel list of
    liveness flags, return either the composed message (≥2 alive) or the
    deterministic fallback message. No I/O — trivially unit-testable."""
    alive = [c for c, ok in zip(candidates, alive_flags) if ok][:4]
    if len(alive) < 2:
        log.warning("jobs_fallback", reason="too_few_alive",
                    alive=len(alive), candidates=len(candidates))
        return _fallback_message(curriculo)
    return _compose_message(curriculo, alive)


class GeminiJobsClient(Protocol):
    async def find_jobs(self, curriculo: Curriculo) -> str: ...


class RealGeminiJobsClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = GEMINI_JOBS_MODEL,
        liveness_checker: Callable[[list[str]], "asyncio.Future[list[bool]] | list[bool]"] | None = None,
    ):
        self.model = model
        self._client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        self._liveness_checker = liveness_checker  # for tests; defaults to real HEAD checks

    async def find_jobs(self, curriculo: Curriculo) -> str:
        objetivo = curriculo.objetivo
        cidade = curriculo.dados_pessoais.cidade
        nome = (curriculo.dados_pessoais.nome or "").split(" ")[0]

        experiencia_txt = "; ".join(
            f"{e.cargo} na {e.empresa}" for e in curriculo.experiencia
        ) or "sem experiência formal relevante"

        prompt = f"""Você é o Biu, assistente de emprego via WhatsApp. {nome} acaba de terminar o currículo dela.

Objetivo profissional: {objetivo}
Cidade: {cidade}
Experiências: {experiencia_txt}

Use o Google Search para encontrar ATÉ 5 VAGAS REAIS E RECENTES para essa pessoa.

REGRAS DE FRESCOR (CRÍTICO):
- Cada vaga DEVE ter sido publicada nos últimos 7 DIAS. Se o resultado de busca não mostrar a data de publicação, NÃO inclua essa vaga.
- O link deve apontar para a PÁGINA DE DETALHE DA VAGA em um destes portais: Indeed (indeed.com.br), Gupy (gupy.io), Catho (catho.com.br), Vagas.com (vagas.com.br), SINE (sine.com.br) ou InfoJobs (infojobs.com.br). Nenhum outro domínio é aceito.
- Use o URL COMPLETO e ORIGINAL (ex: https://www.indeed.com.br/viewjob?jk=...). NUNCA use encurtadores (bit.ly, tinyurl, t.co, goo.gl, encurtador, etc.).
- NUNCA invente URLs. Se o link completo não estiver disponível, omita a vaga.

FORMATO DA RESPOSTA (CRÍTICO):
- Responda APENAS com bullets, UMA vaga por linha, no formato EXATO:
  - Cargo na Empresa — URL_COMPLETO
- Não inclua abertura, despedida, numeração, comentários, nem qualquer outro texto. Apenas as bullets.
- Se não encontrar NENHUMA vaga que atenda às regras de frescor, responda APENAS com a palavra: NONE"""

        config = gtypes.GenerateContentConfig(
            tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())],
            temperature=0.3,
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

        candidates = _parse_candidates(text)
        if candidates is None or not candidates:
            return _fallback_message(curriculo)

        urls = [u for _, u in candidates]
        try:
            if self._liveness_checker is not None:
                result = self._liveness_checker(urls)
                alive_flags = await result if asyncio.iscoroutine(result) else list(result)
            else:
                alive_flags = await _check_urls_alive(urls)
        except Exception as e:
            log.warning("jobs_liveness_error", error=str(e))
            alive_flags = [False] * len(urls)

        return _build_reply_from_candidates(curriculo, candidates, alive_flags)
