from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.models import BiuReply, Curriculo


def test_biu_reply_valid_pergunta():
    reply = BiuReply.model_validate(
        {
            "user_transcript": "oi",
            "response": "Oi! Eu sou o Biu.",
            "type": "saudacao",
            "generate_pdf": False,
        }
    )
    assert reply.type == "saudacao"
    assert reply.generate_pdf is False


def test_biu_reply_invalid_type():
    with pytest.raises(ValidationError):
        BiuReply.model_validate(
            {
                "user_transcript": "x",
                "response": "y",
                "type": "conversa",
                "generate_pdf": False,
            }
        )


def test_biu_reply_missing_fields():
    with pytest.raises(ValidationError):
        BiuReply.model_validate({"type": "pergunta"})


def test_curriculo_full_parse(maria_curriculo_json):
    curr = Curriculo.model_validate(maria_curriculo_json)
    assert curr.dados_pessoais.nome == "Maria da Silva"
    assert len(curr.experiencia) == 2
    assert curr.experiencia[0].cargo == "Cabeleireira"
    assert len(curr.experiencia[0].descricao) == 3


def test_curriculo_minimal():
    minimal = {
        "dados_pessoais": {
            "nome": "João",
            "telefone": "11 99999-0000",
            "cidade": "São Paulo",
        },
        "objetivo": "Qualquer",
        "educacao": {"escolaridade": "Fundamental"},
        "habilidades": {},
    }
    curr = Curriculo.model_validate(minimal)
    assert curr.experiencia == []
    assert curr.habilidades.tecnicas == []
    assert curr.atividades == []


def test_curriculo_rejects_missing_objetivo():
    with pytest.raises(ValidationError):
        Curriculo.model_validate(
            {
                "dados_pessoais": {"nome": "X", "telefone": "1", "cidade": "Y"},
                "educacao": {"escolaridade": "F"},
                "habilidades": {},
            }
        )


def test_biu_reply_curriculo_contains_nested_json():
    curriculo_str = json.dumps(
        {
            "dados_pessoais": {"nome": "X", "telefone": "1", "cidade": "Y"},
            "objetivo": "teste",
            "educacao": {"escolaridade": "F"},
            "habilidades": {},
        }
    )
    reply = BiuReply.model_validate(
        {
            "user_transcript": "pode gerar",
            "response": curriculo_str,
            "type": "curriculo",
            "generate_pdf": True,
        }
    )
    parsed = Curriculo.model_validate(json.loads(reply.response))
    assert parsed.dados_pessoais.nome == "X"
