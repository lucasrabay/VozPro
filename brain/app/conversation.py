from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_history(phone: str, db_path: str | None = None) -> list[dict[str, Any]]:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT history_json FROM conversations WHERE phone = ?",
            (phone,),
        ).fetchone()
    if not row:
        return []
    return json.loads(row["history_json"])


def append_turn(
    phone: str,
    role: str,
    text: str,
    extra: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> None:
    turn: dict[str, Any] = {"role": role, "text": text, "ts": _now_iso()}
    if extra:
        turn.update(extra)

    history = get_history(phone, db_path=db_path)
    history.append(turn)
    history_json = json.dumps(history, ensure_ascii=False)

    with db.connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM conversations WHERE phone = ?", (phone,)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE conversations SET history_json = ?, updated_at = CURRENT_TIMESTAMP WHERE phone = ?",
                (history_json, phone),
            )
        else:
            conn.execute(
                "INSERT INTO conversations (phone, history_json) VALUES (?, ?)",
                (phone, history_json),
            )


def mark_completed(phone: str, db_path: str | None = None) -> None:
    with db.connect(db_path) as conn:
        conn.execute(
            "UPDATE conversations SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE phone = ?",
            (phone,),
        )


def forget(phone: str, db_path: str | None = None) -> list[str]:
    """Delete all data for a phone. Returns list of PDF paths that should be removed from disk."""
    with db.connect(db_path) as conn:
        pdf_paths = [
            row["pdf_path"]
            for row in conn.execute(
                "SELECT pdf_path FROM curriculos WHERE phone = ?", (phone,)
            )
        ]
        conn.execute("DELETE FROM curriculos WHERE phone = ?", (phone,))
        conn.execute("DELETE FROM conversations WHERE phone = ?", (phone,))
    return pdf_paths


def save_curriculo(
    phone: str,
    curriculo_json: str,
    pdf_path: str,
    db_path: str | None = None,
) -> int:
    with db.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO curriculos (phone, curriculo_json, pdf_path) VALUES (?, ?, ?)",
            (phone, curriculo_json, pdf_path),
        )
        return cur.lastrowid or 0


def latest_curriculo(phone: str, db_path: str | None = None) -> dict[str, Any] | None:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, curriculo_json, pdf_path, created_at "
            "FROM curriculos WHERE phone = ? ORDER BY id DESC LIMIT 1",
            (phone,),
        ).fetchone()
    if not row:
        return None
    return dict(row)
