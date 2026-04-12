from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.environ.get("BIU_DB_PATH", "./data/sqlite/biu.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
  phone         TEXT PRIMARY KEY,
  history_json  TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curriculos (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  phone          TEXT NOT NULL,
  curriculo_json TEXT NOT NULL,
  pdf_path       TEXT NOT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_curriculos_phone ON curriculos(phone);
"""


def _ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def init_db(db_path: str | None = None) -> None:
    path = db_path or DB_PATH
    _ensure_parent_dir(path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def connect(db_path: str | None = None, retries: int = 3, delay: float = 0.1):
    path = db_path or DB_PATH
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            conn = sqlite3.connect(path, timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
            return
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower() and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
