from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML

from .models import Curriculo

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PDF_DIR = os.environ.get("BIU_PDF_DIR", "./data/pdfs")


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _sanitize_phone(phone: str) -> str:
    return "".join(c for c in phone if c.isalnum()) or "anon"


def render_html(curriculo: Curriculo) -> str:
    template = _env.get_template("curriculo.html")
    return template.render(c=curriculo)


def render_pdf(curriculo: Curriculo, out_dir: str | None = None, phone: str | None = None) -> str:
    directory = Path(out_dir or PDF_DIR)
    directory.mkdir(parents=True, exist_ok=True)

    phone_part = _sanitize_phone(phone or "anon")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{phone_part}_{ts}_{uuid.uuid4().hex[:6]}.pdf"
    out_path = directory / filename

    html = render_html(curriculo)
    css_path = STATIC_DIR / "curriculo.css"
    stylesheets = [CSS(filename=str(css_path))] if css_path.exists() else []
    HTML(string=html, base_url=str(STATIC_DIR)).write_pdf(
        target=str(out_path), stylesheets=stylesheets
    )
    return str(out_path)
