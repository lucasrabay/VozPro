from __future__ import annotations

import pytest

from app.models import Curriculo


def test_render_pdf_produces_file(maria_curriculo_json, temp_pdf_dir):
    pytest.importorskip("weasyprint")
    from app import pdf

    curriculo = Curriculo.model_validate(maria_curriculo_json)
    path = pdf.render_pdf(curriculo, out_dir=temp_pdf_dir, phone="+5581999991234")

    from pathlib import Path
    assert Path(path).exists()
    size = Path(path).stat().st_size
    assert size > 2000
    with open(path, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF"


def test_render_html_contains_fields(maria_curriculo_json):
    from app import pdf as pdf_mod

    curriculo = Curriculo.model_validate(maria_curriculo_json)
    html = pdf_mod.render_html(curriculo)
    assert "Maria da Silva" in html
    assert "Cabeleireira" in html
    assert "Salão Beleza Pura" in html
    assert "Recife" in html
