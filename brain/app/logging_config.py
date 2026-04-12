from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog

LOG_DIR = os.environ.get("BIU_LOG_DIR", "./data/logs")
LOG_LEVEL = os.environ.get("BIU_LOG_LEVEL", "INFO").upper()


def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 6:
        return "***"
    return phone[:4] + "****" + phone[-4:]


def configure_logging() -> None:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        fh = logging.FileHandler(Path(LOG_DIR) / "brain.log", encoding="utf-8")
        handlers.append(fh)
    except OSError:
        pass

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        handlers=handlers,
    )

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, LOG_LEVEL, logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "biu"):
    return structlog.get_logger(name)
