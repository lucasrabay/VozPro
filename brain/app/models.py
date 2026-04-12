from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


BiuMessageType = Literal[
    "saudacao",
    "pergunta",
    "confirmacao",
    "correcao",
    "curriculo",
    "vagas",
    "despedida",
]


class BiuReply(BaseModel):
    user_transcript: str
    response: str
    type: BiuMessageType
    generate_pdf: bool = False


class DadosPessoais(BaseModel):
    nome: str
    telefone: str
    email: Optional[str] = None
    cidade: str
    bairro: Optional[str] = None


class Curso(BaseModel):
    nome: str
    instituicao: Optional[str] = None
    ano: Optional[str] = None
    carga_horaria: Optional[str] = None


class Educacao(BaseModel):
    escolaridade: str
    instituicao: Optional[str] = None
    ano_conclusao: Optional[str] = None
    cursos: list[Curso] = Field(default_factory=list)


class Experiencia(BaseModel):
    cargo: str
    empresa: str
    cidade: Optional[str] = None
    periodo: Optional[str] = None
    descricao: list[str] = Field(default_factory=list)


class Habilidades(BaseModel):
    tecnicas: list[str] = Field(default_factory=list)
    idiomas: list[str] = Field(default_factory=list)
    interesses: list[str] = Field(default_factory=list)


class Atividade(BaseModel):
    atividade: str
    descricao: str


class Curriculo(BaseModel):
    dados_pessoais: DadosPessoais
    objetivo: str
    educacao: Educacao
    experiencia: list[Experiencia] = Field(default_factory=list)
    habilidades: Habilidades
    atividades: list[Atividade] = Field(default_factory=list)


class MessageRequest(BaseModel):
    phone: str
    kind: Literal["text", "audio"]
    content: str
    mime: Optional[str] = None


class MessageResponse(BaseModel):
    text: str
    type: BiuMessageType
    audio_b64: Optional[str] = None
    pdf_path: Optional[str] = None


class ForgetRequest(BaseModel):
    phone: str
