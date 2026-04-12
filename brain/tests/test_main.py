from __future__ import annotations

import base64
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import BiuReply, Curriculo


class FakeChatClient:
    def __init__(self, replies: list[BiuReply]):
        self.replies = replies
        self.calls = []

    async def reply(self, history, user_kind, user_content, user_mime=None):
        self.calls.append(
            {"history": list(history), "kind": user_kind, "content": user_content}
        )
        return self.replies.pop(0)


class FakeJobsClient:
    async def find_jobs(self, curriculo: Curriculo) -> str:
        return f"Olha, achei vagas de {curriculo.objetivo}! https://indeed.com.br"


class FakeTTSClient:
    async def synthesize(self, text: str) -> bytes:
        return b"FAKEWAV" + text.encode("utf-8")[:16]


@pytest.fixture()
async def client(temp_db, temp_pdf_dir, monkeypatch):
    monkeypatch.setenv("BIU_DISABLE_RETENTION_LOOP", "1")
    from app import main as main_mod
    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c, main_mod


async def test_health(client):
    c, _ = client
    r = await c.get("/health")
    assert r.status_code == 200


async def test_text_message_saudacao(client):
    c, main_mod = client
    chat = FakeChatClient(
        [
            BiuReply(
                user_transcript="oi",
                response="Oi! Eu sou o Biu.",
                type="saudacao",
                generate_pdf=False,
            )
        ]
    )
    main_mod.set_clients(chat=chat, jobs=FakeJobsClient(), tts=FakeTTSClient())

    r = await c.post(
        "/message",
        json={"phone": "+5581999990000", "kind": "text", "content": "oi"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "saudacao"
    assert data["audio_b64"] is not None
    assert data["pdf_path"] is None
    assert base64.b64decode(data["audio_b64"]).startswith(b"FAKEWAV")


async def test_curriculo_flow_generates_pdf_and_vagas(client, maria_curriculo_json):
    c, main_mod = client
    curriculo_str = json.dumps(maria_curriculo_json, ensure_ascii=False)
    chat = FakeChatClient(
        [
            BiuReply(
                user_transcript="isso, pode gerar",
                response=curriculo_str,
                type="curriculo",
                generate_pdf=True,
            )
        ]
    )
    main_mod.set_clients(chat=chat, jobs=FakeJobsClient(), tts=FakeTTSClient())

    r = await c.post(
        "/message",
        json={"phone": "+5581999990000", "kind": "text", "content": "isso"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "vagas"
    assert "Cabeleireira" in data["text"] or "vagas" in data["text"].lower()
    assert data["pdf_path"] is not None
    assert os.path.exists(data["pdf_path"])


async def test_forget_removes_data(client):
    c, main_mod = client
    chat = FakeChatClient(
        [
            BiuReply(
                user_transcript="oi",
                response="Oi!",
                type="saudacao",
                generate_pdf=False,
            )
        ]
    )
    main_mod.set_clients(chat=chat, jobs=FakeJobsClient(), tts=FakeTTSClient())

    phone = "+5581999990000"
    await c.post("/message", json={"phone": phone, "kind": "text", "content": "oi"})

    r = await c.post("/forget", json={"phone": phone})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    from app import conversation
    assert conversation.get_history(phone) == []


async def test_invalid_curriculo_json_falls_back(client):
    c, main_mod = client
    chat = FakeChatClient(
        [
            BiuReply(
                user_transcript="pode gerar",
                response="isso não é json",
                type="curriculo",
                generate_pdf=True,
            )
        ]
    )
    main_mod.set_clients(chat=chat, jobs=FakeJobsClient(), tts=FakeTTSClient())

    r = await c.post(
        "/message",
        json={"phone": "+5581999990000", "kind": "text", "content": "ok"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["pdf_path"] is None
    assert "probleminha" in data["text"].lower() or "problema" in data["text"].lower()
