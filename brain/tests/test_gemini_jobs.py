from __future__ import annotations

import pytest

from app.gemini_jobs import (
    _build_reply_from_candidates,
    _compose_message,
    _fallback_message,
    _parse_candidates,
    _parse_vagas,
    _search_urls,
    _url_allowed,
)
from app.models import Curriculo, DadosPessoais, Experiencia


def _make_curriculo(**overrides) -> Curriculo:
    base = dict(
        dados_pessoais=DadosPessoais(nome="Maria Silva", cidade="Recife"),
        objetivo="atuar como auxiliar administrativo",
        experiencia=[Experiencia(cargo="atendente", empresa="Padaria X")],
    )
    base.update(overrides)
    return Curriculo(**base)


def test_search_urls_include_freshness_filters():
    cur = _make_curriculo()
    urls = dict(_search_urls(cur))
    assert "fromage=7" in urls["Indeed"]
    assert "sort=date" in urls["Indeed"]
    assert "ordenar=data" in urls["Vagas.com"]
    assert "recife" in urls["Vagas.com"].lower()


def test_url_allowed_accepts_indeed_and_gupy():
    assert _url_allowed("https://www.indeed.com.br/viewjob?jk=abc")
    assert _url_allowed("https://gupy.io/jobs/xyz")
    assert _url_allowed("https://empresa.gupy.io/jobs/xyz") is False  # subdomain not in allowlist
    assert _url_allowed("https://linkedin.com/jobs/view/123") is False
    assert _url_allowed("not-a-url") is False


def test_parse_vagas_extracts_bullets():
    text = (
        "- Auxiliar Administrativo na Empresa A — https://www.indeed.com.br/viewjob?jk=111\n"
        "* Atendente na Loja B - https://www.catho.com.br/vagas/atendente/222\n"
        "1. Assistente na Padaria C: https://www.vagas.com.br/vagas/v3333\n"
        "lixo sem bullet https://www.indeed.com.br/viewjob?jk=x\n"
    )
    vagas = _parse_vagas(text)
    assert len(vagas) == 3
    assert vagas[0][1].endswith("jk=111")
    assert "Atendente na Loja B" in vagas[1][0]


def test_parse_candidates_none_sentinel_returns_none():
    assert _parse_candidates("NONE") is None
    assert _parse_candidates("  none  ".upper()) is None


def test_parse_candidates_empty_returns_none():
    assert _parse_candidates("") is None
    assert _parse_candidates("   ") is None


def test_parse_candidates_shortener_returns_none():
    text = "- Vaga legal — https://bit.ly/xyz"
    assert _parse_candidates(text) is None


def test_parse_candidates_drops_disallowed_hosts():
    text = (
        "- Vaga no LinkedIn — https://linkedin.com/jobs/view/1\n"
        "- Vaga no Indeed — https://www.indeed.com.br/viewjob?jk=2\n"
    )
    result = _parse_candidates(text)
    assert result is not None
    assert len(result) == 1
    assert "indeed" in result[0][1]


def test_build_reply_all_alive_caps_at_four():
    cur = _make_curriculo()
    candidates = [
        (f"Vaga {i}", f"https://www.indeed.com.br/viewjob?jk={i}") for i in range(5)
    ]
    alive = [True] * 5
    msg = _build_reply_from_candidates(cur, candidates, alive)
    # exactly 4 vaga bullet lines in the "Achei" section
    vaga_lines = [l for l in msg.splitlines() if l.startswith("- Vaga ")]
    assert len(vaga_lines) == 4
    # safety-net search URLs always appended
    assert "indeed.com.br/jobs" in msg
    assert "vagas.com.br/vagas-de" in msg


def test_build_reply_some_dead_keeps_alive_and_appends_search():
    cur = _make_curriculo()
    candidates = [
        ("Vaga 0", "https://www.indeed.com.br/viewjob?jk=0"),
        ("Vaga 1", "https://www.indeed.com.br/viewjob?jk=1"),
        ("Vaga 2", "https://www.catho.com.br/vagas/x/2"),
        ("Vaga 3", "https://www.vagas.com.br/vagas/v3"),
        ("Vaga 4", "https://gupy.io/jobs/4"),
    ]
    alive = [True, False, True, False, False]
    msg = _build_reply_from_candidates(cur, candidates, alive)
    assert "Vaga 0" in msg
    assert "Vaga 2" in msg
    assert "Vaga 1" not in msg
    assert "Vaga 3" not in msg
    # safety-net search URLs still there
    assert "fromage=7" in msg


def test_build_reply_too_few_alive_falls_back():
    cur = _make_curriculo()
    candidates = [
        ("Vaga 0", "https://www.indeed.com.br/viewjob?jk=0"),
        ("Vaga 1", "https://www.indeed.com.br/viewjob?jk=1"),
    ]
    alive = [True, False]  # only 1 alive, below 2-threshold
    msg = _build_reply_from_candidates(cur, candidates, alive)
    assert msg == _fallback_message(cur)


def test_fallback_message_contains_all_portals():
    cur = _make_curriculo()
    msg = _fallback_message(cur)
    assert "Indeed" in msg
    assert "Vagas.com" in msg
    assert "fromage=7" in msg


def test_compose_message_uses_first_name():
    cur = _make_curriculo()
    msg = _compose_message(cur, [("Vaga X", "https://www.indeed.com.br/viewjob?jk=x")])
    assert "Maria" in msg
    assert "Silva" not in msg.splitlines()[0]  # only first name in greeting
