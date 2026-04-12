from __future__ import annotations

from app import conversation


def test_empty_history(temp_db):
    assert conversation.get_history("+5581999990000") == []


def test_append_and_read(temp_db):
    phone = "+5581999990000"
    conversation.append_turn(phone, "user", "oi")
    conversation.append_turn(phone, "model", "Olá!", extra={"type": "saudacao"})

    history = conversation.get_history(phone)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["text"] == "oi"
    assert history[1]["type"] == "saudacao"
    assert "ts" in history[0]


def test_forget_removes_everything(temp_db):
    phone = "+5581999990000"
    conversation.append_turn(phone, "user", "oi")
    conversation.save_curriculo(phone, '{"x":1}', "/tmp/fake.pdf")
    assert conversation.latest_curriculo(phone) is not None

    pdf_paths = conversation.forget(phone)
    assert pdf_paths == ["/tmp/fake.pdf"]
    assert conversation.get_history(phone) == []
    assert conversation.latest_curriculo(phone) is None


def test_mark_completed(temp_db):
    phone = "+5581999990000"
    conversation.append_turn(phone, "user", "oi")
    conversation.mark_completed(phone)
    from app import db as _db
    with _db.connect() as conn:
        row = conn.execute(
            "SELECT status FROM conversations WHERE phone = ?", (phone,)
        ).fetchone()
    assert row["status"] == "completed"
