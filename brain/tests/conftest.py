from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def temp_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    monkeypatch.setenv("BIU_DB_PATH", db_path)
    from app import db
    db.DB_PATH = db_path
    db.init_db(db_path)
    try:
        yield db_path
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def temp_pdf_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("BIU_PDF_DIR", tmp)
    from app import pdf as pdf_mod
    pdf_mod.PDF_DIR = tmp
    try:
        yield tmp
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def maria_curriculo_json():
    path = Path(__file__).parent / "fixtures" / "curriculo_maria.json"
    import json
    return json.loads(path.read_text(encoding="utf-8"))
